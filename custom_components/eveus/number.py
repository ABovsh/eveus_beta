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

class EveusCurrentLimitNumber(BaseEveusEntity, NumberEntity):
    """Number entity for current limit adjustment."""
    
    ENTITY_NAME = "Current Limit"
    _attr_icon = "mdi:current-ac"
    _attr_native_min_value = MIN_CURRENT
    _attr_native_step = 1

    def __init__(self, updater: EveusUpdater, model: str):
        super().__init__(updater)
        self._attr_native_max_value = MODEL_MAX_CURRENT.get(model, 16)
        self._attr_unique_id = f"{super().unique_id}_current_limit"

    @property
    def native_value(self) -> float:
        """Return current limit value."""
        return float(self._updater.data.get("currentSet", 0))

    async def async_set_native_value(self, value: float) -> None:
        """Set new current limit."""
        success = await send_eveus_command(
            session=await self._updater._get_session(),
            host=self._updater.host,
            username=self._updater.username,
            password=self._updater.password,
            command="currentSet",
            value=int(value)
        )
        
        if success:
            self._updater.data["currentSet"] = int(value)
            self.async_write_ha_state()

class EveusEnergyLimitNumber(BaseEveusEntity, NumberEntity):
    """Number entity for energy limit adjustment."""
    
    ENTITY_NAME = "Energy Limit"
    _attr_icon = "mdi:lightning-bolt"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 0.1

    @property
    def native_value(self) -> float:
        """Return energy limit value."""
        return float(self._updater.data.get("energyLimit", 0))

    async def async_set_native_value(self, value: float) -> None:
        """Set new energy limit."""
        success = await send_eveus_command(
            session=await self._updater._get_session(),
            host=self._updater.host,
            username=self._updater.username,
            password=self._updater.password,
            command="energyLimit",
            value=value
        )
        
        if success:
            self._updater.data["energyLimit"] = value
            self.async_write_ha_state()

class EveusCostLimitNumber(BaseEveusEntity, NumberEntity):
    """Number entity for cost limit adjustment."""
    
    ENTITY_NAME = "Cost Limit"
    _attr_icon = "mdi:cash"
    _attr_native_min_value = 0
    _attr_native_max_value = 1000
    _attr_native_step = 1

    @property
    def native_value(self) -> float:
        """Return cost limit value."""
        return float(self._updater.data.get("costLimit", 0))

    async def async_set_native_value(self, value: float) -> None:
        """Set new cost limit."""
        success = await send_eveus_command(
            session=await self._updater._get_session(),
            host=self._updater.host,
            username=self._updater.username,
            password=self._updater.password,
            command="costLimit",
            value=value
        )
        
        if success:
            self._updater.data["costLimit"] = value
            self.async_write_ha_state()
