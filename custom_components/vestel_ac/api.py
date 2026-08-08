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
                    devices.append(
                        {
                            "device_id": device_id,
                            "device_name": dev.get("deviceName", device_id),
                            "home_name": home_name,
                        }
                    )
        return devices

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

        return {
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
            # Full, unparsed status payload from Vestel - we only decode
            # ACGENSI/ACTEMOT/ACROOTE/ACFANPO/ACOFFTV above, but the API
            # returns other AC* fields too. Exposed as a climate entity
            # attribute so you can diff it before/after pressing a button
            # in the official app and spot which field changes - see
            # async_send_raw_code() to then test your guess.
            "raw": d,
        }

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
