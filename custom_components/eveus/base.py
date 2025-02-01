"""Base implementations for Eveus integration."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

import aiohttp
from homeassistant.helpers.entity import Entity
from homeassistant.core import callback

from .const import DOMAIN
from .exceptions import EveusConnectionError, EveusCommandError, EveusAuthError

_LOGGER = logging.getLogger(__name__)

# Constants for API interaction
MAX_RETRIES = 3
RETRY_DELAY = 2
COMMAND_TIMEOUT = 5
UPDATE_TIMEOUT = 10
MIN_UPDATE_INTERVAL = 2
MIN_COMMAND_INTERVAL = 1

class EveusBaseConnection:
    """Base class for Eveus API communication."""

    def __init__(self, host: str, username: str, password: str) -> None:
        """Initialize connection."""
        self._host = host
        self._username = username
        self._password = password
        self._session = None
        self._available = True
        self._error_count = 0
        self._max_errors = 3
        self._command_lock = asyncio.Lock()
        self._update_lock = asyncio.Lock()
        self._last_command_time = 0
        self._last_update = 0
        self._state_data = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create client session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10, connect=5)
            connector = aiohttp.TCPConnector(limit=1, force_close=True)
            self._session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return self._session

    async def _send_command(self, command: str, value: Any, verify_command: bool = True) -> bool:
        """Send command with retry logic."""
        current_time = time.time()
        if current_time - self._last_command_time < MIN_COMMAND_INTERVAL:
            await asyncio.sleep(MIN_COMMAND_INTERVAL)

        async with self._command_lock:
            for attempt in range(MAX_RETRIES):
                try:
                    session = await self._get_session()
                    async with session.post(
                        f"http://{self._host}/pageEvent",
                        auth=aiohttp.BasicAuth(self._username, self._password),
                        headers={"Content-type": "application/x-www-form-urlencoded"},
                        data=f"pageevent={command}&{command}={value}",
                        timeout=COMMAND_TIMEOUT,
                    ) as response:
                        if response.status == 401:
                            raise EveusAuthError("Invalid authentication")
                        response.raise_for_status()
                        response_text = await response.text()
                        
                        if "error" in response_text.lower():
                            raise EveusCommandError(f"Error in response: {response_text}")

                        if verify_command:
                            await self._verify_command(command, value)

                        self._available = True
                        self._last_command_time = current_time
                        self._error_count = 0
                        return True

                except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                    if attempt + 1 < MAX_RETRIES:
                        await asyncio.sleep(RETRY_DELAY * (2 ** attempt))
                        continue
                    raise EveusConnectionError(f"Connection error: {str(err)}") from err
                except Exception as err:
                    if attempt + 1 < MAX_RETRIES:
                        await asyncio.sleep(RETRY_DELAY * (2 ** attempt))
                        continue
                    raise EveusError(f"Command error: {str(err)}") from err

            return False

    async def _verify_command(self, command: str, value: Any) -> bool:
        """Verify command execution."""
        session = await self._get_session()
        async with session.post(
            f"http://{self._host}/main",
            auth=aiohttp.BasicAuth(self._username, self._password),
            timeout=COMMAND_TIMEOUT,
        ) as response:
            response.raise_for_status()
            verify_data = await response.json()
            return self._validate_command_response(verify_data, command, value)

    def _validate_command_response(self, response_data: dict, command: str, value: Any) -> bool:
        """Validate command response data."""
        if not isinstance(response_data, dict):
            return False

        try:
            if command == "evseEnabled":
                return response_data.get("evseEnabled") == value
            elif command == "oneCharge":
                return response_data.get("oneCharge") == value
            elif command == "rstEM1":
                return True  # Reset commands don't need validation
            elif command == "currentSet":
                return float(response_data.get("currentSet", 0)) == float(value)
            return False
        except (TypeError, ValueError) as err:
            _LOGGER.debug("Validation error for command %s: %s", command, str(err))
            return False

    async def async_update(self) -> None:
        """Update device state."""
        current_time = time.time()
        if current_time - self._last_update < MIN_UPDATE_INTERVAL:
            return

        async with self._update_lock:
            for attempt in range(MAX_RETRIES):
                try:
                    session = await self._get_session()
                    async with session.post(
                        f"http://{self._host}/main",
                        auth=aiohttp.BasicAuth(self._username, self._password),
                        timeout=UPDATE_TIMEOUT,
                    ) as response:
                        if response.status == 401:
                            raise EveusAuthError("Invalid authentication")
                        response.raise_for_status()
                        self._state_data = await response.json()
                        self._available = True
                        self._error_count = 0
                        self._last_update = current_time
                        return

                except Exception as err:
                    if attempt + 1 < MAX_RETRIES:
                        await asyncio.sleep(RETRY_DELAY * (2 ** attempt))
                        continue
                    self._error_count += 1
                    self._available = self._error_count < self._max_errors
                    raise EveusError(f"Update error: {str(err)}") from err

    @property
    def state_data(self) -> dict:
        """Return current state data."""
        return self._state_data

    @property
    def available(self) -> bool:
        """Return if connection is available."""
        return self._available

    async def async_close(self) -> None:
        """Close connection."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

class EveusBaseEntity(Entity):
    """Base entity for Eveus integration."""

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the entity."""
        self._connection = connection
        self._attr_has_entity_name = True
        self._attr_should_poll = False

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._connection.available

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._connection._host)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": f"Eveus ({self._connection._host})",
        }

    async def async_update(self) -> None:
        """Update entity state."""
        await self._connection.async_update()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up resources when entity is removed."""
        await self._connection.async_close()
