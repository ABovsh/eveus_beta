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
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

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
)

_LOGGER = logging.getLogger(__name__)

class DeviceError(HomeAssistantError):
    """Device specific error."""
    pass

class CommandError(HomeAssistantError):
    """Command execution error."""
    pass

class ValidationError(HomeAssistantError):
    """Data validation error."""
    pass

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
        self._model = "Eveus"
        
        # Device info
        self._firmware_version = None
        self._station_id = None
        self._capabilities = {
            "min_current": 7.0,
            "max_current": 16.0,
            "firmware_version": "Unknown",
            "station_id": "Unknown",
            "supports_one_charge": True,
        }
        
        # Connection management
        self._base_url = f"http://{self._host}"
        self._session: Optional[aiohttp.ClientSession] = None
        self._session_lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()
        self._command_timestamps = deque(maxlen=MAX_COMMANDS_PER_MINUTE)
        self._last_command_time = 0
        
        # State management
        self._state_cache = {}
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
        self._store: Optional[Store] = None
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
            # Initialize store
            self._store = Store(self.hass, 1, f"{DOMAIN}_{self._entry_id}_session")
            self._stored_data = await self._store.async_load() or {}
            
            # Get initial state and capabilities
            state = await self.get_state(force_refresh=True)
            await self._update_capabilities(state)
            
            _LOGGER.debug(
                "Session manager initialized for %s (Current range: %s-%sA, FW: %s)",
                self._host,
                self._capabilities["min_current"],
                self._capabilities["max_current"],
                self._firmware_version
            )
            
        except Exception as err:
            _LOGGER.error("Failed to initialize session manager: %s", str(err))
            self._available = False
            raise

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an HTTP session."""
        if not self._session or self._session.closed:
            async with self._session_lock:
                if not self._session or self._session.closed:
                    self._session = async_get_clientsession(self.hass)
                    self._session.auth = aiohttp.BasicAuth(
                        self._username,
                        self._password
                    )
        return self._session

    async def _update_capabilities(self, state: dict) -> None:
        """Update device capabilities."""
        try:
            # Extract capabilities
            min_current = float(state.get("minCurrent", 7))
            max_current = float(state.get("curDesign", 16))
            firmware = state.get("verFWMain", "Unknown").strip()
            station_id = state.get("stationId", "Unknown").strip()
            
            # Validate values
            if not (0 < min_current <= max_current <= 32):
                raise ValidationError(
                    f"Invalid current range: {min_current}-{max_current}A"
                )
            
            # Update capabilities
            self._capabilities.update({
                "min_current": min_current,
                "max_current": max_current,
                "firmware_version": firmware,
                "station_id": station_id,
                "last_update": time.time()
            })
            
            self._firmware_version = firmware
            self._station_id = station_id
            
            _LOGGER.info(
                "Device capabilities updated - Current range: %.1f-%.1fA, Firmware: %s, ID: %s",
                min_current,
                max_current,
                firmware,
                station_id
            )
            
        except Exception as err:
            _LOGGER.error("Failed to update capabilities: %s", str(err))
            raise

    def _validate_state_response(self, data: dict) -> None:
        """Validate state response data."""
        if not isinstance(data, dict):
            raise ValidationError("Invalid response format")
            
        missing = REQUIRED_STATE_FIELDS - set(data.keys())
        if missing:
            raise ValidationError(f"Missing required fields: {missing}")
            
        try:
            # Validate critical fields
            state = int(data.get("state", -1))
            if state not in CHARGING_STATES:
                raise ValidationError(f"Invalid state value: {state}")
                
            current = float(data.get("currentSet", 0))
            if not (self._capabilities["min_current"] <= current <= self._capabilities["max_current"]):
                raise ValidationError(f"Current out of range: {current}A")
                
        except (TypeError, ValueError) as err:
            raise ValidationError(f"Data validation failed: {err}")

    async def get_state(self, force_refresh: bool = False) -> dict[str, Any]:
        """Get current state with caching and validation."""
        async with self._state_lock:
            current_time = time.time()
            
            # Use cache if valid and not forcing refresh
            if (
                not force_refresh 
                and self._state_cache
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
                except ValidationError as err:
                    last_error = f"Validation error: {err}"
                except Exception as err:
                    last_error = f"Unexpected error: {err}"
                
                retry_count += 1
                if retry_count < MAX_RETRIES:
                    await asyncio.sleep(self._retry_delay)
                    self._retry_delay = min(self._retry_delay * 2, MAX_RETRY_DELAY)
            
            # Update error tracking
            self._error_count += 1
            self._available = self._error_count < 3
            
            _LOGGER.error(
                "Failed to get state after %d retries: %s",
                retry_count,
                last_error
            )
            raise DeviceError(f"Failed to get state: {last_error}")

    async def send_command(
        self,
        command: str,
        value: Any,
        verify: bool = True,
        retry_count: int = MAX_RETRIES,
    ) -> tuple[bool, dict[str, Any]]:
        """Send command with improved error handling."""
        async with self._command_lock:
            current_time = time.time()
            
            # Implement rate limiting
            if len(self._command_timestamps) >= MAX_COMMANDS_PER_MINUTE:
                while (
                    self._command_timestamps and 
                    current_time - self._command_timestamps[0] > 60
                ):
                    self._command_timestamps.popleft()
                    
            if len(self._command_timestamps) >= MAX_COMMANDS_PER_MINUTE:
                return False, {"error": "Rate limit exceeded"}

            # Enforce minimum interval
            time_since_last = current_time - self._last_command_time
            if time_since_last < MIN_COMMAND_INTERVAL:
                await asyncio.sleep(MIN_COMMAND_INTERVAL - time_since_last)

            # Update command tracking
            self._command_timestamps.append(current_time)
            self._last_command_time = current_time

            # Execute command with retries
            for retry in range(retry_count):
                try:
                    session = await self._get_session()
                    
                    data = {
                        command: value,
                        "pageevent": command
                    }

                    async with async_timeout.timeout(COMMAND_TIMEOUT):
                        async with session.post(
                            f"{self._base_url}{API_ENDPOINT_EVENT}",
                            data=data,
                            ssl=False,
                        ) as response:
                            response.raise_for_status()
                            response_text = await response.text()

                            if "error" in response_text.lower():
                                raise CommandError(f"Error in response: {response_text}")

                            # Verify command if required
                            if verify:
                                await asyncio.sleep(0.5)
                                state = await self.get_state(force_refresh=True)
                                if not self._verify_command(state, command, value):
                                    raise CommandError("Command verification failed")

                            # Update metrics
                            self._error_count = 0
                            self._retry_delay = RETRY_BASE_DELAY
                            self._last_successful_connection = dt_util.utcnow()
                            self._available = True
                            
                            return True, {"response": response_text}

                except Exception as err:
                    last_error = f"{type(err).__name__}: {str(err)}"
                    _LOGGER.warning(
                        "Command attempt %d/%d failed: %s",
                        retry + 1,
                        retry_count,
                        last_error
                    )
                    
                    if retry < retry_count - 1:
                        await asyncio.sleep(self._retry_delay)
                        self._retry_delay = min(self._retry_delay * 2, MAX_RETRY_DELAY)

            # Update error tracking after all retries failed
            self._error_count += 1
            self._available = self._error_count < 3
            
            return False, {"error": f"Command failed after {retry_count} attempts: {last_error}"}

    def _verify_command(self, state: dict, command: str, value: Any) -> bool:
        """Verify command was applied correctly."""
        try:
            if command == "evseEnabled":
                return int(state.get("evseEnabled", -1)) == int(value)
                
            elif command == "oneCharge":
                return int(state.get("oneCharge", -1)) == int(value)
                
            elif command == "currentSet":
                device_current = float(state.get("currentSet", 0))
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

    async def _store_session_data(self, state: dict) -> None:
        """Store persistent session data."""
        if not self._store:
            return
            
        try:
            session_data = {
                key: state.get(key)
                for key in PERSISTENT_SESSION_DATA
                if key in state
            }
            session_data["last_update"] = dt_util.utcnow().isoformat()
            
            await self._store.async_save(session_data)
            
        except Exception as err:
            _LOGGER.error("Failed to store session data: %s", str(err))

    @property
    def available(self) -> bool:
        """Return if device is available."""
        return self._available

    @property
    def last_update(self) -> float:
        """Return timestamp of last successful update."""
        return self._last_state_update

    @property
    def firmware_version(self) -> str:
        """Return firmware version."""
        return self._firmware_version or "Unknown"

    @property
    def station_id(self) -> str:
        """Return station ID."""
        return self._station_id or "Unknown"

    @property
    def model(self) -> str:
        """Return model name."""
        min_current = self._capabilities.get("min_current", 7)
        max_current = self._capabilities.get("max_current", 16)
        return f"Eveus {min_current}-{max_current}A"

    @property
    def capabilities(self) -> dict:
        """Return device capabilities."""
        return self._capabilities.copy()

    async def close(self) -> None:
        """Close session manager and cleanup resources."""
        self._available = False
        self._state_cache = {}
        self._registered_entities.clear()
        
        try:
            # Store final state if charging
            if self._state_cache.get("state") == 4:  # Charging
                await self._store_session_data(self._state_cache)
            
            # Close HTTP session
            if self._session and not self._session.closed:
                await self._session.close()
                self._session = None
                
        except Exception as err:
            _LOGGER.error("Error during session manager cleanup: %s", str(err))
        
        finally:
            self._command_timestamps.clear()
            self._last_command_time = 0
            self._error_count = 0
            self._last_state_update = 0

    async def async_update(self, *_) -> None:
        """Update all registered entities efficiently."""
        if not self._registered_entities:
            return

        try:
            # Get current state once
            state = await self.get_state(force_refresh=True)
            
            # Determine charging state
            charging_state = int(state.get("state", 2))
            is_charging = charging_state == 4

            # Update entities in batches
            entities = list(self._registered_entities)
            for i in range(0, len(entities), self._entity_batch_size):
                batch = entities[i:i + self._entity_batch_size]
                
                for entity in batch:
                    if hasattr(entity, '_handle_state_update'):
                        try:
                            entity._handle_state_update(state)
                            if hasattr(entity, 'async_write_ha_state'):
                                entity.async_write_ha_state()
                        except Exception as err:
                            _LOGGER.error(
                                "Error updating entity %s: %s",
                                getattr(entity, 'name', 'Unknown'),
                                str(err)
                            )
                
                # Small delay between batches
                if i + self._entity_batch_size < len(entities):
                    await asyncio.sleep(self._entity_update_delay)

            # Store session data if charging
            if is_charging:
                await self._store_session_data(state)

        except Exception as err:
            _LOGGER.error("Failed to update entities: %s", str(err))
            self._error_count += 1
            if self._error_count >= 3:
                self._available = False

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
                    
        except Exception as err:
            _LOGGER.warning("Error determining update interval: %s", str(err))
            return UPDATE_INTERVAL_IDLE

    async def validate_current(self, current: float) -> bool:
        """Validate current against device capabilities."""
        try:
            min_current = self._capabilities.get("min_current", 7)
            max_current = self._capabilities.get("max_current", 16)
            
            if not min_current <= current <= max_current:
                _LOGGER.warning(
                    "Current value %s outside allowed range [%s, %s]",
                    current,
                    min_current,
                    max_current
                )
                return False
                
            return True
            
        except Exception as err:
            _LOGGER.error("Error validating current: %s", str(err))
            return False

    async def reset_counter(self) -> bool:
        """Reset energy counter with verification."""
        try:
            success, result = await self.send_command("rstEM1", 0, verify=False)
            if not success:
                _LOGGER.error("Failed to reset counter: %s", result.get("error"))
                return False
                
            # Verify reset
            await asyncio.sleep(1)
            state = await self.get_state(force_refresh=True)
            
            return float(state.get("IEM1", 0)) == 0
            
        except Exception as err:
            _LOGGER.error("Error resetting counter: %s", str(err))
            return False

    async def get_stored_session_data(self) -> dict:
        """Get stored session data safely."""
        try:
            if not self._store:
                return {}
                
            data = await self._store.async_load()
            return data if data else {}
            
        except Exception as err:
            _LOGGER.error("Error loading stored session data: %s", str(err))
            return {}

    def should_update(self) -> bool:
        """Determine if an update is needed based on time and state."""
        if not self._last_state_update:
            return True
            
        current_time = time.time()
        time_since_update = current_time - self._last_state_update
        
        try:
            state_code = int(self._state_cache.get("state", 2))
            
            if state_code == 4:  # Charging
                return time_since_update >= UPDATE_INTERVAL_CHARGING.total_seconds()
            elif state_code == 7:  # Error
                return time_since_update >= UPDATE_INTERVAL_ERROR.total_seconds()
            else:
                return time_since_update >= UPDATE_INTERVAL_IDLE.total_seconds()
                
        except Exception:
            return time_since_update >= UPDATE_INTERVAL_IDLE.total_seconds()
