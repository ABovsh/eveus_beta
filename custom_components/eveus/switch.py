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
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD

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
        self._initial_update = False  # Track if we've received first data update

    async def _async_send_command(self, command_value: int) -> None:
        """Send command to device."""
        async with self._command_lock:
            if await self._updater.send_command(self._command, command_value):
                self._is_on = bool(command_value)
                self.async_write_ha_state()

    async def _async_restore_state(self, state: State) -> None:
        """Restore previous state without triggering commands."""
        try:
            self._is_on = state.state == "on"
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Error restoring state for %s: %s", self.name, err)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._initial_update = True  # Mark that we've received live data
        try:
            value = self._updater.data.get(self._state_key)
            if value is not None:
                new_state = bool(int(value))
                if new_state != self._is_on:
                    self._is_on = new_state
                    self.async_write_ha_state()
        except (TypeError, ValueError):
            pass

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self._is_on

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self._state_key in self._updater.data

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
    """Representation of Eveus reset counter A switch with safe handling."""

    ENTITY_NAME = "Reset Counter A"
    _attr_icon = "mdi:refresh-circle"
    _command = "rstEM1"
    _state_key = "IEM1"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize with safety flags."""
        super().__init__(updater)
        self._pending_reset = False
        self._safe_mode = True  # Block commands until first update

    async def async_added_to_hass(self) -> None:
        """Handle entity addition with delayed safe mode disable."""
        await super().async_added_to_hass()
        self.hass.async_create_task(self._disable_safe_mode())

    async def _disable_safe_mode(self) -> None:
        """Disable safe mode after first successful update."""
        await self._updater.async_start_updates()
        self._safe_mode = False

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update state from live data."""
        super()._handle_coordinator_update()
        # Sync pending state with actual device state
        if self._initial_update and self._pending_reset:
            self._pending_reset = False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Mark reset needed (visual only)."""
        if self._safe_mode:
            return
        self._pending_reset = True
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Perform actual reset command."""
        if self._safe_mode or not self._pending_reset:
            return

        if await self._updater.send_command(self._command, 0):
            self._pending_reset = False
            self._is_on = False
            self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return True if counter needs reset."""
        if self._safe_mode:
            return self._pending_reset
            
        try:
            # Use live data when available, fallback to pending state
            value = float(self._updater.data.get(self._state_key, 0))
            return value > 0 or self._pending_reset
        except (TypeError, ValueError):
            return self._pending_reset

    async def _async_restore_state(self, state: State) -> None:
        """Restore state without immediate action."""
        self._pending_reset = state.state == "on"
        self._is_on = self._pending_reset
        self.async_write_ha_state()

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Eveus switches with safe reset handling."""
    data = hass.data[DOMAIN][entry.entry_id]
    updater = data["updater"]

    switches = [
        EveusStopChargingSwitch(updater),
        EveusOneChargeSwitch(updater),
        EveusResetCounterASwitch(updater),
    ]

    if "entities" not in data:
        data["entities"] = {}

    data["entities"]["switch"] = {
        switch.unique_id: switch for switch in switches
    }

    async_add_entities(switches)
