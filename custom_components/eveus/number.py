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
   UnitOfElectricCurrent
)

from .const import (
   DOMAIN,
   MODEL_MAX_CURRENT,
   MIN_CURRENT,
   CONF_MODEL
)

_LOGGER = logging.getLogger(__name__)

class EveusCurrentNumber(RestoreNumber):
   """Eveus current control."""
   _attr_native_step = 1.0
   _attr_mode = NumberMode.SLIDER
   _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
   _attr_device_class = NumberDeviceClass.CURRENT
   _attr_has_entity_name = True
   _attr_name = "Charging Current"
   _attr_icon = "mdi:current-ac"
   _attr_entity_category = EntityCategory.CONFIG

   def __init__(self, host: str, username: str, password: str, model: str) -> None:
       """Initialize current control."""
       super().__init__()
       self._host = host
       self._username = username
       self._password = password
       self._model = model
       self._session = None
       self._attr_unique_id = f"{host}_charging_current"
       self._attr_native_min_value = float(MIN_CURRENT)
       self._attr_native_max_value = float(MODEL_MAX_CURRENT[model])
       self._value = min(self._attr_native_max_value, 16.0)

   @property
   def native_value(self) -> float | None:
       """Return current value."""
       return self._value

   @property
   def device_info(self) -> dict[str, Any]:
       """Return device info."""
       return {
           "identifiers": {(DOMAIN, self._host)},
           "name": "Eveus EV Charger",
           "manufacturer": "Eveus",
           "model": f"Eveus ({self._host})"
       }

   async def _get_session(self) -> aiohttp.ClientSession:
       """Get/create session."""
       if self._session is None or self._session.closed:
           self._session = aiohttp.ClientSession(
               timeout=aiohttp.ClientTimeout(total=10),
               connector=aiohttp.TCPConnector(limit=1, force_close=True)
           )
       return self._session

   async def async_set_native_value(self, value: float) -> None:
       """Set current value."""
       try:
           value = int(min(self._attr_native_max_value, max(self._attr_native_min_value, value)))
           session = await self._get_session()
           async with session.post(
               f"http://{self._host}/pageEvent",
               auth=aiohttp.BasicAuth(self._username, self._password),
               headers={"Content-type": "application/x-www-form-urlencoded"},
               data=f"currentSet={value}",
               timeout=10
           ) as response:
               response.raise_for_status()
               self._value = float(value)
       except Exception as err:
           _LOGGER.error("Error setting current: %s", str(err))

   async def async_update(self) -> None:
       """Update current value."""
       try:
           session = await self._get_session()
           async with session.post(
               f"http://{self._host}/main",
               auth=aiohttp.BasicAuth(self._username, self._password),
               timeout=10
           ) as response:
               data = await response.json()
               if "currentSet" in data:
                   self._value = float(data["currentSet"])
       except Exception as err:
           _LOGGER.error("Error updating current: %s", str(err))

   async def async_added_to_hass(self) -> None:
       """Handle added to Home Assistant."""
       await super().async_added_to_hass()
       state = await self.async_get_last_state()
       if state and state.state not in ('unknown', 'unavailable'):
           try:
               restored_value = float(state.state)
               if self._attr_native_min_value <= restored_value <= self._attr_native_max_value:
                   self._value = restored_value
           except (TypeError, ValueError):
               pass

async def async_setup_entry(
   hass: HomeAssistant,
   entry: ConfigEntry,
   async_add_entities: AddEntitiesCallback,
) -> None:
   """Set up number entities."""
   entities = [
       EveusCurrentNumber(
           entry.data[CONF_HOST],
           entry.data[CONF_USERNAME],
           entry.data[CONF_PASSWORD],
           entry.data[CONF_MODEL]
       )
   ]

   if "entities" not in hass.data[DOMAIN][entry.entry_id]:
       hass.data[DOMAIN][entry.entry_id]["entities"] = {}

   hass.data[DOMAIN][entry.entry_id]["entities"]["number"] = {
       entity.unique_id: entity for entity in entities
   }

   async_add_entities(entities)
