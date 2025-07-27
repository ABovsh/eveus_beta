"""Support for Eveus switches with proper state persistence."""
from __future__ import annotations

import logging
import asyncio
import time
from typing import Any, Optional

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
    """Base switch entity for Eveus with proper state persistence."""

    _attr_entity_category = EntityCategory.CONFIG
    _command: str = None
    _state_key: str = None

    def __init__(self, updater, device_number: int = 1) -> None:
        """Initialize the switch."""
        super().__init__(updater, device_number)
        self._command_lock = asyncio.Lock()
        
        # State management for persistence
        self._intended_state: Optional[bool] = None  # What user wants
        self._device_state: Optional[bool] = None    # What device reports
        self._pending_command: Optional[bool] = None # Command in progress
        self._last_command_time = 0
        self._restore_attempted = False

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on - prioritize intended state."""
        # Priority: pending command > intended state > device state > default
        if self._pending_command is not None:
            return self._pending_command
        if self._intended_state is not None:
            return self._intended_state
        if self._device_state is not None:
            return self._device_state
        
        # Default fallback
        device_value = get_safe_value(self._updater.data, self._state_key, int, 0)
        return bool(device_value)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available

    async def _async_send_command(self, command_value: int) -> bool:
        """Send command to device and track state."""
        async with self._command_lock:
            # Set pending state
            self._pending_command = bool(command_value)
            self.async_write_ha_state()
            
            try:
                # Send command
                success = await self._updater.send_command(self._command, command_value)
                
                if success:
                    # Command succeeded - update intended state
                    self._intended_state = bool(command_value)
                    _LOGGER.debug("Successfully set %s to %s", self.name, "on" if command_value else "off")
                else:
                    # Command failed - keep previous intended state
                    _LOGGER.warning("Failed to set %s to %s", self.name, "on" if command_value else "off")
                
                return success
                
            finally:
                # Clear pending state
                self._pending_command = None
                self._last_command_time = time.time()
                self.async_write_ha_state()

    async def _async_restore_state(self, state: State) -> None:
        """Restore previous intended state."""
        try:
            if state and state.state in ("on", "off"):
                restored_state = state.state == "on"
                self._intended_state = restored_state
                _LOGGER.debug("Restored %s intended state to %s", self.name, state.state)
                
                # Try to apply the restored state when device becomes available
                self.hass.async_create_task(self._apply_restored_state(restored_state))
                
        except Exception as err:
            _LOGGER.debug("Error restoring state for %s: %s", self.name, err)

    async def _apply_restored_state(self, target_state: bool) -> None:
        """Apply restored state when device becomes available."""
        # Wait a bit for device to be ready
        await asyncio.sleep(5)
        
        # Check if we should apply the restored state
        if not self._restore_attempted and self._intended_state is not None:
            self._restore_attempted = True
            
            # Only send command if device state differs from intended state
            current_device_state = bool(get_safe_value(self._updater.data, self._state_key, int, 0))
            
            if current_device_state != self._intended_state:
                _LOGGER.info("Applying restored state for %s: %s", self.name, "on" if self._intended_state else "off")
                await self._async_send_command(1 if self._intended_state else 0)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Update device state from coordinator data
        if self._state_key in self._updater.data:
            new_device_state = bool(get_safe_value(self._updater.data, self._state_key, int, 0))
            
            # Only update if device state actually changed
            if self._device_state != new_device_state:
                self._device_state = new_device_state
                
                # If no command is pending and no intended state is set, sync with device
                if self._pending_command is None and self._intended_state is None:
                    self._intended_state = new_device_state
                
        self.async_write_ha_state()


class EveusStopChargingSwitch(BaseSwitchEntity):
    """Representation of Eveus charging control switch."""

    ENTITY_NAME = "Stop Charging"
    _attr_icon = "mdi:ev-station"
    _command = "evseEnabled"
    _state_key = "evseEnabled"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on charging (enable EVSE)."""
        await self._async_send_command(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off charging (disable EVSE)."""
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
    """Representation of Eveus reset counter A switch with special behavior."""

    ENTITY_NAME = "Reset Counter A"
    _attr_icon = "mdi:refresh-circle"
    _command = "rstEM1"
    _state_key = "IEM1"

    def __init__(self, updater, device_number: int = 1) -> None:
        """Initialize with special reset behavior."""
        super().__init__(updater, device_number)
        self._safe_mode = True
        self._last_reset_time = 0

    async def async_added_to_hass(self) -> None:
        """Handle entity addition with delayed safe mode disable."""
        await super().async_added_to_hass()
        self.hass.async_create_task(self._disable_safe_mode())

    async def _disable_safe_mode(self) -> None:
        """Disable safe mode after first successful update."""
        await self._updater.async_start_updates()
        await asyncio.sleep(5)  # Give time for first update
        self._safe_mode = False

    @property
    def is_on(self) -> bool:
        """Return True if counter has a value (special logic for reset switch)."""
        if self._safe_mode:
            return False
            
        # For reset switch, "on" means there's energy to reset
        value = get_safe_value(self._updater.data, self._state_key, float, 0)
        return value > 0

    async def async_turn_on(self, **kwargs: Any) -> None:
        """No action needed for turn_on - switch state represents counter status."""
        # Do nothing on turn_on as it's just a representation of counter status
        pass

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Perform reset command whenever switch is turned off."""
        if self._safe_mode:
            return

        # Always send the reset command when turned off
        success = await self._updater.send_command(self._command, 0)
        if success:
            self._last_reset_time = time.time()
            _LOGGER.info("Successfully reset counter A")
        else:
            _LOGGER.warning("Failed to reset counter A")

    async def _async_restore_state(self, state: State) -> None:
        """No state restoration for reset switch - state depends on counter value."""
        # Reset switch state is determined by counter value, not user setting
        pass

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data - state based on counter value."""
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Eveus switches."""
    data = hass.data[DOMAIN][entry.entry_id]
    updater = data["updater"]
    device_number = data.get("device_number", 1)  # Default to 1 for backward compatibility

    switches = [
        EveusStopChargingSwitch(updater, device_number),
        EveusOneChargeSwitch(updater, device_number),
        EveusResetCounterASwitch(updater, device_number),
    ]

    if "entities" not in data:
        data["entities"] = {}

    data["entities"]["switch"] = {
        switch.unique_id: switch for switch in switches
    }

    async_add_entities(switches)
