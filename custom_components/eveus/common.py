"""Common code for Eveus integration."""
from __future__ import annotations

import logging
import asyncio
import time
import json
from typing import Any
from contextlib import asynccontextmanager

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers import aiohttp_client
from homeassistant.exceptions import HomeAssistantError
from homeassistant.components.sensor import SensorEntity

from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

# Constants
RETRY_DELAY = 15
COMMAND_TIMEOUT = 5
UPDATE_TIMEOUT = 20
SESSION_TIMEOUT = aiohttp.ClientTimeout(total=10, connect=3)

class EveusError(HomeAssistantError):
    """Base class for Eveus errors."""

class EveusConnectionError(EveusError):
    """Error indicating connection issues."""

class EveusResponseError(EveusError):
    """Error indicating invalid response."""

class EveusUpdater:
    """Class to handle Eveus data updates."""

    def __init__(self, host: str, username: str, password: str, hass: HomeAssistant) -> None:
        """Initialize the updater."""
        self.host = host
        self.username = username
        self.password = password
        self._hass = hass
        self._data = {}
        self._available = True
        self._session = None
        self._entities = set()
        self._update_task = None
        self._last_update = 0
        self._update_lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()
        self._retry_count = 0
        self._failed_requests = 0
        self._consecutive_errors = 0
        self._last_error_time = 0
        self._last_error_type = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create client session."""
        if not self._session or self._session.closed:
            self._session = aiohttp_client.async_get_clientsession(self._hass)
        return self._session

    def register_entity(self, entity: "BaseEveusEntity") -> None:
        """Register an entity for updates."""
        if entity not in self._entities:
            self._entities.add(entity)
            _LOGGER.debug("Registered entity: %s", entity.name)

    @property
    def data(self) -> dict:
        """Return the latest data."""
        return self._data

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

    async def _update(self) -> None:
        """Update the data."""
        try:
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
                    
                except ValueError as err:
                    _LOGGER.error("Invalid JSON received: %s", err)
                    self._handle_error("Data error", err)
                    raise

        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            self._handle_error("Connection error", err)
            
        except Exception as err:
            self._handle_error("Unexpected error", err)

    def _handle_error(self, error_type: str, error: Exception) -> None:
        """Handle update errors."""
        self._failed_requests += 1
        self._consecutive_errors += 1
        self._last_error_time = time.time()
        self._last_error_type = error_type
        
        if self._retry_count < 1:
            self._retry_count += 1
            _LOGGER.warning(
                "%s for %s: %s (attempt %d/2)",
                error_type,
                self.host,
                str(error),
                self._retry_count
            )
        else:
            self._available = False
            _LOGGER.error(
                "%s for %s: %s (max retries reached)",
                error_type,
                self.host,
                str(error)
            )

    async def send_command(self, command: str, value: Any) -> bool:
        """Send command to device."""
        async with self._command_lock:
            try:
                async with (await self._get_session()).post(
                    f"http://{self.host}/pageEvent",
                    auth=aiohttp.BasicAuth(self.username, self.password),
                    headers={"Content-type": "application/x-www-form-urlencoded"},
                    data=f"pageevent={command}&{command}={value}",
                    timeout=COMMAND_TIMEOUT,
                ) as response:
                    response.raise_for_status()
                    return True
            except Exception as err:
                _LOGGER.error("Command %s failed: %s", command, str(err))
                return False

    async def async_start_updates(self) -> None:
        """Start the update loop."""
        if self._update_task is None:
            self._update_task = asyncio.create_task(self.update_loop())
            _LOGGER.debug("Started update loop for %s", self.host)

    async def update_loop(self) -> None:
        """Handle update loop."""
        _LOGGER.debug("Starting update loop for %s", self.host)
        while True:
            try:
                async with self._update_lock:
                    await self._update()
                    
                if self._retry_count > 0:
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    await asyncio.sleep(SCAN_INTERVAL.total_seconds())
                    
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Error in update loop: %s", str(err))
                await asyncio.sleep(RETRY_DELAY)

    async def async_shutdown(self) -> None:
        """Shutdown the updater."""
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
        return {
            "identifiers": {(DOMAIN, self._updater.host)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": "Eveus EV Charger",
            "sw_version": self._updater.data.get('verFWMain', 'Unknown'),
        }

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

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity removal."""
        await self._updater.async_shutdown()

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
