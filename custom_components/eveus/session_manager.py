"""Optimized session manager for Eveus integration."""
from __future__ import annotations

import logging
import asyncio
import time
from typing import Any, Optional
from datetime import datetime

import aiohttp
from aiohttp import ClientTimeout, ClientError, ClientResponse, ClientSession

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    DOMAIN,
    UPDATE_INTERVAL,
    API_ENDPOINT_MAIN,
    API_ENDPOINT_EVENT,
    COMMAND_TIMEOUT,
    MAX_RETRIES,
    RETRY_DELAY,
    MIN_COMMAND_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

class SessionManager:
    """Optimized session manager for Eveus."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        username: str,
        password: str,
        entry_id: str,
    ) -> None:
        """Initialize session manager."""
        self.hass = hass
        self._host = host
        self._username = username
        self._password = password
        self._entry_id = entry_id
        self._firmware_version = None
        self._station_id = None
        
        # Basic state management
        self._base_url = f"http://{self._host}"
        self._last_state: Optional[dict] = None
        self._last_update = 0
        self._request_count = 0
        
        # Connection state
        self._available = True
        self._last_command_time = 0
        self._error_count = 0
        self._current_retry_delay = RETRY_DELAY
        self._last_successful_connection: Optional[datetime] = None
        
        # Timeouts
        self._timeout = ClientTimeout(
            total=COMMAND_TIMEOUT,
            connect=3,
            sock_connect=3,
            sock_read=5
        )

        # Setup periodic updates
        async_track_time_interval(
            hass,
            self._async_update_data,
            UPDATE_INTERVAL
        )

    async def _async_update_data(self, *_) -> None:
        """Update state periodically."""
        try:
            await self.get_state(force_refresh=True)
        except Exception as err:
            _LOGGER.error("Error in periodic update: %s", str(err))

    async def send_command(
        self,
        command: str,
        value: Any,
        verify: bool = True,
        retry_count: int = MAX_RETRIES,
    ) -> tuple[bool, dict[str, Any]]:
        """Send command with error handling and verification."""
        current_time = time.time()
        
        # Rate limiting
        time_since_last = current_time - self._last_command_time
        if time_since_last < MIN_COMMAND_INTERVAL:
            await asyncio.sleep(MIN_COMMAND_INTERVAL - time_since_last)

        for attempt in range(retry_count):
            try:
                self._request_count += 1
                async with aiohttp.ClientSession(
                    auth=aiohttp.BasicAuth(self._username, self._password),
                    timeout=self._timeout,
                ) as session:
                    async with session.post(
                        f"{self._base_url}{API_ENDPOINT_EVENT}",
                        data={command: value, "pageevent": command},
                        ssl=False,
                    ) as response:
                        response.raise_for_status()
                        response_text = await response.text()

                        if "error" in response_text.lower():
                            raise CommandError(f"Error in response: {response_text}")

                        # Verify command if required
                        if verify:
                            state = await self.get_state(force_refresh=True)
                            if not self._verify_command(state, command, value):
                                raise CommandError("Command verification failed")

                        # Update success metrics
                        self._last_command_time = current_time
                        self._error_count = 0
                        self._current_retry_delay = RETRY_DELAY
                        self._last_successful_connection = dt_util.utcnow()
                        self._available = True
                        
                        return True, {"response": response_text}

            except Exception as err:
                _LOGGER.error(
                    "Command error for %s (attempt %d/%d): %s",
                    command,
                    attempt + 1,
                    retry_count,
                    str(err)
                )
                self._error_count += 1

                if attempt + 1 < retry_count:
                    await asyncio.sleep(self._current_retry_delay)
                    self._current_retry_delay = min(self._current_retry_delay * 2, 60)
                else:
                    self._available = self._error_count < 3
                    return False, {"error": str(err)}

    async def get_state(self, force_refresh: bool = False) -> dict[str, Any]:
        """Get current state with smart caching."""
        current_time = time.time()

        # Use cache if valid and not forcing refresh
        if not force_refresh and self._last_state is not None:
            if current_time - self._last_update < UPDATE_INTERVAL.total_seconds():
                return self._last_state

        try:
            self._request_count += 1
            async with aiohttp.ClientSession(
                auth=aiohttp.BasicAuth(self._username, self._password),
                timeout=self._timeout,
            ) as session:
                async with session.post(
                    f"{self._base_url}{API_ENDPOINT_MAIN}",
                    ssl=False,
                ) as response:
                    response.raise_for_status()
                    data = await response.json()

                    # Validate response
                    if not isinstance(data, dict):
                        raise ValueError("Invalid response format")

                    # Update device info
                    if "verFWMain" in data:
                        self._firmware_version = data["verFWMain"].strip()
                    if "stationId" in data:
                        self._station_id = data["stationId"].strip()
                    
                    # Update state tracking
                    self._last_state = data
                    self._last_update = current_time
                    self._error_count = 0
                    self._current_retry_delay = RETRY_DELAY
                    self._last_successful_connection = dt_util.utcnow()
                    self._available = True
                    
                    return data

        except Exception as err:
            self._error_count += 1
            self._available = self._error_count < 3
            _LOGGER.error("Error getting state: %s", str(err))
            raise

    def _verify_command(
        self,
        state_data: dict[str, Any],
        command: str,
        value: Any
    ) -> bool:
        """Verify command was applied correctly."""
        try:
            if command == "evseEnabled":
                return state_data.get("evseEnabled") == value
            elif command == "oneCharge":
                return state_data.get("oneCharge") == value
            elif command == "currentSet":
                return state_data.get("currentSet") == value
            elif command == "rstEM1":
                return True  # Reset commands don't need verification
            return False
        except Exception as err:
            _LOGGER.error("Error verifying command: %s", str(err))
            return False

    @property
    def available(self) -> bool:
        """Return if device is available."""
        return self._available

    @property
    def last_successful_connection(self) -> Optional[datetime]:
        """Return last successful connection time."""
        return self._last_successful_connection

    @property
    def last_state(self) -> Optional[dict[str, Any]]:
        """Return last known state."""
        return self._last_state

    @property
    def firmware_version(self) -> str | None:
        """Return firmware version."""
        return self._firmware_version

    @property
    def station_id(self) -> str | None:
        """Return station ID."""
        return self._station_id

    @property
    def request_count(self) -> int:
        """Return total request count."""
        return self._request_count

    async def close(self) -> None:
        """Close session manager."""
        self._available = False
        self._last_state = None


class CommandError(HomeAssistantError):
    """Error to indicate command failure."""
