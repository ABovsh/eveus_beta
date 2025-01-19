"""Config flow for Eveus integration with improved validation."""
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
    HELPER_EV_BATTERY_CAPACITY,
    HELPER_EV_INITIAL_SOC,
    HELPER_EV_SOC_CORRECTION,
    HELPER_EV_TARGET_SOC,
    MODEL_16A,
    MODEL_32A,
    MODELS,
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

async def validate_device_model(host: str, auth: aiohttp.BasicAuth, model: str) -> bool:
    """Validate device matches specified model."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"http://{host}{API_ENDPOINT_MAIN}",
                auth=auth,
                timeout=COMMAND_TIMEOUT,
                ssl=False,
            ) as response:
                response.raise_for_status()
                data = await response.json()
                
                max_current = float(data.get("curDesign", 16))
                detected_model = "32A" if max_current > 16 else "16A"
                
                if detected_model != model:
                    _LOGGER.warning(
                        "Model mismatch: specified %s but detected %s",
                        model,
                        detected_model
                    )
                    return False
                    
                return True
                
    except Exception as err:
        _LOGGER.error("Error validating device model: %s", err)
        return False

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input with comprehensive checks."""
    
    # Validate host format
    if not await validate_host_format(data[CONF_HOST]):
        raise InvalidHost("Invalid host format")
    
    # Validate helper entities
    valid_helpers, invalid_list = await validate_helper_values(hass)
    if not valid_helpers:
        raise InvalidHelperValues(invalid_list)

    # Test connection and validate model
    try:
        session = aiohttp_client.async_get_clientsession(hass)
        auth = aiohttp.BasicAuth(data[CONF_USERNAME], data[CONF_PASSWORD])
        
        async with session.post(
            f"http://{data[CONF_HOST]}{API_ENDPOINT_MAIN}",
            auth=auth,
            timeout=COMMAND_TIMEOUT,
            ssl=False,
        ) as response:
            if response.status == 401:
                raise InvalidAuth
                
            response.raise_for_status()
            result = await response.json()
            
            if not isinstance(result, dict):
                raise CannotConnect("Invalid response format")
                
            # Get device info
            device_info = {
                "title": f"Eveus ({data[CONF_HOST]})",
                "firmware_version": result.get("verFWMain", "Unknown").strip(),
                "station_id": result.get("stationId", "Unknown").strip(),
                "min_current": float(result.get("minCurrent", 7)),
                "max_current": float(result.get("curDesign", 16)),
            }
            
            return device_info

    except aiohttp.ClientResponseError as err:
        if err.status == 401:
            raise InvalidAuth from err
        raise CannotConnect(f"Connection error: {err}") from err
        
    except asyncio.TimeoutError as err:
        raise CannotConnect("Connection timeout") from err
        
    except aiohttp.ClientError as err:
        raise CannotConnect(f"Connection failed: {err}") from err
        
    except Exception as err:
        _LOGGER.error("Unexpected error: %s", err)
        raise CannotConnect(f"Unexpected error: {err}") from err

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Eveus with improved validation."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step with comprehensive validation."""
        errors = {}
        error_details = []

        if user_input is not None:
            try:
                await self.async_set_unique_id(
                    f"eveus_{user_input[CONF_HOST]}"
                )
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
                        "model": info["model"],
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
                
            except InvalidModel:
                errors["base"] = "invalid_model"
                error_details = [
                    f"Device model does not match specified model: {user_input[CONF_MODEL]}"
                ]
                
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
            "models": ", ".join(MODELS),
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

        schema = {
            vol.Optional(
                CONF_MODEL,
                default=self.config_entry.options.get(
                    CONF_MODEL,
                    self.config_entry.data.get(CONF_MODEL, MODEL_16A)
                ),
            ): vol.In(MODELS),
        }

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
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
    def __init__(self, msg: str) -> None:
        """Initialize with error message."""
        super().__init__(msg)

class InvalidAuth(HomeAssistantError):
    """Error to indicate invalid authentication."""

class InvalidModel(HomeAssistantError):
    """Error to indicate model mismatch."""
