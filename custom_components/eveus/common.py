"""Common code for Eveus integration."""
from __future__ import annotations

import logging
import asyncio
import time
from typing import Any

import aiohttp
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.core import HomeAssistant

from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

# Common Constants
MAX_RETRIES = 3
RETRY_DELAY = 2
COMMAND_TIMEOUT = 5
UPDATE_TIMEOUT = 10
MIN_UPDATE_INTERVAL = 2
MIN_COMMAND_INTERVAL = 1

class EveusUpdater:
    """Class to handle Eveus data updates."""

    def __init__(self, host: str, username: str, password: str, hass: HomeAssistant) -> None:
        """Initialize the updater."""
        self._host = host
        self._username = username
        self._password = password
        self._hass = hass
        self._data = {}
        self._available = True
        self._session = None
        self._entities = []
        self._update_task = None
        self._last_update = time.time()
        self._update_lock = asyncio.Lock()
        self._error_count = 0
        self._max_errors = 3

    def register_entity(self, entity: "BaseEveusEntity") -> None:
        """Register an entity for updates."""
        self._entities.append(entity)

    @property
    def data(self) -> dict:
        """Return the latest data."""
        return self._data

    @property
    def available(self) -> bool:
        """Return if updater is available."""
        return self._available

    @property
    def last_update(self) -> float:
        """Return last update time."""
        return self._last_update

    async def async_start_updates(self) -> None:
        """Start the update loop."""
        if self._update_task is None:
            self._update_task = asyncio.create_task(self._update_loop())

    async def _update_loop(self) -> None:
            """Handle updates with improved error handling."""
            while True:
                try:
                    start_time = time.time()
                    await self._update()
                    
                    # Calculate sleep time to maintain exact interval
                    elapsed = time.time() - start_time
                    sleep_time = max(0, SCAN_INTERVAL.total_seconds() - elapsed)
                    await asyncio.sleep(sleep_time)
                except asyncio.CancelledError:
                    break
                except Exception as err:
                    _LOGGER.error("Error updating data: %s", str(err))
                    await asyncio.sleep(5)  # Short retry on error

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create client session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10, connect=5)
            connector = aiohttp.TCPConnector(limit=1, force_close=True)
            self._session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return self._session

    async def _update(self) -> None:
        """Update the data."""
        session = None
        try:
            session = await self._get_session()
            async with session.post(
                f"http://{self._host}/main",
                auth=aiohttp.BasicAuth(self._username, self._password),
                timeout=UPDATE_TIMEOUT,
            ) as response:
                response.raise_for_status()
                data = await response.text()  # First get raw text
                _LOGGER.debug("Raw response: %s", data)
                
                try:
                    self._data = {} if not data else response.json()
                except ValueError as json_err:
                    _LOGGER.error("Failed to parse JSON response: %s. Raw data: %s", json_err, data)
                    return

                self._available = True
                self._last_update = time.time()
                self._error_count = 0

                for entity in self._entities:
                    try:
                        entity.async_write_ha_state()
                    except Exception as entity_err:
                        _LOGGER.error(
                            "Error updating entity %s: %s",
                            getattr(entity, 'name', 'unknown'),
                            str(entity_err),
                        )

        except aiohttp.ClientError as err:
            self._error_count += 1
            self._available = False if self._error_count >= self._max_errors else True
            _LOGGER.error("Connection error: %s", str(err))
        except Exception as err:
            self._error_count += 1
            self._available = False if self._error_count >= self._max_errors else True
            _LOGGER.error("Unexpected error: %s", str(err), exc_info=True)
        finally:
            if session and not session.closed:
                await session.close()
            
    async def async_shutdown(self) -> None:
        """Shutdown the updater."""
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        if self._session and not self._session.closed:
            await self._session.close()

class RestorableEntity(RestoreEntity):
    """Restorable entity mixin."""

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state:
            await self._async_restore_state(state)

    async def _async_restore_state(self, state) -> None:
        """Restore previous state."""
        pass

class BaseEveusEntity(RestorableEntity, Entity):
    """Base implementation for all Eveus entities."""

    ENTITY_NAME: str = None
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_registry_enabled_default = True
    _attr_entity_registry_visible_default = True

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the entity."""
        super().__init__()
        self._updater = updater
        self._updater.register_entity(self)
        
        if self.ENTITY_NAME is None:
            raise NotImplementedError("ENTITY_NAME must be defined")
            
        self._attr_name = self.ENTITY_NAME
        self._attr_unique_id = f"{updater._host}_{self.ENTITY_NAME.lower().replace(' ', '_')}"

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        await self._updater.async_start_updates()

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity removal."""
        await self._updater.async_shutdown()

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._updater._host)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": f"Eveus ({self._updater._host})",
            "sw_version": self._updater.data.get("verFWMain", "Unknown"),
            "hw_version": self._updater.data.get("verHW", "Unknown"),
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._updater.available

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
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

async def send_eveus_command(
    host: str, 
    username: str, 
    password: str, 
    command: str, 
    value: Any,
    session: aiohttp.ClientSession | None = None
) -> bool:
    """Send command to Eveus device."""
    if session is None:
        timeout = aiohttp.ClientTimeout(total=10, connect=5)
        connector = aiohttp.TCPConnector(limit=1, force_close=True)
        session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        should_close = True
    else:
        should_close = False

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
    except Exception as err:
        _LOGGER.error("Failed to send command %s: %s", command, str(err))
        return False
    finally:
        if should_close:
            await session.close()
