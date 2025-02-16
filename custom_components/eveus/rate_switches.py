"""Support for Eveus rate control switches."""
from __future__ import annotations

import logging
import asyncio
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.core import State

from .common import BaseEveusEntity
from .const import RATE_COMMANDS
from .utils import get_safe_value

_LOGGER = logging.getLogger(__name__)

class EveusRateSwitchBase(BaseEveusEntity, SwitchEntity):
    """Base switch for Eveus rate control."""

    _attr_entity_category = EntityCategory.CONFIG
    _command: str = None
    _state_key: str = None

    def __init__(self, updater) -> None:
        """Initialize the switch."""
        super().__init__(updater)
        self._command_lock = asyncio.Lock()
        self._pending_state = None
        self._initial_update = False

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        if self._pending_state is not None:
            return self._pending_state
        return bool(get_safe_value(self._updater.data, self._state_key, int, 0))

    async def _async_send_command(self, command_value: int) -> None:
        """Send command to device."""
        async with self._command_lock:
            self._pending_state = bool(command_value)
            self.async_write_ha_state()
            
            await self._updater.send_command(self._command, command_value)

    async def _async_restore_state(self, state: State) -> None:
        """Restore previous state."""
        try:
            if state.state == "on":
                await self._async_send_command(1)
            else:
                await self._async_send_command(0)
        except Exception as err:
            _LOGGER.error("Error restoring state for %s: %s", self.name, err)

class EveusRate2EnableSwitch(EveusRateSwitchBase):
    """Switch to enable/disable Rate 2."""

    ENTITY_NAME = "Rate 2 Enable"
    _attr_icon = "mdi:toggle-switch"
    _command = RATE_COMMANDS["RATE2_ENABLE"]
    _state_key = "tarifAEnable"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable Rate 2."""
        await self._async_send_command(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable Rate 2."""
        await self._async_send_command(0)

class EveusRate3EnableSwitch(EveusRateSwitchBase):
    """Switch to enable/disable Rate 3."""

    ENTITY_NAME = "Rate 3 Enable"
    _attr_icon = "mdi:toggle-switch"
    _command = RATE_COMMANDS["RATE3_ENABLE"]
    _state_key = "tarifBEnable"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable Rate 3."""
        await self._async_send_command(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable Rate 3."""
        await self._async_send_command(0)
