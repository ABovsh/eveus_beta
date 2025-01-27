"""Shared mixins for Eveus integration."""
from __future__ import annotations

import logging
import asyncio
import aiohttp
from typing import Any, Optional, Callable
from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.exceptions import HomeAssistantError
from homeassistant.const import CONF_HOST

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class ConnectionManager:
    """Manage API connections with retry and backoff."""
    def __init__(self):
        """Initialize connection manager."""
        self._retry_interval = 5
        self._backoff_factor = 1.5
        self._max_retry_interval = 300
        self._request_timeout = 10
        self._connection_lock = asyncio.Lock()

    async def execute_request(
        self,
        session: aiohttp.ClientSession,
        method: str,
        url: str,
        **kwargs
    ) -> Any:
        """Execute request with retry logic."""
        timeout = aiohttp.ClientTimeout(total=self._request_timeout)
        kwargs['timeout'] = timeout

        async with self._connection_lock:
            for attempt in range(3):
                try:
                    async with session.request(method, url, **kwargs) as response:
                        response.raise_for_status()
                        if response.content_length == 0:
                            raise ValueError("Empty response received")
                        return await response.json()
                except asyncio.TimeoutError:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(self._retry_interval * (self._backoff_factor ** attempt))
                except (aiohttp.ClientError, ValueError) as err:
                    if attempt == 2:
                        raise
                    _LOGGER.warning(
                        "Request failed (attempt %d/3): %s",
                        attempt + 1,
                        str(err)
                    )
                    await asyncio.sleep(self._retry_interval * (self._backoff_factor ** attempt))

class SessionMixin:
    """Enhanced session mixin with improved connection handling."""
    
    def __init__(self, host: str, username: str, password: str, hass: HomeAssistant = None) -> None:
        """Initialize session mixin."""
        self._host = host
        self._username = username
        self._password = password
        self.hass = hass
        self._available = True
        self._error_count = 0
        self._max_errors = 3
        self._command_lock = asyncio.Lock()
        self._data = {}
        self._last_update = datetime.now().timestamp()
        self._connection_manager = ConnectionManager()
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create client session."""
        if not self.hass:
            raise HomeAssistantError("HomeAssistant instance not set")
        if not self._session:
            self._session = async_create_clientsession(self.hass)
        return self._session

    async def async_api_call(
        self,
        endpoint: str,
        method: str = "POST",
        data: dict = None,
        **kwargs
    ) -> Optional[dict]:
        """Execute API call with improved error handling."""
        try:
            session = await self._get_session()
            url = f"http://{self._host}/{endpoint}"
            
            kwargs.update({
                "auth": aiohttp.BasicAuth(self._username, self._password),
                "headers": {"Content-type": "application/x-www-form-urlencoded"} if data else None,
                "data": data
            })

            result = await self._connection_manager.execute_request(session, method, url, **kwargs)
            
            if result is None or not isinstance(result, dict):
                _LOGGER.warning("Invalid API response: %s", result)
                return None

            self._error_count = 0
            self._available = True
            return result

        except asyncio.CancelledError:
            self._available = False
            raise

        except Exception as err:
            self._error_count += 1
            self._available = self._error_count < self._max_errors
            _LOGGER.error("API call failed: %s", str(err))
            return None

    async def _cleanup_session(self) -> None:
        """Clean up session resources."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

class UpdaterMixin:
    """Mixin for entity update functionality."""
    
    async def async_update_data(self, full_update: bool = True) -> bool:
        """Common update method with rate limiting and data validation."""
        current_time = datetime.now().timestamp()
        
        if hasattr(self, '_min_update_interval') and \
           hasattr(self, '_last_update') and \
           current_time - self._last_update < self._min_update_interval:
            return True
            
        async with self._command_lock:
            data = await self.async_api_call("main")
            if data:
                if full_update:
                    self._data = data
                else:
                    self._data.update(data)
                self._last_update = current_time
                return True
        return False

    def get_data_value(self, key: str, default: Any = None) -> Any:
        """Safely get value from data with type conversion."""
        try:
            value = self._data.get(key, default)
            if isinstance(value, (int, float)) and isinstance(default, (int, float)):
                return type(default)(value)
            return value
        except (TypeError, ValueError):
            return default

class StateMixin:
    """Mixin for state management and mapping."""
    
    def get_mapped_state(self, state_value: Any, mapping: dict, default: str = "Unknown") -> str:
        """Get mapped state with error handling."""
        try:
            if state_value is None:
                return default
            return mapping.get(int(state_value), default)
        except (TypeError, ValueError):
            return default

    def format_duration(self, seconds: int) -> str:
        """Format duration in seconds to human readable string."""
        try:
            minutes = seconds // 60
            hours = minutes // 60
            days = hours // 24
            
            parts = []
            if days > 0:
                parts.append(f"{days}d")
            if hours % 24 > 0:
                parts.append(f"{hours % 24}h")
            if minutes % 60 > 0:
                parts.append(f"{minutes % 60}m")
                
            return " ".join(parts) if parts else "0m"
        except (TypeError, ValueError):
            return "Invalid"

class ErrorHandlingMixin:
    """Enhanced error handling with retry logic."""
    
    async def handle_error(self, err: Exception, context: str = "") -> None:
        """Handle errors with consistent logging and state management."""
        error_msg = f"{context}: {str(err)}" if context else str(err)
        
        if isinstance(err, asyncio.CancelledError):
            return

        if isinstance(err, (asyncio.TimeoutError, aiohttp.ClientError)):
            _LOGGER.warning("Connection error %s", error_msg)
            if hasattr(self, '_error_count'):
                self._error_count += 1
                self._available = self._error_count < self._max_errors
        else:
            _LOGGER.error("Unexpected error %s", error_msg)
            if hasattr(self, '_available'):
                self._available = False

    async def execute_with_retry(
        self, 
        func: Callable, 
        *args, 
        max_retries: int = 3, 
        retry_delay: float = 2.0,
        **kwargs
    ) -> Any:
        """Execute function with retry logic."""
        last_error = None
        
        for attempt in range(max_retries):
            try:
                return await func(*args, **kwargs)
            except asyncio.CancelledError:
                raise
            except Exception as err:
                last_error = err
                if attempt < max_retries - 1:
                    delay = retry_delay * (2 ** attempt)
                    _LOGGER.debug(
                        "Attempt %d failed, retrying in %.1f seconds: %s",
                        attempt + 1, delay, str(err)
                    )
                    await asyncio.sleep(delay)
                    continue
                
                await self.handle_error(err)
                return None

        if last_error:
            _LOGGER.error("Failed after %d attempts: %s", max_retries, str(last_error))
        return None

class ValidationMixin:
    """Mixin for input validation."""
    
    def validate_numeric_value(
        self, 
        value: Any, 
        min_val: float, 
        max_val: float,
        allow_none: bool = False
    ) -> bool:
        """Validate numeric value within range."""
        if value is None:
            return allow_none
            
        try:
            num_value = float(value)
            return min_val <= num_value <= max_val
        except (TypeError, ValueError):
            return False

    def validate_state_value(self, value: Any, valid_states: list) -> bool:
        """Validate state value."""
        try:
            return value in valid_states
        except TypeError:
            return False

    def validate_required_fields(self, data: dict, required_fields: list) -> bool:
        """Validate required fields in data."""
        return all(field in data and data[field] is not None for field in required_fields)

class DeviceInfoMixin:
    """Mixin for device info."""
    
    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        host = getattr(self, '_host', None)
        if not host and hasattr(self, '_updater'):
            host = self._updater._host

        if not host:
            return {}

        return {
            "identifiers": {(DOMAIN, host)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": "Eveus Smart Charger",
            "configuration_url": f"http://{host}",
            "sw_version": self.get_data_value("verFWMain", "unknown") if hasattr(self, 'get_data_value') else "unknown"
        }
