# File: custom_components/eveus/switch.py
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
from homeassistant.util import dt as dt_util

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
        self.entity_id = f"switch.eveus_{self.name.lower().replace(' ', '_')}"
        self._error_count = 0
        self._last_update = None
        self._restored = False
        self.hass = session_manager.hass

    async def async_added_to_hass(self) -> None:
        """Handle entity added to HA."""
        await super().async_added_to_hass()
        
        if last_state := await self.async_get_last_state():
            self._is_on = last_state.state == "on"
            self._restored = True

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
            "name": "Eveus",
            "manufacturer": "Eveus",
            "model": "Eveus",
            "sw_version": self._session_manager.firmware_version,
            "hw_version": f"Current range: {self._session_manager.capabilities['min_current']}-{self._session_manager.capabilities['max_current']}A",
            "configuration_url": f"http://{self._session_manager._host}",
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = {
            "error_count": self._error_count,
            "restored": self._restored,
        }
        if self._last_update is not None:
            if isinstance(self._last_update, (int, float)):
                attrs["last_update"] = dt_util.utc_from_timestamp(self._last_update).isoformat()
            else:
                attrs["last_update"] = self._last_update.isoformat()
        return attrs

    async def _execute_command(self, command: bool) -> None:
        """Execute turn on/off command with retry logic."""
        method = self._execute_turn_on if command else self._execute_turn_off
        attempts = 0
        
        while attempts < self._max_retry_attempts:
            try:
                success, result = await method()
                if success:
                    self._is_on = command
                    self._error_count = 0
                    self._last_update = dt_util.utcnow()
                    self.async_write_ha_state()
                    return
                    
                attempts += 1
                self._error_count += 1
                _LOGGER.error(
                    "Failed to turn %s %s (attempt %d/%d): %s",
                    "on" if command else "off",
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
                    "Error turning %s %s (attempt %d/%d): %s",
                    "on" if command else "off",
                    self.name,
                    attempts,
                    self._max_retry_attempts,
                    str(err)
                )
                if attempts < self._max_retry_attempts:
                    await asyncio.sleep(self._retry_delay)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on with retry logic."""
        await self._execute_command(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off with retry logic."""
        await self._execute_command(False)

    async def _execute_turn_on(self) -> tuple[bool, dict]:
        """Execute turn on command."""
        raise NotImplementedError

    async def _execute_turn_off(self) -> tuple[bool, dict]:
        """Execute turn off command."""
        raise NotImplementedError

class EveusStopChargingSwitch(BaseEveusSwitch):
    """Charging control switch."""

    _attr_name = "Stop Charging"
    _attr_icon = "mdi:ev-station"
    _attr_entity_category = EntityCategory.CONFIG
    _attribute = CMD_EVSE_ENABLED

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

class EveusOneChargeSwitch(BaseEveusSwitch):
    """One charge mode switch."""

    _attr_name = "One Charge"
    _attr_icon = "mdi:lightning-bolt"
    _attr_entity_category = EntityCategory.CONFIG
    _attribute = CMD_ONE_CHARGE

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

class EveusResetCounterASwitch(BaseEveusSwitch):
    """Reset counter switch."""

    _attr_name = "Reset Counter A"
    _attr_icon = "mdi:counter"
    _attr_entity_category = EntityCategory.CONFIG
    _attribute = CMD_RESET_COUNTER

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

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Eveus switches."""
    session_manager = hass.data[DOMAIN][entry.entry_id]["session_manager"]

    switches = [
        EveusStopChargingSwitch(session_manager),
        EveusOneChargeSwitch(session_manager),
        EveusResetCounterASwitch(session_manager),
    ]

    hass.data[DOMAIN][entry.entry_id]["entities"]["switch"] = {
        switch.unique_id: switch for switch in switches
    }

    async def async_update_switches(*_) -> None:
        """Update switches with error handling."""
        if not hass.is_running:
            return

        try:
            # Get current state
            state = await session_manager.get_state(force_refresh=True)
            
            # Update switches
            for switch in switches:
                try:
                    if state.get(switch._attribute) is not None:
                        switch._is_on = bool(int(state.get(switch._attribute, 0)))
                        switch._last_update = dt_util.utcnow()
                        switch.async_write_ha_state()
                except Exception as err:
                    _LOGGER.error(
                        "Error updating switch %s: %s",
                        switch.name,
                        str(err)
                    )
                await asyncio.sleep(0.1)

        except Exception as err:
            _LOGGER.error("Failed to update switches: %s", str(err))

    async_add_entities(switches)

    if hass.is_running:
        await async_update_switches()
    else:
        hass.bus.async_listen_once(
            "homeassistant_start",
            async_update_switches
        )

    async_track_time_interval(
        hass,
        async_update_switches,
        UPDATE_INTERVAL_IDLE
    )
