# Complete implementation of switch.py with all improvements
"""Support for Eveus switches with improved error handling."""
from __future__ import annotations

import logging
import asyncio
from typing import Any, Final

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    DOMAIN,
    CMD_EVSE_ENABLED,
    CMD_ONE_CHARGE,
    CMD_RESET_COUNTER,
    UPDATE_INTERVAL_CHARGING,
    UPDATE_INTERVAL_IDLE,
)

_LOGGER = logging.getLogger(__name__)

class BaseEveusSwitch(SwitchEntity, RestoreEntity):
    """Base class for Eveus switches with error handling."""

    _attr_has_entity_name: Final = True
    _attr_should_poll = False
    _max_retry_attempts = 3
    _retry_delay = 5.0

    def __init__(self, session_manager) -> None:
        """Initialize switch with improved error handling."""
        self._session_manager = session_manager
        self._is_on = False
        self._attr_unique_id = f"{self._session_manager._host}_{self.name}"
        self._error_count = 0
        self._last_update = None
        self._restored = False
        self.hass = session_manager.hass

    async def async_added_to_hass(self) -> None:
        """Handle entity added to HA."""
        await super().async_added_to_hass()
        
        # Restore previous state
        if last_state := await self.async_get_last_state():
            self._is_on = last_state.state == "on"
            self._restored = True

        # Register with session manager
        await self._session_manager.register_entity(self)

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity removal."""
        await self._session_manager.unregister_entity(self)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._session_manager.available

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self._is_on

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._session_manager._host)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": self._session_manager.model,
            "sw_version": self._session_manager.firmware_version,
            "serial_number": self._session_manager.station_id,
            "configuration_url": f"http://{self._session_manager._host}",
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return {
            "error_count": self._error_count,
            "last_update": self._last_update.isoformat() if self._last_update else None,
            "restored": self._restored,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on with retry logic."""
        attempts = 0
        while attempts < self._max_retry_attempts:
            try:
                success, result = await self._execute_turn_on()
                if success:
                    self._is_on = True
                    self._error_count = 0
                    self.async_write_ha_state()
                    return
                    
                attempts += 1
                self._error_count += 1
                _LOGGER.error(
                    "Failed to turn on %s (attempt %d/%d): %s",
                    self.name,
                    attempts,
                    self._max_retry_attempts,
                    result.get("error", "Unknown error")
                )
                if attempts < self._max_retry_attempts:
                    await asyncio.sleep(self._retry_delay)
                    
            except Exception as err:
                attempts += 1
                self._error_count += 1
                _LOGGER.error(
                    "Error turning on %s (attempt %d/%d): %s",
                    self.name,
                    attempts,
                    self._max_retry_attempts,
                    str(err)
                )
                if attempts < self._max_retry_attempts:
                    await asyncio.sleep(self._retry_delay)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off with retry logic."""
        attempts = 0
        while attempts < self._max_retry_attempts:
            try:
                success, result = await self._execute_turn_off()
                if success:
                    self._is_on = False
                    self._error_count = 0
                    self.async_write_ha_state()
                    return
                    
                attempts += 1
                self._error_count += 1
                _LOGGER.error(
                    "Failed to turn off %s (attempt %d/%d): %s",
                    self.name,
                    attempts,
                    self._max_retry_attempts,
                    result.get("error", "Unknown error")
                )
                if attempts < self._max_retry_attempts:
                    await asyncio.sleep(self._retry_delay)
                    
            except Exception as err:
                attempts += 1
                self._error_count += 1
                _LOGGER.error(
                    "Error turning off %s (attempt %d/%d): %s",
                    self.name,
                    attempts,
                    self._max_retry_attempts,
                    str(err)
                )
                if attempts < self._max_retry_attempts:
                    await asyncio.sleep(self._retry_delay)

    async def _execute_turn_on(self) -> tuple[bool, dict]:
        """Execute turn on command."""
        raise NotImplementedError

    async def _execute_turn_off(self) -> tuple[bool, dict]:
        """Execute turn off command."""
        raise NotImplementedError

    def _handle_state_update(self, state: dict) -> None:
        """Handle state update."""
        raise NotImplementedError

class EveusStopChargingSwitch(BaseEveusSwitch):
    """Charging control switch."""

    _attr_name = "Stop Charging"
    _attr_icon = "mdi:ev-station"
    _attr_entity_category = EntityCategory.CONFIG

    async def _execute_turn_on(self) -> tuple[bool, dict]:
        """Execute charging enable."""
        return await self._session_manager.send_command(
            CMD_EVSE_ENABLED,
            1,
            verify=True
        )

    async def _execute_turn_off(self) -> tuple[bool, dict]:
        """Execute charging disable."""
        return await self._session_manager.send_command(
            CMD_EVSE_ENABLED,
            0,
            verify=True
        )

    def _handle_state_update(self, state: dict) -> None:
        """Handle state update."""
        try:
            self._is_on = bool(state.get("evseEnabled"))
            self._last_update = self.hass.loop.time()
        except (TypeError, ValueError) as err:
            self._error_count += 1
            _LOGGER.error(
                "Error parsing evseEnabled state: %s",
                str(err)
            )

class EveusOneChargeSwitch(BaseEveusSwitch):
    """One charge mode switch."""

    _attr_name = "One Charge"
    _attr_icon = "mdi:lightning-bolt"
    _attr_entity_category = EntityCategory.CONFIG

    async def _execute_turn_on(self) -> tuple[bool, dict]:
        """Enable one charge mode."""
        return await self._session_manager.send_command(
            CMD_ONE_CHARGE,
            1,
            verify=True
        )

    async def _execute_turn_off(self) -> tuple[bool, dict]:
        """Disable one charge mode."""
        return await self._session_manager.send_command(
            CMD_ONE_CHARGE,
            0,
            verify=True
        )

    def _handle_state_update(self, state: dict) -> None:
        """Handle state update."""
        try:
            self._is_on = bool(state.get("oneCharge"))
            self._last_update = self.hass.loop.time()
        except (TypeError, ValueError) as err:
            self._error_count += 1
            _LOGGER.error(
                "Error parsing oneCharge state: %s",
                str(err)
            )

class EveusResetCounterASwitch(BaseEveusSwitch):
    """Reset counter switch."""

    _attr_name = "Reset Counter A"
    _attr_icon = "mdi:counter"
    _attr_entity_category = EntityCategory.CONFIG

    async def _execute_turn_on(self) -> tuple[bool, dict]:
        """Reset counter."""
        return await self._session_manager.send_command(
            CMD_RESET_COUNTER,
            0,
            verify=False
        )

    async def _execute_turn_off(self) -> tuple[bool, dict]:
        """Reset command for off state."""
        return await self._execute_turn_on()

    def _handle_state_update(self, state: dict) -> None:
        """Handle state update."""
        try:
            iem1_value = state.get("IEM1")
            if iem1_value in (None, "null", "", "undefined", "ERROR"):
                self._is_on = False
            else:
                self._is_on = float(iem1_value) != 0
            self._last_update = self.hass.loop.time()
        except (TypeError, ValueError) as err:
            self._error_count += 1
            _LOGGER.error(
                "Error parsing IEM1 state: %s",
                str(err)
            )
            self._is_on = False

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Eveus switches with improved error handling."""
    session_manager = hass.data[DOMAIN][entry.entry_id]["session_manager"]

    switches = [
        EveusStopChargingSwitch(session_manager),
        EveusOneChargeSwitch(session_manager),
        EveusResetCounterASwitch(session_manager),
    ]

    # Store entity references
    hass.data[DOMAIN][entry.entry_id]["entities"]["switch"] = {
        switch.unique_id: switch for switch in switches
    }

    async def async_update_switches(*_) -> None:
        """Update switches with error handling."""
        if not hass.is_running:
            return

        try:
            # Get state once for all switches
            state = await session_manager.get_state(force_refresh=True)
            
            for switch in switches:
                try:
                    switch._handle_state_update(state)
                    switch.async_write_ha_state()
                except Exception as err:
                    _LOGGER.error(
                        "Error updating switch %s: %s",
                        switch.name,
                        str(err),
                        exc_info=True
                    )
                
                await asyncio.sleep(0.1)
                    
        except Exception as err:
            _LOGGER.error("Failed to update switches: %s", err)

        # Update interval based on charging state
        try:
            is_charging = any(s.is_on for s in switches)
            interval = UPDATE_INTERVAL_CHARGING if is_charging else UPDATE_INTERVAL_IDLE
            
            async_track_time_interval(
                hass,
                async_update_switches,
                interval
            )
        except Exception as err:
            _LOGGER.error("Failed to adjust update interval: %s", err)

    # Add entities
    async_add_entities(switches)

    # Setup initial update
    if not hass.is_running:
        hass.bus.async_listen_once(
            "homeassistant_start",
            async_update_switches
        )
    else:
        await async_update_switches()
