"""Thin async client for Vestel's (Tuya-backed) Smart Home Cognito + AC API.

This mirrors the logic of https://github.com/iltekin/vestel-ac-remote-control
(lib/token.js + lib/ac-commands.js) but adapted to aiohttp / Home Assistant
conventions. It is unofficial and not affiliated with or endorsed by Vestel.

In addition to the plain "paste a refresh_token" path, this also implements
a headless username/password login (see ``async_login_with_password``) so
the whole setup can happen inside Home Assistant's config flow, from a
phone, with nothing to install outside the integration itself.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import secrets
import time
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlencode, urlparse

import aiohttp
from aiohttp import ClientSession

from .const import (
    API_BASE,
    AUTH_ENDPOINT,
    DEFAULT_SCOPES,
    FAN_MAP,
    FAN_NAME,
    FANPO_ECO_BIT,
    FANPO_HORIZONTAL_SHIFT,
    FANPO_IONIZER_BIT,
    FANPO_LOUVER_MASK,
    FANPO_SLEEP_BIT,
    FANPO_TURBO_BIT,
    FANPO_VERTICAL_SHIFT,
    MAX_TEMP,
    MIN_TEMP,
    MODE_MAP,
    MODE_NAME,
    OFFTV_DISABLED,
    TEMP_OFFSET,
    TOKEN_ENDPOINT,
)

_LOGGER = logging.getLogger(__name__)

# The Cognito Hosted UI login form embeds a CSRF token under one of these
# names depending on how it was deployed. We try each in turn.
_CSRF_FIELD_PATTERNS = (
    r'name=["\']_csrf["\']\s+value=["\']([^"\']+)["\']',
    r'name=["\']csrf_token["\']\s+value=["\']([^"\']+)["\']',
    r'"_csrf"\s*:\s*"([^"]+)"',
)

_LOGIN_ERROR_HINTS = (
    "incorrect username or password",
    "kullanıcı adı veya şifre",
    "kullanici adi veya sifre",
    "hatalı",
    "hatali",
    "invalid username or password",
)

MAX_LOGIN_HOPS = 8

# ---------------------------------------------------------------------- #
# Non-AC appliances (fridges / buzdolabı)
# ---------------------------------------------------------------------- #
# Fridges answer the very same legacy status endpoint as ACs, but with a
# completely different field set whose keys all start with "RF"
# (RFCLOCK, RFCOOER, RFDCOOL, RFDEFEC, RFDOORA, RFMODEA, RFSSAVE,
# RFTEMSE, ...). An AC payload always carries ACGENSI; a fridge payload
# never does. Matching the RF prefix is therefore enough to tell the two
# apart without hard-coding an appliance-type list from the cloud.
FRIDGE_FIELD_PREFIX = "RF"

# RFDOORA is a 2-bit field, one bit per door, reverse engineered on a
# real Vestel fridge:
#
#   00003 (0b11) = fridge closed + freezer closed
#   00001 (0b01) = fridge OPEN   + freezer closed
#   00002 (0b10) = fridge closed + freezer OPEN
#
# so bit 1 (value 2) is the fridge door's "closed" flag and bit 0
# (value 1) is the freezer door's "closed" flag. A door is open when its
# own bit is clear.
FRIDGE_DOOR_CLOSED_BITS = {"fridge": 0b10, "freezer": 0b01}
FRIDGE_DOOR_KEYS = ("RFDOORA", "RFDOORB")

# RFTEMSE packs both setpoints into one integer, high byte = cooler and
# low byte = absolute freezer temperature (the freezer is always below 0).
# Reverse engineered on a real fridge from a 15-point calibration table
# (+2/+4/+5 °C cooler against -16..-24 °C freezer), see fridge_temperatures().
FRIDGE_TEMP_KEYS = ("RFTEMSE",)

# RFMODEA is a bit field of independent fridge modes, reverse engineered on
# a real Vestel fridge:
#
#   00002 (0b00010, bit 1) = fast freeze (hızlı dondurma) on
#   00004 (0b00100, bit 2) = fast cool   (hızlı soğutma)  on
#   00006 (bits 1+2)       = fast cool + fast freeze on together
#   00008 (0b01000, bit 3) = holiday mode (tatil) on
#   00016 (0b10000, bit 4) = eco mode (ekonomi) on
#
# The bits are independent (fast cool and fast freeze can be active at the
# same time), so every bit is decoded on its own.
FRIDGE_MODE_KEYS = ("RFMODEA",)
FRIDGE_MODE_BITS = {
    "fast_freeze": 0b00010,
    "fast_cool": 0b00100,
    "holiday": 0b01000,
    "eco": 0b10000,
}

# Two plain on/off flag fields: 00000 = off, anything else = on.
FRIDGE_CHILD_LOCK_KEYS = ("RFCLOCK",)
FRIDGE_SCREEN_SAVER_KEYS = ("RFSSAVE",)


def _as_int(value: Any) -> Optional[int]:
    """Best-effort decimal parse of a cloud field (values arrive as
    zero-padded strings such as "00003"). Returns None on anything that
    is not a whole number."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def is_fridge_payload(d: dict[str, Any]) -> bool:
    """True when a status payload looks like a fridge (any RF* field)."""
    if not isinstance(d, dict):
        return False
    return any(str(key).upper().startswith(FRIDGE_FIELD_PREFIX) for key in d)


def fridge_door_states(value: Any) -> Optional[dict[str, bool]]:
    """Decode an RFDOORA value into per-door open states.

    Returns ``{"fridge": bool, "freezer": bool}`` where True means that
    door is open, or None when the field is missing/unparseable so the
    binary sensors report "unknown" instead of "closed".
    """
    number = _as_int(value)
    if number is None:
        return None
    return {
        door: (number & bit) == 0 for door, bit in FRIDGE_DOOR_CLOSED_BITS.items()
    }


def _first_upper_field(d: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """Return the value of the first of ``keys`` present in ``d``,
    matching field names case-insensitively; None when none is present."""
    if not isinstance(d, dict):
        return None
    upper = {str(key).upper(): key for key in d}
    for key in keys:
        if key in upper:
            return d[upper[key]]
    return None


def fridge_door_raw(d: dict[str, Any]) -> Any:
    """Return the first present door field (RFDOORA / RFDOORB), if any."""
    return _first_upper_field(d, FRIDGE_DOOR_KEYS)


def fridge_temp_raw(d: dict[str, Any]) -> Any:
    """Return the raw RFTEMSE value, if present."""
    return _first_upper_field(d, FRIDGE_TEMP_KEYS)


def fridge_mode_raw(d: dict[str, Any]) -> Any:
    """Return the raw RFMODEA value, if present."""
    return _first_upper_field(d, FRIDGE_MODE_KEYS)


def fridge_child_lock_raw(d: dict[str, Any]) -> Any:
    """Return the raw RFCLOCK (child lock) value, if present."""
    return _first_upper_field(d, FRIDGE_CHILD_LOCK_KEYS)


def fridge_screen_saver_raw(d: dict[str, Any]) -> Any:
    """Return the raw RFSSAVE (screen saver) value, if present."""
    return _first_upper_field(d, FRIDGE_SCREEN_SAVER_KEYS)


def fridge_modes(value: Any) -> Optional[dict[str, bool]]:
    """Decode an RFMODEA value into the individual mode booleans.

    Returns ``{"fast_freeze": bool, "fast_cool": bool, "holiday": bool,
    "eco": bool}`` or None when the field is missing/unparseable, so the
    binary sensors report "unknown" instead of a bogus "off".
    """
    number = _as_int(value)
    if number is None:
        return None
    return {name: bool(number & bit) for name, bit in FRIDGE_MODE_BITS.items()}


def fridge_flag(value: Any) -> Optional[bool]:
    """Decode a plain on/off RF flag field such as RFCLOCK or RFSSAVE
    (``00000`` = off, anything else = on). Returns None when the field is
    missing/unparseable."""
    number = _as_int(value)
    if number is None:
        return None
    return number != 0


def fridge_temp_display(fridge: dict[str, Any], which: str) -> Any:
    """The value the fridge panel shows for a decoded setpoint ``which``
    ("cooler" or "freezer"), honouring the mode overrides:

    * eco on -> the panel shows ``"E"`` instead of a number for **both**
      the cooler and the freezer;
    * holiday on -> the cooler is switched off, so the cooler has no
      reading at all (``None`` turns into "unknown"/"--" in HA), while the
      freezer keeps its setpoint.

    Pure helper so the display rules stay testable without Home Assistant.
    """
    if fridge.get("eco"):
        return "E"
    if which == "cooler" and fridge.get("holiday"):
        return None
    return fridge.get(f"{which}_temp")


def fridge_temperatures(value: Any) -> Optional[dict[str, int]]:
    """Decode an RFTEMSE value into the cooler/freezer setpoints in °C.

    The field is a bit-packed pair, not two decimal halves:

        RFTEMSE = (cooler << 8) | abs(freezer)

    Reverse engineered on a real Vestel fridge from a 15-point calibration
    table (cooler +2/+4/+5 °C against freezer -16..-24 °C); every point
    fits exactly:

        00528 = 0x210 -> cooler  2 °C, freezer -16 °C
        01042 = 0x412 -> cooler  4 °C, freezer -18 °C
        01304 = 0x518 -> cooler  5 °C, freezer -24 °C

    Returns ``{"cooler": int, "freezer": int}`` or None when the field is
    missing/unparseable, so the temperature sensors report "unknown"
    instead of a bogus °C.
    """
    number = _as_int(value)
    if number is None or number < 0:
        return None
    return {"cooler": number >> 8, "freezer": -(number & 0xFF)}


class VestelAcError(Exception):
    """Generic API error."""


class VestelAuthError(VestelAcError):
    """Raised when authentication / token refresh fails."""


class VestelAutomationError(VestelAcError):
    """Raised when the headless username/password login could not be
    completed automatically (e.g. the login page changed, or there is an
    extra verification step like a captcha). The config flow catches this
    separately from VestelAuthError so it can point the person at the
    manual refresh_token fallback instead of just saying "wrong password".
    """


class VestelAcApi:
    """Handles OAuth token lifecycle and AC device calls."""

    def __init__(
        self,
        session: ClientSession,
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
        self._id_token: Optional[str] = None
        self._expires_at: float = 0
        # Called with {"refresh_token": ...} whenever we get a (possibly new)
        # refresh token, so the caller can persist it in the config entry.
        self._token_update_callback = token_update_callback

    # ------------------------------------------------------------------ #
    # OAuth / token handling
    # ------------------------------------------------------------------ #

    async def async_exchange_code(self, code: str, code_verifier: str) -> None:
        """Exchange an authorization code (from the Hosted UI redirect) for tokens."""
        params = {
            "grant_type": "authorization_code",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "redirect_uri": self._redirect_uri,
            "code": code,
            "code_verifier": code_verifier,
        }
        data = await self._post_token(params)
        self._save_tokens(data)

    @staticmethod
    def _make_pkce_pair() -> tuple[str, str]:
        verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        return verifier, challenge

    def _build_authorize_url(self, challenge: str) -> str:
        params = {
            "client_id": self._client_id,
            "response_type": "code",
            "scope": DEFAULT_SCOPES,
            "redirect_uri": self._redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return f"{AUTH_ENDPOINT}?{urlencode(params)}"

    @staticmethod
    def _extract_csrf(html: str) -> Optional[str]:
        for pattern in _CSRF_FIELD_PATTERNS:
            match = re.search(pattern, html)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _looks_like_invalid_credentials(body: str) -> bool:
        lowered = body.lower()
        return any(hint in lowered for hint in _LOGIN_ERROR_HINTS)

    async def async_login_with_password(self, username: str, password: str) -> str:
        """Log straight into the Vestel account with username + password.

        This drives the same Cognito Hosted UI login form the app's embedded
        browser shows (GET the authorize page, POST the credentials + CSRF
        token to it, follow the redirect chain), but over plain HTTP - no
        real browser, no external script, nothing to install. If that page
        ever changes shape enough that we can't find the CSRF field or the
        redirect chain doesn't end at our redirect_uri, we raise
        VestelAutomationError so the caller can fall back to the manual
        refresh_token method instead of failing silently.
        """
        verifier, challenge = self._make_pkce_pair()
        authorize_url = self._build_authorize_url(challenge)

        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar()) as login_session:
            async with login_session.get(authorize_url) as resp:
                if resp.status != 200:
                    raise VestelAutomationError(
                        f"Giriş sayfası açılamadı (HTTP {resp.status})."
                    )
                html = await resp.text()
                login_url = str(resp.url)

            csrf = self._extract_csrf(html)
            if csrf is None:
                raise VestelAutomationError(
                    "Giriş sayfasının yapısı değişmiş görünüyor (CSRF alanı bulunamadı)."
                )

            method = "POST"
            url = login_url
            data: Optional[dict[str, str]] = {
                "username": username,
                "password": password,
                "_csrf": csrf,
            }
            code: Optional[str] = None

            for _ in range(MAX_LOGIN_HOPS):
                if method == "POST":
                    ctx = login_session.post(
                        url,
                        data=data,
                        allow_redirects=False,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
                else:
                    ctx = login_session.get(url, allow_redirects=False)

                async with ctx as resp:
                    if resp.status in (301, 302, 303):
                        location = resp.headers.get("Location", "")
                        if location.startswith(self._redirect_uri):
                            qs = parse_qs(urlparse(location).query)
                            if "code" in qs:
                                code = qs["code"][0]
                            break
                        url = location
                        method = "GET"
                        data = None
                        continue

                    if resp.status == 200 and method == "POST":
                        body = await resp.text()
                        if self._looks_like_invalid_credentials(body):
                            raise VestelAuthError("Kullanıcı adı veya şifre hatalı.")
                        raise VestelAutomationError(
                            "Otomatik giriş tamamlanamadı - ek bir doğrulama adımı "
                            "(ör. captcha/2FA) olabilir."
                        )

                    raise VestelAutomationError(
                        f"Giriş akışı beklenmedik bir yanıt döndürdü (HTTP {resp.status})."
                    )

            if not code:
                raise VestelAutomationError(
                    "Yönlendirme zincirinde yetkilendirme kodu bulunamadı."
                )

            await self.async_exchange_code(code, verifier)
            if not self._refresh_token:
                raise VestelAutomationError("Token yanıtında refresh_token yoktu.")
            return self._refresh_token

    async def async_refresh(self) -> str:
        """Refresh the id_token using the stored refresh_token."""
        if not self._refresh_token:
            raise VestelAuthError("No refresh token available; re-run setup.")

        params = {
            "grant_type": "refresh_token",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "refresh_token": self._refresh_token,
        }
        data = await self._post_token(params)
        self._save_tokens(data, keep_existing_refresh=True)
        return self._id_token  # type: ignore[return-value]

    async def async_get_id_token(self) -> str:
        if self._id_token and self._expires_at > time.time() + 60:
            return self._id_token
        return await self.async_refresh()

    async def _post_token(self, params: dict[str, str]) -> dict[str, Any]:
        async with self._session.post(
            TOKEN_ENDPOINT,
            data=params,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as resp:
            data = await resp.json(content_type=None)
            if resp.status != 200:
                raise VestelAuthError(f"Token request failed ({resp.status}): {data}")
            return data

    def _save_tokens(self, data: dict[str, Any], keep_existing_refresh: bool = False) -> None:
        self._id_token = data.get("id_token")
        self._expires_at = time.time() + data.get("expires_in", 3600)
        new_refresh = data.get("refresh_token")
        if new_refresh and not keep_existing_refresh:
            self._refresh_token = new_refresh
        elif new_refresh and new_refresh != self._refresh_token:
            # Some Cognito app clients rotate refresh tokens on refresh calls.
            self._refresh_token = new_refresh

        if self._token_update_callback and self._refresh_token:
            self._token_update_callback({"refresh_token": self._refresh_token})

    # ------------------------------------------------------------------ #
    # Device discovery / status / commands
    # ------------------------------------------------------------------ #

    async def async_get_devices(self) -> list[dict[str, str]]:
        token = await self.async_get_id_token()
        headers = {"token": token}

        async with self._session.get(f"{API_BASE}/homes", headers=headers) as resp:
            homes_data = await resp.json(content_type=None)
            if resp.status != 200:
                raise VestelAcError(f"Could not list homes ({resp.status}): {homes_data}")

        devices: list[dict[str, str]] = []
        for home in homes_data.get("items", []):
            home_id = home.get("homeId")
            home_name = home.get("homeName")
            async with self._session.get(
                f"{API_BASE}/homes/{home_id}/devices", headers=headers
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status != 200:
                    continue
                for dev in data.get("items", {}).get("homeappliances", []):
                    device_id = dev.get("deviceId")
                    if not device_id:
                        continue
                    device_type = str(
                        dev.get("deviceType") or dev.get("type") or dev.get("category") or ""
                    )
                    if not device_type:
                        # No recognizable type field - log the whole item at
                        # debug level so new appliance types (fridges,
                        # dishwashers, ...) can be identified from the logs
                        # instead of guesswork.
                        _LOGGER.debug(
                            "Vestel device %s has no recognizable type field; "
                            "item keys: %s (item: %s)",
                            device_id,
                            list(dev),
                            dev,
                        )
                    devices.append(
                        {
                            "device_id": device_id,
                            "device_name": dev.get("deviceName", device_id),
                            "home_name": home_name,
                            "device_type": device_type,
                        }
                    )
        return devices

    @staticmethod
    def _parse_status(d: dict[str, Any]) -> dict[str, Any]:
        """Decode one raw cloud status payload (the "data" object of the
        legacy status endpoint) into the integration's internal format.

        The same endpoint also serves non-AC appliances (e.g. Vestel
        fridges), whose payloads carry a completely different set of fields
        and no ACGENSI at all. Rather than crashing the whole coordinator
        on them (the old KeyError: 'ACGENSI' setup failure), return a
        minimal {"is_ac": False, "raw": ...} record: platforms gate on
        "is_ac" so only the generic raw diagnostic sensors attach to such
        devices, and the raw payload stays available for reverse
        engineering.

        If a payload claims to be an AC (ACGENSI present) but is missing or
        malformed elsewhere, degrade to the same non-AC record instead of
        raising - a half-parsed climate entity is worse than none.
        """
        status: dict[str, Any] = {"is_ac": False, "is_fridge": False, "raw": d}

        if "ACGENSI" not in d:
            # Not an AC. If it looks like a fridge, decode what we already
            # understand (the door) and leave the rest in "raw" for
            # further reverse engineering.
            if is_fridge_payload(d):
                door_raw = fridge_door_raw(d)
                states = fridge_door_states(door_raw)
                temp_raw = fridge_temp_raw(d)
                temps = fridge_temperatures(temp_raw)
                mode_raw = fridge_mode_raw(d)
                modes = fridge_modes(mode_raw)
                child_lock_raw = fridge_child_lock_raw(d)
                screen_saver_raw = fridge_screen_saver_raw(d)
                status["is_fridge"] = True
                status["fridge"] = {
                    "door_raw": door_raw,
                    "fridge_door_open": states["fridge"] if states else None,
                    "freezer_door_open": states["freezer"] if states else None,
                    "temp_raw": temp_raw,
                    "cooler_temp": temps["cooler"] if temps else None,
                    "freezer_temp": temps["freezer"] if temps else None,
                    "mode_raw": mode_raw,
                    "fast_cool": modes["fast_cool"] if modes else None,
                    "fast_freeze": modes["fast_freeze"] if modes else None,
                    "holiday": modes["holiday"] if modes else None,
                    "eco": modes["eco"] if modes else None,
                    "child_lock_raw": child_lock_raw,
                    "child_lock": fridge_flag(child_lock_raw),
                    "screen_saver_raw": screen_saver_raw,
                    "screen_saver": fridge_flag(screen_saver_raw),
                }
            return status

        try:
            gensi = int(d["ACGENSI"])
            mode_raw = gensi & 7
            fan_raw = gensi >> 3
            temp = int(d["ACTEMOT"]) - TEMP_OFFSET
            room_temp = int(d["ACROOTE"])
            mode = MODE_NAME.get(mode_raw, "cool")
            fan = FAN_NAME.get(fan_raw, "auto")
            on = mode_raw != 5

            # ACFANPO: packed toggles (turbo/sleep/ionizer/eco) + louver
            # positions (vertical/horizontal), confirmed against real captures.
            fanpo_raw = int(d.get("ACFANPO", 0))
            turbo = bool(fanpo_raw & FANPO_TURBO_BIT)
            vertical = (fanpo_raw >> FANPO_VERTICAL_SHIFT) & FANPO_LOUVER_MASK
            horizontal = (fanpo_raw >> FANPO_HORIZONTAL_SHIFT) & FANPO_LOUVER_MASK
            sleep = bool(fanpo_raw & FANPO_SLEEP_BIT)
            ionizer = bool(fanpo_raw & FANPO_IONIZER_BIT)
            eco = bool(fanpo_raw & FANPO_ECO_BIT)

            # ACOFFTV: auto-off (delayed shutdown) target clock time.
            offtv_raw = int(d.get("ACOFFTV", OFFTV_DISABLED))
            auto_off_enabled = offtv_raw != OFFTV_DISABLED
            auto_off_hour = offtv_raw & 0x1F if auto_off_enabled else None
            auto_off_minute = (offtv_raw >> 5) & 0x1F if auto_off_enabled else None
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.warning(
                "Vestel AC: status payload had ACGENSI but could not be "
                "decoded (%s); exposing raw fields only: %s",
                err,
                d,
            )
            return status

        # Full, unparsed status payload from Vestel is kept in "raw" - the
        # API returns other AC* fields too. Exposed as a climate entity
        # attribute so you can diff it before/after pressing a button in
        # the official app and spot which field changes - see
        # async_send_raw_code() to then test your guess.
        status.update(
            {
                "is_ac": True,
                "on": on,
                "mode": mode,
                "fan": fan,
                "temp": temp,
                "room_temp": room_temp,
                "fanpo_raw": fanpo_raw,
                "turbo": turbo,
                "vertical": vertical,
                "horizontal": horizontal,
                "sleep": sleep,
                "ionizer": ionizer,
                "eco": eco,
                "auto_off_enabled": auto_off_enabled,
                "auto_off_hour": auto_off_hour,
                "auto_off_minute": auto_off_minute,
            }
        )
        return status

    async def async_get_status(self, device_id: str) -> dict[str, Any]:
        token = await self.async_get_id_token()
        headers = {"token": token}
        async with self._session.get(
            f"{API_BASE}/homeappliances/legacy/status",
            params={"uuid": device_id},
            headers=headers,
        ) as resp:
            data = await resp.json(content_type=None)
            if resp.status != 200 or data.get("status") != "SUCCESS":
                raise VestelAcError(f"Could not get status for {device_id}: {data}")

        d = data["data"]
        return self._parse_status(d)

    @staticmethod
    def _build_field(field: str, value: int) -> str:
        return f"{field}{value:05d}"

    @staticmethod
    def _build_gensi(mode: str, fan: str = "auto") -> str:
        if mode not in MODE_MAP:
            raise ValueError(f"Invalid mode: {mode}")
        if fan not in FAN_MAP:
            raise ValueError(f"Invalid fan speed: {fan}")
        value = (FAN_MAP[fan] << 3) | MODE_MAP[mode]
        return VestelAcApi._build_field("ACGENSI", value)

    @staticmethod
    def _build_temot(temp: float) -> str:
        temp = int(temp)
        if temp < MIN_TEMP or temp > MAX_TEMP:
            raise ValueError(f"Temperature must be between {MIN_TEMP} and {MAX_TEMP}")
        return VestelAcApi._build_field("ACTEMOT", temp + TEMP_OFFSET)

    def _build_code(self, cmd: str, mode: str = "cool", fan: str = "auto", temp: float = 22) -> str:
        if cmd in ("on", "mode", "fan"):
            return self._build_gensi(mode, fan)
        if cmd == "off":
            # Power-off is ACCMODE=5 with fan field cleared.
            return self._build_gensi("off", "auto")
        if cmd == "temp":
            return self._build_temot(temp)
        raise ValueError(f"Invalid command: {cmd}")

    async def async_send_command(
        self,
        device_id: str,
        cmd: str,
        mode: str = "cool",
        fan: str = "auto",
        temp: float = 22,
    ) -> dict[str, Any]:
        code = self._build_code(cmd, mode=mode, fan=fan, temp=temp)
        return await self._post_command(device_id, code)

    async def async_set_fanpo(
        self,
        device_id: str,
        current_raw: int,
        *,
        turbo: bool | None = None,
        vertical: int | None = None,
        horizontal: int | None = None,
        sleep: bool | None = None,
        ionizer: bool | None = None,
        eco: bool | None = None,
    ) -> dict[str, Any]:
        """Update one or more ACFANPO toggles/positions while preserving the
        rest - Vestel's app always transmits the full packed value, not a
        delta, so we must read-modify-write from current_raw (the coordinator's
        cached fanpo_raw for this device)."""
        t = bool(current_raw & FANPO_TURBO_BIT) if turbo is None else turbo
        v = (current_raw >> FANPO_VERTICAL_SHIFT) & FANPO_LOUVER_MASK if vertical is None else vertical
        h = (current_raw >> FANPO_HORIZONTAL_SHIFT) & FANPO_LOUVER_MASK if horizontal is None else horizontal
        s = bool(current_raw & FANPO_SLEEP_BIT) if sleep is None else sleep
        i = bool(current_raw & FANPO_IONIZER_BIT) if ionizer is None else ionizer
        e = bool(current_raw & FANPO_ECO_BIT) if eco is None else eco

        new_value = (
            (FANPO_TURBO_BIT if t else 0)
            | ((v & FANPO_LOUVER_MASK) << FANPO_VERTICAL_SHIFT)
            | ((h & FANPO_LOUVER_MASK) << FANPO_HORIZONTAL_SHIFT)
            | (FANPO_SLEEP_BIT if s else 0)
            | (FANPO_IONIZER_BIT if i else 0)
            | (FANPO_ECO_BIT if e else 0)
        )
        return await self._post_command(device_id, self._build_field("ACFANPO", new_value))

    async def async_set_auto_off(self, device_id: str, hour: int, minute: int) -> dict[str, Any]:
        value = ((minute & 0x1F) << 5) | (hour & 0x1F)
        return await self._post_command(device_id, self._build_field("ACOFFTV", value))

    async def async_clear_auto_off(self, device_id: str) -> dict[str, Any]:
        return await self._post_command(device_id, self._build_field("ACOFFTV", OFFTV_DISABLED))

    async def async_send_raw_code(self, device_id: str, code: str) -> dict[str, Any]:
        """Send an arbitrary, hand-crafted command code (e.g. "ACSWUD00001")
        straight through, bypassing _build_code entirely.

        This exists purely for reverse-engineering buttons the integration
        doesn't model yet. Workflow: dump the "raw_status" attribute on the
        climate entity before and after pressing the button in the official
        app to spot the field that changed, then use this to try sending a
        code that sets that same field yourself and watch whether the unit
        reacts.
        """
        return await self._post_command(device_id, code)

    async def _post_command(self, device_id: str, code: str) -> dict[str, Any]:
        token = await self.async_get_id_token()
        payload = {
            "device_type": "AC",
            "wifi_card_type": "HM07",
            "brand": "Vestel",
            "message": json.dumps({"cmd": f"c:{device_id},{code}"}),
        }
        headers = {"Content-Type": "application/json", "token": token}

        async with self._session.post(
            f"{API_BASE}/customer/devices/{device_id}/legacy/command",
            json=payload,
            headers=headers,
        ) as resp:
            data = await resp.json(content_type=None)
            if resp.status != 200:
                raise VestelAcError(f"Command failed ({resp.status}): {data}")
            return data
