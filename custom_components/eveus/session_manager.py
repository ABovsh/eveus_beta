"""Optimized session manager for Eveus integration."""
from __future__ import annotations

import logging
import asyncio
import time
from typing import Any, Optional
from datetime import datetime
from collections import deque

import aiohttp
from aiohttp import ClientTimeout, ClientError, ClientResponse
import async_timeout
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    UPDATE_INTERVAL_CHARGING,
    UPDATE_INTERVAL_IDLE,
    UPDATE_INTERVAL_ERROR,
    API_ENDPOINT_MAIN,
    API_ENDPOINT_EVENT,
    COMMAND_TIMEOUT,
    MAX_RETRIES,
    RETRY_BASE_DELAY,
    MAX_RETRY_DELAY,
    MIN_COMMAND_INTERVAL,
    MAX_COMMANDS_PER_MINUTE,
    COMMAND_COOLDOWN,
    STATE_CACHE_TTL,
    REQUIRED_STATE_FIELDS,
    PERSISTENT_SESSION_DATA,
    CHARGING_STATES,
    MODEL_MAX_CURRENT,
)

_LOGGER = logging.getLogger(__name__)

class DeviceError(HomeAssistantError):
    """Device specific error."""

class CommandError(HomeAssistantError):
    """Command execution error."""

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
        
        # Device info
        self._model = None
        self._firmware_version = None
        self._station_id = None
        self._capabilities = None
        
        # Connection management
        self._base_url = f"http://{self._host}"
        self._session: Optional[aiohttp.ClientSession] = None
        self._session_lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()
        self._command_timestamps = deque(maxlen=MAX_COMMANDS_PER_MINUTE)
        self._last_command_time = 0
        
        # State management
        self._state_cache = None
        self._last_state_update = 0
        self._state_lock = asyncio.Lock()
        self._available = True
        self._error_count = 0
        self._retry_delay = RETRY_BASE_DELAY
        self._last_successful_connection = None
        
        # Entity tracking
        self._registered_entities = set()
        self._entity_batch_size = 5
        self._entity_update_delay = 0.1
        
        # Persistent storage
        self._store = Store(hass, 1, f"{DOMAIN}_{entry_id}_session")
        self._stored_data = None

        # Timeouts
        self._timeout = ClientTimeout(
            total=COMMAND_TIMEOUT,
            connect=3,
            sock_connect=3,
            sock_read=5
        )

    async def initialize(self) -> None:
        """Initialize the session manager."""
        try:
            # Load stored data
            self._stored_data = await self._store.async_load() or {}
            
            # Get initial state and capabilities
            state = await self.get_state(force_refresh=True)
            await self._update_capabilities(state)
            
            _LOGGER.debug(
                "Session manager initialized for %s (Model: %s, FW: %s)",
                self._host,
                self._model,
                self._firmware_version
            )
            
        except Exception as err:
            _LOGGER.error("Failed to initialize session manager: %s", err)
            raise

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an HTTP session."""
        async with self._session_lock:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession(
                    auth=aiohttp.BasicAuth(self._username, self._password),
                    timeout=self._timeout,
                    connector=aiohttp.TCPConnector(
                        limit=10,
                        enable_cleanup_closed=True,
                        force_close=False,
                        keepalive_timeout=30
                    )
                )
            return self._session

    async def _update_capabilities(self, state: dict) -> None:
        """Update device capabilities."""
        try:
            self._capabilities = {
                "min_current": float(state.get("minCurrent", 7)),  # Use device's minCurrent
                "max_current": float(state.get("curDesign", 16)),  # Use device's curDesign
                "firmware_version": state.get("verFWMain", "Unknown").strip(),
                "station_id": state.get("stationId", "Unknown").strip(),
                "supports_one_charge": bool(state.get("oneChargeSupported", True)),
                "last_update": time.time()
            }
            
            self._firmware_version = self._capabilities["firmware_version"]
            self._station_id = self._capabilities["station_id"]
            
        except Exception as err:
            _LOGGER.error("Failed to update capabilities: %s", err)
            raise

    def _validate_state_response(self, data: dict) -> None:
        """Validate state response data."""
        if not isinstance(data, dict):
            raise ValueError("Invalid response format")
            
        missing = REQUIRED_STATE_FIELDS - set(data.keys())
        if missing:
            raise ValueError(f"Missing required fields: {missing}")

    async def get_state(self, force_refresh: bool = False) -> dict[str, Any]:
        """Get current state with caching and validation."""
        async with self._state_lock:
            current_time = time.time()
            
            # Use cache if valid and not forcing refresh
            if (
                not force_refresh 
                and self._state_cache is not None 
                and current_time - self._last_state_update < STATE_CACHE_TTL
            ):
                return self._state_cache.copy()

            # Get fresh state with retries
            retry_count = 0
            last_error = None
            
            while retry_count < MAX_RETRIES:
                try:
                    session = await self._get_session()
                    async with async_timeout.timeout(COMMAND_TIMEOUT):
                        async with session.post(
                            f"{self._base_url}{API_ENDPOINT_MAIN}",
                            ssl=False,
                        ) as response:
                            response.raise_for_status()
                            data = await response.json()
                            
                            # Validate response
                            self._validate_state_response(data)
                            
                            # Update state tracking
                            self._state_cache = data.copy()
                            self._last_state_update = current_time
                            self._error_count = 0
                            self._retry_delay = RETRY_BASE_DELAY
                            self._last_successful_connection = dt_util.utcnow()
                            self._available = True
                            
                            return data
                            
                except asyncio.TimeoutError as err:
                    last_error = f"Timeout getting state: {err}"
                except ClientError as err:
                    last_error = f"Client error: {err}"
                except ValueError as err:
                    last_error = f"Invalid response: {err}"
                except Exception as err:
                    last_error = f"Unexpected error: {err}"
                
                retry_count += 1
                if retry_count < MAX_RETRIES:
                    await asyncio.sleep(self._retry_delay)
                    self._retry_delay = min(self._retry_delay * 2, MAX_RETRY_DELAY)
            
            # Update error tracking
            self._error_count += 1
            self._available = self._error_count < 3
            
            raise DeviceError(f"Failed to get state after {retry_count} retries: {last_error}")

    async def send_command(
        self,
        command: str,
        value: Any,
        verify: bool = True,
        retry_count: int = MAX_RETRIES,
    ) -> tuple[bool, dict[str, Any]]:
        """Send command with rate limiting and verification."""
        async with self._command_lock:
            # Implement rate limiting
            current_time = time.time()
            
            # Clean old timestamps
            while (
                self._command_timestamps and 
                current_time - self._command_timestamps[0] > 60
            ):
                self._command_timestamps.popleft()
            
            # Check rate limits
            if len(self._command_timestamps) >= MAX_COMMANDS_PER_MINUTE:
                raise CommandError("Command rate limit exceeded")
            
            # Enforce minimum interval between commands
            time_since_last = current_time - self._last_command_time
            if time_since_last < MIN_COMMAND_INTERVAL:
                await asyncio.sleep(MIN_COMMAND_INTERVAL - time_since_last)

            # Add current timestamp to queue
            self._command_timestamps.append(current_time)
            self._last_command_time = current_time

            # Execute command with retries
            retry = 0
            last_error = None
            
            while retry < retry_count:
                try:
                    session = await self._get_session()
                    async with async_timeout.timeout(COMMAND_TIMEOUT):
                        async with session.post(
                            f"{self._base_url}{API_ENDPOINT_EVENT}",
                            data={
                                command: value,
                                "pageevent": command
                            },
                            ssl=False,
                        ) as response:
                            response.raise_for_status()
                            response_text = await response.text()

                            if "error" in response_text.lower():
                                raise CommandError(f"Error in response: {response_text}")

                            # Verify command if required
                            if verify:
                                await asyncio.sleep(0.5)  # Brief delay for device to process
                                state = await self.get_state(force_refresh=True)
                                if not self._verify_command(state, command, value):
                                    raise CommandError("Command verification failed")

                            # Update success metrics
                            self._error_count = 0
                            self._retry_delay = RETRY_BASE_DELAY
                            self._last_successful_connection = dt_util.utcnow()
                            self._available = True
                            
                            return True, {"response": response_text}

                except asyncio.TimeoutError as err:
                    last_error = f"Command timeout: {err}"
                except ClientError as err:
                    last_error = f"Client error: {err}"
                except CommandError as err:
                    last_error = str(err)
                except Exception as err:
                    last_error = f"Unexpected error: {err}"

                retry += 1
                if retry < retry_count:
                    await asyncio.sleep(self._retry_delay)
                    self._retry_delay = min(self._retry_delay * 2, MAX_RETRY_DELAY)

            # Update error tracking
            self._error_count += 1
            self._available = self._error_count < 3
            
            return False, {"error": last_error}

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
                device_current = float(state_data.get("currentSet", 0))
                target_current = float(value)
                return abs(device_current - target_current) <= 0.5
            elif command == "rstEM1":
                return True  # Reset commands don't need verification
            return False
            
        except (TypeError, ValueError) as err:
            _LOGGER.error("Error verifying command: %s", str(err))
            return False

    async def register_entity(self, entity) -> None:
        """Register an entity for batch updates."""
        self._registered_entities.add(entity)

    async def unregister_entity(self, entity) -> None:
        """Unregister an entity from batch updates."""
        self._registered_entities.discard(entity)

    async def update_entities(self) -> None:
        """Update all registered entities efficiently."""
        if not self._registered_entities:
            return

        try:
            # Get current state once
            state = await self.get_state(force_refresh=True)
            
            # Determine update interval based on charging state
            charging_state = int(state.get("state", 2))
            is_charging = charging_state == 4

            # Update entities in batches
            entities = list(self._registered_entities)
            for i in range(0, len(entities), self._entity_batch_size):
                batch = entities[i:i + self._entity_batch_size]
                
                update_tasks = []
                for entity in batch:
                    if hasattr(entity, '_handle_state_update'):
                        try:
                            entity._handle_state_update(state)
                            entity.async_write_ha_state()
                        except Exception as err:
                            _LOGGER.error(
                                "Error updating entity %s: %s",
                                entity.name,
                                str(err)
                            )
                
                # Small delay between batches
                if i + self._entity_batch_size < len(entities):
                    await asyncio.sleep(self._entity_update_delay)

            # Store session data if charging
            if is_charging:
                await self._store_session_data(state)

        except Exception as err:
            _LOGGER.error("Failed to update entities: %s", err)

    async def _store_session_data(self, state: dict) -> None:
        """Store persistent session data."""
        try:
            session_data = {
                key: state.get(key)
                for key in PERSISTENT_SESSION_DATA
                if key in state
            }
            session_data["last_update"] = dt_util.utcnow().isoformat()
            
            await self._store.async_save(session_data)
        except Exception as err:
            _LOGGER.error("Failed to store session data: %s", err)

    async def get_stored_session_data(self) -> dict:
        """Get stored session data."""
        return self._stored_data or {}

    def get_update_interval(self) -> timedelta:
        """Get appropriate update interval based on state."""
        try:
            if not self._state_cache:
                return UPDATE_INTERVAL_IDLE
                
            state_code = int(self._state_cache.get("state", 2))
            
            if state_code == 4:  # Charging
                return UPDATE_INTERVAL_CHARGING
            elif state_code == 7:  # Error
                return UPDATE_INTERVAL_ERROR
            else:
                return UPDATE_INTERVAL_IDLE
                
        except Exception:
            return UPDATE_INTERVAL_IDLE

    @property
    def available(self) -> bool:
        """Return if device is available."""
        return self._available

    @property
    def last_successful_connection(self) -> Optional[datetime]:
        """Return last successful connection time."""
        return self._last_successful_connection

    @property
    def firmware_version(self) -> Optional[str]:
        """Return firmware version."""
        return self._firmware_version

    @property
    def station_id(self) -> Optional[str]:
        """Return station ID."""
        return self._station_id

    @property
    def model(self) -> Optional[str]:
        """Return device model."""
        return self._model

    @property
    def capabilities(self) -> Optional[dict]:
        """Return device capabilities."""
        return self._capabilities

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._session_manager._host)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": f"Eveus ({self._capabilities.get('min_current', 7)}-{self._capabilities.get('max_current', 16)}A)",
            "sw_version": self._firmware_version,
            "serial_number": self._station_id,
            "configuration_url": f"http://{self._session_manager._host}",
            "hw_version": f"Current range: {self._capabilities.get('min_current', 7)}-{self._capabilities.get('max_current', 16)}A"
        }

    async def validate_current(self, current: float) -> bool:
        """Validate current against device model."""
        if not self._model:
            return False
            
        max_current = MODEL_MAX_CURRENT.get(self._model, 16)
        return 8 <= current <= max_current

    async def close(self) -> None:
        """Close session manager."""
        self._available = False
        self._state_cache = None
        
        if self._session and not self._session.closed:
            await self._session.close()     
        
