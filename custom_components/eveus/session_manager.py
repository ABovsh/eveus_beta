"""Session manager for Eveus integration with connection pooling."""
from __future__ import annotations

import logging
import asyncio
import time
from typing import Any, Optional
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

import aiohttp
from aiohttp import (
    ClientSession,
    ClientTimeout,
    TCPConnector,
    ClientResponse,
    ClientError
)

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    COMMAND_TIMEOUT,
    UPDATE_TIMEOUT,
    MAX_RETRIES,
    RETRY_DELAY,
    MIN_COMMAND_INTERVAL,
    API_ENDPOINT_MAIN,
    API_ENDPOINT_EVENT,
)

_LOGGER = logging.getLogger(__name__)

class SessionManager:
    """Manages API sessions with connection pooling and error recovery."""

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
        
        # Session management
        self._session: Optional[ClientSession] = None
        self._connection_pool: Optional[TCPConnector] = None
        self._base_url = f"http://{self._host}"
        self._last_state: Optional[dict] = None
        
        # Connection state
        self._available = True
        self._last_connection_attempt = 0
        self._error_count = 0
        self._current_retry_delay = RETRY_DELAY
        self._last_successful_connection: Optional[datetime] = None
        
        # Locks
        self._session_lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()
        self._last_command_time = 0
        
        # Pool configuration
        self._pool_size = 5
        self._keepalive_timeout = 60
        self._session_timeout = ClientTimeout(
            total=COMMAND_TIMEOUT,
            connect=COMMAND_TIMEOUT / 3,
            sock_connect=COMMAND_TIMEOUT / 3,
            sock_read=COMMAND_TIMEOUT / 2
        )

    async def _init_session(self) -> None:
        """Initialize or reinitialize the session with proper configuration."""
        try:
            await self._cleanup_session()

            self._connection_pool = TCPConnector(
                limit=self._pool_size,
                enable_cleanup_closed=True,
                keepalive_timeout=self._keepalive_timeout,
                ssl=False,
            )

            self._session = aiohttp.ClientSession(
                timeout=self._session_timeout,
                connector=self._connection_pool,
                raise_for_status=True,
                auth=aiohttp.BasicAuth(self._username, self._password),
            )

            # Reset state
            self._error_count = 0
            self._current_retry_delay = RETRY_DELAY
            self._available = True

        except Exception as err:
            _LOGGER.error("Failed to initialize session: %s", str(err))
            self._available = False
            raise

    async def _cleanup_session(self) -> None:
        """Cleanup existing session and pool."""
        try:
            if self._session and not self._session.closed:
                await self._session.close()
            if self._connection_pool and not self._connection_pool.closed:
                await self._connection_pool.close()
        except Exception as err:
            _LOGGER.warning("Error during session cleanup: %s", str(err))

    @asynccontextmanager
    async def get_session(self) -> ClientSession:
        """Get an active session with automatic retry and error handling."""
        async with self._session_lock:
            try:
                if not self._session or self._session.closed:
                    await self._init_session()
                yield self._session
            except Exception as err:
                _LOGGER.error("Session error: %s", str(err))
                self._available = False
                raise

    async def send_command(
        self,
        command: str,
        value: Any,
        verify: bool = True,
        retry_count: int = MAX_RETRIES,
    ) -> tuple[bool, dict[str, Any]]:
        """Send command with comprehensive error handling and verification."""
        async with self._command_lock:
            # Rate limiting
            current_time = time.time()
            time_since_last = current_time - self._last_command_time
            if time_since_last < MIN_COMMAND_INTERVAL:
                await asyncio.sleep(MIN_COMMAND_INTERVAL - time_since_last)

            for attempt in range(retry_count):
                try:
                    async with self.get_session() as session:
                        # Send command
                        response = await self._send_request(
                            session,
                            API_ENDPOINT_EVENT,
                            data={command: value, "pageevent": command},
                        )
                        
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

                except CommandError as err:
                    _LOGGER.error(
                        "Command error for %s (attempt %d/%d): %s",
                        command,
                        attempt + 1,
                        retry_count,
                        str(err)
                    )
                except asyncio.TimeoutError:
                    _LOGGER.warning(
                        "Timeout sending command %s (attempt %d/%d)",
                        command,
                        attempt + 1,
                        retry_count
                    )
                except ClientError as err:
                    _LOGGER.warning(
                        "Network error for command %s (attempt %d/%d): %s",
                        command,
                        attempt + 1,
                        retry_count,
                        str(err)
                    )
                except Exception as err:
                    _LOGGER.error(
                        "Unexpected error sending command %s (attempt %d/%d): %s",
                        command,
                        attempt + 1,
                        retry_count,
                        str(err),
                        exc_info=True
                    )

                if attempt + 1 < retry_count:
                    await asyncio.sleep(self._current_retry_delay)
                    self._current_retry_delay = min(self._current_retry_delay * 2, 60)
                else:
                    self._error_count += 1
                    self._available = self._error_count < 3
                    raise CommandError(f"Command failed after {retry_count} attempts")

    async def get_state(self, force_refresh: bool = False) -> dict[str, Any]:
        """Get current state with error handling and optional caching."""
        try:
            # Return cached state if available and not forcing refresh
            if not force_refresh and self._last_state is not None:
                return self._last_state

            async with self.get_session() as session:
                response = await self._send_request(session, API_ENDPOINT_MAIN)
                data = await response.json()
                
                # Validate response structure
                if not isinstance(data, dict):
                    raise ValueError("Invalid response format")
                
                # Update cache and success metrics
                self._last_state = data
                self._error_count = 0
                self._current_retry_delay = RETRY_DELAY
                self._last_successful_connection = dt_util.utcnow()
                self._available = True

                # Update firmware and station ID if available
                if "verFWMain" in data:
                    self._firmware_version = data["verFWMain"].strip()
                if "stationId" in data:
                    self._station_id = data["stationId"].strip()
                return data

        except Exception as err:
            self._error_count += 1
            self._available = self._error_count < 3
            _LOGGER.error("Error getting state: %s", str(err))
            raise

    async def _send_request(
        self,
        session: ClientSession,
        endpoint: str,
        method: str = "POST",
        **kwargs
    ) -> ClientResponse:
        """Send request with proper error handling."""
        url = f"{self._base_url}{endpoint}"
        
        try:
            response = await session.request(
                method,
                url,
                timeout=kwargs.pop('timeout', self._session_timeout),
                ssl=False,
                **kwargs
            )
            return response

        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout accessing %s: %s", url, str(err))
            raise
        except ClientError as err:
            _LOGGER.error("Network error accessing %s: %s", url, str(err))
            raise
        except Exception as err:
            _LOGGER.error("Unexpected error accessing %s: %s", url, str(err))
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
                # Reset commands don't need verification
                return True
            return False
        except Exception as err:
            _LOGGER.error("Error verifying command: %s", str(err))
            return False

    @property
    def available(self) -> bool:
        """Return if the device is available."""
        return self._available

    @property
    def last_successful_connection(self) -> Optional[datetime]:
        """Return the last successful connection time."""
        return self._last_successful_connection

    @property
    def last_state(self) -> Optional[dict[str, Any]]:
        """Return the last known state."""
        return self._last_state

    @property
    def firmware_version(self) -> str | None:
        """Return the firmware version."""
        return self._firmware_version

    @property
    def station_id(self) -> str | None:
        """Return the station ID."""
        return self._station_id
    
    
    async def close(self) -> None:
        """Close all sessions and cleanup resources."""
        try:
            await self._cleanup_session()
        except Exception as err:
            _LOGGER.error("Error closing session manager: %s", str(err))
        finally:
            self._session = None
            self._connection_pool = None
            self._available = False
            self._last_state = None


class CommandError(HomeAssistantError):
    """Error to indicate command failure."""
