"""Support for Eveus number entities."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import (
    NumberEntity,
    NumberMode,
    NumberDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
from .common import (
    BaseEveusEntity,
    EveusUpdater,
    send_eveus_command,
)

_LOGGER = logging.getLogger(__name__)

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

    def __init__(self, updater: EveusUpdater, model: str) -> None:
        """Initialize the current control."""
        super().__init__(updater)
        self._model = model
        
        # Set min/max values based on model
        self._attr_native_min_value = float(MIN_CURRENT)
        self._attr_native_max_value = float(MODEL_MAX_CURRENT[model])
        self._attr_native_value = min(self._attr_native_max_value, 16.0)

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        try:
            value = self._updater.data.get("currentSet")
            if value is not None:
                self._attr_native_value = float(value)
            return self._attr_native_value
        except (TypeError, ValueError):
            return self._attr_native_value

    async def async_set_native_value(self, value: float) -> None:
        """Set new current value."""
        value = int(min(self._attr_native_max_value, max(self._attr_native_min_value, value)))
        
        if await send_eveus_command(
            self.hass,  # ADDED: Required first parameter
            self._updater.host,  # FIXED: Remove underscore
            self._updater.username,  # FIXED: Remove underscore
            self._updater.password,  # FIXED: Remove underscore
            "currentSet",
            value
        ):
            self._attr_native_value = float(value)

    async def _async_restore_state(self, state) -> None:
        """Restore previous state."""
        try:
            restored_value = float(state.state)
            if self._attr_native_min_value <= restored_value <= self._attr_native_max_value:
                self._attr_native_value = restored_value
        except (TypeError, ValueError):
            pass

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eveus number entities."""
    # FIXED: Get existing updater from hass.data
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
