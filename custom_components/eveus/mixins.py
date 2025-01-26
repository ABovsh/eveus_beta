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
    ATTR_FIRMWARE_VERSION,
    ATTR_SERIAL_NUMBER,
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

    async def _make_request(self) -> dict:
        """Make an authenticated request to get device data."""
        try:
            session = await self._get_session()
            async with session.post(
                f"http://{self._host}/main",
                auth=aiohttp.BasicAuth(self._username, self._password),
                timeout=10
            ) as response:
                response.raise_for_status()
                self._data = await response.json()
                self._error_count = 0
                self._available = True
                return self._data
        except Exception as err:
            self._error_count += 1
            self._available = self._error_count < self._max_errors
            raise err

class DeviceInfoMixin:
    """Mixin for device info."""
    
    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        data = {}
        host = None

        # Get data from updater if available
        if hasattr(self, '_updater'):
            data = self._updater.data if self._updater.data else {}
            host = self._updater._host
        # Get data from self if no updater
        else:
            data = getattr(self, '_data', {})
            host = getattr(self, '_host', None)

        if not host:
            return {}

        # Get firmware and serial number from data
        firmware = str(data.get(ATTR_FIRMWARE_VERSION, '')).strip()
        serial = str(data.get(ATTR_SERIAL_NUMBER, '')).strip()

        info = {
            "identifiers": {(DOMAIN, host)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": "Eveus Smart Charger",
            "configuration_url": f"http://{host}",
        }

        # Only add version info if we have actual data
        if firmware:
            info["sw_version"] = firmware
        if serial:
            info["hw_version"] = serial

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
