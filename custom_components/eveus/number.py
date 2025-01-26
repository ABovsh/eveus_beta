"""Support for Eveus number entities."""
from __future__ import annotations

import logging
from typing import Any

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
from homeassistant.const import (
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
    UnitOfElectricCurrent
)

from .const import (
    DOMAIN,
    MODEL_MAX_CURRENT,
    MIN_CURRENT,
    CONF_MODEL
)
from .mixins import SessionMixin, DeviceInfoMixin, ErrorHandlingMixin, ValidationMixin

_LOGGER = logging.getLogger(__name__)

class EveusCurrentNumber(SessionMixin, DeviceInfoMixin, ErrorHandlingMixin, ValidationMixin, RestoreNumber):
    """Eveus current control."""
    
    _attr_native_step = 1.0
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_device_class = NumberDeviceClass.CURRENT
    _attr_has_entity_name = True
    _attr_name = "Charging Current"
    _attr_icon = "mdi:current-ac"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, host: str, username: str, password: str, model: str) -> None:
        """Initialize current control."""
        super().__init__(host, username, password)
        self._model = model
        self._attr_unique_id = f"{host}_charging_current"
        self._attr_native_min_value = float(MIN_CURRENT)
        self._attr_native_max_value = float(MODEL_MAX_CURRENT[model])
        self._value = None

    @property
    def native_value(self) -> float | None:
        """Return current value."""
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        """Set current value."""
        if not self.validate_numeric_value(value, self._attr_native_min_value, self._attr_native_max_value):
            _LOGGER.warning("Value %s outside allowed range", value)
            return

        data = {"currentSet": int(value)}
        if await self.async_api_call("pageEvent", data=data):
            self._value = value

    async def async_update(self) -> None:
        """Update current value."""
        data = await self.async_api_call("main")
        if data and "currentSet" in data:
            value = float(data["currentSet"])
            if self.validate_numeric_value(value, self._attr_native_min_value, self._attr_native_max_value):
                self._value = value

    async def async_added_to_hass(self) -> None:
        """Handle added to Home Assistant."""
        await super().async_added_to_hass()
        
        if self._value is not None:
            return

        if state := await self.async_get_last_state():
            try:
                value = float(state.state)
                if self.validate_numeric_value(value, self._attr_native_min_value, self._attr_native_max_value):
                    self._value = value
                    return
            except (TypeError, ValueError) as err:
                _LOGGER.warning("Could not restore state: %s", err)

        self._value = min(self._attr_native_max_value, 16.0)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities."""
    entities = [
        EveusCurrentNumber(
            entry.data[CONF_HOST],
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            entry.data[CONF_MODEL]
        )
    ]

    if "entities" not in hass.data[DOMAIN][entry.entry_id]:
        hass.data[DOMAIN][entry.entry_id]["entities"] = {}

    hass.data[DOMAIN][entry.entry_id]["entities"]["number"] = {
        entity.unique_id: entity for entity in entities
    }

    async_add_entities(entities)
