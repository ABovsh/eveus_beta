"""Common code for Eveus integration with enhanced network resilience."""
from __future__ import annotations

import logging
import asyncio
import time
import json
from datetime import datetime
from typing import Any, Optional
from collections import deque, Counter
from contextlib import asynccontextmanager

import aiohttp
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers import aiohttp_client
from homeassistant.components.sensor import SensorEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import utcnow

from .const import DOMAIN
from .utils import get_device_info, get_safe_value

_LOGGER = logging.getLogger(__name__)

# Constants
RETRY_DELAY = 15
COMMAND_TIMEOUT = 25
UPDATE_TIMEOUT = 20
MAX_RETRIES = 3
ERROR_COOLDOWN = 300  # 5 minutes
SESSION_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=5)
CHARGING_UPDATE_INTERVAL = 30  # 30 seconds when charging
IDLE_UPDATE_INTERVAL = 60      # 60 seconds when not charging
CACHE_VALIDITY = 300  # 5 minutes
MAX_QUEUE_AGE = 300  # 5 minutes
MAX_BACKOFF = 300   # 5 minutes

class EveusError(HomeAssistantError):
    """Base class for Eveus errors."""

class EveusConnectionError(EveusError):
    """Error indicating connection issues."""

class EveusResponseError(EveusError):
    """Error indicating invalid response."""

class NetworkManager:
    """Manage network resilience and command queueing."""

    def __init__(self, updater: "EveusUpdater"):
        """Initialize network manager."""
        self._updater = updater
        self._offline_commands = []
        self._last_successful_state = None
        self._reconnect_attempts = 0
        self._quality_metrics = {
            'latency': deque(maxlen=100),
            'success_rate': deque(maxlen=100),
            'error_types': Counter(),
            'last_errors': deque(maxlen=10)
        }
        self._request_timestamps = deque(maxlen=100)

    @property
    def connection_quality(self) -> dict:
        """Get connection quality metrics."""
        if not self._quality_metrics['latency']:
            return {
                'latency_avg': 0,
                'success_rate': 100,
                'recent_errors': 0,
                'requests_per_minute': 0
            }

        now = time.time()
        recent_requests = sum(1 for t in self._request_timestamps 
                            if now - t < 60)

        return {
            'latency_avg': sum(self._quality_metrics['latency']) / len(self._quality_metrics['latency']),
            'success_rate': (sum(self._quality_metrics['success_rate']) / len(self._quality_metrics['success_rate'])) * 100,
            'recent_errors': len(self._quality_metrics['last_errors']),
            'requests_per_minute': recent_requests
        }

    def cache_state(self, state_data: dict) -> None:
        """Cache last known good state."""
        self._last_successful_state = {
            'timestamp': time.time(),
            'data': state_data.copy(),
            'charging_state': state_data.get('state'),
            'critical_values': {
                'current': state_data.get('currentSet'),
                'enabled': state_data.get('evseEnabled')
            }
        }

    def get_cached_state(self) -> dict | None:
        """Get cached state if valid."""
        if not self._last_successful_state:
            return None
            
        age = time.time() - self._last_successful_state['timestamp']
        if age > CACHE_VALIDITY:
            return None
            
        return self._last_successful_state['data']

    async def queue_offline_command(self, command: str, value: Any) -> None:
        """Queue command for later execution when offline."""
        self._offline_commands.append({
            'command': command,
            'value': value,
            'timestamp': time.time(),
            'priority': self._get_command_priority(command)
        })
        _LOGGER.debug("Queued offline command: %s = %s", command, value)

    def _get_command_priority(self, command: str) -> int:
        """Get command priority for replay ordering."""
        priorities = {
            'evseEnabled': 1,  # Highest priority
            'currentSet': 2,
            'oneCharge': 3,
            'rstEM1': 4
        }
        return priorities.get(command, 10)

    async def _replay_commands(self) -> None:
        """Replay queued commands when back online."""
        if not self._offline_commands:
            return

        current_time = time.time()
        valid_commands = [
            cmd for cmd in self._offline_commands 
            if current_time - cmd['timestamp'] < MAX_QUEUE_AGE
        ]
        
        if not valid_commands:
            self._offline_commands.clear()
            return

        _LOGGER.info("Replaying %d queued commands", len(valid_commands))
        valid_commands.sort(key=lambda x: x['priority'])
        
        for cmd in valid_commands:
            try:
                success = await self._updater.send_command(
                    cmd['command'], 
                    cmd['value']
                )
                if success:
                    self._offline_commands.remove(cmd)
            except Exception as err:
                _LOGGER.warning(
                    "Failed to replay command %s: %s",
                    cmd['command'],
                    str(err)
                )

        # Clear old commands
        self._offline_commands = [
            cmd for cmd in self._offline_commands
            if current_time - cmd['timestamp'] < MAX_QUEUE_AGE
        ]

    async def handle_connection_loss(self) -> None:
        """Handle connection loss with exponential backoff."""
        delay = min(30 * (2 ** self._reconnect_attempts), MAX_BACKOFF)
        self._reconnect_attempts += 1
        
        try:
            # Try to reconnect
            success = await self._updater._update(force_retry=True)
            if success:
                self._reconnect_attempts = 0
                if self._offline_commands:
                    await self._replay_commands()
            else:
                await asyncio.sleep(delay)
        except Exception as err:
            _LOGGER.error("Reconnection attempt failed: %s", str(err))
            await asyncio.sleep(delay)

    def update_quality_metrics(
        self, 
        response_time: float, 
        success: bool, 
        error_type: str | None = None
    ) -> None:
        """Update connection quality metrics."""
        self._quality_metrics['latency'].append(response_time)
        self._quality_metrics['success_rate'].append(1 if success else 0)
        self._request_timestamps.append(time.time())
        
        if not success and error_type:
            self._quality_metrics['error_types'][error_type] += 1
            self._quality_metrics['last_errors'].append({
                'type': error_type,
                'timestamp': time.time()
            })

class CommandManager:
    """Manage command execution and retries."""
    
    def __init__(self, updater: "EveusUpdater"):
        """Initialize command manager."""
        self._updater = updater
        self._queue = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None
        self._last_command_time = 0
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start command processing."""
        if not self._task:
            self._task = asyncio.create_task(self._process_queue())

    async def stop(self) -> None:
        """Stop command processing."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _process_queue(self) -> None:
        """Process commands in queue."""
        while True:
            try:
                command, value, future = await self._queue.get()
                try:
                    if not future.done():
                        result = await asyncio.wait_for(
                            self._execute_command(command, value),
                            timeout=COMMAND_TIMEOUT
                        )
                        future.set_result(result)
                except asyncio.TimeoutError:
                    if not future.done():
                        future.set_exception(asyncio.TimeoutError("Command timed out"))
                except Exception as err:
                    if not future.done():
                        future.set_exception(err)
                finally:
                    self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Error processing command queue: %s", err)
                await asyncio.sleep(1)

    async def _execute_command(self, command: str, value: Any) -> bool:
        """Execute command with retries and rate limiting."""
        async with self._lock:
            retries = 3
            delay = 1

            for attempt in range(retries):
                try:
                    # Rate limiting
                    time_since_last = time.time() - self._last_command_time
                    if time_since_last < 1:
                        await asyncio.sleep(1 - time_since_last)

                    session = await self._updater._get_session()
                    start_time = time.time()
                    
                    async with session.post(
                        f"http://{self._updater.host}/pageEvent",
                        auth=aiohttp.BasicAuth(
                            self._updater.username, 
                            self._updater.password
                        ),
                        headers={"Content-type": "application/x-www-form-urlencoded"},
                        data=f"pageevent={command}&{command}={value}",
                        timeout=COMMAND_TIMEOUT,
                    ) as response:
                        response.raise_for_status()
                        self._last_command_time = time.time()
                        
                        # Update metrics
                        self._updater._network_manager.update_quality_metrics(
                            response_time=time.time() - start_time,
                            success=True
                        )
                        return True

                except aiohttp.ClientError as err:
                    if attempt == retries - 1:
                        self._updater._network_manager.update_quality_metrics(
                            response_time=time.time() - start_time,
                            success=False,
                            error_type="client_error"
                        )
                        _LOGGER.error(
                            "Command %s failed after %d retries: %s",
                            command, retries, str(err)
                        )
                        raise
                    _LOGGER.warning(
                        "Command %s failed (attempt %d/%d): %s",
                        command, attempt + 1, retries, str(err)
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
                except Exception as err:
                    self._updater._network_manager.update_quality_metrics(
                        response_time=time.time() - start_time,
                        success=False,
                        error_type="unexpected_error"
                    )
                    _LOGGER.error(
                        "Unexpected error executing command %s: %s",
                        command, str(err)
                    )
                    raise

            return False

    async def send_command(self, command: str, value: Any) -> bool:
        """Send command through queue."""
        try:
            future = asyncio.get_running_loop().create_future()
            await self._queue.put((command, value, future))
            return await asyncio.wait_for(future, timeout=30)
        except asyncio.TimeoutError:
            _LOGGER.error("Command execution timed out")
            return False
        except Exception as err:
            _LOGGER.error("Command execution failed: %s", err)
            return False

class EveusUpdater:
    """Class to handle Eveus data updates."""

    def __init__(self, host: str, username: str, password: str, hass: HomeAssistant) -> None:
        """Initialize the updater."""
        self.host = host
        self.username = username
        self.password = password
        self._hass = hass
        self._data: dict = {}
        self._available = True
        self._session: Optional[aiohttp.ClientSession] = None
        self._entities = set()
        self._update_task: Optional[asyncio.Task] = None
        self._last_update = 0
        self._update_lock = asyncio.Lock()
        self._retry_count = 0
        self._failed_requests = 0
        self._consecutive_errors = 0
        self._last_error_time = 0
        self._last_error_type = None
        self._shutdown_event = asyncio.Event()
        self._command_manager = CommandManager(self)
        self._network_manager = NetworkManager(self)

    @property
    def data(self) -> dict:
        """Return the latest data."""
        return self._data.copy()

    @property
    def available(self) -> bool:
        """Return if updater is available."""
        return self._available

    @property
    def failed_requests(self) -> int:
        """Return number of failed requests."""
        return self._failed_requests

    @property
    def last_error_time(self) -> float:
        """Return timestamp of last error."""
        return self._last_error_time

    @property
    def last_error_type(self) -> str:
        """Return type of last error."""
        return self._last_error_type

    @property
    def consecutive_errors(self) -> int:
        """Return number of consecutive errors."""
        return self._consecutive_errors

    @property
    def connection_quality(self) -> dict:
        """Return connection quality metrics."""
        return self._network_manager.connection_quality

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create client session."""
        if not self._session or self._session.closed:
            self._session = aiohttp_client.async_get_clientsession(self._hass)
        return self._session

    def register_entity(self, entity: BaseEveusEntity) -> None:
        """Register an entity for updates."""
        if entity not in self._entities:
            self._entities.add(entity)
            _LOGGER.debug("Registered entity: %s", entity.name)

    async def send_command(self, command: str, value: Any) -> bool:
        """Send command to device."""
        try:
            return await self._command_manager.send_command(command, value)
        except ConnectionError:
            await self._network_manager.queue_offline_command(command, value)
            return False

    async def _update(self, force_retry: bool = False) -> bool:
        """Update the data."""
        try:
            start_time = time.time()
            session = await self._get_session()
            async with session.post(
                f"http://{self.host}/main",
                auth=aiohttp.BasicAuth(self.username, self.password),
                timeout=aiohttp.ClientTimeout(total=UPDATE_TIMEOUT),
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
                        self._last_update = time.time()
                        self._retry_count = 0
                        self._failed_requests = 0
                        self._consecutive_errors = 0

                        # Cache successful state
                        self._network_manager.cache_state(data)
                        
                        # Update connection metrics
                        self._network_manager.update_quality_metrics(
                            response_time=time.time() - start_time,
                            success=True
                        )

                        # Update all registered entities
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
                    return True
                    
                except ValueError as err:
                    self._network_manager.update_quality_metrics(
                        response_time=time.time() - start_time,
                        success=False,
                        error_type="data_error"
                    )
                    _LOGGER.error("Invalid JSON received: %s", err)
                    self._handle_error("Data error", err)
                    raise

        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            self._network_manager.update_quality_metrics(
                response_time=time.time() - start_time,
                success=False,
                error_type="connection_error"
            )
            self._handle_error("Connection error", err)
            
            # Try to use cached state
            cached_state = self._network_manager.get_cached_state()
            if cached_state:
                self._data = cached_state
                return True
                
            if force_retry:
                await self._network_manager.handle_connection_loss()
            return False
            
        except Exception as err:
            self._network_manager.update_quality_metrics(
                response_time=time.time() - start_time,
                success=False,
                error_type="unexpected_error"
            )
            self._handle_error("Unexpected error", err)
            return False

    def _handle_error(self, error_type: str, error: Exception) -> None:
        """Handle update errors."""
        current_time = time.time()
        self._failed_requests += 1
        self._consecutive_errors += 1
        self._last_error_time = current_time
        self._last_error_type = error_type
        
        # Reset consecutive errors if enough time has passed
        if (current_time - self._last_error_time) > ERROR_COOLDOWN:
            self._consecutive_errors = 1
        
        if self._retry_count < MAX_RETRIES:
            self._retry_count += 1
            _LOGGER.warning(
                "%s for %s: %s (attempt %d/%d)",
                error_type,
                self.host,
                str(error),
                self._retry_count,
                MAX_RETRIES
            )
        else:
            self._available = False
            _LOGGER.error(
                "%s for %s: %s (max retries reached)",
                error_type,
                self.host,
                str(error)
            )

    async def async_start_updates(self) -> None:
        """Start the update loop."""
        if self._update_task is None:
            self._shutdown_event.clear()
            self._update_task = asyncio.create_task(self.update_loop())
            await self._command_manager.start()
            _LOGGER.debug("Started update loop for %s", self.host)

    async def update_loop(self) -> None:
        """Handle update loop with dynamic intervals."""
        _LOGGER.debug("Starting update loop for %s", self.host)
        
        while not self._shutdown_event.is_set():
            try:
                async with self._update_lock:
                    success = await self._update()
                    
                if self._retry_count > 0:
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    # Use shorter interval if charging
                    is_charging = get_safe_value(self._data, "state", int) == 4
                    interval = CHARGING_UPDATE_INTERVAL if is_charging else IDLE_UPDATE_INTERVAL
                    await asyncio.sleep(interval)
                    
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Error in update loop: %s", str(err))
                await asyncio.sleep(RETRY_DELAY)

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
            self._update_task = None

class BaseEveusEntity(RestoreEntity, Entity):
    """Base implementation for Eveus entities."""

    ENTITY_NAME: str = None
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the entity."""
        super().__init__()
        self._updater = updater
        self._updater.register_entity(self)

        if self.ENTITY_NAME is None:
            raise NotImplementedError("ENTITY_NAME must be defined in child class")

        self._attr_name = self.ENTITY_NAME
        self._attr_unique_id = f"eveus_{self.ENTITY_NAME.lower().replace(' ', '_')}"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._updater.available

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return get_device_info(self._updater.host, self._updater.data)

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state:
            await self._async_restore_state(state)
        await self._updater.async_start_updates()

    async def _async_restore_state(self, state) -> None:
        """Restore previous state."""
        pass

class EveusSensorBase(BaseEveusEntity, SensorEntity):
    """Base sensor entity for Eveus."""
    
    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_native_value = None

    @property
    def native_value(self) -> Any | None:
        """Return sensor value."""
        return self._attr_native_value

async def send_eveus_command(
    session: aiohttp.ClientSession,
    host: str,
    username: str,
    password: str,
    command: str,
    value: Any
) -> bool:
    """Legacy command function maintained for compatibility."""
    try:
        async with session.post(
            f"http://{host}/pageEvent",
            auth=aiohttp.BasicAuth(username, password),
            headers={"Content-type": "application/x-www-form-urlencoded"},
            data=f"pageevent={command}&{command}={value}",
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            response.raise_for_status()
            return True
    except Exception as err:
        _LOGGER.error("Command %s failed: %s", command, str(err))
        return False
