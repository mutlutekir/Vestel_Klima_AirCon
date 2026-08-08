"""Climate platform for the Vestel Klima AirCon integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import VestelAcCoordinator
from .api import VestelAcApi
from .const import DOMAIN, LOCAL_DEVICE_PICTURE, MAX_TEMP, MIN_TEMP

HVAC_TO_VESTEL = {
    HVACMode.AUTO: "auto",
    HVACMode.COOL: "cool",
    HVACMode.DRY: "dry",
    HVACMode.FAN_ONLY: "fan",
    HVACMode.HEAT: "heat",
}
VESTEL_TO_HVAC = {v: k for k, v in HVAC_TO_VESTEL.items()}

FAN_MODES = ["auto", "fan1", "fan2", "fan3", "fan4", "fan5"]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    stored = hass.data[DOMAIN][entry.entry_id]
    coordinator: VestelAcCoordinator = stored["coordinator"]
    api: VestelAcApi = stored["api"]
    devices: list[dict[str, str]] = stored["devices"]

    entities = [
        VestelAcClimateEntity(coordinator, api, entry.entry_id, device)
        for device in devices
    ]
    async_add_entities(entities)


class VestelAcClimateEntity(CoordinatorEntity[VestelAcCoordinator], ClimateEntity):
    """Represents a single Vestel air conditioner."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_target_temperature_step = 1
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.AUTO,
        HVACMode.COOL,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
        HVACMode.HEAT,
    ]
    _attr_fan_modes = FAN_MODES
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

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
        self._attr_unique_id = f"{entry_id}_{self._device_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer="Vestel",
            name=device.get("device_name", self._device_id),
            model="Smart AC (WiFi)",
        )

    @property
    def _status(self) -> dict[str, Any]:
        return self.coordinator.data.get(self._device_id, {})

    @property
    def entity_picture(self) -> str | None:
        # Points at a file YOU place under <ha config>/www/vestel_ac/ -
        # see README "Cihaz fotoğrafı ekleme". Nothing is bundled here.
        return LOCAL_DEVICE_PICTURE

    @property
    def current_temperature(self) -> float | None:
        return self._status.get("room_temp")

    @property
    def target_temperature(self) -> float | None:
        return self._status.get("temp")

    @property
    def hvac_mode(self) -> HVACMode:
        if not self._status.get("on", False):
            return HVACMode.OFF
        return VESTEL_TO_HVAC.get(self._status.get("mode"), HVACMode.COOL)

    @property
    def fan_mode(self) -> str | None:
        return self._status.get("fan", "auto")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # Full unparsed status from Vestel's API - see api.py's
        # async_get_status() docstring-comment. Open this entity's
        # attributes (Ayarlar > Cihazlar ve Hizmetler > entity, or
        # Geliştirici Araçları > Durumlar on desktop) before/after pressing
        # a button in the official app (swing, volume/buzzer, sleep, ...)
        # to spot which raw field changed.
        return {"raw_status": self._status.get("raw", {})}

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self._api.async_send_command(self._device_id, "off", mode="off", fan="auto")
        else:
            mode = HVAC_TO_VESTEL.get(hvac_mode, "cool")
            fan = self.fan_mode or "auto"
            await self._api.async_send_command(
                self._device_id, "mode", mode=mode, fan=fan
            )
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        mode = HVAC_TO_VESTEL.get(self.hvac_mode, "cool")
        fan = self.fan_mode or "auto"
        await self._api.async_send_command(self._device_id, "on", mode=mode, fan=fan)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        await self._api.async_send_command(self._device_id, "off", mode="off", fan="auto")
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        # Mirrors the reference API: mode/fan/temp changes are rejected
        # server-side context wise while the unit is off (ACGENSI's mode
        # field would otherwise get clobbered) - the original web UI blocks
        # this client-side, so we do the same rather than send a command
        # that would silently do nothing useful.
        if not self._status.get("on", False):
            raise HomeAssistantError(
                "Klima kapalıyken sıcaklık değiştirilemez. Önce klimayı açın."
            )
        await self._api.async_send_command(self._device_id, "temp", temp=temp)
        await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        if not self._status.get("on", False):
            raise HomeAssistantError(
                "Klima kapalıyken fan hızı değiştirilemez. Önce klimayı açın."
            )
        # Use the current mode (not a hardcoded fallback) since ACGENSI
        # encodes mode+fan together - sending the wrong mode here would
        # silently switch cool/dry/heat as a side effect of a fan change.
        mode = self._status.get("mode", "cool")
        await self._api.async_send_command(
            self._device_id, "fan", mode=mode, fan=fan_mode
        )
        await self.coordinator.async_request_refresh()
