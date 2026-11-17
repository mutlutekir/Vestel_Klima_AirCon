"""Live updates from the unit's AWS IoT messages.

The REST status document can be minutes behind, and after a command sent through the
cloud its ``Mode`` is not refreshed at all. The official app instead listens to the
messages the unit publishes whenever something changes (remote control, buttons or a
cloud command). This module does the same: MQTT over WebSocket to AWS IoT, signed with
temporary credentials from the app's Cognito identity pool. See docs/protocol.md.
"""
from __future__ import annotations

import asyncio
import datetime
import hashlib
import hmac
import json
import logging
import urllib.parse
from collections.abc import Callable
from typing import Any

from .api import VestelAcApi, VestelAcError
from .const import AWS_IOT_HOST, AWS_REGION

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 20
KEEPALIVE = 30
STABLE_AFTER = 30
RETRY_MIN = 5
RETRY_MAX = 300


def presigned_ws_path(creds: dict[str, Any], *, host: str = AWS_IOT_HOST, region: str = AWS_REGION,
                      now: datetime.datetime | None = None) -> str:
    """Return the ``/mqtt?...`` path AWS IoT accepts for MQTT over WebSocket (SigV4 in the query)."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    day = now.strftime("%Y%m%d")
    scope = f"{day}/{region}/iotdevicegateway/aws4_request"
    params = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{creds['AccessKeyId']}/{scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-SignedHeaders": "host",
    }
    query = "&".join(f"{k}={urllib.parse.quote(v, safe='-_.~')}" for k, v in sorted(params.items()))
    canonical = "\n".join(["GET", "/mqtt", query, f"host:{host}\n", "host", hashlib.sha256(b"").hexdigest()])
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = ("AWS4" + creds["SecretKey"]).encode()
    for part in (day, region, "iotdevicegateway", "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    path = f"/mqtt?{query}&X-Amz-Signature={signature}"
    if creds.get("SessionToken"):  # added after signing, as the AWS IoT SDKs do
        path += f"&X-Amz-Security-Token={urllib.parse.quote(creds['SessionToken'], safe='-_.~')}"
    return path


class VestelLive:
    """Keeps one MQTT connection open and hands every published change to ``on_update``."""

    def __init__(
        self,
        api: VestelAcApi,
        topics: dict[str, str],
        on_update: Callable[[str, Any], None],
        on_lost: Callable[[], None],
        *,
        host: str = AWS_IOT_HOST,
        port: int = 443,
        tls: bool = True,
    ) -> None:
        """``topics`` maps each MQTT topic to the device id whose messages it carries."""
        self._api = api
        self._topics = topics
        self._on_update = on_update
        self._on_lost = on_lost
        self._host, self._port, self._tls = host, port, tls
        self._task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.connected = False

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._task = self._loop.create_task(self._run())

    async def async_stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    # -- connection loop ------------------------------------------------------

    async def _run(self) -> None:
        loop = self._loop
        assert loop is not None
        delay = RETRY_MIN
        failures = 0
        policy_tried = False
        while True:
            client = None
            ever_connected = False
            try:
                identity, creds = await self._api.async_get_aws_credentials()
                # First choice is an id of our own so the phone app, which may use the plain
                # identity id, is not knocked off; fall back to the plain id if refused.
                client_id = identity if (failures // 2) % 2 == 1 else f"{identity}-hass"
                connected, closed = asyncio.Event(), asyncio.Event()
                client = await loop.run_in_executor(
                    None, self._build_client, client_id, creds, connected, closed
                )
                client.connect_async(self._host, self._port, keepalive=KEEPALIVE)
                client.loop_start()
                await asyncio.wait_for(connected.wait(), CONNECT_TIMEOUT)
                self.connected = True
                started = loop.time()
                _LOGGER.debug("Live connection to AWS IoT established")
                await closed.wait()
                # A connection that dies right away (for example because a subscription is
                # refused) counts as a failure, so the retry delay keeps growing.
                ever_connected = loop.time() - started >= STABLE_AFTER
                if ever_connected:
                    delay, failures = RETRY_MIN, 0
                _LOGGER.debug("Live connection to AWS IoT closed")
            except asyncio.CancelledError:
                raise
            except (VestelAcError, asyncio.TimeoutError, OSError) as err:
                _LOGGER.debug("Live connection failed: %s", err)
            except Exception:  # noqa: BLE001 - keep the retry loop alive whatever paho raises
                _LOGGER.debug("Unexpected live connection error", exc_info=True)
            finally:
                if client is not None:
                    await loop.run_in_executor(None, self._stop_client, client)
                if self.connected:
                    self.connected = False
                    self._on_lost()
            if not ever_connected:
                failures += 1
                if failures == 2 and not policy_tried:
                    policy_tried = True
                    await self._attach_policy()
                if failures == 3:
                    _LOGGER.warning(
                        "Cannot open the live connection to Vestel's cloud; "
                        "falling back to periodic polling (status may lag by minutes)"
                    )
            await asyncio.sleep(delay)
            delay = min(delay * 2, RETRY_MAX)

    async def _attach_policy(self) -> None:
        try:
            identity, _ = await self._api.async_get_aws_credentials()
            await self._api.async_attach_iot_policy(identity)
            _LOGGER.debug("Attached the IoT policy to this account's identity")
        except VestelAcError as err:
            _LOGGER.debug("Could not attach the IoT policy: %s", err)

    # -- paho (runs in its own thread) ---------------------------------------

    def _build_client(self, client_id: str, creds: dict[str, Any], connected: asyncio.Event,
                      closed: asyncio.Event) -> Any:
        import paho.mqtt.client as mqtt  # imported late: loading it can block

        loop = self._loop
        assert loop is not None
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            transport="websockets",
            reconnect_on_failure=False,
        )
        if self._tls:
            client.tls_set()
        client.ws_set_options(path=presigned_ws_path(creds, host=self._host))

        def on_connect(cl, _userdata, _flags, reason_code, _props=None):
            if getattr(reason_code, "is_failure", reason_code != 0):
                loop.call_soon_threadsafe(closed.set)
                return
            for topic in self._topics:
                cl.subscribe(topic, qos=0)
            loop.call_soon_threadsafe(connected.set)

        def on_message(_cl, _userdata, msg):
            loop.call_soon_threadsafe(self._handle, msg.topic, msg.payload)

        def on_disconnect(_cl, _userdata, *_args):
            loop.call_soon_threadsafe(closed.set)

        client.on_connect, client.on_message, client.on_disconnect = on_connect, on_message, on_disconnect
        return client

    @staticmethod
    def _stop_client(client: Any) -> None:
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001
            pass
        client.loop_stop()

    def _handle(self, topic: str, payload: bytes) -> None:
        device_id = self._topics.get(topic)
        if device_id is None:
            return
        try:
            data = json.loads(payload)
        except ValueError:
            _LOGGER.debug("Ignoring a message that is not JSON on %s", topic)
            return
        self._on_update(device_id, data)
