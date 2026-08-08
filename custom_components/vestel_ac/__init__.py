"""Vestel Klima AirCon integration for Home Assistant."""
from __future__ import annotations

import logging
import shutil
from datetime import timedelta
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VestelAcApi, VestelAcError, VestelAuthError
from .const import (
    CONF_REDIRECT_URI,
    CONF_REFRESH_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.TIME,
    Platform.SENSOR,
]

SERVICE_SEND_RAW_CODE = "send_raw_code"
SERVICE_DUMP_RAW_STATUS = "dump_raw_status"

# Both services exist purely to help reverse-engineer buttons the
# integration doesn't model yet (vertical swing, buzzer/volume, sleep...):
# dump the raw status before/after pressing a button in the official app to
# spot which field changed, then try sending a code that sets it yourself.
# Callable straight from the HA app (Developer Tools > Actions) - no
# computer needed.
_SEND_RAW_CODE_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Required("code"): cv.string,
    }
)
_DUMP_RAW_STATUS_SCHEMA = vol.Schema({vol.Required("device_id"): cv.string})


def _find_stored_entry_for_device(
    hass: HomeAssistant, ha_device_id: str
) -> tuple[dict[str, Any] | None, str | None]:
    """Resolve a HA device_id (from the service call's device selector) to
    the (stored entry data, Vestel device_id) it belongs to."""
    device = dr.async_get(hass).async_get(ha_device_id)
    if device is None:
        return None, None

    vestel_device_id = next(
        (ident for domain, ident in device.identifiers if domain == DOMAIN), None
    )
    if vestel_device_id is None:
        return None, None

    for stored in hass.data.get(DOMAIN, {}).values():
        if any(d["device_id"] == vestel_device_id for d in stored["devices"]):
            return stored, vestel_device_id
    return None, None


async def _async_publish_device_picture(hass: HomeAssistant) -> None:
    """Copy the bundled device picture into <config>/www/vestel_ac/ so the
    climate entity's entity_picture (/local/vestel_ac/vestel_ac.png) has
    something to point at - runs once per HA startup, skips silently if
    it's already there or if anything goes wrong (never blocks setup)."""
    source = Path(__file__).parent / "assets" / "vestel_ac.png"
    dest_dir = Path(hass.config.path("www", "vestel_ac"))
    dest = dest_dir / "vestel_ac.png"

    def _copy() -> None:
        if not source.exists() or dest.exists():
            return
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)

    try:
        await hass.async_add_executor_job(_copy)
    except OSError as err:
        _LOGGER.warning(
            "Vestel AC: could not publish device picture to www/vestel_ac/: %s. "
            "Entities will still work, just without a picture - copy "
            "assets/vestel_ac.png to <config>/www/vestel_ac/ yourself if you want it.",
            err,
        )


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register debug services and publish the bundled device picture."""
    await _async_publish_device_picture(hass)


    async def _handle_send_raw_code(call: ServiceCall) -> None:
        stored, vestel_device_id = _find_stored_entry_for_device(
            hass, call.data["device_id"]
        )
        if stored is None:
            raise HomeAssistantError("Vestel AC cihazı bulunamadı.")

        api: VestelAcApi = stored["api"]
        code = call.data["code"]
        result = await api.async_send_raw_code(vestel_device_id, code)
        persistent_notification.async_create(
            hass,
            f"Gönderilen kod: `{code}`\n\nYanıt: `{result}`",
            title="Vestel AC - Ham komut gönderildi",
            notification_id="vestel_ac_raw_code",
        )
        # Refresh so the climate entity's raw_status attribute reflects
        # whatever the code actually changed (if anything).
        await stored["coordinator"].async_request_refresh()

    async def _handle_dump_raw_status(call: ServiceCall) -> None:
        stored, vestel_device_id = _find_stored_entry_for_device(
            hass, call.data["device_id"]
        )
        if stored is None:
            raise HomeAssistantError("Vestel AC cihazı bulunamadı.")

        api: VestelAcApi = stored["api"]
        status = await api.async_get_status(vestel_device_id)
        persistent_notification.async_create(
            hass,
            f"```\n{status.get('raw', {})}\n```",
            title="Vestel AC - Ham durum",
            notification_id="vestel_ac_raw_status",
        )

    hass.services.async_register(
        DOMAIN, SERVICE_SEND_RAW_CODE, _handle_send_raw_code, schema=_SEND_RAW_CODE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DUMP_RAW_STATUS,
        _handle_dump_raw_status,
        schema=_DUMP_RAW_STATUS_SCHEMA,
    )
    return True


class VestelAcCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Polls status for every known device and keeps it keyed by device_id."""

    def __init__(self, hass: HomeAssistant, api: VestelAcApi, device_ids: list[str]) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api
        self.device_ids = device_ids

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        try:
            for device_id in self.device_ids:
                result[device_id] = await self.api.async_get_status(device_id)
        except VestelAuthError as err:
            raise UpdateFailed(f"Auth error talking to Vestel cloud: {err}") from err
        except VestelAcError as err:
            raise UpdateFailed(f"Error talking to Vestel cloud: {err}") from err
        return result


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)

    def _on_token_update(tokens: dict[str, Any]) -> None:
        new_data = {**entry.data, **tokens}
        hass.config_entries.async_update_entry(entry, data=new_data)

    api = VestelAcApi(
        session,
        entry.data[CONF_CLIENT_ID],
        entry.data[CONF_CLIENT_SECRET],
        entry.data[CONF_REDIRECT_URI],
        refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
        token_update_callback=_on_token_update,
    )

    try:
        devices = await api.async_get_devices()
    except VestelAuthError as err:
        _LOGGER.error("Vestel AC authentication failed, re-run setup: %s", err)
        return False
    except VestelAcError as err:
        raise ConfigEntryNotReady(str(err)) from err

    device_ids = [d["device_id"] for d in devices]
    coordinator = VestelAcCoordinator(hass, api, device_ids)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "devices": devices,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
