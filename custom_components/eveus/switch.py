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
RETRY_DELAY = 10
MAX_STATE_VERIFICATION_TIME = 20  # Maximum time to wait for state verification
STATE_CHECK_INTERVAL = 2  # Time between state checks

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

    async def _async_verify_state(self, expected_state: bool) -> bool:
        """Verify that the state matches the expected state with longer tolerance."""
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < MAX_STATE_VERIFICATION_TIME:
            try:
                current_state = bool(int(self._updater.data.get(self._state_key, 0)))
                if current_state == expected_state:
                    return True
                
                # Only log if we're still within tolerance time
                if (asyncio.get_event_loop().time() - start_time) < (MAX_STATE_VERIFICATION_TIME - STATE_CHECK_INTERVAL):
                    _LOGGER.debug(
                        "%s: State not yet matched. Expected: %s, Current: %s",
                        self.name,
                        expected_state,
                        current_state
                    )
                await asyncio.sleep(STATE_CHECK_INTERVAL)
                
            except Exception as err:
                _LOGGER.debug(
                    "Error checking state for %s: %s",
                    self.name,
                    str(err)
                )
                await asyncio.sleep(STATE_CHECK_INTERVAL)

        # Only log error if final state doesn't match
        try:
            final_state = bool(int(self._updater.data.get(self._state_key, 0)))
            if final_state != expected_state:
                _LOGGER.warning(
                    "%s: Final state mismatch. Expected: %s, Got: %s",
                    self.name,
                    expected_state,
                    final_state
                )
        except Exception:
            pass
            
        return False

    async def _async_send_command(self, command_value: int) -> bool:
        """Send command with relaxed verification."""
        async with self._command_lock:
            try:
                # Send command
                if not await self._updater.send_command(self._command, command_value):
                    # Single retry after delay
                    await asyncio.sleep(RETRY_DELAY)
                    if not await self._updater.send_command(self._command, command_value):
                        _LOGGER.error("%s: Failed to send command", self.name)
                        return False

                # Update state immediately to improve responsiveness
                self._is_on = bool(command_value)
                self.async_write_ha_state()

                # Verify state change in background
                asyncio.create_task(self._async_verify_state(bool(command_value)))
                return True

            except Exception as err:
                _LOGGER.error(
                    "Error sending command to %s: %s",
                    self.name,
                    str(err)
                )
                return False

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
        await self._async_send_command(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off charging."""
        await self._async_send_command(0)

class EveusOneChargeSwitch(BaseSwitchEntity):
    """Representation of Eveus one charge switch."""

    ENTITY_NAME = "One Charge"
    _attr_icon = "mdi:lightning-bolt"
    _command = "oneCharge"
    _state_key = "oneCharge"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable one charge mode."""
        await self._async_send_command(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable one charge mode."""
        await self._async_send_command(0)

class EveusResetCounterASwitch(BaseSwitchEntity):
    """Representation of Eveus reset counter A switch."""

    ENTITY_NAME = "Reset Counter A"
    _attr_icon = "mdi:counter"
    _command = "rstEM1"
    _state_key = "IEM1"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Reset counter A."""
        await self._async_send_command(0)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Reset counter - off state is same as on for reset."""
        await self._async_send_command(0)

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

    # Store switch references
    data["entities"]["switch"] = {
        switch.unique_id: switch for switch in switches
    }

    async_add_entities(switches)
