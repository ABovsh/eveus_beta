"""Support for Eveus number entities."""
from __future__ import annotations

import logging
from typing import Any, Final

from homeassistant.components.number import (
    NumberEntity,
    NumberMode,
    NumberDeviceClass,
    RestoreNumber,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.const import UnitOfElectricCurrent

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DEFAULT_MIN_CURRENT = 8.0
DEFAULT_MAX_CURRENT = 16.0

class EveusCurrentNumber(RestoreNumber):
    """Representation of Eveus current control."""

    _attr_native_step: Final = 1.0
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_device_class = NumberDeviceClass.CURRENT
    _attr_has_entity_name = True
    _attr_name = "Charging Current"
    _attr_icon = "mdi:current-ac"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "charging_current"

    def __init__(self, session_manager, entry_id: str) -> None:
        """Initialize current control."""
        super().__init__()
        self._session_manager = session_manager
        self._entry_id = entry_id
        self._attr_unique_id = f"{session_manager._host}_charging_current"
        self._value = None
        
        # Set default limits until we get real values from device
        self._attr_native_min_value = DEFAULT_MIN_CURRENT
        self._attr_native_max_value = DEFAULT_MAX_CURRENT

    async def _init_current_limits(self) -> None:
        """Initialize current limits from device state."""
        try:
            state = await self._session_manager.get_state()
            
            # Get minimum current
            min_current = float(state.get("minCurrent", DEFAULT_MIN_CURRENT))
            if not 6 <= min_current <= 32:
                _LOGGER.warning(
                    "Invalid minimum current from device: %s, using default",
                    min_current
                )
                min_current = DEFAULT_MIN_CURRENT
                
            # Get maximum current
            max_current = float(state.get("curDesign", DEFAULT_MAX_CURRENT))
            if not 16 <= max_current <= 32:
                _LOGGER.warning(
                    "Invalid maximum current from device: %s, using default",
                    max_current
                )
                max_current = DEFAULT_MAX_CURRENT
                
            # Validate min is less than max
            if min_current >= max_current:
                _LOGGER.warning(
                    "Minimum current (%s) >= maximum current (%s), using defaults",
                    min_current,
                    max_current
                )
                min_current = DEFAULT_MIN_CURRENT
                max_current = DEFAULT_MAX_CURRENT
                
            self._attr_native_min_value = min_current
            self._attr_native_max_value = max_current
            
            # Set initial value if not set
            if self._value is None:
                initial_current = float(state.get("currentSet", max_current))
                self._value = max(min_current, min(initial_current, max_current))
                
            _LOGGER.debug(
                "Current limits initialized: min=%s, max=%s, current=%s",
                self._attr_native_min_value,
                self._attr_native_max_value,
                self._value
            )
                
        except Exception as err:
            _LOGGER.warning(
                "Could not get current limits from device, using defaults: %s", 
                err
            )
            self._attr_native_min_value = DEFAULT_MIN_CURRENT
            self._attr_native_max_value = DEFAULT_MAX_CURRENT
            if self._value is None:
                self._value = DEFAULT_MAX_CURRENT

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        return self._value

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._session_manager.available

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._session_manager._host)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": "Eveus",
            "configuration_url": f"http://{self._session_manager._host}",
            "sw_version": self._session_manager.firmware_version,
            "serial_number": self._session_manager.station_id,
        }

    async def async_set_native_value(self, value: float) -> None:
        """Set new current value."""
        # Validate value
        if not self._attr_native_min_value <= value <= self._attr_native_max_value:
            _LOGGER.warning(
                "Current value %s outside allowed range [%s, %s]",
                value,
                self._attr_native_min_value,
                self._attr_native_max_value
            )
            return

        try:
            success, result = await self._session_manager.send_command(
                "currentSet", 
                int(value),
                verify=True
            )
            
            if success:
                self._value = float(value)
                self.async_write_ha_state()
                _LOGGER.debug("Current successfully set to %s", value)
            else:
                _LOGGER.warning(
                    "Failed to set current to %s: %s",
                    value,
                    result.get("error", "Unknown error")
                )
                
        except Exception as err:
            _LOGGER.error("Error setting current to %s: %s", value, str(err))

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        
        # Initialize current limits
        await self._init_current_limits()
        
        # Try to restore previous state
        if state := await self.async_get_last_state():
            try:
                restored_value = float(state.state)
                if self._attr_native_min_value <= restored_value <= self._attr_native_max_value:
                    self._value = restored_value
                    _LOGGER.debug("Restored previous current value: %s", restored_value)
            except (TypeError, ValueError) as err:
                _LOGGER.warning(
                    "Could not restore previous state for %s: %s",
                    self.entity_id,
                    err
                )

        # Get initial state from device if restore failed
        if self._value is None:
            try:
                device_state = await self._session_manager.get_state()
                if "currentSet" in device_state:
                    current = float(device_state["currentSet"])
                    if self._attr_native_min_value <= current <= self._attr_native_max_value:
                        self._value = current
                        _LOGGER.debug("Got initial current from device: %s", current)
            except Exception as err:
                _LOGGER.error("Error getting initial current: %s", str(err))

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Eveus number entities."""
    session_manager = hass.data[DOMAIN][entry.entry_id]["session_manager"]

    entities = [
        EveusCurrentNumber(session_manager, entry.entry_id),
    ]

    hass.data[DOMAIN][entry.entry_id]["entities"]["number"] = {
        entity.unique_id: entity for entity in entities
    }

    async_add_entities(entities)
