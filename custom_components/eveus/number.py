"""Support for Eveus number entities."""
from __future__ import annotations

import logging
import asyncio
from typing import Any

from homeassistant.components.number import (
    NumberEntity,
    NumberMode,
    NumberDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.const import (
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
    UnitOfElectricCurrent,
    UnitOfTime,
)

from .const import (
    DOMAIN,
    MODEL_MAX_CURRENT,
    MIN_CURRENT,
    CONF_MODEL,
    RATE_COMMANDS,
)
from .common import (
    BaseEveusEntity,
    EveusUpdater,
)
from .utils import get_safe_value

_LOGGER = logging.getLogger(__name__)

class EveusNumberEntity(BaseEveusEntity, NumberEntity):
    """Base number entity for Eveus."""
    
    _attr_has_entity_name = True
    _attr_should_poll = False
    
    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the entity."""
        super().__init__(updater)
        self._attr_native_value = None
        
    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state:
            await self._async_restore_state(state)
        
    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

class EveusCurrentNumber(EveusNumberEntity):
    """Representation of Eveus current control."""

    ENTITY_NAME = "Charging Current"
    _attr_native_step = 1.0
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_device_class = NumberDeviceClass.CURRENT
    _attr_icon = "mdi:current-ac"
    _attr_entity_category = EntityCategory.CONFIG
    _command = "currentSet"

    def __init__(self, updater: EveusUpdater, model: str) -> None:
        """Initialize the current control."""
        super().__init__(updater)
        self._model = model
        self._command_lock = asyncio.Lock()
        
        # Set min/max values based on model
        self._attr_native_min_value = float(MIN_CURRENT)
        self._attr_native_max_value = float(MODEL_MAX_CURRENT[model])
        self._attr_native_value = None  # Will be set from device state

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        try:
            value = self._updater.data.get(self._command)
            if value is not None:
                self._attr_native_value = float(value)
            return self._attr_native_value
        except (TypeError, ValueError) as err:
            _LOGGER.error("Error getting current value: %s", err)
            return self._attr_native_value

    async def async_set_native_value(self, value: float) -> None:
        """Set new current value."""
        async with self._command_lock:
            try:
                value = int(min(self._attr_native_max_value, max(self._attr_native_min_value, value)))
                if await self._updater.send_command(self._command, value):
                    self._attr_native_value = float(value)
                    self.async_write_ha_state()
            except Exception as err:
                _LOGGER.error("Failed to set current value: %s", err)

class EveusRateCostNumber(EveusNumberEntity):
    """Rate cost configuration."""
    
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 1000
    _attr_native_step = 0.01
    _attr_suggested_display_precision = 2
    _attr_native_unit_of_measurement = "₴/kWh"
    _attr_icon = "mdi:currency-uah"
    _command: str = None
    _state_key: str = None

    def __init__(self, updater) -> None:
        """Initialize the entity."""
        super().__init__(updater)
        self._command_lock = asyncio.Lock()

    async def async_set_native_value(self, value: float) -> None:
        """Set new rate value."""
        async with self._command_lock:
            # Convert to expected format (e.g., 4.30 -> 430)
            int_value = int(value * 100)
            if await self._updater.send_command(self._command, int_value):
                self._attr_native_value = value
                self.async_write_ha_state()

class EveusTimeNumber(EveusNumberEntity):
    """Time configuration base class."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 1439  # 23:59 in minutes
    _attr_native_step = 30
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:clock-outline"
    _command: str = None
    _state_key: str = None

    def __init__(self, updater) -> None:
        """Initialize the entity."""
        super().__init__(updater)
        self._command_lock = asyncio.Lock()

    async def async_set_native_value(self, value: float) -> None:
        """Set new time value."""
        async with self._command_lock:
            int_value = int(value)
            if await self._updater.send_command(self._command, int_value):
                self._attr_native_value = float(int_value)
                self.async_write_ha_state()

class EveusPrimaryRateCostNumber(EveusRateCostNumber):
    """Primary rate cost configuration."""

    ENTITY_NAME = "Primary Rate Cost Config"
    _command = RATE_COMMANDS["PRIMARY_RATE"]
    _state_key = "tarif"

    @property
    def native_value(self) -> float | None:
        """Return the current rate value."""
        try:
            value = get_safe_value(self._updater.data, self._state_key, float)
            if value is not None:
                return value / 100
            return self._attr_native_value
        except Exception as err:
            _LOGGER.error("Error getting primary rate value: %s", err)
            return self._attr_native_value

class EveusRate2StartNumber(EveusTimeNumber):
    """Rate 2 start time configuration."""

    ENTITY_NAME = "Rate 2 Start Time"
    _command = RATE_COMMANDS["RATE2_START"]
    _state_key = "tarifAStart"

    @property
    def native_value(self) -> float | None:
        """Return current start time."""
        try:
            value = get_safe_value(self._updater.data, self._state_key, int)
            if value is not None:
                return float(value)
            return self._attr_native_value
        except Exception as err:
            _LOGGER.error("Error getting rate 2 start time: %s", err)
            return self._attr_native_value

class EveusRate2StopNumber(EveusTimeNumber):
    """Rate 2 stop time configuration."""

    ENTITY_NAME = "Rate 2 Stop Time"
    _command = RATE_COMMANDS["RATE2_STOP"]
    _state_key = "tarifAStop"

    @property
    def native_value(self) -> float | None:
        """Return current stop time."""
        try:
            value = get_safe_value(self._updater.data, self._state_key, int)
            if value is not None:
                return float(value)
            return self._attr_native_value
        except Exception as err:
            _LOGGER.error("Error getting rate 2 stop time: %s", err)
            return self._attr_native_value

class EveusRate3StartNumber(EveusTimeNumber):
    """Rate 3 start time configuration."""

    ENTITY_NAME = "Rate 3 Start Time"
    _command = RATE_COMMANDS["RATE3_START"]
    _state_key = "tarifBStart"

    @property
    def native_value(self) -> float | None:
        """Return current start time."""
        try:
            value = get_safe_value(self._updater.data, self._state_key, int)
            if value is not None:
                return float(value)
            return self._attr_native_value
        except Exception as err:
            _LOGGER.error("Error getting rate 3 start time: %s", err)
            return self._attr_native_value

class EveusRate3StopNumber(EveusTimeNumber):
    """Rate 3 stop time configuration."""

    ENTITY_NAME = "Rate 3 Stop Time"
    _command = RATE_COMMANDS["RATE3_STOP"]
    _state_key = "tarifBStop"

    @property
    def native_value(self) -> float | None:
        """Return current stop time."""
        try:
            value = get_safe_value(self._updater.data, self._state_key, int)
            if value is not None:
                return float(value)
            return self._attr_native_value
        except Exception as err:
            _LOGGER.error("Error getting rate 3 stop time: %s", err)
            return self._attr_native_value

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eveus number entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    updater = data["updater"]
    model = entry.data.get(CONF_MODEL)
    
    if not updater:
        _LOGGER.error("No updater found in data")
        return
        
    if not model:
        _LOGGER.error("No model specified in config")
        return

    entities = [
        # Current control
        EveusCurrentNumber(updater, model),
        
        # Rate configuration
        EveusPrimaryRateCostNumber(updater),
        EveusRate2StartNumber(updater),
        EveusRate2StopNumber(updater),
        EveusRate3StartNumber(updater),
        EveusRate3StopNumber(updater),
    ]

    # Initialize entities dict if needed
    if "entities" not in data:
        data["entities"] = {}
    
    data["entities"]["number"] = {
        entity.unique_id: entity for entity in entities
    }

    async_add_entities(entities)
