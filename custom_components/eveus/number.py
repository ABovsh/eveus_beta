"""Support for Eveus number entities."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MIN_CURRENT, MODEL_MAX_CURRENT
from .common import BaseEveusEntity, EveusUpdater, send_eveus_command

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eveus number platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    updater = data["updater"]
    model = entry.data.get("model", "16A")

    entities = [
        EveusCurrentLimitNumber(updater, model),
        EveusEnergyLimitNumber(updater),
        EveusCostLimitNumber(updater)
    ]

    async_add_entities(entities)

class EveusNumberEntity(BaseEveusEntity, NumberEntity):
    """Base number entity for Eveus."""
    
    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the entity."""
        super().__init__(updater)
        self._attr_native_value = None

class EveusCurrentNumber(EveusNumberEntity):
    """Representation of Eveus current control."""

    ENTITY_NAME = "Charging Current"
    _attr_native_step = 1.0
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_device_class = NumberDeviceClass.CURRENT
    _attr_icon = "mdi:current-ac"
    _attr_entity_category = EntityCategory.CONFIG
    _state_key = "currentSet"

    def __init__(self, updater: EveusUpdater, model: str) -> None:
        """Initialize the current control."""
        super().__init__(updater)
        self._model = model
        
        # Set min/max values based on model
        self._attr_native_min_value = float(MIN_CURRENT)
        self._attr_native_max_value = float(MODEL_MAX_CURRENT[model])
        self._attr_native_value = min(self._attr_native_max_value, 16.0)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        try:
            value = self._updater.data.get(self._state_key)
            if value is not None:
                new_value = float(value)
                if new_value != self._attr_native_value:
                    self._attr_native_value = new_value
                    self.async_write_ha_state()
        except (TypeError, ValueError) as err:
            _LOGGER.error("Error updating current value: %s", err)

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        try:
            value = self._updater.data.get(self._state_key)
            if value is not None:
                self._attr_native_value = float(value)
            return self._attr_native_value
        except (TypeError, ValueError) as err:
            _LOGGER.error("Error getting current value: %s", err)
            return self._attr_native_value

    async def async_set_native_value(self, value: float) -> None:
        """Set new current value."""
        try:
            value = int(min(self._attr_native_max_value, max(self._attr_native_min_value, value)))
            
            if await self._updater.send_command(self._state_key, value):
                self._attr_native_value = float(value)
                self.async_write_ha_state()
            else:
                _LOGGER.error("Failed to set current value to %s", value)
                
        except (TypeError, ValueError, ConnectionError, TimeoutError) as err:
            _LOGGER.error("Error setting current value: %s", err)

    async def _async_restore_state(self, state) -> None:
        """Restore previous state."""
        try:
            restored_value = float(state.state)
            if self._attr_native_min_value <= restored_value <= self._attr_native_max_value:
                self._attr_native_value = restored_value
        except (TypeError, ValueError) as err:
            _LOGGER.error("Error restoring current value: %s", err)
            
async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eveus number entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    updater = data["updater"]
    model = entry.data[CONF_MODEL]

    entities = [
        EveusCurrentNumber(updater, model),
    ]

    # Initialize entities dict if needed
    if "entities" not in data:
        data["entities"] = {}
    
    data["entities"]["number"] = {
        entity.unique_id: entity for entity in entities
    }

    async_add_entities(entities)
