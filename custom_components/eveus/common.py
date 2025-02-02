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

from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

# Constants
RETRY_DELAY = 10
COMMAND_TIMEOUT = 5
UPDATE_TIMEOUT = 5
SESSION_TIMEOUT = aiohttp.ClientTimeout(total=10, connect=3)

class EveusError(HomeAssistantError):
    """Base class for Eveus errors."""

class EveusConnectionError(EveusError):
    """Error indicating connection issues."""

@asynccontextmanager
async def get_eveus_session(hass: HomeAssistant) -> aiohttp.ClientSession:
    """Get aiohttp session."""
    session = aiohttp_client.async_get_clientsession(hass)
    try:
        yield session
    finally:
        pass  # Session managed by HA

async def send_eveus_command(
    host: str, 
    username: str, 
    password: str, 
    command: str, 
    value: Any,
    session: aiohttp.ClientSession | None = None
) -> bool:
    """Send command to Eveus device."""
    try:
        async with session.post(
            f"http://{host}/pageEvent",
            auth=aiohttp.BasicAuth(username, password),
            headers={"Content-type": "application/x-www-form-urlencoded"},
            data=f"pageevent={command}&{command}={value}",
            timeout=COMMAND_TIMEOUT,
        ) as response:
            response.raise_for_status()
            return True
    
    except aiohttp.ClientError as err:
        _LOGGER.error(
            "Command %s failed: %s (Host: %s)",
            command,
            str(err),
            host
        )
        return False

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
        self._retry_needed = False
        self._failed_requests = 0

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
        """Return number of consecutive failed requests."""
        return self._failed_requests

    async def _update(self) -> None:
        """Update the data."""
        try:
            session = await self._get_session()
            async with session.post(
                f"http://{self.host}/main",
                auth=aiohttp.BasicAuth(self.username, self.password),
                timeout=aiohttp.ClientTimeout(total=10),
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
                        self._retry_needed = False
                        self._failed_requests = 0  # Reset on successful update

                        # Update registered entities
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
                    
                except ValueError as json_err:
                    _LOGGER.error("Invalid JSON received: %s", json_err)
                    self._failed_requests += 1
                    raise

        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            self._available = False
            self._retry_needed = True
            self._failed_requests += 1
            _LOGGER.error("Connection error for %s: %s", self.host, str(err))
            
        except Exception as err:
            self._available = False
            self._failed_requests += 1
            _LOGGER.error("Error updating data for %s: %s", self.host, str(err))

    async def send_command(self, command: str, value: Any) -> bool:
        """Send command to device."""
        async with self._command_lock:
            return await send_eveus_command(
                self.host,
                self.username,
                self.password,
                command,
                value,
                await self._get_session()
            )

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
                    
                if self._retry_needed:
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                    
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
        self._attr_unique_id = f"{updater.host}_{self.ENTITY_NAME.lower().replace(' ', '_')}"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._updater.available

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._updater.host)},
            "name": f"Eveus ({self._updater.host})",
            "manufacturer": "Eveus",
            "model": "Eveus EV Charger",
            "sw_version": f"Firmware: {self._updater.data.get('verFWMain', 'Unknown')}",
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

class BaseEveusNumericEntity(BaseEveusEntity):
    """Base class for numeric entities."""

    _key: str = None
    _attr_suggested_display_precision = 2
    _attr_native_value = None

    @property
    def native_value(self) -> float | None:
        """Return the entity value."""
        try:
            value = self._updater.data.get(self._key)
            if value in (None, "", "undefined", "null"):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None
