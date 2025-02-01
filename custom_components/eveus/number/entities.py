"""Support for Eveus number entities."""
from typing import Any

from homeassistant.components.number import (
    NumberEntity,
    NumberMode,
    NumberDeviceClass,
    RestoreNumber,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.const import UnitOfElectricCurrent

from ..api.client import EveusClient
from ..const import DOMAIN, MODEL_MAX_CURRENT, MIN_CURRENT

class EveusCurrentNumber(RestoreNumber):
    """Representation of Eveus current control."""

    _attr_native_step = 1.0
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_device_class = NumberDeviceClass.CURRENT
    _attr_has_entity_name = True
    _attr_name = "Charging Current"
    _attr_icon = "mdi:current-ac"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, client: EveusClient) -> None:
        """Initialize the current control."""
        super().__init__()
        self._client = client
        self._attr_unique_id = f"{client._device_info.identifier}_charging_current"
        
        # Set min/max values based on model
        self._attr_native_min_value = float(MIN_CURRENT)
        self._attr_native_max_value = float(MODEL_MAX_CURRENT[client._device_info.model])
        self._value = min(self._attr_native_max_value, 16.0)

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        return self._value

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._client._device_info.identifier)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": f"Eveus ({self._client._device_info.host})",
        }

    async def async_set_native_value(self, value: float) -> None:
        """Set new current value."""
        value = int(min(self._attr_native_max_value, max(self._attr_native_min_value, value)))
        await self._client.send_command("currentSet", value)
        self._value = float(value)

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state and state.state not in ('unknown', 'unavailable'):
            try:
                restored_value = float(state.state)
                if self._attr_native_min_value <= restored_value <= self._attr_native_max_value:
                    self._value = restored_value
            except (TypeError, ValueError):
                pass
