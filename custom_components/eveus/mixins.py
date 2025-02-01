"""Mixins for Eveus integration."""
from __future__ import annotations

import logging
import asyncio
import time
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Constants for mixin configuration
MAX_RETRIES = 3
RETRY_DELAY = 2
COMMAND_TIMEOUT = 5
UPDATE_TIMEOUT = 10
MIN_UPDATE_INTERVAL = 2
MIN_COMMAND_INTERVAL = 1

class EveusDeviceInfoMixin:
    """Mixin for Eveus device info."""

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._host)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": f"Eveus ({self._host})",
            "sw_version": getattr(self, '_version', 'Unknown'),
        }

class EveusSessionMixin:
    """Mixin for Eveus session management."""

    def __init__(self) -> None:
        """Initialize session attributes."""
        self._session = None
        self._command_lock = asyncio.Lock()
        self._update_lock = asyncio.Lock()
        self._last_command_time = 0
        self._last_update = 0
        self._available = True
        self._error_count = 0
        self._max_errors = 3

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create client session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10, connect=5)
            connector = aiohttp.TCPConnector(limit=1, force_close=True)
            self._session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return self._session

    async def _send_command(self, command: str, value: int, verify_command: bool = True) -> bool:
        """Send command to device with retry logic."""
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
                        response.raise_for_status()
                        response_text = await response.text()
                        
                        if "error" in response_text.lower():
                            raise ValueError(f"Error in response: {response_text}")

                        if verify_command:
                            async with session.post(
                                f"http://{self._host}/main",
                                auth=aiohttp.BasicAuth(self._username, self._password),
                                timeout=COMMAND_TIMEOUT,
                            ) as verify_response:
                                verify_response.raise_for_status()
                                verify_data = await verify_response.json()
                                if not self._validate_command_response(verify_data, command, value):
                                    raise ValueError("Command verification failed")

                        self._available = True
                        self._last_command_time = current_time
                        self._error_count = 0
                        return True

                except aiohttp.ClientError as err:
                    if "Connection reset by peer" in str(err) or "Server disconnected" in str(err):
                        if attempt + 1 < MAX_RETRIES:
                            await asyncio.sleep(RETRY_DELAY * (2 ** attempt))
                            continue
                    raise

                except Exception as error:
                    if attempt + 1 >= MAX_RETRIES:
                        self._error_count += 1
                        self._available = False if self._error_count >= self._max_errors else True
                        _LOGGER.error(
                            "Failed to send command after %d attempts to %s: %s",
                            MAX_RETRIES,
                            self._host,
                            str(error),
                        )
                        return False
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))

            return False

    def _validate_command_response(self, response_data: dict, command: str, value: int) -> bool:
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
        except Exception as err:
            _LOGGER.debug("Validation error for command %s: %s", command, str(err))
            return False

        return False

class EveusUpdateMixin:
    """Mixin for Eveus update management."""

    async def async_update(self) -> None:
        """Update device state."""
        current_time = time.time()
        if hasattr(self, '_last_update') and current_time - self._last_update < MIN_UPDATE_INTERVAL:
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
                        response.raise_for_status()
                        self._state_data = await response.json()
                        self._available = True
                        self._error_count = 0
                        self._last_update = current_time
                        return

                except aiohttp.ClientError as err:
                    if "Connection reset by peer" in str(err) or "Server disconnected" in str(err):
                        if attempt + 1 < MAX_RETRIES:
                            await asyncio.sleep(RETRY_DELAY * (2 ** attempt))
                            continue
                    self._handle_error(err)
                    break

                except Exception as err:
                    self._handle_error(err)
                    break

    def _handle_error(self, error: Exception) -> None:
        """Handle update errors."""
        self._error_count += 1
        self._available = False if self._error_count >= self._max_errors else True
        _LOGGER.error("Error updating state for %s: %s", getattr(self, 'name', 'Unknown'), str(error))

class EveusStateMixin:
    """Mixin for Eveus state management."""

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()  # type: ignore[misc]
        if isinstance(self, RestoreEntity):
            state = await self.async_get_last_state()
            if state and state.state not in ('unknown', 'unavailable'):
                try:
                    if hasattr(self, '_attr_suggested_display_precision'):
                        self._previous_value = float(state.state)
                    else:
                        self._previous_value = state.state
                except (TypeError, ValueError):
                    self._previous_value = state.state

    async def async_will_remove_from_hass(self) -> None:
        """Clean up resources when entity is removed."""
        if hasattr(self, '_session') and not self._session.closed:
            await self._session.close()
            self._session = None
