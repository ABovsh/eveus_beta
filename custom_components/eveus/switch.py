"""Support for Eveus switches."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.const import (
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
)

from .const import DOMAIN
from .mixins import SessionMixin, DeviceInfoMixin, ErrorHandlingMixin, ValidationMixin

_LOGGER = logging.getLogger(__name__)

class BaseEveusSwitch(SessionMixin, DeviceInfoMixin, ErrorHandlingMixin, ValidationMixin, SwitchEntity):
    """Base class for Eveus switches."""
    
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    
    def __init__(self, host: str, username: str, password: str) -> None:
        """Initialize switch."""
        super().__init__(host, username, password)
        self._is_on = False

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"{self._host}_{self.name}"

    @property
    def is_on(self) -> bool:
        """Return switch state."""
        return self._is_on

    async def _verify_command(self, command: str, value: int) -> bool:
        """Verify command execution."""
        data = await self.async_api_call("main")
        if not data:
            return False
            
        if command == "evseEnabled":
            return data.get("evseEnabled") == value
        elif command == "oneCharge":
            return data.get("oneCharge") == value
        return True

    async def async_send_command(self, command: str, value: int, verify: bool = True) -> bool:
        """Send command with verification."""
        data = {"pageevent": command, command: value}
        result = await self.async_api_call("pageEvent", data=data)
        
        if not result:
            return False
            
        if verify:
            return await self._verify_command(command, value)
        return True

class EveusStopChargingSwitch(BaseEveusSwitch):
    """Charging control switch."""
    _attr_name = "Stop Charging"
    _attr_icon = "mdi:ev-station"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable charging."""
        if await self.async_send_command("evseEnabled", 1):
            self._is_on = True

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable charging."""
        if await self.async_send_command("evseEnabled", 0):
            self._is_on = False

    async def async_update(self) -> None:
        """Update state."""
        data = await self.async_api_call("main")
        if data:
            self._is_on = data.get("evseEnabled") == 1

class EveusOneChargeSwitch(BaseEveusSwitch):
    """One charge mode switch."""
    _attr_name = "One Charge"
    _attr_icon = "mdi:lightning-bolt"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable one charge."""
        if await self.async_send_command("oneCharge", 1):
            self._is_on = True

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable one charge."""
        if await self.async_send_command("oneCharge", 0):
            self._is_on = False

    async def async_update(self) -> None:
        """Update state."""
        data = await self.async_api_call("main")
        if data:
            self._is_on = data.get("oneCharge") == 1

class EveusResetCounterASwitch(BaseEveusSwitch):
    """Reset counter A switch."""
    _attr_name = "Reset Counter A"
    _attr_icon = "mdi:counter"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Reset counter."""
        if await self.async_send_command("rstEM1", 0, verify=False):
            self._is_on = False

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Reset action for off state."""
        if await self.async_send_command("rstEM1", 0, verify=False):
            self._is_on = False

    async def async_update(self) -> None:
        """Update state."""
        data = await self.async_api_call("main")
        if data:
            try:
                iem1 = float(data.get("IEM1", 0))
                self._is_on = iem1 != 0
            except (ValueError, TypeError):
                self._is_on = False

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches."""
    switches = [
        EveusStopChargingSwitch(
            entry.data[CONF_HOST],
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD]
        ),
        EveusOneChargeSwitch(
            entry.data[CONF_HOST],
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD]
        ),
        EveusResetCounterASwitch(
            entry.data[CONF_HOST],
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD]
        )
    ]

    if "entities" not in hass.data[DOMAIN][entry.entry_id]:
        hass.data[DOMAIN][entry.entry_id]["entities"] = {}

    hass.data[DOMAIN][entry.entry_id]["entities"]["switch"] = {
        switch.unique_id: switch for switch in switches
    }

    async_add_entities(switches)
