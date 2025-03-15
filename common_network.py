"""Network handling and state management for Eveus integration."""
import logging
import asyncio
import time
import json
from typing import Any, Optional, Set, Dict, List
from collections import deque, Counter
from enum import Enum

import aiohttp
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import aiohttp_client

from .const import (
    CHARGING_UPDATE_INTERVAL,
    IDLE_UPDATE_INTERVAL,
    RETRY_DELAY,
    UPDATE_TIMEOUT,
    ERROR_COOLDOWN
)
from .utils import get_safe_value
from .common_command import CommandManager

_LOGGER = logging.getLogger(__name__)

class ErrorClassification(Enum):
    """Error classifications for recovery strategies."""
    TRANSIENT = "transient"         # Temporary errors that should resolve on their own
    CONNECTIVITY = "connectivity"   # Network connectivity issues
    AUTHENTICATION = "authentication"  # Authentication or permission errors
    DEVICE = "device"               # Device-related errors (power, reboot)
    PROTOCOL = "protocol"           # Protocol or format errors
    INTERNAL = "internal"           # Internal errors in Home Assistant
    CRITICAL = "critical"           # Serious errors requiring user intervention
    UNKNOWN = "unknown"             # Unclassified errors

class NetworkManager:
    """Network resilience management with improved error handling."""
    def __init__(self, host: str) -> None:
        """Initialize network manager."""
        self.host = host
        self._last_successful_state = None
        self._reconnect_attempts = 0
        self._quality_metrics = {
            'latency': deque(maxlen=20),
            'success_rate': deque(maxlen=20),
            'success_rate_history': deque(maxlen=100),  # Added success rate history
            'error_types': Counter(),
            'error_classes': Counter(),
            'last_errors': deque(maxlen=10),
            'last_successful_connection': time.time(),  # Added timestamp tracking
            'consecutive_errors': 0,
            'health_score': 100,
        }
        self._request_timestamps = deque(maxlen=30)
        self._error_classifications = {
            "TimeoutError": ErrorClassification.TRANSIENT,
            "asyncio.TimeoutError": ErrorClassification.TRANSIENT,
            "ClientConnectorError": ErrorClassification.CONNECTIVITY,
            "ClientOSError": ErrorClassification.CONNECTIVITY,
            "ServerDisconnectedError": ErrorClassification.CONNECTIVITY,
            "ConnectionError": ErrorClassification.CONNECTIVITY,
            "ClientResponseError": ErrorClassification.PROTOCOL,
            "ContentTypeError": ErrorClassification.PROTOCOL,
            "JSONDecodeError": ErrorClassification.PROTOCOL,
            "KeyError": ErrorClassification.PROTOCOL,
            "ValueError": ErrorClassification.PROTOCOL,
            "RuntimeError": ErrorClassification.INTERNAL,
            "AttributeError": ErrorClassification.INTERNAL,
            "TypeError": ErrorClassification.INTERNAL,
            "Exception": ErrorClassification.UNKNOWN,
        }
        # Recovery strategies by error class
        self._recovery_strategies = {
            ErrorClassification.TRANSIENT: "wait_and_retry",
            ErrorClassification.CONNECTIVITY: "connection_reset",
            ErrorClassification.AUTHENTICATION: "notify_user",
            ErrorClassification.DEVICE: "power_cycle",
            ErrorClassification.PROTOCOL: "adjust_timeout",
            ErrorClassification.INTERNAL: "report_issue",
            ErrorClassification.CRITICAL: "notify_user",
            ErrorClassification.UNKNOWN: "wait_and_retry",
        }

    def _classify_error(self, error_type: str) -> ErrorClassification:
        """Classify error type into error category."""
        # Check for exact matches
        if error_type in self._error_classifications:
            return self._error_classifications[error_type]
            
        # Check for partial matches (class hierarchy)
        for known_error, classification in self._error_classifications.items():
            if error_type.endswith(known_error):
                return classification
                
        return ErrorClassification.UNKNOWN

    @property
    def connection_quality(self) -> dict:
        """Get connection quality metrics."""
        if not self._quality_metrics['latency']:
            return {
                'latency_avg': 0,
                'success_rate': 100,
                'recent_errors': 0,
                'requests_per_minute': 0,
                'success_rate_history': list(self._quality_metrics['success_rate_history']),
                'last_successful_connection': self._quality_metrics.get('last_successful_connection', time.time()),
                'health_score': self._quality_metrics.get('health_score', 100),
                'consecutive_errors': self._quality_metrics.get('consecutive_errors', 0),
                'error_classes': dict(self._quality_metrics.get('error_classes', {})),
                'recovery_recommendation': self.get_recovery_recommendation(),
            }

        now = time.time()
        recent_requests = sum(1 for t in self._request_timestamps 
                            if now - t < 60)
        
        # Calculate success rate
        success_rate = (sum(self._quality_metrics['success_rate']) / 
                     max(len(self._quality_metrics['success_rate']), 1)) * 100
                     
        # Store in history
        self._quality_metrics['success_rate_history'].append(success_rate)
        
        # Calculate health score based on multiple factors
        health_score = self._calculate_health_score(success_rate)
        self._quality_metrics['health_score'] = health_score

        return {
            'latency_avg': sum(self._quality_metrics['latency']) / max(len(self._quality_metrics['latency']), 1),
            'success_rate': success_rate,
            'recent_errors': len(self._quality_metrics['last_errors']),
            'requests_per_minute': recent_requests,
            'success_rate_history': list(self._quality_metrics['success_rate_history']),
            'last_successful_connection': self._quality_metrics.get('last_successful_connection', time.time()),
            'health_score': health_score,
            'consecutive_errors': self._quality_metrics.get('consecutive_errors', 0),
            'error_classes': {str(k.value): v for k, v in self._quality_metrics.get('error_classes', {}).items()},
            'recovery_recommendation': self.get_recovery_recommendation(),
        }
        
    def _calculate_health_score(self, success_rate: float) -> int:
        """Calculate network health score based on various metrics."""
        score = 100
        
        # Success rate impact (0-50 points)
        success_points = min(50, success_rate / 2)
        
        # Recent errors impact (0-20 points)
        recent_errors = len(self._quality_metrics['last_errors'])
        error_points = max(0, 20 - recent_errors * 4)
        
        # Consecutive errors impact (0-15 points)
        consecutive_errors = self._quality_metrics.get('consecutive_errors', 0)
        consecutive_points = max(0, 15 - consecutive_errors * 3)
        
        # Latency impact (0-15 points)
        if self._quality_metrics['latency']:
            avg_latency = sum(self._quality_metrics['latency']) / len(self._quality_metrics['latency'])
            latency_points = max(0, 15 - (avg_latency / 2))
        else:
            latency_points = 15
            
        # Calculate final score
        score = success_points + error_points + consecutive_points + latency_points
        
        return max(0, min(100, int(score)))

    def update_metrics(self, response_time: float, success: bool, error_type: str = None) -> None:
        """Update connection quality metrics with improved error classification."""
        self._quality_metrics['latency'].append(response_time)
        self._quality_metrics['success_rate'].append(1 if success else 0)
        self._request_timestamps.append(time.time())
        
        if success:
            self._quality_metrics['last_successful_connection'] = time.time()
            self._quality_metrics['consecutive_errors'] = 0
        else:
            self._quality_metrics['consecutive_errors'] = self._quality_metrics.get('consecutive_errors', 0) + 1
            
        if not success and error_type:
            error_class = self._classify_error(error_type)
            self._quality_metrics['error_types'][error_type] += 1
            self._quality_metrics['error_classes'][error_class] = self._quality_metrics.get('error_classes', Counter()).get(error_class, 0) + 1
            self._quality_metrics['last_errors'].append({
                'type': error_type,
                'class': str(error_class.value),
                'timestamp': time.time(),
                'details': self._get_error_details(error_type, error_class)
            })

    def _get_error_details(self, error_type: str, error_class: ErrorClassification) -> str:
        """Get human-readable error details."""
        details = {
            ErrorClassification.TRANSIENT: "Temporary error that should resolve on its own",
            ErrorClassification.CONNECTIVITY: "Network connectivity issue with the device",
            ErrorClassification.AUTHENTICATION: "Authentication or permission error",
            ErrorClassification.DEVICE: "Device-related error (may need power cycle)",
            ErrorClassification.PROTOCOL: "Communication protocol or data format error",
            ErrorClassification.INTERNAL: "Internal Home Assistant error",
            ErrorClassification.CRITICAL: "Serious error requiring user intervention",
            ErrorClassification.UNKNOWN: "Unclassified error",
        }
        
        return details.get(error_class, "Unknown error type")

    def get_recovery_recommendation(self) -> Dict[str, Any]:
        """Get recommended recovery action based on error patterns."""
        # Analyze recent errors
        recent_errors = [e for e in self._quality_metrics['last_errors'] 
                       if time.time() - e['timestamp'] < 300]
        
        if not recent_errors:
            return {
                "action": "none",
                "description": "No recovery action needed",
                "severity": "none"
            }
            
        # Count error classes
        error_classes = Counter()
        for error in recent_errors:
            error_class = error.get('class', 'unknown')
            error_classes[error_class] += 1
            
        # Check for consecutive errors
        consecutive_errors = self._quality_metrics.get('consecutive_errors', 0)
        
        # Determine recovery action based on error patterns
        if consecutive_errors >= 10:
            return {
                "action": "power_cycle_device",
                "description": "Device may be unresponsive, consider power cycling",
                "severity": "high"
            }
        elif error_classes.get('connectivity', 0) >= 3:
            return {
                "action": "check_network",
                "description": "Network connectivity issues detected",
                "severity": "medium"
            }
        elif error_classes.get('protocol', 0) >= 3:
            return {
                "action": "restart_integration",
                "description": "Communication protocol issues detected",
                "severity": "medium"
            }
        elif consecutive_errors >= 5:
            return {
                "action": "retry_with_backoff",
                "description": "Multiple consecutive errors, backing off",
                "severity": "low"
            }
        
        return {
            "action": "monitor",
            "description": "Minor errors detected, monitoring situation",
            "severity": "low"
        }

    def cache_state(self, state_data: dict) -> None:
        """Cache last known good state."""
        self._last_successful_state = {
            'timestamp': time.time(),
            'data': state_data.copy()
        }

    def get_cached_state(self) -> dict | None:
        """Get cached state if valid."""
        if not self._last_successful_state:
            return None
            
        age = time.time() - self._last_successful_state['timestamp']
        if age > ERROR_COOLDOWN:
            return None
            
        return self._last_successful_state['data']


class EveusUpdater:
    """Main updater class with enhanced network handling."""

    def __init__(self, host: str, username: str, password: str, hass: HomeAssistant) -> None:
        """Initialize the updater."""
        self.host = host
        self.username = username
        self.password = password
        self._hass = hass
        self._data: Dict[str, Any] = {}
        self._available = True
        self._session: Optional[aiohttp.ClientSession] = None
        self._entities: Set[Any] = set()
        self._update_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._command_manager = CommandManager(self)
        self._network = NetworkManager(host)
        self._entity_update_callbacks = []

    @property
    def data(self) -> dict:
        """Return the latest data."""
        return self._data.copy()

    @property
    def available(self) -> bool:
        """Return if updater is available."""
        return self._available

    @property
    def hass(self) -> HomeAssistant:
        """Return Home Assistant instance."""
        return self._hass

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create client session."""
        if not self._session or self._session.closed:
            self._session = aiohttp_client.async_get_clientsession(self._hass)
        return self._session

    def register_entity(self, entity) -> None:
        """Register an entity for updates."""
        if entity not in self._entities:
            self._entities.add(entity)

    def register_update_callback(self, callback_fn: callback) -> None:
        """Register callback for data updates."""
        if callback_fn not in self._entity_update_callbacks:
            self._entity_update_callbacks.append(callback_fn)
    
    def unregister_update_callback(self, callback_fn: callback) -> None:
        """Unregister callback for data updates."""
        if callback_fn in self._entity_update_callbacks:
            self._entity_update_callbacks.remove(callback_fn)

    def notify_entities(self) -> None:
        """Notify all registered entities of data update."""
        for entity in self._entities:
            if hasattr(entity, 'hass') and entity.hass:
                try:
                    entity.async_write_ha_state()
                except Exception as err:
                    _LOGGER.error(
                        "Error updating entity %s: %s",
                        getattr(entity, 'name', 'unknown'),
                        str(err)
                    )
        
        for callback_fn in self._entity_update_callbacks:
            try:
                callback_fn()
            except Exception as err:
                _LOGGER.error("Error in update callback: %s", str(err))

    async def send_command(self, command: str, value: Any) -> bool:
        """Send command to device."""
        return await self._command_manager.send_command(command, value)

    async def _update(self) -> None:
        """Update device data with improved error handling."""
        try:
            start_time = time.time()
            session = await self._get_session()
            
            async with session.post(
                f"http://{self.host}/main",
                auth=aiohttp.BasicAuth(self.username, self.password),
                timeout=UPDATE_TIMEOUT,
            ) as response:
                response.raise_for_status()
                text = await response.text()
                
                try:
                    data = json.loads(text)
                    if not isinstance(data, dict):
                        raise ValueError(f"Unexpected data type: {type(data)}")
                    
                    if data != self._data:
                        self._data = data
                        self._available = True
                        self._network.cache_state(data)
                        self._network.update_metrics(
                            response_time=time.time() - start_time,
                            success=True
                        )
                        self.notify_entities()
                    else:
                        # Still update metrics even if data hasn't changed
                        self._network.update_metrics(
                            response_time=time.time() - start_time,
                            success=True
                        )
                except ValueError as err:
                    _LOGGER.error("Error parsing JSON: %s", err)
                    self._network.update_metrics(
                        response_time=time.time() - start_time,
                        success=False,
                        error_type="JSONDecodeError"
                    )
                
        except aiohttp.ClientResponseError as err:
            self._network.update_metrics(
                response_time=time.time() - start_time,
                success=False,
                error_type=f"ClientResponseError:{err.status}"
            )
            self._handle_update_error(err)
        except aiohttp.ClientConnectorError as err:
            self._network.update_metrics(
                response_time=time.time() - start_time,
                success=False,
                error_type="ClientConnectorError"
            )
            self._handle_update_error(err)
        except asyncio.TimeoutError as err:
            self._network.update_metrics(
                response_time=UPDATE_TIMEOUT,
                success=False,
                error_type="TimeoutError"
            )
            self._handle_update_error(err)
        except Exception as err:
            self._network.update_metrics(
                response_time=time.time() - start_time,
                success=False,
                error_type=type(err).__name__
            )
            self._handle_update_error(err)

    def _handle_update_error(self, err: Exception) -> None:
        """Handle update errors with improved recovery logic."""
        # Try to use cached state first
        cached_state = self._network.get_cached_state()
        if cached_state:
            if self._data != cached_state:
                _LOGGER.info("Using cached state due to connection error: %s", str(err))
                self._data = cached_state
                self.notify_entities()
            return
            
        # No cached state available, mark as unavailable
        if self._available:
            self._available = False
            self.notify_entities()
            
        _LOGGER.error("Update failed: %s", str(err))
        
        # Get recovery recommendation - we could take automated actions here
        # based on the recommendation, like adjusting update intervals
        recovery = self._network.get_recovery_recommendation()
        if recovery["severity"] == "high":
            _LOGGER.warning("Connection issue requires attention: %s", recovery["description"])

    async def async_start_updates(self) -> None:
        """Start the update loop."""
        if self._update_task is None:
            self._shutdown_event.clear()
            self._update_task = asyncio.create_task(self.update_loop())
            await self._command_manager.start()
            _LOGGER.debug("Started update loop for %s", self.host)

    async def update_loop(self) -> None:
        """Handle update loop with dynamic intervals and exponential backoff."""
        retry_count = 0
        max_retry_delay = 300  # 5 minutes maximum
        
        while not self._shutdown_event.is_set():
            try:
                await self._update()
                
                # Reset retry count after successful update
                retry_count = 0
                
                # Use shorter interval if charging
                is_charging = get_safe_value(self._data, "state", int) == 4
                interval = CHARGING_UPDATE_INTERVAL if is_charging else IDLE_UPDATE_INTERVAL
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Error in update loop: %s", str(err))
                
                # Calculate backoff time with exponential increase
                retry_delay = min(RETRY_DELAY * (2 ** retry_count), max_retry_delay)
                retry_count += 1
                
                _LOGGER.debug("Retrying in %s seconds (attempt %s)", retry_delay, retry_count)
                await asyncio.sleep(retry_delay)

    async def async_shutdown(self) -> None:
        """Shutdown the updater."""
        self._shutdown_event.set()
        await self._command_manager.stop()
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
