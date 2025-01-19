"""Support for Eveus number entities with improved validation."""
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
        
        # Set initial limits from device capabilities
        capabilities = session_manager.capabilities
        if capabilities:
            self._attr_native_min_value = capabilities["min_current"]
            self._attr_native_max_value = capabilities["max_current"]
        else:
            # Temporary defaults until we get real values
            self._attr_native_min_value = 7
            self._attr_native_max_value = 16

        except Exception as err:
            _LOGGER.error("Error initializing current control: %s", err)
            raise

    async def _validate_current(self, value: float) -> bool:
        """Validate current value."""
        try:
            if not self._attr_native_min_value <= value <= self._attr_native_max_value:
                _LOGGER.warning(
                    "Current %s outside allowed range [%s, %s]",
                    value,
                    self._attr_native_min_value,
                    self._attr_native_max_value
                )
                return False

            # Additional model-specific validation
            if not await self._session_manager.validate_current(value):
                _LOGGER.warning(
                    "Current %s not valid for model %s",
                    value,
                    self._session_manager.model
                )
                return False

            return True

        except Exception as err:
            _LOGGER.error("Error validating current: %s", err)
            return False

    async def async_set_native_value(self, value: float) -> None:
        """Set new current value with validation."""
        try:
            if not await self._validate_current(value):
                return

            success, result = await self._session_manager.send_command(
                "currentSet",
                int(value),
                verify=True
            )
            
            if success:
                self._value = float(value)
                self._error_count = 0
                self.async_write_ha_state()
                _LOGGER.debug("Current set to %s", value)
            else:
                self._error_count += 1
                _LOGGER.warning(
                    "Failed to set current to %s: %s",
                    value,
                    result.get("error", "Unknown error")
                )
                
        except Exception as err:
            self._error_count += 1
            _LOGGER.error("Error setting current to %s: %s", value, err)

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
            "model": self._session_manager.model,
            "sw_version": self._session_manager.firmware_version,
            "serial_number": self._session_manager.station_id,
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return {
            "error_count": self._error_count,
            "restored": self._restored,
            "model_max_current": self._attr_native_max_value,
        }

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
