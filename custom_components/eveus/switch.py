# switch.py
"""Support for Eveus switches."""
from __future__ import annotations

import logging
import asyncio
import time
import aiohttp
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.const import (
   CONF_HOST,
   CONF_USERNAME,
   CONF_PASSWORD,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 2
COMMAND_TIMEOUT = 5
MIN_COMMAND_INTERVAL = 1

class BaseEveusSwitch(SwitchEntity):
   """Base class for Eveus switches."""
   _attr_has_entity_name = True
   _attr_entity_category = EntityCategory.CONFIG

   def __init__(self, host: str, username: str, password: str) -> None:
       """Initialize switch."""
       self._host = host
       self._username = username
       self._password = password
       self._available = True
       self._session = None
       self._is_on = False
       self._command_lock = asyncio.Lock()
       self._last_command_time = 0
       self._error_count = 0
       self._max_errors = 3

   @property
   def unique_id(self) -> str:
       """Return unique ID."""
       return f"{self._host}_{self.name}"

   @property
   def available(self) -> bool:
       """Return availability."""
       return self._available

   @property
   def is_on(self) -> bool:
       """Return switch state."""
       return self._is_on

   async def _get_session(self) -> aiohttp.ClientSession:
       """Get/create session."""
       if self._session is None or self._session.closed:
           timeout = aiohttp.ClientTimeout(total=COMMAND_TIMEOUT)
           connector = aiohttp.TCPConnector(limit=1, force_close=True)
           self._session = aiohttp.ClientSession(timeout=timeout, connector=connector)
       return self._session

   async def _send_command(self, command: str, value: int, verify: bool = True) -> bool:
       """Send command with retry logic."""
       current_time = time.time()
       if current_time - self._last_command_time < MIN_COMMAND_INTERVAL:
           await asyncio.sleep(MIN_COMMAND_INTERVAL)

       async with self._command_lock:
           for attempt in range(MAX_RETRIES):
               try:
                   session = await self._get_session()
                   async with session.post(
                       f"http://{self._host}/pageEvent",
                       auth=aiohttp.BasicAuth(self._username, self._password),
                       headers={"Content-type": "application/x-www-form-urlencoded"},
                       data=f"pageevent={command}&{command}={value}",
                       timeout=COMMAND_TIMEOUT
                   ) as response:
                       response.raise_for_status()
                       response_text = await response.text()
                       
                       if "error" in response_text.lower():
                           raise ValueError(f"Error in response: {response_text}")

                       if verify:
                           verify_data = await self._verify_command(session, command, value)
                           if not verify_data:
                               raise ValueError("Command verification failed")

                       self._available = True
                       self._last_command_time = current_time
                       self._error_count = 0
                       return True

               except aiohttp.ClientError as err:
                   if attempt + 1 < MAX_RETRIES and any(x in str(err) for x in ["Connection reset", "Server disconnected"]):
                       await asyncio.sleep(RETRY_DELAY * (2 ** attempt))
                       continue
                   raise

               except Exception as err:
                   if attempt + 1 >= MAX_RETRIES:
                       self._error_count += 1
                       self._available = self._error_count < self._max_errors
                       _LOGGER.error("Command failed: %s", str(err))
                       return False
                   await asyncio.sleep(RETRY_DELAY * (attempt + 1))

           return False

   async def _verify_command(self, session: aiohttp.ClientSession, command: str, value: int) -> bool:
       """Verify command execution."""
       try:
           async with session.post(
               f"http://{self._host}/main",
               auth=aiohttp.BasicAuth(self._username, self._password),
               timeout=COMMAND_TIMEOUT
           ) as response:
               response.raise_for_status()
               data = await response.json()
               if command == "evseEnabled":
                   return data.get("evseEnabled") == value
               elif command == "oneCharge":
                   return data.get("oneCharge") == value
               return True
       except Exception as err:
           _LOGGER.debug("Verification error: %s", str(err))
           return False

   async def async_will_remove_from_hass(self) -> None:
       """Clean up resources."""
       if self._session and not self._session.closed:
           await self._session.close()
           self._session = None

class EveusStopChargingSwitch(BaseEveusSwitch):
   """Charging control switch."""
   _attr_name = "Stop Charging"
   _attr_icon = "mdi:ev-station"

   async def async_turn_on(self, **kwargs: Any) -> None:
       """Enable charging."""
       if await self._send_command("evseEnabled", 1):
           self._is_on = True

   async def async_turn_off(self, **kwargs: Any) -> None:
       """Disable charging."""
       if await self._send_command("evseEnabled", 0):
           self._is_on = False

   async def async_update(self) -> None:
       """Update state."""
       try:
           session = await self._get_session()
           async with session.post(
               f"http://{self._host}/main",
               auth=aiohttp.BasicAuth(self._username, self._password),
               timeout=COMMAND_TIMEOUT
           ) as response:
               response.raise_for_status()
               data = await response.json()
               self._is_on = data.get("evseEnabled") == 1
               self._available = True
       except Exception:
           self._available = False

class EveusOneChargeSwitch(BaseEveusSwitch):
   """One charge mode switch."""
   _attr_name = "One Charge"
   _attr_icon = "mdi:lightning-bolt"

   async def async_turn_on(self, **kwargs: Any) -> None:
       """Enable one charge."""
       if await self._send_command("oneCharge", 1):
           self._is_on = True

   async def async_turn_off(self, **kwargs: Any) -> None:
       """Disable one charge."""
       if await self._send_command("oneCharge", 0):
           self._is_on = False

   async def async_update(self) -> None:
       """Update state."""
       try:
           session = await self._get_session()
           async with session.post(
               f"http://{self._host}/main",
               auth=aiohttp.BasicAuth(self._username, self._password),
               timeout=COMMAND_TIMEOUT
           ) as response:
               response.raise_for_status()
               data = await response.json()
               self._is_on = data.get("oneCharge") == 1
               self._available = True
       except Exception:
           self._available = False

class EveusResetCounterASwitch(BaseEveusSwitch):
   """Reset counter A switch."""
   _attr_name = "Reset Counter A"
   _attr_icon = "mdi:counter"

   async def async_turn_on(self, **kwargs: Any) -> None:
       """Reset counter."""
       if await self._send_command("rstEM1", 0, verify=False):
           self._is_on = False

   async def async_turn_off(self, **kwargs: Any) -> None:
       """Reset action for off state."""
       if await self._send_command("rstEM1", 0, verify=False):
           self._is_on = False

   async def async_update(self) -> None:
       """Update state."""
       try:
           session = await self._get_session()
           async with session.post(
               f"http://{self._host}/main",
               auth=aiohttp.BasicAuth(self._username, self._password),
               timeout=COMMAND_TIMEOUT
           ) as response:
               response.raise_for_status()
               data = await response.json()
               try:
                   iem1 = float(data.get("IEM1", 0))
                   self._is_on = iem1 != 0
               except (ValueError, TypeError):
                   self._is_on = False
               self._available = True
       except Exception:
           self._available = False

async def async_setup_entry(
   hass: HomeAssistant,
   entry: ConfigEntry,
   async_add_entities: AddEntitiesCallback,
) -> None:
   """Set up switches."""
   switches = [
       EveusStopChargingSwitch(
           entry.data[CONF_HOST],
           entry.data[CONF_USERNAME],
           entry.data[CONF_PASSWORD]
       ),
       EveusOneChargeSwitch(
           entry.data[CONF_HOST],
           entry.data[CONF_USERNAME],
           entry.data[CONF_PASSWORD]
       ),
       EveusResetCounterASwitch(
           entry.data[CONF_HOST],
           entry.data[CONF_USERNAME],
           entry.data[CONF_PASSWORD]
       )
   ]

   if "entities" not in hass.data[DOMAIN][entry.entry_id]:
       hass.data[DOMAIN][entry.entry_id]["entities"] = {}

   hass.data[DOMAIN][entry.entry_id]["entities"]["switch"] = {
       switch.unique_id: switch for switch in switches
   }

   async_add_entities(switches)
