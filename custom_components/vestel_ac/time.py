"""Time platform: target clock time for the auto-off (delayed shutdown)
timer - ACOFFTV, confirmed against a real capture (14:18 -> 00590).

Note: the "auto-start" timer Vestel's app also offers reuses the ACTEMOT
field (normally target temperature) with an extra tag in its low 4 bits
that wasn't fully confirmed (only one example was captured), so it isn't
implemented as a dedicated entity yet to avoid risking the temperature
control - see README for the decode and how to test/extend it via the
send_raw_code service.
"""
from __future__ import annotations

import datetime as dt

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import VestelAcCoordinator
from .api import VestelAcApi
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    stored = hass.data[DOMAIN][entry.entry_id]
    coordinator: VestelAcCoordinator = stored["coordinator"]
    api: VestelAcApi = stored["api"]
    devices: list[dict[str, str]] = stored["devices"]

    async_add_entities(
        _VestelAcAutoOffTime(coordinator, api, entry.entry_id, device)
        for device in devices
    )


class _VestelAcAutoOffTime(CoordinatorEntity[VestelAcCoordinator], TimeEntity):
    """Sets the auto-off target clock time. Setting this also (re)enables
    the timer, mirroring how the official app's time picker behaves."""

    _attr_has_entity_name = True
    _attr_name = "Otomatik Kapatma Saati"

    def __init__(
        self,
        coordinator: VestelAcCoordinator,
        api: VestelAcApi,
        entry_id: str,
        device: dict[str, str],
    ) -> None:
        super().__init__(coordinator)
        self._api = api
        self._device_id = device["device_id"]
        self._attr_unique_id = f"{entry_id}_{self._device_id}_auto_off_time"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, self._device_id)})

    @property
    def native_value(self) -> dt.time | None:
        status = self.coordinator.data.get(self._device_id, {})
        if not status.get("auto_off_enabled"):
            return None
        hour = status.get("auto_off_hour") or 0
        minute = status.get("auto_off_minute") or 0
        return dt.time(hour=hour, minute=minute)

    async def async_set_value(self, value: dt.time) -> None:
        await self._api.async_set_auto_off(self._device_id, value.hour, value.minute)
        await self.coordinator.async_request_refresh()
