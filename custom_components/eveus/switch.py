"""Support for Eveus switches."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.const import (
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
)

from .const import DOMAIN
from .common import (
    BaseEveusEntity,
    EveusUpdater,
    send_eveus_command,
)

_LOGGER = logging.getLogger(__name__)

class BaseSwitchEntity(BaseEveusEntity, SwitchEntity):
    """Base switch entity for Eveus."""

    _attr_entity_category = EntityCategory.CONFIG
    _command: str = None
    _state_key: str = None
    
    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the switch."""
        super().__init__(updater)
        self._is_on = False

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self._is_on

    async def _send_switch_command(self, value: int) -> None:
        """Send command to switch."""
        if self._command is None:
            raise NotImplementedError("_command must be defined")
        
        _LOGGER.debug("Sending command %s=%s to %s", self._command, value, self._updater._host)
            
        if await send_eveus_command(
            self._updater._host,
            self._updater._username,
            self._updater._password,
            self._command,
            value,
            await self._updater._get_session()
        ):
            self._is_on = bool(value)
            self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update state."""
        if self._updater.available and self._state_key:
            value = self._updater.data.get(self._state_key)
            if value is not None:
                new_state = bool(int(value))
                if new_state != self._is_on:
                    self._is_on = new_state
                    _LOGGER.debug("%s state updated to %s", self.name, self._is_on)
                    
class EveusStopChargingSwitch(BaseSwitchEntity):
    """Representation of Eveus charging control switch."""

    ENTITY_NAME = "Stop Charging"
    _attr_icon = "mdi:ev-station"
    _command = "evseEnabled"
    _state_key = "evseEnabled"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on charging."""
        await self._send_switch_command(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off charging."""
        await self._send_switch_command(0)

class EveusOneChargeSwitch(BaseSwitchEntity):
    """Representation of Eveus one charge switch."""

    ENTITY_NAME = "One Charge"
    _attr_icon = "mdi:lightning-bolt"
    _command = "oneCharge"
    _state_key = "oneCharge"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable one charge mode."""
        await self._send_switch_command(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable one charge mode."""
        await self._send_switch_command(0)

class EveusResetCounterASwitch(BaseSwitchEntity):
    """Representation of Eveus reset counter A switch."""

    ENTITY_NAME = "Reset Counter A"
    _attr_icon = "mdi:refresh-circle"
    _command = "rstEM1"
    _state_key = "IEM1"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Reset counter A."""
        await self._send_switch_command(0)
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Reset command for off state."""
        await self._send_switch_command(0)
        self._is_on = False
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update state based on IEM1 value."""
        if self._updater.available:
            value = self._updater.data.get(self._state_key)
            if value is not None:
                try:
                    float_value = float(value)
                    self._is_on = float_value > 0
                    _LOGGER.debug("Reset Counter A value: %s, state: %s", float_value, self._is_on)
                except (ValueError, TypeError):
                    self._is_on = False
                    
async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Eveus switches based on config entry."""
    updater = EveusUpdater(
        host=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        hass=hass,
    )

    switches = [
        EveusStopChargingSwitch(updater),
        EveusOneChargeSwitch(updater),
        EveusResetCounterASwitch(updater),
    ]

    # Initialize entities dict if needed
    if "entities" not in hass.data[DOMAIN][entry.entry_id]:
        hass.data[DOMAIN][entry.entry_id]["entities"] = {}

    # Store switch references with unique_id as key
    hass.data[DOMAIN][entry.entry_id]["entities"]["switch"] = {
        switch.unique_id: switch for switch in switches
    }

    async_add_entities(switches)
