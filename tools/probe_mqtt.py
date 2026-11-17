#!/usr/bin/env python3
"""Listen to your own air conditioner's AWS IoT messages for a while (read-only).

The Smart Life app learns the unit's live state from messages the unit publishes
on its MQTT topic. This script subscribes to the same topics, prints what arrives
(ids masked) and publishes nothing. Needs ``paho-mqtt`` (pip install paho-mqtt):

    python3 tools/probe_mqtt.py <refresh_token> [seconds]

Start it, then switch the unit on and off with its remote control a few times and
change the mode or temperature. The default listening time is 120 seconds.
Needs probe_status.py and probe_shadow.py in the same folder.
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import re
import sys
import threading
import time
import urllib.parse

sys.path.insert(0, __file__.rsplit("/", 1)[0] if "/" in __file__ else ".")
from probe_shadow import (  # noqa: E402
    IDENTITY_POOL, IOT_HOST, REGION, USER_POOL, cognito, mask_text, shape,
)
from probe_status import API, http, refresh  # noqa: E402


def presigned_ws_path(creds: dict, *, host: str = IOT_HOST, region: str = REGION,
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


def first_ac(id_token: str) -> dict:
    status, text = http("GET", API + "v1.0/homes", {"Token": id_token})
    homes = json.loads(text) if status == 200 else {}
    home_id = next((h.get("homeId") or h.get("id") for h in (homes.get("items") or []) if isinstance(h, dict)), None)
    status, text = http("GET", API + f"v1.0/homes/{home_id}/devices", {"Token": id_token})
    try:
        return next(d for d in json.loads(text)["items"]["homeappliances"] if d.get("deviceType") == "AC")
    except (ValueError, KeyError, TypeError, StopIteration):
        sys.exit(f"No air conditioner found (devices call returned HTTP {status}).")


def listen(identity: str, creds: dict, topics: list[str], seconds: float, *,
           host: str = IOT_HOST, port: int = 443, tls: bool = True) -> bool:
    """Connect, subscribe to each topic in turn and print every message.

    AWS IoT drops the connection when a subscription is not allowed, so each topic is
    subscribed on its own, the broker's answer is printed, and the run stops after two
    unexpected disconnects (naming the topic that was subscribed last).
    """
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        sys.exit("paho-mqtt is missing. Install it with:  pip install paho-mqtt  (add --break-system-packages if asked)")

    started = time.monotonic()
    state = {"connected": False, "drops": 0, "last": None, "refused": None, "done": False}
    pending = list(topics)
    kwargs = {"callback_api_version": mqtt.CallbackAPIVersion.VERSION2} if hasattr(mqtt, "CallbackAPIVersion") else {}
    client = mqtt.Client(client_id=identity, transport="websockets", **kwargs)
    if tls:
        client.tls_set()
    client.ws_set_options(path=presigned_ws_path(creds, host=host))

    def stamp() -> str:
        return f"[{time.monotonic() - started:6.1f}s]"

    def subscribe_next(cl) -> None:
        if pending:
            state["last"] = pending.pop(0)
            print(f"{stamp()} subscribing to {shape(state['last'])}")
            cl.subscribe(state["last"], qos=0)

    def on_connect(cl, _userdata, _flags, rc, *_rest):
        code = getattr(rc, "value", rc)
        if code != 0:
            state["refused"] = f"MQTT connect refused, code {code}"
            return
        state["connected"] = True
        print(f"{stamp()} connected to AWS IoT")
        subscribe_next(cl)

    def on_subscribe(cl, _userdata, _mid, *rest):
        print(f"{stamp()} subscribe answer for {shape(state['last'])}: {rest[0] if rest else ''}")
        subscribe_next(cl)

    def on_message(_cl, _userdata, msg):
        body = msg.payload.decode("utf-8", "replace")
        print(f"\n{stamp()} message on {shape(msg.topic)}\n{mask_text(body)[:3000]}\n")

    def on_disconnect(cl, *_args):
        if state["done"]:
            return
        state["drops"] += 1
        print(f"{stamp()} disconnected (last subscribed: {shape(state['last']) if state['last'] else 'none'})")
        if state["drops"] >= 2:
            cl.disconnect()  # stop paho's automatic reconnect loop

    client.on_connect, client.on_subscribe = on_connect, on_subscribe
    client.on_message, client.on_disconnect = on_message, on_disconnect
    try:
        client.connect(host, port, keepalive=30)
    except Exception as err:  # noqa: BLE001 - report whatever the socket layer says
        print(f"Could not connect: {type(err).__name__}: {mask_text(str(err))[:200]}")
        return False
    client.loop_start()
    print("Switch the unit on/off with its remote control now, change its mode and temperature.")
    end = time.monotonic() + seconds
    while time.monotonic() < end and state["drops"] < 2 and not state["refused"]:
        time.sleep(0.2)
    state["done"] = True
    client.loop_stop()
    client.disconnect()
    if state["refused"]:
        print(state["refused"])
    return state["connected"] and state["drops"] < 2


def main() -> None:
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    seconds = float(sys.argv[2]) if len(sys.argv) == 3 else 120.0
    id_token = refresh(sys.argv[1].strip())
    device = first_ac(id_token)
    logins = {USER_POOL: id_token}
    identity = cognito("GetId", {"IdentityPoolId": IDENTITY_POOL, "Logins": logins})["IdentityId"]
    creds = cognito("GetCredentialsForIdentity", {"IdentityId": identity, "Logins": logins})["Credentials"]
    pub = device.get("pubTopic") or ""
    # The app subscribes to ".../from" (see its string resources); the device record lists
    # the newer ".../fromJson" variant. Try both, one at a time.
    topics = [t for t in (re.sub(r"Json$", "", pub), pub) if t]
    print("Topics to try:", ", ".join(shape(t) for t in topics) or "(none)")
    if listen(identity, creds, topics, seconds):
        return
    # The app attaches the IoT policy to the account's identity when it logs in; do the same once.
    print("Attaching the IoT policy to this account's identity, as the app does at login, and retrying.")
    status, text = http(
        "POST", API + "v1.0/customer/attachpolicy",
        {"Token": id_token, "Content-Type": "application/json"},
        json.dumps({"cognitoIdentityId": identity}).encode(),
    )
    print(f"attachpolicy -> HTTP {status} {mask_text(text)[:200]}")
    listen(identity, creds, topics, seconds)


if __name__ == "__main__":
    main()
