# File: custom_components/eveus/number.py
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

class EveusCurrentNumber(RestoreNumber):
    """Representation of Eveus current control with dynamic range."""

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
        
        # Set current range from device capabilities
        self._attr_native_min_value = session_manager.capabilities["min_current"]
        self._attr_native_max_value = session_manager.capabilities["max_current"]

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
            "model": f"Eveus {self._attr_native_min_value}-{self._attr_native_max_value}A",
            "sw_version": self._session_manager.firmware_version,
            "serial_number": self._session_manager.station_id,
            "configuration_url": f"http://{self._session_manager._host}",
            "hw_version": f"Current range: {self._attr_native_min_value}-{self._attr_native_max_value}A"
        }

    async def async_set_native_value(self, value: float) -> None:
        """Set new current value."""
        # Validate value against device capabilities
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
                _LOGGER.debug("Current set to %s", value)
            else:
                _LOGGER.warning(
                    "Failed to set current to %s: %s",
                    value,
                    result.get("error", "Unknown error")
                )
                
        except Exception as err:
            _LOGGER.error("Error setting current to %s: %s", value, err)

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        
        # Try to restore previous state
        if state := await self.async_get_last_state():
            try:
                restored_value = float(state.state)
                if self._attr_native_min_value <= restored_value <= self._attr_native_max_value:
                    self._value = restored_value
                    _LOGGER.debug("Restored previous current value: %s", restored_value)
            except (TypeError, ValueError) as err:
                _LOGGER.warning(
                    "Could not restore previous state: %s",
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
