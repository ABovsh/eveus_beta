"""Base entity classes for Eveus integration."""
from typing import Any, Optional

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import EntityCategory

from .utils import get_device_info, get_device_suffix

class BaseEveusEntity(RestoreEntity, Entity):
    """Base implementation for Eveus entities."""

    ENTITY_NAME: str = None
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, updater, device_number: int = 1) -> None:
        """Initialize the entity."""
        super().__init__()
        self._updater = updater
        self._device_number = device_number
        self._updater.register_entity(self)

        if self.ENTITY_NAME is None:
            raise NotImplementedError("ENTITY_NAME must be defined in child class")

        self._attr_name = self.ENTITY_NAME
        
        # Generate unique ID with device suffix for multi-device support
        device_suffix = get_device_suffix(device_number)
        entity_key = self.ENTITY_NAME.lower().replace(' ', '_')
        self._attr_unique_id = f"eveus{device_suffix}_{entity_key}"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._updater.available

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return get_device_info(self._updater.host, self._updater.data, self._device_number)

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        
        # Restore previous state if available
        state = await self.async_get_last_state()
        if state:
            await self._async_restore_state(state)
            
        # Start updates if needed
        await self._updater.async_start_updates()

    async def _async_restore_state(self, state) -> None:
        """Restore previous state - overridden by child classes."""
        pass

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


class EveusSensorBase(BaseEveusEntity, SensorEntity):
    """Base sensor entity for Eveus."""
    
    def __init__(self, updater: "EveusUpdater", device_number: int = 1) -> None:
        """Initialize the sensor."""
        super().__init__(updater, device_number)
        self._attr_native_value = None

    @property
    def native_value(self) -> Any:
        """Return sensor value."""
        return self._attr_native_value


class EveusDiagnosticSensor(EveusSensorBase):
    """Base diagnostic sensor."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:information"
