"""Async client for the Vestel Smart Life / Evin Aklı cloud (air conditioners).

Unofficial and not affiliated with or endorsed by Vestel.

Everything here is written from observations documented in docs/protocol.md:
the Smart Life Android app (endpoints, header, command packing) and responses
captured from a real account with tools/probe_status.py.

* Authentication: Cognito hosted UI, OAuth2 authorization code + PKCE; the
  refresh token is exchanged for an ID token that is sent as ``Token: <id>``.
* Reading state: ``GET v1.0/appliances/{id}/status`` returns named items.
* Writing state: ``POST v1.0/customer/devices/{id}/legacy/command`` with a
  packed ``<NAME><5 digits>`` command (see ``_pack``).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import time
from html.parser import HTMLParser
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import aiohttp

from .const import (
    API_BASE,
    AWS_IDENTITY_POOL_ID,
    AWS_REGION,
    AWS_USER_POOL_PROVIDER,
    AUTH_ENDPOINT,
    DEFAULT_SCOPES,
    FAN_MAP,
    MAX_TEMP,
    MIN_TEMP,
    MODE_MAP,
    OFFTV_DISABLED,
    TOKEN_ENDPOINT,
)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
# After a command, keep showing the value we just sent until the cloud reports
# it too (or this many seconds pass): the status endpoint can lag behind.
PENDING_TTL = 900.0
BRAND = "Vestel"

# Names the cloud uses -> names used by the Home Assistant entities.
_MODE_FROM_CLOUD = {
    "PowerOff": "off",
    "Auto": "auto",
    "Cooling": "cool",
    "Heating": "heat",
    "Dehumidifying": "dry",
    "Ventilating": "fan",
}
_FAN_FROM_CLOUD = {
    "Auto": "auto",
    "Speed1": "fan1",
    "Speed2": "fan2",
    "Speed3": "fan3",
    "Speed4": "fan4",
    "Speed5": "fan5",
}

# Error items of the status document, in bit order of the ACERROR register.
_ERROR_ITEMS = (
    "ACInfoError",
    "InitialPOEError",
    "RoomTemperatureSensorError",
    "CoilTemperatureSensorError",
    "FanMotorError",
    "GasLeakageError",
    "OutAmbientTemperatureSensorError",
    "DischargeTemperatureSensorError",
    "OutPipeTemperatureError",
    "CommunicationError",
    "TripFError",
    "IgbtNtcError",
    "PoeError",
    "VbusError",
    "CompressorCableError",
    "OutdoorBldcTachoError",
)

# The cloud reports "unset" timer hours as 31 (all five bits set).
_TIMER_UNSET_HOUR = 31
_TIMER_UNSET_MINUTE = 63


class VestelAcError(Exception):
    """Any problem talking to the Vestel cloud."""


class VestelAuthError(VestelAcError):
    """The stored credentials are no longer accepted."""


class VestelAutomationError(VestelAcError):
    """The hosted login page could not be driven automatically."""


def _pack(*fields: tuple[int, int]) -> str:
    """Pack (width_in_bits, value) pairs, least significant field first.

    The result is the zero-padded 5 digit decimal the cloud expects.
    """
    number = 0
    shift = 0
    for width, value in fields:
        if not 0 <= value < (1 << width):
            raise VestelAcError(f"Value {value} does not fit in {width} bits")
        number |= value << shift
        shift += width
    return f"{number:05d}"


def _louver(value: Any) -> int:
    """'Off' -> 0, 'Pos3' -> 3, ..., 'Pos6' -> 6."""
    if isinstance(value, str) and value.startswith("Pos"):
        try:
            return int(value[3:])
        except ValueError:
            return 0
    return 0


class _FormParser(HTMLParser):
    """Collect forms and their inputs from the hosted login page."""

    def __init__(self) -> None:
        super().__init__()
        self.forms: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {k: (v or "") for k, v in attrs}
        if tag == "form":
            self._current = {"action": values.get("action", ""), "inputs": []}
            self.forms.append(self._current)
        elif tag == "input" and self._current is not None and values.get("name"):
            self._current["inputs"].append(
                (values["name"], values.get("type", "text").lower(), values.get("value", ""))
            )

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._current = None


class VestelAcApi:
    """Thin client; one instance per config entry."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        refresh_token: Optional[str] = None,
        token_update_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> None:
        self._session = session
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._refresh_token = refresh_token
        self._token_update_callback = token_update_callback
        self._id_token: Optional[str] = None
        self._expires_at = 0.0
        self._devices: dict[str, dict[str, Any]] = {}
        self._status: dict[str, dict[str, Any]] = {}
        self._pending: dict[str, dict[str, tuple[Any, float, Any]]] = {}
        self._cloud_last: dict[str, dict[str, Any]] = {}
        # Last REST status document per device, and the newer values the unit published itself.
        self._last_props: dict[str, dict[str, Any]] = {}
        self._live: dict[str, dict[str, dict[str, Any]]] = {}
        self._token_lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Authentication
    # ------------------------------------------------------------------ #

    def _basic_auth(self) -> str:
        raw = f"{self._client_id}:{self._client_secret}".encode()
        return "Basic " + base64.b64encode(raw).decode()

    async def _token_request(self, params: dict[str, str]) -> dict[str, Any]:
        try:
            async with self._session.post(
                TOKEN_ENDPOINT,
                data=params,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": self._basic_auth(),
                },
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                try:
                    body = await resp.json(content_type=None)
                except (ValueError, aiohttp.ContentTypeError):
                    body = {}
                if resp.status in (400, 401):
                    # Expired or revoked grant: the user has to sign in again.
                    raise VestelAuthError(f"Token request rejected ({resp.status}): {body}")
                if resp.status != 200:
                    raise VestelAcError(f"Token request failed ({resp.status})")
                return body
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise VestelAcError(f"Cannot reach the Vestel login service: {err}") from err

    def _store_tokens(self, body: dict[str, Any]) -> None:
        self._id_token = body.get("id_token")
        self._expires_at = time.time() + int(body.get("expires_in", 3600))
        new_refresh = body.get("refresh_token")
        if new_refresh and new_refresh != self._refresh_token:
            self._refresh_token = new_refresh
            if self._token_update_callback:
                self._token_update_callback({"refresh_token": new_refresh})

    async def async_refresh(self) -> str:
        """Exchange the refresh token for a fresh ID token."""
        if not self._refresh_token:
            raise VestelAuthError("No refresh token available")
        body = await self._token_request(
            {
                "grant_type": "refresh_token",
                "client_id": self._client_id,
                "refresh_token": self._refresh_token,
            }
        )
        if not body.get("id_token"):
            raise VestelAcError("Token response contained no id_token")
        self._store_tokens(body)
        return self._id_token  # type: ignore[return-value]

    async def async_get_id_token(self) -> str:
        async with self._token_lock:
            if self._id_token and self._expires_at > time.time() + 60:
                return self._id_token
            return await self.async_refresh()

    async def async_login_with_password(self, username: str, password: str) -> str:
        """Sign in through the hosted login page and return a refresh token.

        Needs a session with a cookie jar (the login page sets a CSRF cookie).
        """
        verifier = secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "scope": DEFAULT_SCOPES,
                "state": secrets.token_urlsafe(16),
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        try:
            async with self._session.get(
                f"{AUTH_ENDPOINT}?{query}", timeout=REQUEST_TIMEOUT
            ) as resp:
                if resp.status != 200:
                    raise VestelAutomationError(
                        f"Login page could not be opened (HTTP {resp.status})."
                    )
                page_url = str(resp.url)
                page = await resp.text()
            form = self._find_login_form(page)
            data, post_url = self._fill_form(form, page_url, username, password)
            code = await self._submit_login(post_url, data)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise VestelAcError(f"Cannot reach the Vestel login service: {err}") from err

        body = await self._token_request(
            {
                "grant_type": "authorization_code",
                "client_id": self._client_id,
                "code": code,
                "redirect_uri": self._redirect_uri,
                "code_verifier": verifier,
            }
        )
        if not body.get("refresh_token"):
            raise VestelAutomationError("The token response had no refresh_token.")
        self._store_tokens(body)
        return self._refresh_token  # type: ignore[return-value]

    @staticmethod
    def _find_login_form(page: str) -> dict[str, Any]:
        parser = _FormParser()
        parser.feed(page)
        for form in parser.forms:
            if any(kind == "password" for _, kind, _ in form["inputs"]):
                return form
        raise VestelAutomationError("No login form found on the Vestel login page.")

    @staticmethod
    def _fill_form(
        form: dict[str, Any], page_url: str, username: str, password: str
    ) -> tuple[dict[str, str], str]:
        data: dict[str, str] = {}
        user_field = None
        for name, kind, value in form["inputs"]:
            if kind == "password":
                data[name] = password
            elif kind in ("text", "email") and user_field is None:
                user_field = name
                data[name] = username
            elif kind == "hidden":
                data[name] = value
        if user_field is None:
            raise VestelAutomationError("No user name field on the login form.")
        return data, urljoin(page_url, form["action"] or page_url)

    async def _submit_login(self, url: str, data: dict[str, str]) -> str:
        """POST the form and follow redirects by hand until the app redirect."""
        redirect_scheme = urlparse(self._redirect_uri).scheme
        resp = await self._session.post(
            url, data=data, allow_redirects=False, timeout=REQUEST_TIMEOUT
        )
        for _ in range(8):
            async with resp:
                location = resp.headers.get("Location")
                if resp.status not in (301, 302, 303, 307, 308) or not location:
                    page = await resp.text()
                    try:
                        self._find_login_form(page)
                    except VestelAutomationError:
                        pass
                    else:  # the login form came back: credentials were refused
                        raise VestelAuthError("Wrong user name or password.")
                    raise VestelAutomationError(
                        f"Unexpected login response (HTTP {resp.status})."
                    )
                if urlparse(location).scheme == redirect_scheme:
                    codes = parse_qs(urlparse(location).query).get("code")
                    if not codes:
                        raise VestelAutomationError("The redirect carried no code.")
                    return codes[0]
                next_url = urljoin(str(resp.url), location)
            resp = await self._session.get(
                next_url, allow_redirects=False, timeout=REQUEST_TIMEOUT
            )
        raise VestelAutomationError("Too many redirects during login.")

    # ------------------------------------------------------------------ #
    # REST helper
    # ------------------------------------------------------------------ #

    async def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> Any:
        for attempt in (1, 2):
            token = await self.async_get_id_token()
            try:
                async with self._session.request(
                    method,
                    f"{API_BASE}/{path}",
                    json=payload,
                    headers={"Token": token, "Accept-Charset": "utf-8"},
                    timeout=REQUEST_TIMEOUT,
                ) as resp:
                    try:
                        body = await resp.json(content_type=None)
                    except (ValueError, aiohttp.ContentTypeError):
                        body = None
                    if resp.status in (401, 403):
                        if attempt == 1:
                            self._expires_at = 0  # force a refresh and retry once
                            continue
                        raise VestelAuthError(f"Vestel rejected the token ({resp.status})")
                    if resp.status != 200:
                        raise VestelAcError(f"{method} {path} failed ({resp.status}): {body}")
                    return body
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise VestelAcError(f"Cannot reach the Vestel cloud: {err}") from err
        raise VestelAuthError("Vestel rejected the token")

    # ------------------------------------------------------------------ #
    # Devices and state
    # ------------------------------------------------------------------ #

    async def async_get_devices(self) -> list[dict[str, str]]:
        """Return the air conditioners on the account."""
        homes = await self._request("GET", "v1.0/homes")
        devices: dict[str, dict[str, Any]] = {}
        for home in (homes or {}).get("items") or []:
            home_id = home.get("homeId") or home.get("id")
            if not home_id:
                continue
            body = await self._request("GET", f"v1.0/homes/{home_id}/devices")
            for item in ((body or {}).get("items") or {}).get("homeappliances") or []:
                if item.get("deviceType") != "AC" or not item.get("deviceId"):
                    continue
                devices[item["deviceId"]] = {
                    "device_id": item["deviceId"],
                    "device_name": item.get("deviceName") or item["deviceId"],
                    "device_type": item["deviceType"],
                    "wifi_card_type": item.get("wifiCardType", ""),
                    "pub_topic": item.get("pubTopic") or "",
                }
        self._devices = devices
        return list(devices.values())

    async def async_get_status(self, device_id: str) -> dict[str, Any]:
        body = await self._request("GET", f"v1.0/appliances/{device_id}/status")
        props = (body or {}).get("properties")
        if not isinstance(props, dict):
            raise VestelAcError(f"Unexpected status response for {device_id}")
        self._last_props[device_id] = props
        return self._build_status(device_id)

    def _build_status(self, device_id: str) -> dict[str, Any]:
        props = self._overlay(self._last_props[device_id], self._live.get(device_id))
        status = self._parse_status(props)
        reported = dict(status)  # what the cloud says, before pending values
        status = self._apply_pending(device_id, status)
        self._cloud_last[device_id] = reported
        self._status[device_id] = status
        return status

    @staticmethod
    def _overlay(props: dict[str, Any], live: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
        """Put values the unit published itself over the (possibly older) REST document."""
        if not live:
            return props
        merged = dict(props)
        for group, items in live.items():
            current = {
                e["item"]: e.get("value")
                for e in props.get(group) or []
                if isinstance(e, dict) and "item" in e
            }
            current.update(items)
            merged[group] = [{"item": k, "value": v} for k, v in current.items()]
        return merged

    def apply_live(self, device_id: str, delta: Any) -> dict[str, Any] | None:
        """Merge one message the unit published and return the new status (None if unusable).

        Messages carry only what changed, in the same shape as the REST document:
        ``{"settings": [{"item": "Mode", "value": "Heating"}], "status": [...]}``.
        """
        if not isinstance(delta, dict) or device_id not in self._last_props:
            return None
        live = self._live.setdefault(device_id, {})
        changed = False
        for group in ("settings", "status", "errors", "commands"):
            for entry in delta.get(group) or []:
                if isinstance(entry, dict) and "item" in entry:
                    live.setdefault(group, {})[entry["item"]] = entry.get("value")
                    changed = True
        return self._build_status(device_id) if changed else None

    def clear_live(self) -> None:
        """Forget published values, for example after the live connection dropped."""
        self._live.clear()

    async def async_get_aws_credentials(self) -> tuple[str, dict[str, Any]]:
        """Trade the Cognito ID token for temporary AWS credentials (and the identity id)."""
        id_token = await self.async_get_id_token()
        logins = {AWS_USER_POOL_PROVIDER: id_token}
        identity = (
            await self._cognito_identity("GetId", {"IdentityPoolId": AWS_IDENTITY_POOL_ID, "Logins": logins})
        )["IdentityId"]
        creds = (
            await self._cognito_identity("GetCredentialsForIdentity", {"IdentityId": identity, "Logins": logins})
        )["Credentials"]
        return identity, creds

    async def _cognito_identity(self, target: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            async with self._session.post(
                f"https://cognito-identity.{AWS_REGION}.amazonaws.com/",
                json=body,
                headers={
                    "Content-Type": "application/x-amz-json-1.1",
                    "X-Amz-Target": f"AWSCognitoIdentityService.{target}",
                },
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status in (400, 401, 403):
                    raise VestelAuthError(f"AWS identity call {target} refused (HTTP {resp.status})")
                if resp.status != 200:
                    raise VestelAcError(f"AWS identity call {target} failed (HTTP {resp.status})")
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise VestelAcError(f"AWS identity call {target} failed: {err}") from err

    async def async_attach_iot_policy(self, identity_id: str) -> None:
        """Attach the IoT policy to this identity, as the official app does when it logs in."""
        await self._request("POST", "v1.0/customer/attachpolicy", {"cognitoIdentityId": identity_id})

    def _expect(self, device_id: str, **values: Any) -> None:
        """Remember what a command just set.

        The cloud's status document is refreshed when the unit reports a change
        it made itself (remote control, buttons), but not reliably after a command
        sent through the cloud. So the value is kept for PENDING_TTL, and dropped
        earlier when the cloud confirms it or reports a different value than it
        had when the command was sent (someone changed it since).
        """
        until = time.monotonic() + PENDING_TTL
        before = self._cloud_last.get(device_id, {})
        bucket = self._pending.setdefault(device_id, {})
        for key, value in values.items():
            bucket[key] = (value, until, before.get(key))

    def _apply_pending(self, device_id: str, status: dict[str, Any]) -> dict[str, Any]:
        bucket = self._pending.get(device_id)
        if not bucket:
            return status
        now = time.monotonic()
        for key, (value, until, baseline) in list(bucket.items()):
            cloud = status.get(key)
            changed = baseline is not None and cloud != baseline
            if cloud == value or changed or now >= until:
                del bucket[key]  # confirmed, overtaken by a newer change, or expired
            else:
                status[key] = value
        return status

    @staticmethod
    def _parse_status(props: dict[str, Any]) -> dict[str, Any]:
        items: dict[str, Any] = {}
        reported: dict[str, Any] = {}  # settings and status only, for raw sensors
        for group in ("settings", "status", "errors"):
            for entry in props.get(group) or []:
                if isinstance(entry, dict) and "item" in entry:
                    items[entry["item"]] = entry.get("value")
                    if group != "errors":
                        reported[entry["item"]] = entry.get("value")

        # "CurrentMode" keeps the last running mode while the unit is off, so only
        # "Mode" tells whether it is on.
        mode = _MODE_FROM_CLOUD.get(items.get("Mode"), "auto")
        vertical = _louver(items.get("Fan.VerticalSwing"))
        horizontal = _louver(items.get("Fan.HorizontalSwing"))
        turbo = bool(items.get("Fan.Turbo"))
        sleep = bool(items.get("Fan.SleepMode"))
        ionizer = bool(items.get("Fan.Ionizer"))
        eco = bool(items.get("Fan.Eco"))
        fanpo_raw = (
            int(turbo)
            | (vertical << 1)
            | (horizontal << 4)
            | (int(sleep) << 7)
            | (int(ionizer) << 8)
            | (int(eco) << 9)
        )

        off_hour = items.get("AutoOff.Hour")
        auto_off_enabled = isinstance(off_hour, int) and 0 <= off_hour <= 23

        errors = sum(1 << bit for bit, name in enumerate(_ERROR_ITEMS) if items.get(name))

        raw: dict[str, Any] = dict(reported)
        raw["ACERROR"] = errors
        raw["ACWARNG"] = items.get("Warning")
        raw["WIFIRSS"] = items.get("Wifi.SignalRSS")
        raw["CONNRSS"] = items.get("Connection.SignalRSS")
        raw["ACVERSI"] = items.get("SoftwareInfo.Version")
        for entry in props.get("commands") or []:
            if isinstance(entry, dict) and "item" in entry:
                raw[f"Command.{entry['item']}"] = entry.get("value")
        raw = {k: v for k, v in raw.items() if v is not None}

        return {
            "on": mode != "off",
            "mode": mode,
            "fan": _FAN_FROM_CLOUD.get(items.get("Fan.Speed"), "auto"),
            "temp": items.get("Temperature"),
            "room_temp": items.get("RoomTemperature"),
            "fanpo_raw": fanpo_raw,
            "turbo": turbo,
            "vertical": vertical,
            "horizontal": horizontal,
            "sleep": sleep,
            "ionizer": ionizer,
            "eco": eco,
            "auto_off_enabled": auto_off_enabled,
            "auto_off_hour": off_hour if auto_off_enabled else None,
            "auto_off_minute": items.get("AutoOff.Minute") if auto_off_enabled else None,
            "auto_on_hour": items.get("AutoOn.Hour"),
            "auto_on_minute": items.get("AutoOn.Minute"),
            "raw": raw,
        }

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #

    async def _post_command(self, device_id: str, code: str) -> dict[str, Any]:
        device = self._devices.get(device_id)
        if device is None:
            await self.async_get_devices()
            device = self._devices.get(device_id)
        if device is None:
            raise VestelAcError(f"Unknown device {device_id}")
        payload = {
            "wifi_card_type": device["wifi_card_type"],
            "device_type": device["device_type"],
            "brand": BRAND,
            "message": json.dumps({"cmd": f"c:{device_id},{code}"}),
        }
        body = await self._request(
            "POST", f"v1.0/customer/devices/{device_id}/legacy/command", payload
        )
        return body if isinstance(body, dict) else {"result": body}

    async def async_send_command(
        self,
        device_id: str,
        cmd: str,
        *,
        mode: str | None = None,
        fan: str | None = None,
        temp: float | None = None,
    ) -> dict[str, Any]:
        """Set mode/fan (ACGENSI) or target temperature (ACTEMOT)."""
        if cmd == "temp":
            if temp is None:
                raise VestelAcError("A temperature is required")
            target = max(MIN_TEMP, min(MAX_TEMP, int(round(temp))))
            status = self._status.get(device_id) or await self.async_get_status(device_id)
            on_hour = status.get("auto_on_hour")
            on_minute = status.get("auto_on_minute")
            if not isinstance(on_hour, int) or on_hour > 23 or not isinstance(on_minute, int):
                on_hour, on_minute = _TIMER_UNSET_HOUR, _TIMER_UNSET_MINUTE
            code = "ACTEMOT" + _pack((4, target - 16), (5, on_hour), (6, on_minute))
            expected = {"temp": target}
        elif cmd in ("on", "off", "mode", "fan"):
            if mode not in MODE_MAP or fan not in FAN_MAP:
                raise VestelAcError(f"Unsupported mode/fan: {mode}/{fan}")
            code = "ACGENSI" + _pack((3, MODE_MAP[mode]), (3, FAN_MAP[fan]))
            expected = {"mode": mode, "on": mode != "off", "fan": fan}
        else:
            raise VestelAcError(f"Unsupported command {cmd}")
        result = await self._post_command(device_id, code)
        self._expect(device_id, **expected)
        return result

    async def async_set_fanpo(
        self,
        device_id: str,
        current_raw: int,
        *,
        turbo: bool | None = None,
        vertical: int | None = None,
        sleep: bool | None = None,
        ionizer: bool | None = None,
        eco: bool | None = None,
    ) -> dict[str, Any]:
        """Change toggles / the vertical louver, keeping everything else.

        The horizontal louver bits are echoed back exactly as reported: their
        encoding has not been confirmed on a real unit, so they are never set.
        """
        t = bool(current_raw & 1) if turbo is None else turbo
        v = (current_raw >> 1) & 7 if vertical is None else vertical
        h = (current_raw >> 4) & 7
        s = bool(current_raw & 128) if sleep is None else sleep
        i = bool(current_raw & 256) if ionizer is None else ionizer
        e = bool(current_raw & 512) if eco is None else eco
        code = "ACFANPO" + _pack(
            (1, int(t)), (3, v), (3, h), (1, int(s)), (1, int(i)), (1, int(e))
        )
        result = await self._post_command(device_id, code)
        self._expect(
            device_id,
            turbo=t,
            vertical=v,
            sleep=s,
            ionizer=i,
            eco=e,
            fanpo_raw=int(code[len("ACFANPO"):]),
        )
        return result

    async def async_set_auto_off(self, device_id: str, hour: int, minute: int) -> dict[str, Any]:
        result = await self._post_command(
            device_id, "ACOFFTV" + _pack((5, hour), (6, minute))
        )
        self._expect(
            device_id, auto_off_enabled=True, auto_off_hour=hour, auto_off_minute=minute
        )
        return result

    async def async_clear_auto_off(self, device_id: str) -> dict[str, Any]:
        result = await self._post_command(device_id, f"ACOFFTV{OFFTV_DISABLED:05d}")
        self._expect(
            device_id, auto_off_enabled=False, auto_off_hour=None, auto_off_minute=None
        )
        return result

    async def async_send_raw_code(self, device_id: str, code: str) -> dict[str, Any]:
        """Send a hand-made command such as ``ACSWUD00001`` unchanged.

        For experiments only: watch which field changes in the climate
        entity's ``raw_status`` attribute after pressing a button in the app.
        """
        return await self._post_command(device_id, code)
