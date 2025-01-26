"""Shared mixins for Eveus integration."""
from __future__ import annotations
import logging
import asyncio
import aiohttp
from typing import Any

from homeassistant.const import CONF_HOST
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    ATTR_FIRMWARE_VERSION,  # "verFWMain"
    ATTR_SERIAL_NUMBER,     # "serialNum"
)

_LOGGER = logging.getLogger(__name__)

class SessionMixin:
    """Mixin for session management."""
    
    def __init__(self, host: str, username: str, password: str) -> None:
        """Initialize session mixin."""
        self._host = host
        self._username = username
        self._password = password
        self._available = True
        self._error_count = 0
        self._max_errors = 3
        self._command_lock = asyncio.Lock()
        self._data = {}
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get client session from Home Assistant."""
        return async_get_clientsession(self.hass)

class DeviceInfoMixin:
    """Mixin for device info."""
    
    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        # First try to get data from updater
        if hasattr(self, '_updater') and self._updater and hasattr(self._updater, 'data'):
            data = self._updater.data or {}
            host = self._updater._host
            _LOGGER.debug("Device Info from updater data: %s", data)
        else:
            data = getattr(self, '_data', {})
            host = getattr(self, '_host', None)
            _LOGGER.debug("Device Info from self data: %s", data)

        if not host:
            return {}

        # Debug logging
        _LOGGER.debug(
            "Looking for firmware version at '%s': %s", 
            ATTR_FIRMWARE_VERSION, 
            data.get(ATTR_FIRMWARE_VERSION)
        )
        _LOGGER.debug(
            "Looking for serial number at '%s': %s", 
            ATTR_SERIAL_NUMBER, 
            data.get(ATTR_SERIAL_NUMBER)
        )

        # Get raw values
        firmware = data.get(ATTR_FIRMWARE_VERSION)
        serial = data.get(ATTR_SERIAL_NUMBER)

        info = {
            "identifiers": {(DOMAIN, host)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": "Eveus Smart Charger",
            "configuration_url": f"http://{host}"
        }

        # Only add if we have actual values
        if firmware is not None and str(firmware).strip():
            info["sw_version"] = str(firmware).strip()
            _LOGGER.debug("Added firmware version: %s", info["sw_version"])
            
        if serial is not None and str(serial).strip():
            info["hw_version"] = str(serial).strip()
            _LOGGER.debug("Added serial number: %s", info["hw_version"])

        _LOGGER.debug("Final device info: %s", info)
        return info

class ErrorHandlingMixin:
    """Mixin for error handling."""
    
    async def handle_error(self, err: Exception, context: str = "") -> None:
        """Handle errors with consistent logging and state management."""
        error_msg = f"{context}: {str(err)}" if context else str(err)
        
        if isinstance(err, (asyncio.TimeoutError, aiohttp.ClientError)):
            _LOGGER.warning("Connection error %s", error_msg)
            if hasattr(self, '_error_count'):
                self._error_count += 1
                self._available = self._error_count < self._max_errors
        else:
            _LOGGER.error("Unexpected error %s", error_msg)
            if hasattr(self, '_available'):
                self._available = False
