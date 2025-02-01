"""Platform for Eveus number entities."""
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.number import (
    NumberEntity,
    NumberMode,
    NumberDeviceClass,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.const import UnitOfElectricCurrent

from .const import DOMAIN, MODEL_MAX_CURRENT, MIN_CURRENT

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Eveus number based on a config entry."""
    client = hass.data[DOMAIN][entry.entry_id]["client"]
    async_add_entities([EveusCurrentNumber(client)])

class EveusCurrentNumber(NumberEntity):
    """Representation of Eveus current control."""

    _attr_native_step = 1.0
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_device_class = NumberDeviceClass.CURRENT
    _attr_has_entity_name = True
    _attr_name = "Charging Current"
    _attr_icon = "mdi:current-ac"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, client) -> None:
        """Initialize the current control."""
        self._client = client
        self._client.register_entity(self)
        self._attr_unique_id = f"{client._device_info.identifier}_charging_current"
        
        # Set min/max values based on model
        self._attr_native_min_value = float(MIN_CURRENT)
        self._attr_native_max_value = float(MODEL_MAX_CURRENT[client._device_info.model])

    @property
    def native_value(self) -> float:
        """Return the current value."""
        if not self._client.state:
            return self._attr_native_min_value
        return float(self._client.state.current_set)

    async def async_set_native_value(self, value: float) -> None:
        """Set new current value."""
        value = int(min(self._attr_native_max_value, max(self._attr_native_min_value, value)))
        await self._client.send_command("currentSet", value)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._client.available
