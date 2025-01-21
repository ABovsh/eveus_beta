"""Config flow for Eveus integration."""
from __future__ import annotations

import logging
import asyncio
from typing import Any, Final
from functools import partial

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult, AbortFlow
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import aiohttp_client

from .const import (
   DOMAIN,
   COMMAND_TIMEOUT,
   API_ENDPOINT_MAIN,
   HELPER_EV_BATTERY_CAPACITY,
   HELPER_EV_INITIAL_SOC,
   HELPER_EV_SOC_CORRECTION,
   HELPER_EV_TARGET_SOC,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
   {
       vol.Required(CONF_HOST): str,
       vol.Required(CONF_USERNAME): str,
       vol.Required(CONF_PASSWORD): str,
   }
)

# Required helper entities with their valid ranges
REQUIRED_HELPERS = {
   HELPER_EV_BATTERY_CAPACITY: (10, 160),  # kWh
   HELPER_EV_INITIAL_SOC: (0, 100),  # %
   HELPER_EV_SOC_CORRECTION: (0, 10),  # %
   HELPER_EV_TARGET_SOC: (0, 100),  # %
}

async def validate_host_format(host: str) -> bool:
   """Validate host format."""
   if not host:
       return False
   if host.startswith(("http://", "https://")):
       return False
   if ":" in host or "/" in host:
       return False
   return True

async def validate_helper_values(hass: HomeAssistant) -> tuple[bool, list[str]]:
   """Validate helper entities and their values."""
   invalid_helpers = []
   for helper_id, (min_val, max_val) in REQUIRED_HELPERS.items():
       state = hass.states.get(helper_id)
       if not state:
           invalid_helpers.append(f"Missing helper: {helper_id}")
           continue
           
       try:
           value = float(state.state)
           if not min_val <= value <= max_val:
               invalid_helpers.append(
                   f"{helper_id}: Value {value} outside range [{min_val}, {max_val}]"
               )
       except (ValueError, TypeError):
           invalid_helpers.append(
               f"{helper_id}: Invalid value '{state.state}'"
           )
           
   return len(invalid_helpers) == 0, invalid_helpers

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input with comprehensive checks."""
    
    # Validate host format
    if not await validate_host_format(data[CONF_HOST]):
        raise InvalidHost("Invalid host format")
   
    # Validate helper entities
    valid_helpers, invalid_list = await validate_helper_values(hass)
    if not valid_helpers:
        raise InvalidHelperValues(invalid_list)

    # Test connection and get device info
    try:
        session = aiohttp_client.async_get_clientsession(hass)
        auth = aiohttp.BasicAuth(data[CONF_USERNAME], data[CONF_PASSWORD])
        
        async with async_timeout.timeout(COMMAND_TIMEOUT):
            async with session.post(
                f"http://{data[CONF_HOST]}{API_ENDPOINT_MAIN}",
                auth=auth,
                ssl=False,
            ) as response:
                if response.status == 401:
                    raise InvalidAuth
                    
                response.raise_for_status()
                result = await response.json()
                
                if not isinstance(result, dict):
                    raise CannotConnect("Invalid response format")
                
                # Get device info with dynamic current range
                device_info = {
                    "title": f"Eveus ({data[CONF_HOST]})",
                    "firmware_version": result.get("verFWMain", "Unknown").strip(),
                    "station_id": result.get("stationId", "Unknown").strip(),
                    "min_current": float(result.get("minCurrent", 7)),
                    "max_current": float(result.get("curDesign", 16)),
                }
                
                return device_info

    except asyncio.TimeoutError:
        raise CannotConnect("Connection timeout")
    except aiohttp.ClientResponseError as err:
        if err.status == 401:
            raise InvalidAuth
        raise CannotConnect(f"Connection error: {err}")
    except (aiohttp.ClientError, ValueError) as err:
        raise CannotConnect(f"Connection failed: {err}")
    except Exception as err:
        _LOGGER.exception("Unexpected error: %s", err)
        raise CannotConnect(f"Unexpected error: {err}")

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
   """Handle a config flow for Eveus."""

   VERSION = 1

   async def async_step_user(
       self, user_input: dict[str, Any] | None = None
   ) -> FlowResult:
       """Handle the initial step."""
       errors = {}
       error_details = []

       if user_input is not None:
           try:
               unique_id = f"{DOMAIN}_{user_input[CONF_HOST]}"
               await self.async_set_unique_id(unique_id)
               
               # Check if already configured
               if self._async_current_entries() and any(entry.unique_id == unique_id for entry in self._async_current_entries()):
                   return self.async_abort(reason="already_configured")
               
               info = await validate_input(self.hass, user_input)
               
               return self.async_create_entry(
                   title=info["title"],
                   data={
                       **user_input,
                       "firmware_version": info["firmware_version"],
                       "station_id": info["station_id"],
                       "min_current": info["min_current"],
                       "max_current": info["max_current"],
                   }
               )

           except InvalidHost:
               errors["base"] = "invalid_host"
               error_details = ["Invalid host format"]
               
           except InvalidHelperValues as err:
               errors["base"] = "invalid_helpers"
               error_details = err.invalid_values
               
           except InvalidAuth:
               errors["base"] = "invalid_auth"
               
           except CannotConnect as err:
               errors["base"] = "cannot_connect"
               error_details = [str(err)]
               
           except Exception:
               _LOGGER.exception("Unexpected exception")
               errors["base"] = "unknown"
               error_details = ["An unexpected error occurred"]

       # Show form with any errors
       schema = self.add_suggested_values_to_schema(
           STEP_USER_DATA_SCHEMA, user_input or {}
       )
       
       placeholders = {
           "error_detail": "\n".join(error_details) if error_details else None,
           "helper_list": "\n".join([
               f"{helper}: {ranges[0]}-{ranges[1]}"
               for helper, ranges in REQUIRED_HELPERS.items()
           ]),
       }
       
       return self.async_show_form(
           step_id="user",
           data_schema=schema,
           errors=errors,
           description_placeholders=placeholders
       )

   @staticmethod
   @callback
   def async_get_options_flow(
       config_entry: config_entries.ConfigEntry,
   ) -> config_entries.OptionsFlow:
       """Create options flow."""
       return OptionsFlowHandler(config_entry)

class OptionsFlowHandler(config_entries.OptionsFlow):
   """Handle options flow for Eveus."""

   def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
       """Initialize options flow."""
       self.config_entry = config_entry
       self.options = dict(config_entry.options)

   async def async_step_init(
       self, user_input: dict[str, Any] | None = None
   ) -> FlowResult:
       """Manage options."""
       errors = {}
       
       if user_input is not None:
           valid_helpers, invalid_list = await validate_helper_values(self.hass)
           if not valid_helpers:
               errors["base"] = "invalid_helpers"
           else:
               return self.async_create_entry(
                   title="",
                   data=user_input
               )

       return self.async_show_form(
           step_id="init",
           data_schema=vol.Schema({}),
           errors=errors,
       )

class InvalidHost(HomeAssistantError):
   """Error to indicate invalid host format."""

class InvalidHelperValues(HomeAssistantError):
   """Error to indicate invalid helper values."""
   def __init__(self, invalid_values: list[str]) -> None:
       """Initialize with list of invalid values."""
       super().__init__("Invalid helper values")
       self.invalid_values = invalid_values

class CannotConnect(HomeAssistantError):
   """Error to indicate connection failure."""

class InvalidAuth(HomeAssistantError):
   """Error to indicate invalid authentication."""
