"""Support for Eveus number entities."""
from __future__ import annotations

import logging
import asyncio
import time
from typing import Any, Final

import aiohttp

from homeassistant.components.number import (
    NumberEntity,
    NumberMode,
    NumberDeviceClass,
    RestoreNumber,
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

from .const import (
    DOMAIN,
    MODEL_MAX_CURRENT,
    MIN_CURRENT,
    CONF_MODEL,
    API_ENDPOINT_MAIN,
    API_ENDPOINT_EVENT,
    COMMAND_TIMEOUT,
    MAX_RETRIES,
    RETRY_DELAY,
    MIN_COMMAND_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_CURRENT: Final = 16

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eveus number entities."""
    host = entry.data[CONF_HOST]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    model = entry.data[CONF_MODEL]

    entities = [
        EveusCurrentNumber(host, username, password, model),
    ]

    # Store entity references
    if "entities" not in hass.data[DOMAIN][entry.entry_id]:
        hass.data[DOMAIN][entry.entry_id]["entities"] = {}
    
    hass.data[DOMAIN][entry.entry_id]["entities"]["number"] = {
        entity.unique_id: entity for entity in entities
    }

    async_add_entities(entities)

class EveusCurrentNumber(RestoreNumber):
    """Representation of Eveus current control."""

    _attr_native_step: Final = 1.0
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_device_class = NumberDeviceClass.CURRENT
    _attr_has_entity_name = True
    _attr_name = "Charging Current"
    _attr_icon = "mdi:current-ac"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "charging_current"

    def __init__(self, host: str, username: str, password: str, model: str) -> None:
        """Initialize the current control."""
        super().__init__()
        self._host = host
        self._username = username
        self._password = password
        self._model = model
        self._session = None
        self._attr_unique_id = f"{host}_charging_current"
        self._command_lock = asyncio.Lock()
        self._last_command_time = 0
        self._error_count = 0
        self._available = True
        
        # Set min/max values based on model
        self._attr_native_min_value = float(MIN_CURRENT)
        self._attr_native_max_value = float(MODEL_MAX_CURRENT[model])
        self._value = min(self._attr_native_max_value, DEFAULT_CURRENT)

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        return self._value

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._host)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": f"Eveus {self._model}",
            "suggested_area": "Garage",
            "configuration_url": f"http://{self._host}",
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create client session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=COMMAND_TIMEOUT)
            connector = aiohttp.TCPConnector(limit=1, force_close=True)
            self._session = aiohttp.ClientSession(
                timeout=timeout, 
                connector=connector,
                raise_for_status=True
            )
        return self._session

    async def async_set_native_value(self, value: float) -> None:
        """Set new current value with improved error handling and rate limiting."""
        current_time = time.time()
        if current_time - self._last_command_time < MIN_COMMAND_INTERVAL:
            await asyncio.sleep(MIN_COMMAND_INTERVAL)

        async with self._command_lock:
            value = int(min(self._attr_native_max_value, max(self._attr_native_min_value, value)))

            for attempt in range(MAX_RETRIES):
                try:
                    session = await self._get_session()
                    async with session.post(
                        f"http://{self._host}{API_ENDPOINT_EVENT}",
                        auth=aiohttp.BasicAuth(self._username, self._password),
                        headers={"Content-type": "application/x-www-form-urlencoded"},
                        data=f"currentSet={value}",
                        timeout=COMMAND_TIMEOUT,
                    ) as response:
                        await response.text()  # Ensure response is read
                        
                        # Verify setting was applied
                        async with session.post(
                            f"http://{self._host}{API_ENDPOINT_MAIN}",
                            auth=aiohttp.BasicAuth(self._username, self._password),
                            timeout=COMMAND_TIMEOUT,
                        ) as verify_response:
                            data = await verify_response.json()
                            if data.get("currentSet") == value:
                                self._value = float(value)
                                self._last_command_time = time.time()
                                self._error_count = 0
                                self._available = True
                                return
                            raise ValueError("Current setting verification failed")

                except Exception as err:
                    if attempt + 1 >= MAX_RETRIES:
                        self._error_count += 1
                        self._available = self._error_count < 3
                        _LOGGER.error(
                            "Failed to set current after %d attempts: %s",
                            MAX_RETRIES,
                            str(err)
                        )
                        return
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))

    async def async_update(self) -> None:
        """Update current value from API with error handling."""
        try:
            session = await self._get_session()
            async with session.post(
                f"http://{self._host}{API_ENDPOINT_MAIN}",
                auth=aiohttp.BasicAuth(self._username, self._password),
                timeout=COMMAND_TIMEOUT,
            ) as response:
                data = await response.json()
                if "currentSet" in data:
                    self._value = float(data["currentSet"])
                    self._available = True
                    self._error_count = 0

        except Exception as err:
            self._error_count += 1
            self._available = self._error_count < 3
            _LOGGER.error("Error updating current value: %s", str(err))

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
