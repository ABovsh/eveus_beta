"""Support for Eveus number entities with proper state persistence."""
from __future__ import annotations

import logging
import asyncio
import time
from typing import Any, Optional

from homeassistant.components.number import (
    NumberEntity,
    NumberMode,
    NumberDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback, State
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.const import (
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
    UnitOfElectricCurrent,
)

from .const import (
    DOMAIN,
    MODEL_MAX_CURRENT,
    MIN_CURRENT,
    CONF_MODEL,
)
from .common import BaseEveusEntity
from .utils import get_safe_value

_LOGGER = logging.getLogger(__name__)

class EveusNumberEntity(BaseEveusEntity, NumberEntity):
    """Base number entity for Eveus with proper state persistence."""
    
    _attr_has_entity_name = True
    _attr_should_poll = False
    
    def __init__(self, updater, device_number: int = 1) -> None:
        """Initialize the entity."""
        super().__init__(updater, device_number)
        
        # State management for persistence
        self._intended_value: Optional[float] = None  # What user set
        self._device_value: Optional[float] = None    # What device reports  
        self._pending_value: Optional[float] = None   # Value being set
        self._last_command_time = 0
        self._restore_attempted = False
        
    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        
    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


class EveusCurrentNumber(EveusNumberEntity):
    """Representation of Eveus current control with state persistence."""

    ENTITY_NAME = "Charging Current"
    _attr_native_step = 1.0
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_device_class = NumberDeviceClass.CURRENT
    _attr_icon = "mdi:current-ac"
    _attr_entity_category = EntityCategory.CONFIG
    _command = "currentSet"

    def __init__(self, updater, model: str, device_number: int = 1) -> None:
        """Initialize the current control."""
        super().__init__(updater, device_number)
        self._model = model
        self._command_lock = asyncio.Lock()
        
        # Set min/max values based on model
        self._attr_native_min_value = float(MIN_CURRENT)
        self._attr_native_max_value = float(MODEL_MAX_CURRENT[model])

    @property
    def native_value(self) -> float | None:
        """Return the current value - prioritize intended value."""
        # Priority: pending value > intended value > device value > fallback
        if self._pending_value is not None:
            return self._pending_value
        if self._intended_value is not None:
            return self._intended_value
        if self._device_value is not None:
            return self._device_value
            
        # Fallback to device data
        device_value = get_safe_value(self._updater.data, self._command)
        if device_value is not None:
            self._device_value = float(device_value)
            return self._device_value
            
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set new current value with proper state tracking."""
        async with self._command_lock:
            try:
                # Clamp value to valid range
                clamped_value = max(self._attr_native_min_value, 
                                  min(self._attr_native_max_value, value))
                int_value = int(clamped_value)
                
                # Set pending value
                self._pending_value = float(int_value)
                self.async_write_ha_state()
                
                # Send command
                success = await self._updater.send_command(self._command, int_value)
                
                if success:
                    # Command succeeded - update intended value
                    self._intended_value = float(int_value)
                    _LOGGER.debug("Successfully set %s to %dA", self.name, int_value)
                else:
                    # Command failed - keep previous intended value
                    _LOGGER.warning("Failed to set %s to %dA", self.name, int_value)
                    
            except Exception as err:
                _LOGGER.error("Failed to set current value: %s", err)
            finally:
                # Clear pending value
                self._pending_value = None
                self._last_command_time = time.time()
                self.async_write_ha_state()

    async def _async_restore_state(self, state: State) -> None:
        """Restore previous intended value."""
        try:
            if state and state.state not in (None, 'unknown', 'unavailable'):
                restored_value = float(state.state)
                
                # Validate restored value is in range
                if self._attr_native_min_value <= restored_value <= self._attr_native_max_value:
                    self._intended_value = restored_value
                    _LOGGER.debug("Restored %s intended value to %.1fA", self.name, restored_value)
                    
                    # Try to apply the restored value when device becomes available
                    self.hass.async_create_task(self._apply_restored_value(restored_value))
                else:
                    _LOGGER.warning("Restored value %.1fA for %s is out of range (%.1f-%.1f)", 
                                  restored_value, self.name, 
                                  self._attr_native_min_value, self._attr_native_max_value)
                    
        except (TypeError, ValueError) as err:
            _LOGGER.debug("Could not restore number state for %s: %s", self.name, err)

    async def _apply_restored_value(self, target_value: float) -> None:
        """Apply restored value when device becomes available."""
        # Wait a bit for device to be ready
        await asyncio.sleep(5)
        
        # Check if we should apply the restored value
        if not self._restore_attempted and self._intended_value is not None:
            self._restore_attempted = True
            
            # Only send command if device value differs significantly from intended value
            current_device_value = get_safe_value(self._updater.data, self._command, float)
            
            if (current_device_value is None or 
                abs(current_device_value - self._intended_value) > 0.5):
                _LOGGER.info("Applying restored current value for %s: %.1fA", 
                           self.name, self._intended_value)
                await self.async_set_native_value(self._intended_value)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Update device value from coordinator data
        if self._command in self._updater.data:
            new_device_value = get_safe_value(self._updater.data, self._command, float)
            
            if new_device_value is not None:
                # Only update if device value actually changed significantly
                if (self._device_value is None or 
                    abs(self._device_value - new_device_value) > 0.5):
                    self._device_value = new_device_value
                    
                    # If no command is pending and no intended value is set, sync with device
                    if self._pending_value is None and self._intended_value is None:
                        self._intended_value = new_device_value
                
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eveus number entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    updater = data.get("updater")
    device_number = data.get("device_number", 1)  # Default to 1 for backward compatibility
    
    if not updater:
        _LOGGER.error("No updater found in data")
        return
        
    model = entry.data.get(CONF_MODEL)
    if not model:
        _LOGGER.error("No model specified in config")
        return

    entities = [
        EveusCurrentNumber(updater, model, device_number),
    ]

    # Initialize entities dict if needed
    if "entities" not in data:
        data["entities"] = {}
    
    data["entities"]["number"] = {
        entity.unique_id: entity for entity in entities
    }

    async_add_entities(entities)
