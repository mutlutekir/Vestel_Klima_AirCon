"""Binary sensors for Vestel appliances that are not air conditioners.

Right now this is the fridge: the two doors decoded from ``RFDOORA`` plus
the modes decoded from ``RFMODEA`` and the two plain flags ``RFCLOCK``
(child lock) and ``RFSSAVE`` (screen saver). Everything here is read-only:
the fridge command format is still undocumented, so the integration cannot
toggle them (see the README for the reverse-engineering workflow).
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import VestelAcCoordinator, filter_fridge_devices
from .const import DOMAIN

# (unique_id suffix, entity name, key in the decoded status["fridge"] dict)
# Both doors are named explicitly so it is obvious which door is which.
_DOORS = (
    ("fridge_door", "Soğutucu Kapısı", "fridge_door_open"),
    ("freezer_door", "Dondurucu Kapısı", "freezer_door_open"),
)

# Read-only fridge flags/modes: (suffix, name, state key, raw key).
# RFMODEA is a bit field (holiday / eco / fast cool / fast freeze), while
# RFCLOCK and RFSSAVE are plain on/off fields.
_FLAGS = (
    ("fridge_fast_cool", "Hızlı Soğutma", "fast_cool", "mode_raw"),
    ("fridge_fast_freeze", "Hızlı Dondurma", "fast_freeze", "mode_raw"),
    ("fridge_holiday", "Tatil Modu", "holiday", "mode_raw"),
    ("fridge_eco", "Ekonomi Modu", "eco", "mode_raw"),
    ("fridge_child_lock", "Çocuk Kilidi", "child_lock", "child_lock_raw"),
    ("fridge_screen_saver", "Ekran Koruyucu", "screen_saver", "screen_saver_raw"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    stored = hass.data[DOMAIN][entry.entry_id]
    coordinator: VestelAcCoordinator = stored["coordinator"]

    # Fridges carry the RF* fields; an AC never does. Gating on the fridge
    # filter keeps this platform inert for accounts with only air
    # conditioners.
    entities: list[BinarySensorEntity] = []
    for device in filter_fridge_devices(stored):
        for suffix, name, key in _DOORS:
            entities.append(
                _VestelFridgeBinarySensor(
                    coordinator, entry.entry_id, device, suffix, name, key,
                    raw_key="door_raw", device_class=BinarySensorDeviceClass.DOOR,
                )
            )
        for suffix, name, key, raw_key in _FLAGS:
            entities.append(
                _VestelFridgeBinarySensor(
                    coordinator, entry.entry_id, device, suffix, name, key,
                    raw_key=raw_key,
                )
            )

    async_add_entities(entities)


class _VestelFridgeBinarySensor(
    CoordinatorEntity[VestelAcCoordinator], BinarySensorEntity
):
    """One decoded fridge boolean (a door, or a mode/flag).

    ``state_key`` points into the decoded ``status["fridge"]`` dict, so a
    missing/unparseable field yields ``None`` -> "unknown" in HA rather
    than a wrong "off".
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VestelAcCoordinator,
        entry_id: str,
        device: dict[str, str],
        suffix: str,
        name: str,
        state_key: str,
        raw_key: str,
        device_class: BinarySensorDeviceClass | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device["device_id"]
        self._state_key = state_key
        self._raw_key = raw_key
        self._attr_name = name
        self._attr_device_class = device_class
        self._attr_unique_id = f"{entry_id}_{self._device_id}_{suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer="Vestel",
            name=device.get("device_name", self._device_id),
            model="Buzdolabı",
        )
        self._entry_id = entry_id

    @property
    def _fridge(self) -> dict[str, Any]:
        status = self.coordinator.data.get(self._device_id, {})
        fridge = status.get("fridge")
        return fridge if isinstance(fridge, dict) else {}

    @property
    def is_on(self) -> bool | None:
        return self._fridge.get(self._state_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # Keep the raw cloud value visible so further states (once more of
        # them are observed) can be interpreted without guessing.
        return {"ham_deger": self._fridge.get(self._raw_key)}
