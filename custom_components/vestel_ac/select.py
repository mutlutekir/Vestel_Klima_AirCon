"""Select platform: vertical/horizontal louver position control.

Confirmed against real device captures (see README): the louver field is a
single 0-6 value where 0 = durdur (stop/fixed at last position), 1-5 = sabit
kademe (fixed step, 1=en yatay/açık .. 5=en dik), 6 = salınım (continuous
swing). Horizontal uses the identical 0-6 encoding in the adjacent bits of
the same ACFANPO register, but - unlike vertical - it wasn't independently
exercised in testing, so its behavior is inferred by symmetry rather than
confirmed.
"""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import VestelAcCoordinator
from .api import VestelAcApi
from .const import DOMAIN, LOUVER_OPTION_NAMES, LOUVER_OPTIONS


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    stored = hass.data[DOMAIN][entry.entry_id]
    coordinator: VestelAcCoordinator = stored["coordinator"]
    api: VestelAcApi = stored["api"]
    devices: list[dict[str, str]] = stored["devices"]

    entities: list[SelectEntity] = []
    for device in devices:
        entities.append(
            _VestelAcLouverSelect(
                coordinator, api, entry.entry_id, device, axis="vertical", name="Dikey Kanatçık"
            )
        )
        entities.append(
            _VestelAcLouverSelect(
                coordinator, api, entry.entry_id, device, axis="horizontal", name="Yatay Kanatçık"
            )
        )
    async_add_entities(entities)


class _VestelAcLouverSelect(CoordinatorEntity[VestelAcCoordinator], SelectEntity):
    """A single louver axis (vertical or horizontal), 0-6 as a dropdown."""

    _attr_has_entity_name = True
    _attr_options = list(LOUVER_OPTIONS.keys())

    def __init__(
        self,
        coordinator: VestelAcCoordinator,
        api: VestelAcApi,
        entry_id: str,
        device: dict[str, str],
        axis: str,
        name: str,
    ) -> None:
        super().__init__(coordinator)
        self._api = api
        self._device_id = device["device_id"]
        self._axis = axis  # "vertical" or "horizontal"
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{self._device_id}_{axis}_louver"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, self._device_id)})

    @property
    def current_option(self) -> str | None:
        status = self.coordinator.data.get(self._device_id, {})
        value = status.get(self._axis)
        if value is None:
            return None
        return LOUVER_OPTION_NAMES.get(value, "durdur")

    async def async_select_option(self, option: str) -> None:
        status = self.coordinator.data.get(self._device_id, {})
        current_raw = status.get("fanpo_raw", 0)
        value = LOUVER_OPTIONS[option]
        kwargs = {self._axis: value}
        await self._api.async_set_fanpo(self._device_id, current_raw, **kwargs)
        await self.coordinator.async_request_refresh()
