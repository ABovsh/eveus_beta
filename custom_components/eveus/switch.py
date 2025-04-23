"""Support for Eveus switches."""
from __future__ import annotations

import logging
import asyncio
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .common import BaseEveusEntity
from .utils import get_safe_value

_LOGGER = logging.getLogger(__name__)

class BaseSwitchEntity(BaseEveusEntity, SwitchEntity):
    """Base switch entity for Eveus."""

    _attr_entity_category = EntityCategory.CONFIG
    _command: str = None
    _state_key: str = None

    def __init__(self, updater) -> None:
        """Initialize the switch."""
        super().__init__(updater)
        self._command_lock = asyncio.Lock()
        self._pending_state = None # Used for immediate visual feedback

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        # Use pending state if available for immediate UI feedback
        if self._pending_state is not None:
            return self._pending_state
        # Otherwise, determine state based on device data
        value = get_safe_value(self._updater.data, self._state_key, int)
        # Default to False if value is None or not an integer
        return bool(value) if value is not None else False

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Check base availability and if the specific key exists in data
        return super().available and self._state_key in self._updater.data

    async def _async_send_command(self, command_value: int) -> None:
        """Send command to device with visual feedback."""
        async with self._command_lock:
            # Set pending state before sending command for immediate UI update
            self._pending_state = bool(command_value)
            self.async_write_ha_state()

            # Send command
            success = await self._updater.send_command(self._command, command_value)

            # If command failed, revert pending state after a short delay
            # If successful, _handle_coordinator_update will clear pending state
            if not success:
                await asyncio.sleep(1) # Short delay before reverting
                if self._pending_state == bool(command_value): # Check if state wasn't updated by coordinator
                    self._pending_state = not bool(command_value)
                    self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Clear pending state and use actual device state from coordinator
        self._pending_state = None
        super()._handle_coordinator_update() # Calls self.async_write_ha_state()


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
    """Representation of Eveus reset counter A switch (simplified)."""

    ENTITY_NAME = "Reset Counter A"
    _attr_icon = "mdi:refresh-circle"
    _command = "rstEM1"
    _state_key = "IEM1" # State reflects if counter has a value > 0

    def __init__(self, updater) -> None:
        """Initialize the reset switch."""
        super().__init__(updater)
        # No _pending_reset or _safe_mode needed anymore

    @property
    def is_on(self) -> bool:
        """Return True if counter has a value greater than 0."""
        # Use pending state if available for immediate UI feedback after toggle
        if self._pending_state is not None:
            return self._pending_state

        # Determine state based on actual counter value
        value = get_safe_value(self._updater.data, self._state_key, float, 0)
        return value > 0

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turning ON does nothing for the reset switch."""
        _LOGGER.debug("Turning ON Reset Counter A switch has no direct action.")
        # Visually update state immediately if needed (optional)
        # self._pending_state = True
        # self.async_write_ha_state()
        pass # Or explicitly do nothing

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Perform the reset command when turned OFF."""
        _LOGGER.debug("Turning OFF Reset Counter A switch: sending reset command.")
        # Set pending state to OFF for immediate visual feedback
        self._pending_state = False
        self.async_write_ha_state()

        # Send the reset command (rstEM1 with value 0)
        success = await self._updater.send_command(self._command, 0)

        if not success:
            _LOGGER.warning("Failed to send reset command for Counter A.")
            # Optionally revert pending state if command fails
            await asyncio.sleep(1)
            if self._pending_state is False: # Check if state wasn't updated by coordinator
                 self._pending_state = True # Revert visual state
                 self.async_write_ha_state()
        # _handle_coordinator_update will eventually clear _pending_state
        # when the actual counter value (IEM1) is updated.

    # No _async_restore_state override needed, base class handles it if necessary


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
        EveusResetCounterASwitch(updater), # Use the simplified version
    ]

    if "entities" not in data:
        data["entities"] = {}

    data["entities"]["switch"] = {
        switch.unique_id: switch for switch in switches
    }

    async_add_entities(switches)
