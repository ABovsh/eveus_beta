"""Support for Eveus switches."""
from __future__ import annotations

import logging
import asyncio
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
from .common import BaseEveusEntity, EveusUpdater

_LOGGER = logging.getLogger(__name__)

# Constants
COMMAND_TIMEOUT = 5
STATE_VERIFY_DELAY = 2
RETRY_DELAY = 10

class BaseSwitchEntity(BaseEveusEntity, SwitchEntity):
    """Base switch entity for Eveus."""

    _attr_entity_category = EntityCategory.CONFIG
    _command: str = None
    _state_key: str = None

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the switch."""
        super().__init__(updater)
        self._is_on = False
        self._command_lock = asyncio.Lock()
        self._pending_command = None

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        try:
            value = self._updater.data.get(self._state_key)
            if value is not None:
                self._is_on = bool(int(value))
            return self._is_on
        except (TypeError, ValueError):
            return self._is_on

    async def _async_verify_state(self, expected_state: bool, retries: int = 1) -> bool:
        """Verify that the state matches the expected state."""
        retry_count = 0
        while retry_count <= retries:
            # Wait for state update
            await asyncio.sleep(STATE_VERIFY_DELAY)
            
            try:
                current_state = bool(int(self._updater.data.get(self._state_key, 0)))
                if current_state == expected_state:
                    return True
                
                if retry_count < retries:
                    _LOGGER.warning(
                        "State verification failed for %s. Expected: %s, Got: %s. Retrying...",
                        self.name,
                        expected_state,
                        current_state
                    )
                    retry_count += 1
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    _LOGGER.error(
                        "State verification failed for %s. Expected: %s, Got: %s",
                        self.name,
                        expected_state,
                        current_state
                    )
                    return False
                    
            except Exception as err:
                _LOGGER.error(
                    "Error verifying state for %s: %s",
                    self.name,
                    str(err)
                )
                return False

        return False

    async def _async_send_command(self, command_value: int) -> bool:
        """Send command with verification and retry."""
        async with self._command_lock:
            try:
                # Send command
                if not await self._updater.send_command(self._command, command_value):
                    # Single retry after delay
                    await asyncio.sleep(RETRY_DELAY)
                    if not await self._updater.send_command(self._command, command_value):
                        _LOGGER.error("Failed to send command %s to %s", self._command, self.name)
                        return False

                # Verify state change
                expected_state = bool(command_value)
                if await self._async_verify_state(expected_state):
                    self._is_on = expected_state
                    return True
                    
                return False

            except Exception as err:
                _LOGGER.error(
                    "Error sending command to %s: %s",
                    self.name,
                    str(err)
                )
                return False
            finally:
                self._pending_command = None

    async def _async_restore_state(self, state: State) -> None:
        """Restore previous state."""
        try:
            if state.state == "on":
                await self.async_turn_on()
            elif state.state == "off":
                await self.async_turn_off()
        except Exception as err:
            _LOGGER.error("Error restoring state for %s: %s", self.name, err)

class EveusStopChargingSwitch(BaseSwitchEntity):
    """Representation of Eveus charging control switch."""

    ENTITY_NAME = "Stop Charging"
    _attr_icon = "mdi:ev-station"
    _command = "evseEnabled"
    _state_key = "evseEnabled"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on charging."""
        if await self._async_send_command(1):
            self.async_write_ha_state()
        else:
            _LOGGER.error("%s: Failed to enable charging", self.name)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off charging."""
        if await self._async_send_command(0):
            self.async_write_ha_state()
        else:
            _LOGGER.error("%s: Failed to disable charging", self.name)

class EveusOneChargeSwitch(BaseSwitchEntity):
    """Representation of Eveus one charge switch."""

    ENTITY_NAME = "One Charge"
    _attr_icon = "mdi:lightning-bolt"
    _command = "oneCharge"
    _state_key = "oneCharge"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable one charge mode."""
        if await self._async_send_command(1):
            self.async_write_ha_state()
        else:
            _LOGGER.error("%s: Failed to enable one charge mode", self.name)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable one charge mode."""
        if await self._async_send_command(0):
            self.async_write_ha_state()
        else:
            _LOGGER.error("%s: Failed to disable one charge mode", self.name)

class EveusResetCounterASwitch(BaseSwitchEntity):
    """Representation of Eveus reset counter A switch."""

    ENTITY_NAME = "Reset Counter A"
    _attr_icon = "mdi:counter"
    _command = "rstEM1"
    _state_key = "IEM1"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Reset counter A."""
        if await self._async_send_command(0):
            self.async_write_ha_state()
        else:
            _LOGGER.error("%s: Failed to reset counter", self.name)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Reset counter - off state is same as on for reset."""
        if await self._async_send_command(0):
            self.async_write_ha_state()
        else:
            _LOGGER.error("%s: Failed to reset counter", self.name)

    @property
    def is_on(self) -> bool:
        """Return true if counter has value."""
        try:
            value = self._updater.data.get(self._state_key)
            if value is not None:
                return float(value) > 0
            return False
        except (TypeError, ValueError):
            return False

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Eveus switches."""
    data = hass.data[DOMAIN][entry.entry_id]
    updater = data["updater"]

    switches = [
        EveusStopChargingSwitch(updater),
        EveusOneChargeSwitch(updater),
        EveusResetCounterASwitch(updater),
    ]

    # Initialize entities dict if needed
    if "entities" not in data:
        data["entities"] = {}

    # Store switch references with unique_id as key
    data["entities"]["switch"] = {
        switch.unique_id: switch for switch in switches
    }

    async_add_entities(switches)
