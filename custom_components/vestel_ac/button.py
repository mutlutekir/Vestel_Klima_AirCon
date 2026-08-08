"""Button platform: quick "serbest salınım" / "salınımı durdur" shortcuts.

The select.py dropdown already covers the full 0-6 range, but these buttons
give one-tap access to the two most commonly used actions without opening
the dropdown - as requested, so the swing can be controlled manually too.
"""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VestelAcCoordinator
from .api import VestelAcApi
from .const import DOMAIN

SWING_VALUE = 6
STOP_VALUE = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    stored = hass.data[DOMAIN][entry.entry_id]
    coordinator: VestelAcCoordinator = stored["coordinator"]
    api: VestelAcApi = stored["api"]
    devices: list[dict[str, str]] = stored["devices"]

    entities: list[ButtonEntity] = []
    for device in devices:
        for axis, label in (("vertical", "Dikey"), ("horizontal", "Yatay")):
            entities.append(
                _VestelAcLouverButton(
                    coordinator, api, entry.entry_id, device, axis,
                    value=SWING_VALUE, name=f"{label} Kanatçık - Serbest Salınım",
                    suffix="swing",
                )
            )
            entities.append(
                _VestelAcLouverButton(
                    coordinator, api, entry.entry_id, device, axis,
                    value=STOP_VALUE, name=f"{label} Kanatçık - Salınımı Durdur",
                    suffix="stop",
                )
            )
    async_add_entities(entities)


class _VestelAcLouverButton(ButtonEntity):
    """Sets one louver axis straight to swing (6) or stop (0)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VestelAcCoordinator,
        api: VestelAcApi,
        entry_id: str,
        device: dict[str, str],
        axis: str,
        value: int,
        name: str,
        suffix: str,
    ) -> None:
        self._coordinator = coordinator
        self._api = api
        self._device_id = device["device_id"]
        self._axis = axis
        self._value = value
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{self._device_id}_{axis}_{suffix}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, self._device_id)})

    async def async_press(self) -> None:
        status = self._coordinator.data.get(self._device_id, {})
        current_raw = status.get("fanpo_raw", 0)
        kwargs = {self._axis: self._value}
        await self._api.async_set_fanpo(self._device_id, current_raw, **kwargs)
        await self._coordinator.async_request_refresh()
