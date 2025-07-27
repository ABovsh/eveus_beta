"""Base entity classes for Eveus integration with stable offline handling."""
import logging
import time
from typing import Any, Optional

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import EntityCategory

from .utils import get_device_info, get_device_suffix

_LOGGER = logging.getLogger(__name__)

class BaseEveusEntity(RestoreEntity, Entity):
    """Base implementation for Eveus entities with stable offline handling."""

    ENTITY_NAME: str = None
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, updater, device_number: int = 1) -> None:
        """Initialize the entity."""
        super().__init__()
        self._updater = updater
        self._device_number = device_number
        self._updater.register_entity(self)
        
        # Offline handling
        self._last_available_log = 0
        self._availability_log_interval = 600  # Log availability changes max every 10 minutes
        self._last_known_available = True

        if self.ENTITY_NAME is None:
            raise NotImplementedError("ENTITY_NAME must be defined in child class")

        self._attr_name = self.ENTITY_NAME
        
        # Generate unique ID with device suffix for multi-device support
        device_suffix = get_device_suffix(device_number)
        entity_key = self.ENTITY_NAME.lower().replace(' ', '_')
        self._attr_unique_id = f"eveus{device_suffix}_{entity_key}"

    @property
    def available(self) -> bool:
        """Return if entity is available with quiet offline handling."""
        current_available = self._updater.available
        
        # Only log availability changes occasionally to reduce noise
        if current_available != self._last_known_available:
            current_time = time.time()
            if current_time - self._last_available_log > self._availability_log_interval:
                self._last_available_log = current_time
                if not current_available:
                    _LOGGER.debug("Entity %s became unavailable (device offline)", self.unique_id)
                else:
                    _LOGGER.debug("Entity %s became available (device online)", self.unique_id)
            self._last_known_available = current_available
        
        return current_available

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        try:
            return get_device_info(self._updater.host, self._updater.data, self._device_number)
        except Exception as err:
            # Gracefully handle device info errors when offline
            _LOGGER.debug("Error getting device info for %s: %s", self.unique_id, err)
            # Return minimal device info when offline
            device_suffix = "" if self._device_number == 1 else f" {self._device_number}"
            return {
                "identifiers": {("eveus", f"{self._updater.host}_{self._device_number}")},
                "name": f"Eveus EV Charger{device_suffix}",
                "manufacturer": "Eveus",
                "model": "Eveus EV Charger",
            }

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        
        # Restore previous state if available
        try:
            state = await self.async_get_last_state()
            if state:
                await self._async_restore_state(state)
        except Exception as err:
            # Gracefully handle restore errors
            _LOGGER.debug("Could not restore state for %s: %s", self.unique_id, err)
            
        # Start updates if needed
        try:
            await self._updater.async_start_updates()
        except Exception as err:
            # Don't fail entity setup if updater has issues
            _LOGGER.debug("Could not start updates for %s: %s", self.unique_id, err)

    async def _async_restore_state(self, state) -> None:
        """Restore previous state - overridden by child classes."""
        pass

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        try:
            self.async_write_ha_state()
        except Exception as err:
            # Gracefully handle state write errors (device might be offline)
            _LOGGER.debug("Could not write state for %s: %s", self.unique_id, err)


class EveusSensorBase(BaseEveusEntity, SensorEntity):
    """Base sensor entity for Eveus with stable handling."""
    
    def __init__(self, updater: "EveusUpdater", device_number: int = 1) -> None:
        """Initialize the sensor."""
        super().__init__(updater, device_number)
        self._attr_native_value = None
        self._last_valid_value = None
        self._last_error_log = 0
        self._error_log_interval = 300  # Log errors max every 5 minutes

    @property
    def native_value(self) -> Any:
        """Return sensor value with graceful error handling."""
        try:
            value = self._get_sensor_value()
            if value is not None:
                self._last_valid_value = value
            return value
        except Exception as err:
            # Log errors occasionally, return last known value
            current_time = time.time()
            if current_time - self._last_error_log > self._error_log_interval:
                self._last_error_log = current_time
                _LOGGER.debug("Error getting sensor value for %s: %s", self.unique_id, err)
            return self._last_valid_value

    def _get_sensor_value(self) -> Any:
        """Get sensor value - to be overridden by subclasses."""
        return self._attr_native_value


class EveusDiagnosticSensor(EveusSensorBase):
    """Base diagnostic sensor with stable handling."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:information"
