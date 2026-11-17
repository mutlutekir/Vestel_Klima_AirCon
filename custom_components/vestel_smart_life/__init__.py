"""Vestel Smart Life integration for Home Assistant."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
)
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VestelAcApi, VestelAcError, VestelAuthError
from .const import (
    CONF_REDIRECT_URI,
    CONF_REFRESH_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .live import VestelLive

_LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
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


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the debug services."""

    async def _handle_send_raw_code(call: ServiceCall) -> None:
        stored, vestel_device_id = _find_stored_entry_for_device(
            hass, call.data["device_id"]
        )
        if stored is None:
            raise HomeAssistantError("Vestel Smart Life cihazı bulunamadı.")

        api: VestelAcApi = stored["api"]
        code = call.data["code"]
        result = await api.async_send_raw_code(vestel_device_id, code)
        persistent_notification.async_create(
            hass,
            f"Gönderilen kod: `{code}`\n\nYanıt: `{result}`",
            title="Vestel Smart Life - Ham komut gönderildi",
            notification_id="vestel_smart_life_raw_code",
        )
        # Refresh so the climate entity's raw_status attribute reflects
        # whatever the code actually changed (if anything).
        await stored["coordinator"].async_request_refresh()

    async def _handle_dump_raw_status(call: ServiceCall) -> None:
        stored, vestel_device_id = _find_stored_entry_for_device(
            hass, call.data["device_id"]
        )
        if stored is None:
            raise HomeAssistantError("Vestel Smart Life cihazı bulunamadı.")

        api: VestelAcApi = stored["api"]
        status = await api.async_get_status(vestel_device_id)
        persistent_notification.async_create(
            hass,
            f"```\n{status.get('raw', {})}\n```",
            title="Vestel Smart Life - Ham durum",
            notification_id="vestel_smart_life_raw_status",
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
            raise ConfigEntryAuthFailed(f"Vestel authentication failed: {err}") from err
        except VestelAcError as err:
            raise UpdateFailed(f"Error talking to Vestel cloud: {err}") from err
        return result


def _async_remove_horizontal_louver_entities(
    hass: HomeAssistant, entry: ConfigEntry, device_ids: list[str]
) -> None:
    """Drop horizontal louver entities created by releases before 1.1.0.

    Their command encoding was never confirmed on a real unit, so they are no
    longer created; remove the registry leftovers instead of leaving them
    "unavailable".
    """
    registry = er.async_get(hass)
    for device_id in device_ids:
        prefix = f"{entry.entry_id}_{device_id}_horizontal_"
        for suffix in ("louver", "swing", "stop"):
            for domain in ("select", "button"):
                entity_id = registry.async_get_entity_id(domain, DOMAIN, prefix + suffix)
                if entity_id:
                    registry.async_remove(entity_id)


def _async_start_live(
    hass: HomeAssistant, api: VestelAcApi, coordinator: VestelAcCoordinator, devices: list[dict[str, str]]
) -> VestelLive | None:
    """Listen to the units' own messages so on/off and mode follow the real state at once."""
    topics = {d["pub_topic"]: d["device_id"] for d in devices if d.get("pub_topic")}
    if not topics:
        return None

    def _on_update(device_id: str, delta: Any) -> None:
        status = api.apply_live(device_id, delta)
        if status is not None and coordinator.data is not None:
            coordinator.async_set_updated_data({**coordinator.data, device_id: status})

    def _on_lost() -> None:
        # Changes may have been missed while disconnected; go back to what the cloud says.
        api.clear_live()
        hass.async_create_task(coordinator.async_request_refresh())

    live = VestelLive(api, topics, _on_update, _on_lost)
    live.start()
    return live


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
        raise ConfigEntryAuthFailed(f"Vestel authentication failed: {err}") from err
    except VestelAcError as err:
        raise ConfigEntryNotReady(str(err)) from err

    device_ids = [d["device_id"] for d in devices]
    _async_remove_horizontal_louver_entities(hass, entry, device_ids)
    coordinator = VestelAcCoordinator(hass, api, device_ids)
    await coordinator.async_config_entry_first_refresh()

    live = _async_start_live(hass, api, coordinator, devices)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "devices": devices,
        "live": live,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        stored = hass.data[DOMAIN].pop(entry.entry_id)
        if stored.get("live"):
            await stored["live"].async_stop()
    return unload_ok
