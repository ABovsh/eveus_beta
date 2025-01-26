"""Shared mixins for Eveus integration."""
from __future__ import annotations
import logging
import asyncio
import aiohttp
from typing import Any

from homeassistant.const import CONF_HOST

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
        self._session = None
        self._available = True
        self._error_count = 0
        self._max_errors = 3
        self._command_lock = asyncio.Lock()
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            connector = aiohttp.TCPConnector(limit=1, force_close=True)
            self._session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return self._session

    async def _cleanup_session(self) -> None:
        """Clean up session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

class DeviceInfoMixin:
    """Mixin for device info."""
    
    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        host = getattr(self, '_host', None)
        if not host:
            if hasattr(self, '_updater'):
                host = self._updater._host
            else:
                return {}

        info = {
            "identifiers": {(DOMAIN, host)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": f"Eveus ({host})",
        }

        # Add firmware version if available
        if hasattr(self, '_updater') and self._updater.data:
            firmware = self._updater.data.get(ATTR_FIRMWARE_VERSION)
            if firmware:
                info["sw_version"] = firmware
                
            serial = self._updater.data.get(ATTR_SERIAL_NUMBER)
            if serial:
                info["hw_version"] = serial

        return info

class ErrorHandlingMixin:
    """Mixin for error handling."""
    
    async def handle_error(self, err: Exception, context: str = "") -> None:
        """Handle errors with consistent logging and state management."""
        error_msg = f"{context}: {str(err)}" if context else str(err)
        
        if isinstance(err, (asyncio.TimeoutError, aiohttp.ClientError)):
            _LOGGER.error("Connection error %s", error_msg)
            if hasattr(self, '_error_count'):
                self._error_count += 1
                self._available = self._error_count < getattr(self, '_max_errors', 3)
        else:
            _LOGGER.error("Unexpected error %s", error_msg)
            if hasattr(self, '_available'):
                self._available = False
