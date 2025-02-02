"""Common code for Eveus integration."""
from __future__ import annotations

import logging
import asyncio
import time
import json
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

# Common Constants
RETRY_DELAY = 10
COMMAND_TIMEOUT = 5
UPDATE_TIMEOUT = 5

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
        self._entities = set()
        self._update_task = None
        self._last_update = 0
        self._update_lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()
        self._retry_count = 0
        self._max_retries = 1

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

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create client session."""
        # Always close old session if exists
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

        # Create new session
        timeout = aiohttp.ClientTimeout(total=5, connect=3)
        connector = aiohttp.TCPConnector(
            limit=1,
            force_close=True,
            enable_cleanup_closed=True,
            ssl=False
        )
        self._session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={"Connection": "close"}
        )
        return self._session

    async def _update(self) -> None:
        """Update the data."""
        session = None
        try:
            session = await self._get_session()
            
            async with session.post(
                f"http://{self._host}/main",
                auth=aiohttp.BasicAuth(self._username, self._password),
                timeout=aiohttp.ClientTimeout(total=5, connect=3),
                headers={"Connection": "close"},
            ) as response:
                response.raise_for_status()
                text = await response.text()
                
                try:
                    data = json.loads(text)
                    if not isinstance(data, dict):
                        raise ValueError(f"Unexpected data type: {type(data)}")
                    
                    # Only update if data has changed
                    if data != self._data:
                        self._data = data
                        self._available = True
                        self._last_update = time.time()
                        self._retry_count = 0

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
                    
                except ValueError as json_err:
                    _LOGGER.error("Invalid JSON received: %s. Raw data: %s", json_err, text)
                    raise

        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            self._available = False
            if self._retry_count < self._max_retries:
                self._retry_count += 1
                _LOGGER.warning(
                    "Connection error for %s (retry %d/%d): %s",
                    self._host, self._retry_count, self._max_retries, str(err)
                )
                await asyncio.sleep(RETRY_DELAY)
            else:
                self._retry_count = 0
                _LOGGER.error("Connection error for %s: %s", self._host, str(err))
                
        finally:
            if session and not session.closed:
                await session.close()
            self._session = None

    async def send_command(self, command: str, value: Any) -> bool:
        """Send command to device with proper session management."""
        session = None
        try:
            session = await self._get_session()
            async with self._command_lock:
                async with session.post(
                    f"http://{self._host}/pageEvent",
                    auth=aiohttp.BasicAuth(self._username, self._password),
                    headers={"Content-type": "application/x-www-form-urlencoded"},
                    data=f"pageevent={command}&{command}={value}",
                    timeout=COMMAND_TIMEOUT,
                ) as response:
                    response.raise_for_status()
                    
                    # Force an immediate update after command
                    await self._update()
                    return True

        except Exception as err:
            _LOGGER.error("Failed to send command %s: %s", command, str(err))
            return False

        finally:
            if session and not session.closed:
                await session.close()
            self._session = None

    async def async_start_updates(self) -> None:
        """Start the update loop."""
        if self._update_task is None:
            self._update_task = asyncio.create_task(self.update_loop())
            _LOGGER.debug("Started update loop for %s", self._host)

    async def update_loop(self) -> None:
        """Handle update loop."""
        _LOGGER.debug("Starting update loop for %s", self._host)
        while True:
            try:
                async with self._update_lock:
                    await self._update()
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
            
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

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
        self._attr_unique_id = f"{updater._host}_{self.ENTITY_NAME.lower().replace(' ', '_')}"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._updater.available

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
