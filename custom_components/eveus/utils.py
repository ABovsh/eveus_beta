"""Consolidated and optimized utility functions for Eveus integration."""
from __future__ import annotations

import logging
import time
import socket
import re
from functools import lru_cache, wraps
from typing import Any, Callable, TypeVar, Optional, Union, Dict, List
from datetime import datetime, timedelta
from urllib.parse import urlparse
import pytz

from homeassistant.core import State, HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import aiohttp

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

T = TypeVar('T')

# =============================================================================
# Data Conversion and Validation Utilities
# =============================================================================

def get_safe_value(
    source: Any,
    key: Optional[str] = None,
    converter: Callable[[Any], T] = float,
    default: Optional[T] = None
) -> Optional[T]:
    """Safely extract and convert values with comprehensive error handling.
    
    Optimized version with better performance and error handling.
    """
    try:
        if source is None:
            return default

        # Handle State objects efficiently
        if isinstance(source, State):
            value = source.state
        elif isinstance(source, dict) and key is not None:
            value = source.get(key)
        else:
            value = source

        # Handle unavailable states
        if value in (None, 'unknown', 'unavailable', ''):
            return default

        # Convert value
        return converter(value)
        
    except (TypeError, ValueError, AttributeError) as err:
        _LOGGER.debug("Safe value conversion failed for %s: %s", 
                     f"{source}.{key}" if key else source, err)
        return default

def validate_required_values(*values: Any) -> bool:
    """Validate all required values are present and valid.
    
    Optimized for performance with early exit.
    """
    return not any(v in (None, 'unknown', 'unavailable', '') for v in values)

@lru_cache(maxsize=128)
def safe_float_cached(value: Union[str, int, float], default: float = 0.0) -> float:
    """Cached safe float conversion for frequently used values."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

@lru_cache(maxsize=64)
def safe_int_cached(value: Union[str, int, float], default: int = 0) -> int:
    """Cached safe integer conversion."""
    try:
        return int(float(value))  # Handle string floats like "1.0"
    except (TypeError, ValueError):
        return default

# =============================================================================
# Device Information and Networking
# =============================================================================

def get_device_info(host: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Get standardized device information with optimized data extraction."""
    # Use safe getters with fallbacks
    firmware = (data.get('verFWMain') or data.get('firmware') or 'Unknown').strip()
    hardware = (data.get('verFWWifi') or data.get('hardware') or 'Unknown').strip()
    
    # Ensure minimum viable values
    if len(firmware) < 2:
        firmware = "Unknown"
    if len(hardware) < 2:
        hardware = "Unknown"
        
    return {
        "identifiers": {(DOMAIN, host)},
        "name": "Eveus EV Charger",
        "manufacturer": "Eveus",
        "model": "Eveus EV Charger",
        "sw_version": firmware,
        "hw_version": hardware,
        "configuration_url": f"http://{host}",
    }

@lru_cache(maxsize=32)
def is_valid_ip(ip: str) -> bool:
    """Cached IP address validation."""
    try:
        socket.inet_aton(ip)
        return True
    except socket.error:
        return False

@lru_cache(maxsize=32)
def is_valid_hostname(hostname: str) -> bool:
    """Cached hostname validation."""
    if len(hostname) > 255:
        return False
        
    if hostname[-1] == ".":
        hostname = hostname[:-1]
        
    allowed = re.compile(r"(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)
    return all(allowed.match(x) for x in hostname.split("."))

def validate_host(host: str) -> str:
    """Validate and clean host input."""
    host = host.strip()
    if not host:
        raise ValueError("Host cannot be empty")
    
    # Remove protocol if present
    if host.startswith(("http://", "https://")):
        parsed = urlparse(host)
        host = parsed.hostname or host

    # Validate IP or hostname
    if not is_valid_ip(host) and not is_valid_hostname(host):
        raise ValueError("Invalid IP address or hostname")
        
    return host

def validate_credentials(username: str, password: str) -> tuple[str, str]:
    """Validate credentials with security checks."""
    username = username.strip()
    password = password.strip()
    
    if not username or not password:
        raise ValueError("Username and password cannot be empty")
    
    if len(username) > 32 or len(password) > 64:
        raise ValueError("Credentials exceed maximum length")
        
    return username, password

# =============================================================================
# Time and Date Utilities
# =============================================================================

@lru_cache(maxsize=64)
def is_dst(timezone_str: str, timestamp: float) -> bool:
    """Cached DST check for performance."""
    try:
        tz = pytz.timezone(timezone_str)
        dt = datetime.fromtimestamp(timestamp, tz=pytz.UTC)
        return bool(dt.astimezone(tz).dst())
    except Exception as err:
        _LOGGER.error("Error checking DST for %s: %s", timezone_str, err)
        return False

@lru_cache(maxsize=128)
def format_duration(seconds: int) -> str:
    """Cached duration formatting for performance."""
    try:
        if seconds <= 0:
            return "0m"
            
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60
        
        if days > 0:
            return f"{days}d {hours:02d}h {minutes:02d}m"
        elif hours > 0:
            return f"{hours}h {minutes:02d}m"
        return f"{minutes}m"
    except (TypeError, ValueError):
        return "0m"

def get_system_time_corrected(
    timestamp: int, 
    timezone_str: str, 
    base_offset: int = 7200
) -> Optional[str]:
    """Get system time with timezone correction optimized for EV charger."""
    try:
        if not timestamp or not timezone_str:
            return None

        # Convert to UTC datetime
        dt_utc = datetime.fromtimestamp(timestamp, tz=pytz.UTC)
        
        # Apply DST-aware correction
        offset = base_offset
        if is_dst(timezone_str, timestamp):
            offset += 3600
        
        # Correct timestamp and convert to local time
        corrected_timestamp = timestamp - offset
        dt_corrected = datetime.fromtimestamp(corrected_timestamp, tz=pytz.UTC)
        
        local_tz = pytz.timezone(timezone_str)
        dt_local = dt_corrected.astimezone(local_tz)
        
        return dt_local.strftime("%H:%M")
        
    except Exception as err:
        _LOGGER.error("Error converting system time: %s", err)
        return None

# =============================================================================
# EV Calculation Utilities
# =============================================================================

@lru_cache(maxsize=64)
def calculate_soc_kwh_cached(
    initial_soc: float,
    battery_capacity: float,
    energy_charged: float,
    efficiency_loss: float
) -> float:
    """Cached SOC calculation in kWh for performance."""
    try:
        initial_kwh = (initial_soc / 100) * battery_capacity
        efficiency = (1 - efficiency_loss / 100)
        charged_kwh = energy_charged * efficiency
        total_kwh = initial_kwh + charged_kwh
        return round(max(0, min(total_kwh, battery_capacity)), 2)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0

@lru_cache(maxsize=64)
def calculate_soc_percent_cached(
    initial_soc: float,
    battery_capacity: float,
    energy_charged: float,
    efficiency_loss: float
) -> float:
    """Cached SOC percentage calculation."""
    try:
        if battery_capacity <= 0:
            return initial_soc
            
        soc_kwh = calculate_soc_kwh_cached(
            initial_soc, battery_capacity, energy_charged, efficiency_loss
        )
        percentage = (soc_kwh / battery_capacity) * 100
        return round(max(0, min(percentage, 100)), 0)
    except (TypeError, ValueError, ZeroDivisionError):
        return initial_soc or 0

def calculate_remaining_time(
    current_soc: Union[float, int],
    target_soc: Union[float, int],
    power_meas: Union[float, int],
    battery_capacity: Union[float, int],
    correction: Union[float, int]
) -> str:
    """Calculate remaining charging time with comprehensive validation."""
    try:
        # Input validation and conversion
        if any(v is None for v in [current_soc, target_soc, power_meas, battery_capacity]):
            return "unavailable"
            
        current_soc = float(current_soc)
        target_soc = float(target_soc)
        power_meas = float(power_meas)
        battery_capacity = float(battery_capacity)
        correction = float(correction) if correction is not None else 7.5

        # Range validation
        if not (0 <= current_soc <= 100) or not (0 <= target_soc <= 100):
            return "unavailable"
            
        if battery_capacity <= 0:
            return "unavailable"

        if power_meas <= 0:
            return "Not charging"

        # Calculate energy needed
        remaining_kwh = (target_soc - current_soc) * battery_capacity / 100
        
        if remaining_kwh <= 0:
            return "Target reached"

        # Account for efficiency loss
        efficiency = (1 - correction / 100)
        effective_power_kw = power_meas * efficiency / 1000
        
        if effective_power_kw <= 0:
            return "Not charging"

        # Calculate time in hours, then convert to seconds
        time_hours = remaining_kwh / effective_power_kw
        total_seconds = int(time_hours * 3600)
        
        if total_seconds < 60:
            return "< 1m"

        return format_duration(total_seconds)

    except Exception as err:
        _LOGGER.error("Error calculating remaining time: %s", err)
        return "unavailable"

# =============================================================================
# Performance Utilities
# =============================================================================

def performance_monitor(func: Callable) -> Callable:
    """Decorator to monitor function performance.""" 
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            execution_time = time.time() - start_time
            if execution_time > 0.1:  # Log slow operations
                _LOGGER.debug("Slow operation %s: %.3fs", func.__name__, execution_time)
    return wrapper

def batch_process(items: List[Any], batch_size: int = 50) -> List[List[Any]]:
    """Split items into batches for efficient processing."""
    return [items[i:i + batch_size] for i in range(0, len(items), batch_size)]

class RateLimiter:
    """Simple rate limiter for API calls."""
    
    def __init__(self, max_calls: int = 10, time_window: int = 60):
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = []
    
    def can_proceed(self) -> bool:
        """Check if operation can proceed based on rate limit."""
        now = time.time()
        # Remove old calls outside time window
        self.calls = [call_time for call_time in self.calls if call_time > now - self.time_window]
        
        if len(self.calls) < self.max_calls:
            self.calls.append(now)
            return True
        return False

# =============================================================================
# HTTP Utilities
# =============================================================================

async def make_http_request(
    hass: HomeAssistant,
    method: str,
    url: str,
    auth: Optional[aiohttp.BasicAuth] = None,
    data: Optional[Union[str, Dict[str, Any]]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30
) -> str:
    """Make HTTP request with optimized session management."""
    session = async_get_clientsession(hass)
    
    headers = headers or {}
    headers.setdefault("Connection", "keep-alive")
    
    timeout_obj = aiohttp.ClientTimeout(total=timeout)
    
    try:
        async with session.request(
            method,
            url,
            auth=auth,
            data=data,
            headers=headers,
            timeout=timeout_obj
        ) as response:
            response.raise_for_status()
            return await response.text()
            
    except aiohttp.ClientResponseError as err:
        _LOGGER.error("HTTP %d error for %s: %s", err.status, url, err)
        raise
    except aiohttp.ClientConnectorError as err:
        _LOGGER.error("Connection error for %s: %s", url, err)
        raise
    except asyncio.TimeoutError:
        _LOGGER.error("Timeout error for %s after %ds", url, timeout)
        raise

# =============================================================================
# Configuration Utilities  
# =============================================================================

def validate_config_entry(entry_data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and clean configuration entry data."""
    required_keys = ['host', 'username', 'password', 'model']
    
    # Check required keys
    missing_keys = [key for key in required_keys if key not in entry_data]
    if missing_keys:
        raise ValueError(f"Missing required configuration keys: {missing_keys}")
    
    # Validate and clean data
    cleaned = {}
    cleaned['host'] = validate_host(entry_data['host'])
    cleaned['username'], cleaned['password'] = validate_credentials(
        entry_data['username'], entry_data['password']
    )
    cleaned['model'] = entry_data['model']
    
    return cleaned

def get_config_value(
    config: Dict[str, Any],
    key: str,
    default: Any = None,
    validator: Optional[Callable] = None
) -> Any:
    """Get configuration value with validation."""
    value = config.get(key, default)
    
    if validator and value is not None:
        try:
            value = validator(value)
        except Exception as err:
            _LOGGER.warning("Invalid config value for %s: %s", key, err)
            value = default
    
    return value

# =============================================================================
# State Management Utilities
# =============================================================================

class StateCache:
    """Simple state cache with TTL support."""
    
    def __init__(self, ttl: int = 30):
        self.ttl = ttl
        self._cache: Dict[str, tuple[Any, float]] = {}
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached value if still valid."""
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < self.ttl:
                return value
            else:
                del self._cache[key]
        return None
    
    def set(self, key: str, value: Any) -> None:
        """Set cached value with timestamp."""
        self._cache[key] = (value, time.time())
    
    def clear(self) -> None:
        """Clear all cached values."""
        self._cache.clear()
    
    def cleanup(self) -> None:
        """Remove expired entries."""
        current_time = time.time()
        expired_keys = [
            key for key, (_, timestamp) in self._cache.items()
            if current_time - timestamp >= self.ttl
        ]
        for key in expired_keys:
            del self._cache[key]

# =============================================================================
# Error Handling Utilities
# =============================================================================

class RetryConfig:
    """Configuration for retry operations."""
    
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_factor: float = 2.0,
        jitter: bool = True
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_factor = exponential_factor
        self.jitter = jitter

def retry_with_backoff(config: RetryConfig = None):
    """Decorator for retry with exponential backoff."""
    if config is None:
        config = RetryConfig()
    
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            import asyncio
            last_exception = None
            
            for attempt in range(config.max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    if attempt < config.max_attempts - 1:
                        delay = min(
                            config.base_delay * (config.exponential_factor ** attempt),
                            config.max_delay
                        )
                        
                        if config.jitter:
                            # Add up to 25% jitter
                            jitter_amount = delay * 0.25 * (0.5 - (time.time() % 1))
                            delay += jitter_amount
                        
                        _LOGGER.debug("Retry attempt %d/%d after %.2fs: %s",
                                    attempt + 1, config.max_attempts, delay, e)
                        await asyncio.sleep(delay)
            
            raise last_exception
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(config.max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    if attempt < config.max_attempts - 1:
                        delay = min(
                            config.base_delay * (config.exponential_factor ** attempt),
                            config.max_delay
                        )
                        
                        if config.jitter:
                            jitter_amount = delay * 0.25 * (0.5 - (time.time() % 1))
                            delay += jitter_amount
                        
                        _LOGGER.debug("Retry attempt %d/%d after %.2fs: %s",
                                    attempt + 1, config.max_attempts, delay, e)
                        time.sleep(delay)
            
            raise last_exception
        
        # Return appropriate wrapper based on function type
        import asyncio
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator

# =============================================================================
# Cleanup and Resource Management
# =============================================================================

def cleanup_resources(*resources):
    """Clean up multiple resources safely."""
    import asyncio
    for resource in resources:
        try:
            if hasattr(resource, 'close'):
                if asyncio.iscoroutinefunction(resource.close):
                    asyncio.create_task(resource.close())
                else:
                    resource.close()
            elif hasattr(resource, 'cleanup'):
                resource.cleanup()
        except Exception as err:
            _LOGGER.debug("Error cleaning up resource %s: %s", resource, err)
