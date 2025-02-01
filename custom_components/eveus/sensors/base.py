"""Base sensor implementation."""
from typing import Any, Optional

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.helpers.restore_state import RestoreEntity

from ..const import DOMAIN

class BaseEveusSensor(SensorEntity, RestoreEntity):
    """Base implementation for Eveus sensors."""

    def __init__(self, client) -> None:
        """Initialize the sensor."""
        self._client = client
        self._client.register_entity(self)
        self._previous_value = None
        self._attr_should_poll = False
        self._attr_has_entity_name = True
    
    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._client._device_info.identifier)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": f"Eveus ({self._client._device_info.host})",
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._client.available

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state and state.state not in ('unknown', 'unavailable'):
            try:
                if hasattr(self, '_attr_suggested_display_precision'):
                    self._previous_value = float(state.state)
                else:
                    self._previous_value = state.state
            except (TypeError, ValueError):
                self._previous_value = state.state

class BaseNumericSensor(BaseEveusSensor):
    """Base numeric sensor with suggested precision."""
    
    _attr_suggested_display_precision = 2

    @property
    def native_value(self) -> Optional[float]:
        """Return the sensor value."""
        if not self._client.state:
            return self._previous_value
            
        try:
            value = self.get_value_from_state()
            self._previous_value = value
            return round(value, self._attr_suggested_display_precision)
        except (TypeError, ValueError):
            return self._previous_value
            
    def get_value_from_state(self) -> float:
        """Get value from device state."""
        raise NotImplementedError
