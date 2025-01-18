"""Config flow for Eveus integration."""
from __future__ import annotations

import logging
import asyncio
from typing import Any, Final

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import aiohttp_client

from .const import (
    DOMAIN,
    COMMAND_TIMEOUT,
    API_ENDPOINT_MAIN,
)

_LOGGER = logging.getLogger(__name__)

# Required helper entities
REQUIRED_HELPERS = [
    "input_number.ev_battery_capacity",
    "input_number.ev_initial_soc",
    "input_number.ev_soc_correction",
    "input_number.ev_target_soc",
]

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

async def check_helper_values(hass: HomeAssistant, helper_id: str) -> tuple[bool, str]:
    """Validate helper entity values are within expected ranges."""
    state = hass.states.get(helper_id)
    if not state:
        return False, f"Helper {helper_id} not found"
    
    try:
        value = float(state.state)
        if "battery_capacity" in helper_id:
            if not 10 <= value <= 160:
                return False, f"Battery capacity must be between 10 and 160 kWh, got {value}"
        elif "initial_soc" in helper_id or "target_soc" in helper_id:
            if not 0 <= value <= 100:
                return False, f"SOC value must be between 0 and 100%, got {value}"
        elif "correction" in helper_id:
            if not 0 <= value <= 10:
                return False, f"Correction factor must be between 0 and 10%, got {value}"
        return True, ""
    except (ValueError, TypeError):
        return False, f"Invalid value for {helper_id}: {state.state}"

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    
    # First check if all required helpers exist and are valid
    missing_helpers = []
    invalid_helpers = []
    
    for helper in REQUIRED_HELPERS:
        if not hass.states.get(helper):
            missing_helpers.append(helper)
            continue
            
        is_valid, error_msg = await check_helper_values(hass, helper)
        if not is_valid:
            invalid_helpers.append(error_msg)

    if missing_helpers:
        raise MissingHelpers(missing_helpers)
    
    if invalid_helpers:
        raise InvalidHelperValues(invalid_helpers)

    # Then validate connection
    try:
        session = aiohttp_client.async_get_clientsession(hass)
        timeout = aiohttp.ClientTimeout(total=COMMAND_TIMEOUT)

        async with session.post(
            f"http://{data[CONF_HOST]}{API_ENDPOINT_MAIN}",
            auth=aiohttp.BasicAuth(data[CONF_USERNAME], data[CONF_PASSWORD]),
            timeout=timeout,
            ssl=False,
        ) as response:
            if response.status == 401:
                raise InvalidAuth
            response.raise_for_status()
            
            result = await response.json()
            if not isinstance(result, dict) or "state" not in result:
                raise CannotConnect("Invalid response from device")
            
            # Get device info
            device_info = {
                "title": f"Eveus ({data[CONF_HOST]})",
                "firmware_version": result.get("verFWMain", "Unknown").strip(),
                "station_id": result.get("stationId", "Unknown").strip(),
                "min_current": result.get("minCurrent", 8),
                "max_current": result.get("curDesign", 16),
            }
            
            return device_info

    except aiohttp.ClientResponseError as err:
        if err.status == 401:
            raise InvalidAuth from err
        raise CannotConnect(f"Connection error: {err}") from err
    except (asyncio.TimeoutError, aiohttp.ClientError) as err:
        raise CannotConnect(f"Connection failed: {err}") from err
    except Exception as err:
        _LOGGER.error("Unexpected error: %s", str(err))
        raise CannotConnect(f"Unexpected error: {err}") from err

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
                await self.async_set_unique_id(f"eveus_{user_input[CONF_HOST]}")
                self._abort_if_unique_id_configured()
                
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

            except MissingHelpers as err:
                errors["base"] = "missing_helpers"
                error_details = [
                    f"Missing required helper: {helper}" 
                    for helper in err.missing_helpers
                ]
                
            except InvalidHelperValues as err:
                errors["base"] = "invalid_helpers"
                error_details = err.invalid_values
                
            except CannotConnect as err:
                errors["base"] = "cannot_connect"
                error_details = [str(err)]
                
            except InvalidAuth:
                errors["base"] = "invalid_auth"
                
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
                error_details = ["An unexpected error occurred"]

        # Show form with any errors
        schema = self.add_suggested_values_to_schema(
            STEP_USER_DATA_SCHEMA, user_input or {}
        )
        
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "error_detail": "\n".join(error_details) if error_details else None,
                "helper_list": "\n".join(REQUIRED_HELPERS),
            }
        )

class MissingHelpers(HomeAssistantError):
    """Error to indicate missing required helpers."""
    def __init__(self, missing_helpers: list[str]) -> None:
        """Initialize with list of missing helpers."""
        super().__init__("Required helpers not found")
        self.missing_helpers = missing_helpers

class InvalidHelperValues(HomeAssistantError):
    """Error to indicate invalid helper values."""
    def __init__(self, invalid_values: list[str]) -> None:
        """Initialize with list of invalid values."""
        super().__init__("Invalid helper values")
        self.invalid_values = invalid_values

class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
    def __init__(self, msg: str) -> None:
        """Initialize with error message."""
        super().__init__(msg)

class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
