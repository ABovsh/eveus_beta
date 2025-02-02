"""Support for Eveus switches."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State
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
        self._last_state = None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._updater.available and self._state_key in self._updater.data

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self._is_on

    async def _send_switch_command(self, value: int) -> None:
        """Send command to switch."""
        if self._command is None:
            raise NotImplementedError("_command must be defined")
            
        if await send_eveus_command(
            self._updater._host,
            self._updater._username,
            self._updater._password,
            self._command,
            value,
            await self._updater._get_session()
        ):
            self._is_on = bool(value)
            self._last_state = value
            self.async_write_ha_state()
            _LOGGER.debug("%s: Set to %s successfully", self.name, self._is_on)
        else:
            _LOGGER.error("%s: Failed to set state to %s", self.name, value)

    def _get_state_from_value(self, value: Any) -> bool:
        """Convert value to boolean state."""
        if value is None:
            return self._is_on  # Maintain current state if value is None
            
        try:
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            if isinstance(value, str):
                return value.lower() in ('true', 'on', 'yes', '1', '1.0')
            return False
        except Exception as err:
            _LOGGER.error("Error converting %s to boolean for %s: %s", value, self.name, err)
            return self._is_on  # Maintain current state on error

    async def _async_restore_state(self, state: State) -> None:
        """Restore previous state."""
        try:
            if state.state in ('on', 'true', '1'):
                self._is_on = True
                self._last_state = 1
            elif state.state in ('off', 'false', '0'):
                self._is_on = False
                self._last_state = 0
            _LOGGER.debug("%s: Restored state to %s", self.name, self._is_on)
        except Exception as err:
            _LOGGER.error("Error restoring state for %s: %s", self.name, err)

    async def async_update(self) -> None:
        """Update state."""
        try:
            if not self._updater.available:
                return
                
            if not self._state_key:
                return
                
            value = self._updater.data.get(self._state_key)
            new_state = self._get_state_from_value(value)
            
            if new_state != self._is_on:
                _LOGGER.debug(
                    "%s state changed: value=%s, new_state=%s",
                    self.name,
                    value,
                    new_state
                )
                self._is_on = new_state
                self._last_state = 1 if new_state else 0
                self.async_write_ha_state()
                
        except Exception as err:
            _LOGGER.error("Error updating %s: %s", self.name, err)
                    
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

    async def _async_restore_state(self, state: State) -> None:
        """Restore previous state with retry logic."""
        await super()._async_restore_state(state)
        if self._is_on:  # If restored state is on, ensure device state matches
            await self.async_turn_on()

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

    async def _async_restore_state(self, state: State) -> None:
        """Restore previous state with retry logic."""
        await super()._async_restore_state(state)
        if self._is_on:  # If restored state is on, ensure device state matches
            await self.async_turn_on()

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
