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
        self._attr_state = None
        self._attr_unique_id = f"{self._updater.host}_reset_counter_a"
        self._persistent_value = None
        self._current_value = None
        self._is_on = False
        self._reset_in_progress = False
        self._initialized = False

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        
        # Restore state from last shutdown
        last_state = await self.async_get_last_state()
        if last_state and last_state.attributes:
            try:
                restored_value = last_state.attributes.get("persistent_value")
                if restored_value is not None:
                    self._persistent_value = float(restored_value)
                    self._current_value = self._persistent_value
                    self._initialized = True
                    _LOGGER.debug(
                        "Restored counter A value: %s", 
                        self._persistent_value
                    )
            except (TypeError, ValueError) as err:
                _LOGGER.error("Error restoring counter state: %s", err)

        # Get current value after restoration
        if self._state_key in self._updater.data:
            try:
                new_value = float(self._updater.data[self._state_key])
                if not self._initialized:
                    self._persistent_value = new_value
                    self._current_value = new_value
                    self._initialized = True
                    _LOGGER.debug(
                        "Initialized counter A with value: %s", 
                        new_value
                    )
            except (TypeError, ValueError):
                pass

        self._is_on = bool(self._current_value and self._current_value > 0)
        self.async_write_ha_state()

        # Register for updates
        self._updater.async_add_listener(self._handle_coordinator_update)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        try:
            new_value = self._updater.data.get(self._state_key)
            if new_value is not None:
                try:
                    new_value = float(new_value)
                    self._current_value = new_value

                    # If we haven't initialized yet, do it now
                    if not self._initialized:
                        self._persistent_value = new_value
                        self._initialized = True
                        _LOGGER.debug(
                            "Late initialization of counter A with value: %s", 
                            new_value
                        )
                    # If this is not a reset operation and value increased
                    elif not self._reset_in_progress and new_value > self._persistent_value:
                        self._persistent_value = new_value
                        _LOGGER.debug(
                            "Updated persistent counter A value to: %s", 
                            new_value
                        )
                    # If this is a reset operation and value decreased
                    elif self._reset_in_progress and new_value < self._persistent_value:
                        self._persistent_value = new_value
                        self._reset_in_progress = False
                        _LOGGER.debug(
                            "Reset complete, new counter A value: %s", 
                            new_value
                        )

                    self._is_on = new_value > 0
                    self.async_write_ha_state()

                except ValueError as err:
                    _LOGGER.error("Error converting counter value: %s", err)

        except Exception as err:
            _LOGGER.error("Error handling counter update: %s", err)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Reset counter A."""
        if not self._reset_in_progress:
            self._reset_in_progress = True
            _LOGGER.debug("Initiating counter A reset")
            await self._async_send_command(0)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Reset counter - off state is same as on for reset."""
        await self.async_turn_on()

    @property
    def is_on(self) -> bool:
        """Return true if counter has value."""
        return bool(self._is_on)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not super().available:
            return False
        return self._initialized and self._state_key in self._updater.data

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {
            "persistent_value": self._persistent_value,
            "current_value": self._current_value,
            "is_resetting": self._reset_in_progress
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
