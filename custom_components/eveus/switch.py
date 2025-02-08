"""Support for Eveus switches."""
from __future__ import annotations

import logging
import asyncio
import time
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State, callback
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
        self._last_state = None
        self._last_counter_value = None

    async def _async_send_command(self, command_value: int) -> None:
        """Send command to device."""
        async with self._command_lock:
            _LOGGER.debug(
                "Sending command %s with value %s for entity %s",
                self._command,
                command_value,
                self.name
            )
            if await self._updater.send_command(self._command, command_value):
                self._is_on = bool(command_value)
                self.async_write_ha_state()

    async def _async_restore_state(self, state: State) -> None:
        """Restore previous state."""
        try:
            if state.state == "on":
                await self.async_turn_on()
            elif state.state == "off":
                await self.async_turn_off()
        except Exception as err:
            _LOGGER.error("Error restoring state for %s: %s", self.name, err)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        try:
            value = self._updater.data.get(self._state_key)
            if value is not None:
                new_state = bool(int(value))
                if new_state != self._is_on:
                    _LOGGER.debug(
                        "%s state changed from %s to %s",
                        self.name,
                        self._is_on,
                        new_state
                    )
                    self._is_on = new_state
                    self.async_write_ha_state()
        except (TypeError, ValueError) as err:
            _LOGGER.error("Error handling update for %s: %s", self.name, err)

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self._is_on

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not super().available:
            return False
        return self._state_key in self._updater.data

class EveusStopChargingSwitch(BaseSwitchEntity):
    """Representation of Eveus charging control switch."""

    ENTITY_NAME = "Stop Charging"
    _attr_icon = "mdi:ev-station"
    _command = "evseEnabled"
    _state_key = "evseEnabled"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on charging."""
        _LOGGER.info("Enabling charging")
        await self._async_send_command(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off charging."""
        _LOGGER.info("Disabling charging")
        await self._async_send_command(0)

class EveusOneChargeSwitch(BaseSwitchEntity):
    """Representation of Eveus one charge switch."""

    ENTITY_NAME = "One Charge"
    _attr_icon = "mdi:lightning-bolt"
    _command = "oneCharge"
    _state_key = "oneCharge"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable one charge mode."""
        _LOGGER.info("Enabling one charge mode")
        await self._async_send_command(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable one charge mode."""
        _LOGGER.info("Disabling one charge mode")
        await self._async_send_command(0)

class EveusResetCounterASwitch(BaseSwitchEntity):
    """Representation of Eveus reset counter A switch."""

    ENTITY_NAME = "Reset Counter A"
    _attr_icon = "mdi:refresh-circle"
    _command = "rstEM1"
    _state_key = "IEM1"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the reset counter switch."""
        super().__init__(updater)
        self._last_counter_value = None
        self._is_charging = False
        self._last_charging_state = None
        self._reset_in_progress = False
        self._last_reset_time = 0
        self._reset_events = []
        self._restored = False
        # Initialize time-related attributes in constructor
        current_time = time.time()
        self._last_state_change = current_time
        self._creation_time = current_time

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        
        # Restore previous state and counter value
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._last_counter_value = float(last_state.attributes.get("last_counter_value", 0))
            self._reset_events = last_state.attributes.get("last_reset_events", [])
            self._last_charging_state = last_state.attributes.get("charging_state", False)
            self._restored = True
            _LOGGER.debug(
                "Restored counter state - Last value: %s, Charging: %s",
                self._last_counter_value,
                self._last_charging_state
            )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        try:
            # Get current counter value
            counter_value = self._updater.data.get(self._state_key)
            charging_state = self._updater.data.get("evseEnabled")
            current_time = time.time()

            if counter_value is not None:
                current_value = float(counter_value)
                
                # Skip initial state detection if we've restored state
                if not self._restored and self._last_counter_value is None:
                    self._last_counter_value = current_value
                    _LOGGER.debug("Initial counter value set to: %s", current_value)
                    self.async_write_ha_state()
                    return

                # Track charging state changes
                if charging_state is not None:
                    charging_state = bool(int(charging_state))
                    if charging_state != self._last_charging_state:
                        _LOGGER.debug(
                            "Charging state changed from %s to %s",
                            self._last_charging_state,
                            charging_state
                        )
                        self._last_charging_state = charging_state
                        self._last_state_change = current_time

                # Log counter changes
                if self._last_counter_value is not None and current_value != self._last_counter_value:
                    _LOGGER.debug(
                        "Counter A value changed from %s to %s (charging: %s, time since last change: %s)", 
                        self._last_counter_value,
                        current_value,
                        charging_state,
                        current_time - self._last_state_change
                    )
                    
                    # Detect unauthorized resets
                    if current_value < self._last_counter_value:
                        # Only log if not a manual reset and not right after charging stops
                        if not self._reset_in_progress and (current_time - self._last_reset_time) > 5:
                            _LOGGER.warning(
                                "Counter A was reset unexpectedly! Previous: %s, Current: %s, Charging: %s, Time since charging state change: %s",
                                self._last_counter_value,
                                current_value, 
                                charging_state,
                                current_time - self._last_state_change
                            )
                            # Record reset event
                            self._reset_events.append({
                                'time': current_time,
                                'previous_value': self._last_counter_value,
                                'new_value': current_value,
                                'charging_state': charging_state,
                                'time_since_charging_change': current_time - self._last_state_change
                            })
                            if len(self._reset_events) > 10:
                                self._reset_events.pop(0)

                self._last_counter_value = current_value
                self.async_write_ha_state()

        except Exception as err:
            _LOGGER.error("Error handling counter update: %s", err)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Reset counter A."""
        try:
            _LOGGER.info("Manually resetting Counter A")
            self._reset_in_progress = True
            self._last_reset_time = time.time()
            await self._async_send_command(0)
        finally:
            self._reset_in_progress = False

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Reset counter - off state is same as on for reset."""
        await self.async_turn_on()

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

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        current_time = time.time()
        return {
            "last_counter_value": self._last_counter_value,
            "charging_state": self._last_charging_state,
            "last_reset_events": self._reset_events[-5:],  # Return last 5 reset events
            "total_unexpected_resets": len(self._reset_events),
            "uptime": current_time - self._creation_time,
            "last_state_change": current_time - self._last_state_change
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Reset counter A."""
        try:
            _LOGGER.info("Manually resetting Counter A")
            self._reset_in_progress = True
            self._last_reset_time = time.time()
            await self._async_send_command(0)
        finally:
            self._reset_in_progress = False

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Reset counter - off state is same as on for reset."""
        await self.async_turn_on()

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

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        current_time = time.time()
        return {
            "last_reset_events": self._reset_events[-5:],  # Return last 5 reset events
            "total_unexpected_resets": len(self._reset_events),
            "total_reboot_resets": self._reboot_count,
            "uptime": current_time - self._creation_time,
            "last_state_change": current_time - self._last_state_change
        }
    
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

    data["entities"]["switch"] = {
        switch.unique_id: switch for switch in switches
    }

    async_add_entities(switches)
