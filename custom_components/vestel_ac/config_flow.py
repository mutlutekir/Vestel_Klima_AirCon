"""Config flow for the Vestel AC (unofficial) integration.

Everything needed lives inside the integration - nothing to install or run
outside Home Assistant, so this can be set up entirely from a phone.

Two ways to get set up, both handled on-device by Home Assistant itself:

1. "Kullanıcı adı / şifre" (recommended, fully automatic): you type in your
   Vestel account credentials and Home Assistant logs into the Cognito
   Hosted UI on your behalf (see api.py: async_login_with_password) and
   creates the entry with zero copy/paste.

2. "Refresh token yapıştır" (manual fallback): only needed if step 1 can't
   complete automatically (e.g. Vestel adds a captcha/2FA step to login, or
   changes the login page enough that we can't drive it headlessly). Paste
   a refresh_token you obtained some other way.

App client_id/secret are fixed constants (see const.py) - Vestel's own app
credentials, confirmed from its amplifyconfiguration.json. They are not
asked for in the UI; edit const.py if Vestel ever rotates them.
"""
from __future__ import annotations

import hashlib
from typing import Any

import voluptuous as vol
from aiohttp import ClientError

from homeassistant import config_entries
from homeassistant.const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VestelAcApi, VestelAcError, VestelAuthError, VestelAutomationError
from .const import (
    APP_CLIENT_ID,
    APP_CLIENT_SECRET,
    CONF_REDIRECT_URI,
    CONF_REFRESH_TOKEN,
    DEFAULT_REDIRECT_URI,
    DOMAIN,
)


async def _validate_and_build_entry_data(hass, refresh_token: str) -> dict[str, Any]:
    """Check the refresh_token actually works and the account has devices."""
    session = async_get_clientsession(hass)
    api = VestelAcApi(
        session,
        APP_CLIENT_ID,
        APP_CLIENT_SECRET,
        DEFAULT_REDIRECT_URI,
        refresh_token=refresh_token,
    )
    await api.async_refresh()
    devices = await api.async_get_devices()
    if not devices:
        raise NoDevicesError

    return {
        CONF_CLIENT_ID: APP_CLIENT_ID,
        CONF_CLIENT_SECRET: APP_CLIENT_SECRET,
        CONF_REDIRECT_URI: DEFAULT_REDIRECT_URI,
        CONF_REFRESH_TOKEN: refresh_token,
    }


class NoDevicesError(Exception):
    """Raised when login succeeded but no AC devices were found."""


class VestelAcConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Vestel AC."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Entry point: let the person pick automatic or manual setup."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["credentials", "token"],
        )

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Automatic path: log in with username/password, no browser needed."""
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            api = VestelAcApi(session, APP_CLIENT_ID, APP_CLIENT_SECRET, DEFAULT_REDIRECT_URI)
            try:
                refresh_token = await api.async_login_with_password(
                    user_input[CONF_USERNAME].strip(), user_input[CONF_PASSWORD]
                )
                data = await _validate_and_build_entry_data(self.hass, refresh_token)
            except VestelAutomationError:
                errors["base"] = "automation_failed"
            except VestelAuthError:
                errors["base"] = "invalid_auth"
            except NoDevicesError:
                errors["base"] = "no_devices"
            except (VestelAcError, ClientError):
                errors["base"] = "cannot_connect"
            else:
                await self._set_unique_id_from_token(refresh_token)
                return self.async_create_entry(title="Vestel AC", data=data)

        return self.async_show_form(
            step_id="credentials",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_token(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Manual fallback: paste a refresh_token obtained some other way."""
        errors: dict[str, str] = {}

        if user_input is not None:
            refresh_token = user_input[CONF_REFRESH_TOKEN].strip()
            try:
                data = await _validate_and_build_entry_data(self.hass, refresh_token)
            except VestelAuthError:
                errors["base"] = "invalid_auth"
            except NoDevicesError:
                errors["base"] = "no_devices"
            except (VestelAcError, ClientError):
                errors["base"] = "cannot_connect"
            else:
                await self._set_unique_id_from_token(refresh_token)
                return self.async_create_entry(title="Vestel AC", data=data)

        return self.async_show_form(
            step_id="token",
            data_schema=vol.Schema({vol.Required(CONF_REFRESH_TOKEN): str}),
            errors=errors,
        )

    async def _set_unique_id_from_token(self, refresh_token: str) -> None:
        # We don't have a stable Vestel account id handy, so key uniqueness
        # off a hash of the refresh_token's first chars - stable enough to
        # avoid duplicate entries from repeated imports of the same session.
        unique = hashlib.sha256(refresh_token.encode()).hexdigest()[:16]
        await self.async_set_unique_id(unique)
        self._abort_if_unique_id_configured()
