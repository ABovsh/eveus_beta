"""Support for Eveus switches."""
from __future__ import annotations

import logging
import asyncio
import time
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
from .mixins import SessionMixin, DeviceInfoMixin, ErrorHandlingMixin

_LOGGER = logging.getLogger(__name__)

class BaseEveusSwitch(SessionMixin, DeviceInfoMixin, ErrorHandlingMixin, SwitchEntity):
    """Base class for Eveus switches."""
    
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    
    def __init__(self, host: str, username: str, password: str) -> None:
        """Initialize switch."""
        super().__init__(host, username, password)
        self._is_on = False
        self._last_command_time = 0
        self._min_command_interval = 1
        self._command_timeout = 5
        self._max_retries = 3
        self._retry_delay = 2

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"{self._host}_{self.name}"

    @property
    def is_on(self) -> bool:
        """Return switch state."""
        return self._is_on

    async def _send_command(self, command: str, value: int, verify: bool = True) -> bool:
        """Send command with retry logic."""
        current_time = time.time()
        if current_time - self._last_command_time < self._min_command_interval:
            await asyncio.sleep(self._min_command_interval)
            
        async with self._command_lock:
            for attempt in range(self._max_retries):
                try:
                    session = await self._get_session()
                    async with session.post(
                        f"http://{self._host}/pageEvent",
                        auth=aiohttp.BasicAuth(self._username, self._password),
                        headers={"Content-type": "application/x-www-form-urlencoded"},
                        data=f"pageevent={command}&{command}={value}",
                        timeout=self._command_timeout
                    ) as response:
                        response.raise_for_status()
                        response_text = await response.text()
                        
                        if "error" in response_text.lower():
                            raise ValueError(f"Error in response: {response_text}")

                        if verify:
                            verify_data = await self._verify_command(session, command, value)
                            if not verify_data:
                                raise ValueError("Command verification failed")

                        self._available = True
                        self._last_command_time = current_time
                        self._error_count = 0
                        return True

                except Exception as err:
                    if attempt + 1 < self._max_retries:
                        await asyncio.sleep(self._retry_delay * (2 ** attempt))
                        continue
                    await self.handle_error(err, f"Command {command} failed")
                    return False

            return False

    async def _verify_command(self, session: aiohttp.ClientSession, command: str, value: int) -> bool:
        """Verify command execution."""
        try:
            async with session.post(
                f"http://{self._host}/main",
                auth=aiohttp.BasicAuth(self._username, self._password),
                timeout=self._command_timeout
            ) as response:
                response.raise_for_status()
                data = await response.json()
                
                if command == "evseEnabled":
                    return data.get("evseEnabled") == value
                elif command == "oneCharge":
                    return data.get("oneCharge") == value
                return True
                
        except Exception as err:
            await self.handle_error(err, "Verification error")
            return False

    async def async_will_remove_from_hass(self) -> None:
        """Clean up resources."""
        await self._cleanup_session()

class EveusStopChargingSwitch(BaseEveusSwitch):
    """Charging control switch."""
    _attr_name = "Stop Charging"
    _attr_icon = "mdi:ev-station"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable charging."""
        if await self._send_command("evseEnabled", 1):
            self._is_on = True

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable charging."""
        if await self._send_command("evseEnabled", 0):
            self._is_on = False

    async def async_update(self) -> None:
        """Update state."""
        try:
            session = await self._get_session()
            async with session.post(
                f"http://{self._host}/main",
                auth=aiohttp.BasicAuth(self._username, self._password),
                timeout=self._command_timeout
            ) as response:
                data = await response.json()
                self._is_on = data.get("evseEnabled") == 1
                self._available = True
        except Exception as err:
            await self.handle_error(err, "Update error")

class EveusOneChargeSwitch(BaseEveusSwitch):
    """One charge mode switch."""
    _attr_name = "One Charge"
    _attr_icon = "mdi:lightning-bolt"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable one charge."""
        if await self._send_command("oneCharge", 1):
            self._is_on = True

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable one charge."""
        if await self._send_command("oneCharge", 0):
            self._is_on = False

    async def async_update(self) -> None:
        """Update state."""
        try:
            session = await self._get_session()
            async with session.post(
                f"http://{self._host}/main",
                auth=aiohttp.BasicAuth(self._username, self._password),
                timeout=self._command_timeout
            ) as response:
                data = await response.json()
                self._is_on = data.get("oneCharge") == 1
                self._available = True
        except Exception as err:
            await self.handle_error(err, "Update error")

class EveusResetCounterASwitch(BaseEveusSwitch):
    """Reset counter A switch."""
    _attr_name = "Reset Counter A"
    _attr_icon = "mdi:counter"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Reset counter."""
        if await self._send_command("rstEM1", 0, verify=False):
            self._is_on = False

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Reset action for off state."""
        if await self._send_command("rstEM1", 0, verify=False):
            self._is_on = False

    async def async_update(self) -> None:
        """Update state."""
        try:
            session = await self._get_session()
            async with session.post(
                f"http://{self._host}/main",
                auth=aiohttp.BasicAuth(self._username, self._password),
                timeout=self._command_timeout
            ) as response:
                data = await response.json()
                try:
                    iem1 = float(data.get("IEM1", 0))
                    self._is_on = iem1 != 0
                except (ValueError, TypeError):
                    self._is_on = False
                self._available = True
        except Exception as err:
            await self.handle_error(err, "Update error")

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
