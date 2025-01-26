"""Shared mixins for Eveus integration."""
from __future__ import annotations
import logging
import asyncio
import aiohttp
from typing import Any, Optional

from homeassistant.const import CONF_HOST

from .const import (
    DOMAIN,
    ATTR_FIRMWARE_VERSION,
    ATTR_SERIAL_NUMBER,
)

_LOGGER = logging.getLogger(__name__)

class BaseMixin:
    """Base mixin with common session and error handling methods."""
    
    def __init__(self, host: str, username: str, password: str) -> None:
        """Initialize base mixin."""
        self._host = host
        self._username = username
        self._password = password
        self._session = None
        self._available = True
        self._error_count = 0
        self._max_errors = 3
        self._command_lock = asyncio.Lock()
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with robust configuration."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            connector = aiohttp.TCPConnector(limit=1, force_close=True)
            self._session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return self._session

    async def _cleanup_session(self) -> None:
        """Clean up session safely."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def handle_error(self, err: Exception, context: str = "") -> None:
        """Centralized error handling with logging and state management."""
        error_msg = f"{context}: {str(err)}" if context else str(err)
        
        if isinstance(err, (asyncio.TimeoutError, aiohttp.ClientError)):
            _LOGGER.error("Connection error %s", error_msg)
            self._error_count += 1
            self._available = self._error_count < self._max_errors
        else:
            _LOGGER.error("Unexpected error %s", error_msg)
            self._available = False

class SessionMixin(BaseMixin):
    """Explicit session management mixin."""
    pass

class DeviceInfoMixin:
    """Enhanced device information mixin."""
    
    @property
    def device_info(self) -> dict[str, Any]:
        """Return comprehensive device information."""
        updater = getattr(self, '_updater', None)
        host = getattr(self, '_host', None) or (updater._host if updater else None)
        
        if not host:
            return {}

        info = {
            "identifiers": {(DOMAIN, host)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": f"Eveus ({host})",
        }

        if updater and updater.data:
            firmware = updater.data.get(ATTR_FIRMWARE_VERSION)
            serial = updater.data.get(ATTR_SERIAL_NUMBER)
            
            if firmware:
                info["sw_version"] = firmware
            if serial:
                info["hw_version"] = serial

        return info

class ErrorHandlingMixin(BaseMixin):
    """Comprehensive error handling capabilities."""
    pass
