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

from .const import (
    DOMAIN,
    MODEL_MAX_CURRENT,
    MIN_CURRENT,
    CONF_MODEL,
)

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

    def __init__(self, session_manager, entry_id: str, model: str) -> None:
        """Initialize current control."""
        super().__init__()
        self._session_manager = session_manager
        self._entry_id = entry_id
        self._model = model
        self._attr_unique_id = f"{session_manager._host}_charging_current"
        
        # Set min/max values based on model
        self._attr_native_min_value = float(MIN_CURRENT)
        self._attr_native_max_value = float(MODEL_MAX_CURRENT[model])
        self._value = min(self._attr_native_max_value, 16.0)  # Default to 16A

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
            "model": f"Eveus {self._model}",
            "configuration_url": f"http://{self._session_manager._host}",
        }

    async def async_set_native_value(self, value: float) -> None:
        """Set new current value."""
        value = int(min(self._attr_native_max_value, max(self._attr_native_min_value, value)))
        success, _ = await self._session_manager.send_command("currentSet", value)
        
        if success:
            self._value = float(value)
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        
        # Restore previous state
        if state := await self.async_get_last_state():
            try:
                restored_value = float(state.state)
                if self._attr_native_min_value <= restored_value <= self._attr_native_max_value:
                    self._value = restored_value
            except (TypeError, ValueError):
                _LOGGER.warning("Could not restore previous state for %s", self.entity_id)

        # Get initial state from device
        try:
            device_state = await self._session_manager.get_state()
            if "currentSet" in device_state:
                self._value = float(device_state["currentSet"])
        except Exception as err:
            _LOGGER.error("Error getting initial state: %s", str(err))

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Eveus number entities."""
    session_manager = hass.data[DOMAIN][entry.entry_id]["session_manager"]
    model = entry.data[CONF_MODEL]

    entities = [
        EveusCurrentNumber(session_manager, entry.entry_id, model),
    ]

    hass.data[DOMAIN][entry.entry_id]["entities"]["number"] = {
        entity.unique_id: entity for entity in entities
    }

    async_add_entities(entities)
