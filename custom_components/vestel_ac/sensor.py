"""Sensor platform for Vestel AC diagnostics and air-quality data."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import VestelAcCoordinator
from .api import fridge_temp_display
from .const import DOMAIN

# Numeric PM2.5 / TVOC fields are not present on every Vestel AC model.
# If the cloud status contains any of these aliases, the corresponding
# sensor exposes the raw numeric value. We deliberately do not turn
# ACPOLPM/ACPOLVC into fake numeric concentrations: those are quality grades.
PM25_KEYS = ("ACPM25", "PM25", "PM2_5", "PM2.5", "ACPM2_5", "ACPM2.5")
TVOC_KEYS = ("ACTVOC", "TVOC", "ACVOC", "VOC_PPB", "ACTVOCVALUE")

ERROR_BITS = {
    0: "Bilgi",
    1: "İlk POE",
    2: "Oda sıcaklık sensörü",
    3: "Serpantin sıcaklık sensörü",
    4: "Fan motoru",
    5: "Gaz kaçağı",
    6: "Dış ortam sıcaklık sensörü",
    7: "Deşarj sıcaklık sensörü",
    8: "Dış ünite boru sıcaklığı",
    9: "Haberleşme",
    10: "Trip F",
    11: "IGBT NTC",
    12: "POE",
    13: "VBUS",
    14: "Kompresör kablosu",
    15: "Dış BLDC takometre",
}

ERRTW_BITS = {
    0: "UVC",
    1: "Partikül sensörü",
}


def _raw_value(status: dict[str, Any], key: str) -> Any:
    raw = status.get("raw", {})
    if not isinstance(raw, dict):
        return None
    return raw.get(key)


def _find_key(status: dict[str, Any], aliases: tuple[str, ...]) -> str | None:
    raw = status.get("raw", {})
    if not isinstance(raw, dict):
        return None
    upper = {str(k).upper(): str(k) for k in raw}
    for alias in aliases:
        if alias.upper() in upper:
            return upper[alias.upper()]
    return None


def _number(value: Any) -> int | float | None:
    if value is None:
        return None
    try:
        text = str(value).strip()
        if "." in text:
            return float(text)
        return int(text)
    except (TypeError, ValueError):
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    stored = hass.data[DOMAIN][entry.entry_id]
    coordinator: VestelAcCoordinator = stored["coordinator"]
    devices: list[dict[str, str]] = stored["devices"]

    entities: list[SensorEntity] = []

    for device in devices:
        device_id = device["device_id"]
        status = coordinator.data.get(device_id, {})
        is_ac = status.get("is_ac", False)

        # AC-specific known sensors: the fields and names below only make
        # sense for air conditioners. Other appliance types (e.g. fridges)
        # are covered by the raw sensors at the bottom of this loop.
        # Fridge setpoints decoded from RFTEMSE (cooler high byte, freezer
        # low byte) - plain temperature sensors rather than diagnostics, so
        # they can be charted and automated on.
        if status.get("is_fridge"):
            entities.extend(
                [
                    _VestelFridgeTempSensor(
                        coordinator, entry.entry_id, device,
                        "cooler", "Soğutucu Sıcaklığı", "fridge_cooler_temp",
                    ),
                    _VestelFridgeTempSensor(
                        coordinator, entry.entry_id, device,
                        "freezer", "Dondurucu Sıcaklığı", "fridge_freezer_temp",
                    ),
                ]
            )

        if is_ac:
            entities.extend(
                [
                    _VestelKnownSensor(coordinator, entry.entry_id, device, "ACROOTE",
                                       "Klima Oda Sıcaklığı", "°C", "room_temp"),
                    _VestelKnownSensor(coordinator, entry.entry_id, device, "ACPOLPM",
                                       "PM2.5 Hava Kalitesi", None, "pm_quality"),
                    _VestelKnownSensor(coordinator, entry.entry_id, device, "ACPOLVC",
                                       "VOC Hava Kalitesi", None, "voc_quality"),
                    _VestelKnownSensor(coordinator, entry.entry_id, device, "ACOAFLP",
                                       "Koku/Alerjen Filtre Ömrü", PERCENTAGE, "odor_filter"),
                    _VestelKnownSensor(coordinator, entry.entry_id, device, "ACPSCLP",
                                       "Partikül Sensörü Temizleme Ömrü", PERCENTAGE, "particle_filter"),
                    _VestelKnownSensor(coordinator, entry.entry_id, device, "ACERROR",
                                       "Klima Hata Kodu", None, "ac_error"),
                    _VestelKnownSensor(coordinator, entry.entry_id, device, "ACERRTW",
                                       "Klima İkinci Hata Kodu", None, "ac_error2"),
                    _VestelKnownSensor(coordinator, entry.entry_id, device, "ACWARNG",
                                       "Klima Uyarı Kodu", None, "warning"),
                    _VestelKnownSensor(coordinator, entry.entry_id, device, "CONNRSS",
                                       "Bağlantı RSSI", "dBm", "conn_rssi"),
                    _VestelKnownSensor(coordinator, entry.entry_id, device, "WIFIRSS",
                                       "Wi-Fi RSSI", None, "wifi_rssi"),
                    _VestelKnownSensor(coordinator, entry.entry_id, device, "ACVERSI",
                                       "Klima Yazılım Versiyonu", None, "version"),
                ]
            )

            # Numeric PM2.5 / TVOC: unavailable if this particular model/API
            # does not publish a numeric field. ACPOLPM/ACPOLVC remain quality
            # classification sensors above.
            entities.append(
                _VestelAliasSensor(
                    coordinator, entry.entry_id, device,
                    "pm25", "PM2.5", PM25_KEYS, "µg/m³",
                )
            )
            entities.append(
                _VestelAliasSensor(
                    coordinator, entry.entry_id, device,
                    "tvoc", "TVOC", TVOC_KEYS, "ppb",
                )
            )

            # Individual diagnostic bits from ACERROR / ACERRTW.
            for bit, label in ERROR_BITS.items():
                entities.append(
                    _VestelErrorBitSensor(
                        coordinator, entry.entry_id, device,
                        source="ACERROR", bit=bit, label=label,
                    )
                )
            for bit, label in ERRTW_BITS.items():
                entities.append(
                    _VestelErrorBitSensor(
                        coordinator, entry.entry_id, device,
                        source="ACERRTW", bit=bit, label=label,
                    )
                )

        # Every field returned by the cloud is also exposed as a raw
        # diagnostic sensor - for every appliance type, not just ACs. This
        # is intentional for reverse engineering: when you press a new
        # function in the official app (also on fridges), its changing
        # value immediately becomes visible in HA.
        raw = status.get("raw", {})
        if isinstance(raw, dict):
            for key in raw:
                entities.append(
                    _VestelRawSensor(
                        coordinator, entry.entry_id, device, str(key)
                    )
                )

    async_add_entities(entities)


class _VestelBaseSensor(CoordinatorEntity[VestelAcCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: VestelAcCoordinator,
        entry_id: str,
        device: dict[str, str],
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device["device_id"]
        # The same base sensor serves ACs and non-AC appliances (fridges get
        # the raw RF* fields). Label the device honestly instead of calling
        # every appliance "Smart AC (WiFi)".
        status = coordinator.data.get(self._device_id, {})
        model = "Buzdolabı" if status.get("is_fridge") else "Smart AC (WiFi)"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer="Vestel",
            name=device.get("device_name", self._device_id),
            model=model,
        )
        self._entry_id = entry_id


class _VestelKnownSensor(_VestelBaseSensor):
    def __init__(
        self, coordinator, entry_id, device, key, name, unit, kind
    ) -> None:
        super().__init__(coordinator, entry_id, device)
        self._key = key
        self._kind = kind
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{device['device_id']}_diag_{kind}"
        if unit:
            self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self) -> Any:
        status = self.coordinator.data.get(self._device_id, {})
        if self._key == "ACROOTE":
            return status.get("room_temp")
        value = _raw_value(status, self._key)
        if value is None:
            return None
        if self._kind in {"pm_quality", "voc_quality"}:
            mapping = {
                "pm_quality": {0: "Temiz", 1: "Orta", 2: "Kirli"},
                "voc_quality": {0: "İyi", 1: "Orta", 2: "Kötü"},
            }
            n = _number(value)
            return mapping[self._kind].get(n, str(value))
        if self._kind in {"odor_filter", "particle_filter"}:
            return _number(value)
        if self._kind in {"conn_rssi"}:
            return _number(value)
        return value


class _VestelFridgeTempSensor(_VestelBaseSensor):
    """A decoded fridge setpoint (cooler or freezer), from RFTEMSE.

    Normally the value is a plain °C number. Two modes change what the
    fridge's own panel shows, and we mirror them:

    * eco mode on -> the panel shows ``E`` for **both** setpoints, so the
      state becomes the string ``"E"``;
    * holiday mode on -> the cooler is switched off, so there is no cooler
      reading at all (``unknown``/``--``) while the freezer keeps its
      setpoint.

    When the state is not a number the temperature device class, unit and
    state class are dropped, so Home Assistant never tries to parse ``E``
    as a temperature.
    """

    # Unlike the raw diagnostic sensors this is a normal reading entity.
    _attr_entity_category = None

    def __init__(
        self, coordinator, entry_id, device, which, name, suffix
    ) -> None:
        super().__init__(coordinator, entry_id, device)
        self._which = which
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{device['device_id']}_{suffix}"

    @property
    def _fridge(self) -> dict[str, Any]:
        status = self.coordinator.data.get(self._device_id, {})
        fridge = status.get("fridge")
        return fridge if isinstance(fridge, dict) else {}

    @property
    def native_value(self) -> int | str | None:
        return fridge_temp_display(self._fridge, self._which)

    @property
    def _is_numeric(self) -> bool:
        return isinstance(self.native_value, (int, float))

    @property
    def device_class(self) -> SensorDeviceClass | None:
        return SensorDeviceClass.TEMPERATURE if self._is_numeric else None

    @property
    def native_unit_of_measurement(self) -> str | None:
        return UnitOfTemperature.CELSIUS if self._is_numeric else None

    @property
    def state_class(self) -> SensorStateClass | None:
        return SensorStateClass.MEASUREMENT if self._is_numeric else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # Keep the undecoded RFTEMSE value visible next to the decoded °C,
        # plus the two mode flags that override what is shown.
        fridge = self._fridge
        return {
            "ham_deger": fridge.get("temp_raw"),
            "tatil_modu": fridge.get("holiday"),
            "ekonomi_modu": fridge.get("eco"),
        }


class _VestelAliasSensor(_VestelBaseSensor):
    def __init__(
        self, coordinator, entry_id, device, key, name, aliases, unit
    ) -> None:
        super().__init__(coordinator, entry_id, device)
        self._aliases = aliases
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{device['device_id']}_{key}"
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self) -> int | float | None:
        status = self.coordinator.data.get(self._device_id, {})
        key = _find_key(status, self._aliases)
        return _number(_raw_value(status, key)) if key else None


class _VestelErrorBitSensor(_VestelBaseSensor):
    def __init__(
        self, coordinator, entry_id, device, source, bit, label
    ) -> None:
        super().__init__(coordinator, entry_id, device)
        self._source = source
        self._bit = bit
        self._attr_name = f"Hata - {label}"
        self._attr_unique_id = (
            f"{entry_id}_{device['device_id']}_{source.lower()}_bit_{bit}"
        )

    @property
    def native_value(self) -> int:
        status = self.coordinator.data.get(self._device_id, {})
        value = _number(_raw_value(status, self._source)) or 0
        return 1 if (int(value) & (1 << self._bit)) else 0


class _VestelRawSensor(_VestelBaseSensor):
    def __init__(self, coordinator, entry_id, device, key) -> None:
        super().__init__(coordinator, entry_id, device)
        self._key = key
        self._attr_name = f"Ham {key}"
        self._attr_unique_id = f"{entry_id}_{device['device_id']}_raw_{key.lower()}"

    @property
    def native_value(self) -> Any:
        return _raw_value(
            self.coordinator.data.get(self._device_id, {}), self._key
        )
