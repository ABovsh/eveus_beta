"""Support for Eveus number entities."""
from typing import Optional
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.helpers.entity import EntityCategory
from homeassistant.const import UnitOfElectricCurrent
from .const import DOMAIN, MODEL_MAX_CURRENT, MIN_CURRENT

class EveusCurrentNumber(NumberEntity):
    _attr_native_step = 1.0
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_device_class = NumberDeviceClass.CURRENT
    _attr_has_entity_name = True
    _attr_name = "Charging Current"
    _attr_icon = "mdi:current-ac"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, client) -> None:
        self._client = client
        self._client.register_entity(self)
        self._attr_unique_id = f"{client._device_info.identifier}_charging_current"
        self._attr_native_min_value = float(MIN_CURRENT)
        self._attr_native_max_value = float(MODEL_MAX_CURRENT[client._device_info.model])

    @property
    def available(self) -> bool:
        return self._client.available

    @property
    def native_value(self) -> Optional[float]:
        return float(self._client.state.current_set) if self._client.state else None

    async def async_set_native_value(self, value: float) -> None:
        await self._client.send_command("currentSet", int(value))

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._client._device_info.identifier)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": f"Eveus ({self._client._device_info.host})",
        }

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    client = hass.data[DOMAIN][entry.entry_id]["client"]
    async_add_entities([EveusCurrentNumber(client)])
