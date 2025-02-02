"""Common code for Eveus integration."""
from __future__ import annotations

import logging
import asyncio
import time
import json  # Added import
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.restore_state import RestoreEntity

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
            self._update_task = asyncio.create_task(self.update_loop())

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

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create client session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=5)
            connector = aiohttp.TCPConnector(limit=1, force_close=True, enable_cleanup_closed=True)
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
            
            # Timeout context
            timeout = aiohttp.ClientTimeout(total=5, connect=3)
            
            async with session.post(
                f"http://{self._host}/main",
                auth=aiohttp.BasicAuth(self._username, self._password),
                timeout=timeout,
                headers={"Connection": "close"},
            ) as response:
                response.raise_for_status()
                text = await response.text()
                
                try:
                    data = json.loads(text)  # Fixed JSON parsing
                    
                    if not isinstance(data, dict):
                        _LOGGER.error("Unexpected data type: %s", type(data))
                        return
                    
                    self._data = data
                    self._available = True
                    self._last_update = time.time()
                    self._error_count = 0

                    for entity in self._entities:
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
                    return

        except aiohttp.ClientError as err:
            self._error_count += 1
            self._available = False if self._error_count >= self._max_errors else True
            _LOGGER.error("Connection error for %s: %s", self._host, str(err))
            
        except asyncio.TimeoutError:
            self._error_count += 1
            self._available = False if self._error_count >= self._max_errors else True
            _LOGGER.error("Timeout error for %s", self._host)
            
        except Exception as err:
            self._error_count += 1
            self._available = False if self._error_count >= self._max_errors else True
            _LOGGER.error("Error updating data for %s: %s", self._host, str(err), exc_info=True)
            
        finally:
            # Always close the current session
            if session and not session.closed:
                await session.close()
            self._session = None  # Force new session creation on next update
            
    async def async_shutdown(self) -> None:
        """Shutdown the updater and cleanup resources."""
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                _LOGGER.debug("Update task for %s was cancelled", self._host)
            self._update_task = None
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            
class BaseEveusEntity(RestoreEntity, Entity):
    """Base implementation for all Eveus entities."""

    ENTITY_NAME: str = None
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_registry_enabled_default = True
    _attr_entity_registry_visible_default = True

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the entity."""
        self._updater = updater
        self._updater.register_entity(self)
        
        if self.ENTITY_NAME is None:
            raise NotImplementedError("ENTITY_NAME must be defined")
            
        self._attr_name = self.ENTITY_NAME
        self._attr_unique_id = f"{updater._host}_{self.ENTITY_NAME.lower().replace(' ', '_')}"

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

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self._is_on

    async def _send_switch_command(self, value: int) -> None:
        """Send command to switch."""
        if self._command is None:
            raise NotImplementedError("_command must be defined")
            
        _LOGGER.debug("Sending command %s=%s to %s", self._command, value, self._updater._host)
        
        if await send_eveus_command(
            self._updater._host,
            self._updater._username,
            self._updater._password,
            self._command,
            value,
            await self._updater._get_session()
        ):
            self._is_on = bool(value)
            _LOGGER.debug("Command sent successfully, new state: %s", self._is_on)
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to send command %s=%s to %s", self._command, value, self._updater._host)

    def _get_state_from_value(self, value: Any) -> bool:
        """Convert value to boolean state."""
        if value is None:
            return False
            
        try:
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            if isinstance(value, str):
                return value.lower() in ('true', 'on', 'yes', '1', '1.0')
            return False
        except Exception as err:
            _LOGGER.error("Error converting %s to boolean: %s", value, err)
            return False

    async def async_update(self) -> None:
        """Update state."""
        try:
            if not self._updater.available:
                return
                
            if not self._state_key:
                return
                
            value = self._updater.data.get(self._state_key)
            new_state = self._get_state_from_value(value)
            
            if new_state != self._is_on:
                _LOGGER.debug(
                    "%s state changed: value=%s, new_state=%s",
                    self.name,
                    value,
                    new_state
                )
                self._is_on = new_state
                self.async_write_ha_state()
                
        except Exception as err:
            _LOGGER.error("Error updating %s: %s", self.name, err)

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
