"""Support for Eveus number entities."""
from __future__ import annotations

import logging
import asyncio
import aiohttp
from typing import Any

from homeassistant.components.number import (
    NumberEntity,
    NumberMode,
    NumberDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.const import (
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
    UnitOfElectricCurrent,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Constants for current control
MIN_CURRENT = 8
MAX_CURRENT = 16
DEFAULT_CURRENT = 16
MAX_RETRIES = 3
RETRY_DELAY = 2

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eveus number entities."""
    host = entry.data[CONF_HOST]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    entities = [
        EveusCurrentNumber(host, username, password),
    ]
    
    async_add_entities(entities)

class EveusCurrentNumber(NumberEntity):
    """Representation of Eveus current control."""

    _attr_min_value = MIN_CURRENT
    _attr_max_value = MAX_CURRENT
    _attr_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_device_class = NumberDeviceClass.CURRENT
    _attr_has_entity_name = True
    _attr_name = "Charging Current"
    _attr_icon = "mdi:current-ac"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, host: str, username: str, password: str) -> None:
        """Initialize the current control."""
        self._host = host
        self._username = username
        self._password = password
        self._attr_unique_id = f"{host}_charging_current"
        self._session = None
        self._available = True
        self._value = DEFAULT_CURRENT
        self._last_update = 0
        self._update_lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._available

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._host)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": f"Eveus ({self._host})",
        }
        
    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self._value

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create client session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def async_set_native_value(self, value: float) -> None:
        """Set new current value with retry logic."""
        async with self._command_lock:
            for attempt in range(MAX_RETRIES):
                try:
                    session = await self._get_session()
                    async with session.post(
                        f"http://{self._host}/pageEvent",
                        auth=aiohttp.BasicAuth(self._username, self._password),
                        headers={"Content-type": "application/x-www-form-urlencoded"},
                        data=f"currentSet={int(value)}",
                        timeout=5,
                    ) as response:
                        response.raise_for_status()
                        self._value = value
                        self._available = True
                        _LOGGER.debug(
                            "Successfully set charging current to %s A for %s",
                            value,
                            self._host,
                        )
                        return
                except Exception as error:
                    _LOGGER.warning(
                        "Attempt %d: Failed to set charging current for %s: %s",
                        attempt + 1,
                        self._host,
                        error,
                    )
                    if attempt + 1 < MAX_RETRIES:
                        await asyncio.sleep(RETRY_DELAY)
            
            self._available = False
            _LOGGER.error(
                "Failed to set charging current after %d attempts for %s",
                MAX_RETRIES,
                self._host,
            )

    async def async_update(self) -> None:
        """Update the current value with retry logic."""
        async with self._update_lock:
            for attempt in range(MAX_RETRIES):
                try:
                    session = await self._get_session()
                    async with session.post(
                        f"http://{self._host}/main",
                        auth=aiohttp.BasicAuth(self._username, self._password),
                        timeout=5,
                    ) as response:
                        response.raise_for_status()
                        data = await response.json()
                        if "currentSet" in data:
                            self._value = float(data["currentSet"])
                            self._available = True
                            return
                except Exception as error:
                    if attempt + 1 < MAX_RETRIES:
                        _LOGGER.debug(
                            "Attempt %d: Failed to get charging current for %s: %s",
                            attempt + 1,
                            self._host,
                            error,
                        )
                        await asyncio.sleep(RETRY_DELAY)
                    else:
                        self._available = False
                        _LOGGER.warning(
                            "Failed to get charging current after %d attempts for %s: %s",
                            MAX_RETRIES,
                            self._host,
                            error,
                        )
