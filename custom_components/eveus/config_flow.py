"""Config flow for Eveus integration."""
from __future__ import annotations

import logging
import asyncio
from typing import Any, Final

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import aiohttp_client

from .const import (
    DOMAIN,
    MODEL_16A,
    MODEL_32A,
    CONF_MODEL,
    MODELS,
    HELPER_EV_BATTERY_CAPACITY,
    HELPER_EV_INITIAL_SOC,
    HELPER_EV_SOC_CORRECTION,
    HELPER_EV_TARGET_SOC,
    API_ENDPOINT_MAIN,
    COMMAND_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_MODEL, default=MODEL_16A): vol.In(MODELS),
    }
)

REQUIRED_HELPERS: Final = [
    HELPER_EV_BATTERY_CAPACITY,
    HELPER_EV_INITIAL_SOC,
    HELPER_EV_SOC_CORRECTION,
    HELPER_EV_TARGET_SOC,
]

async def _validate_helper_entities(hass: HomeAssistant) -> bool:
    """Validate that required helper entities exist and are properly configured."""
    for entity_id in REQUIRED_HELPERS:
        state = hass.states.get(entity_id)
        if not state:
            _LOGGER.error("Required helper entity missing: %s", entity_id)
            return False
        # Validate entity attributes based on type
        try:
            if 'battery_capacity' in entity_id:
                if not 10 <= float(state.state) <= 160:
                    _LOGGER.error("Battery capacity must be between 10 and 160 kWh")
                    return False
            elif 'initial_soc' in entity_id or 'target_soc' in entity_id:
                if not 0 <= float(state.state) <= 100:
                    _LOGGER.error("SOC values must be between 0 and 100%")
                    return False
            elif 'correction' in entity_id:
                if not 0 <= float(state.state) <= 10:
                    _LOGGER.error("Correction factor must be between 0 and 10%")
                    return False
        except (ValueError, TypeError):
            _LOGGER.error("Invalid value for helper entity: %s", entity_id)
            return False
    return True

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    if not await _validate_helper_entities(hass):
        raise InvalidInput

    try:
        session = aiohttp_client.async_get_clientsession(hass)
        timeout = aiohttp.ClientTimeout(total=COMMAND_TIMEOUT)

        async with session.post(
            f"http://{data[CONF_HOST]}{API_ENDPOINT_MAIN}",
            auth=aiohttp.BasicAuth(data[CONF_USERNAME], data[CONF_PASSWORD]),
            timeout=timeout,
        ) as response:
            if response.status == 401:
                raise InvalidAuth
            response.raise_for_status()
            
            result = await response.json()
            if not isinstance(result, dict) or "state" not in result:
                raise CannotConnect
            
            # Validate basic device info
            if "verFWMain" not in result or "verHW" not in result:
                _LOGGER.warning("Device firmware or hardware version info missing")
            
            return {
                "title": f"Eveus Charger ({data[CONF_HOST]})",
                "firmware_version": result.get("verFWMain", "Unknown"),
                "hardware_version": result.get("verHW", "Unknown"),
            }

    except aiohttp.ClientResponseError as err:
        if err.status == 401:
            raise InvalidAuth from err
        raise CannotConnect from err
    except (asyncio.TimeoutError, aiohttp.ClientError) as err:
        _LOGGER.error("Connection error: %s", str(err))
        raise CannotConnect from err
    except Exception as err:
        _LOGGER.exception("Unexpected error: %s", str(err))
        raise CannotConnect from err

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Eveus."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                # Check if device is already configured
                await self.async_set_unique_id(f"eveus_{user_input[CONF_HOST]}")
                self._abort_if_unique_id_configured()
                
                info = await validate_input(self.hass, user_input)
                
                return self.async_create_entry(
                    title=info["title"],
                    data={
                        **user_input,
                        "firmware_version": info["firmware_version"],
                        "hardware_version": info["hardware_version"],
                    }
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except InvalidInput:
                errors["base"] = "input_missing"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "battery_capacity_helper": HELPER_EV_BATTERY_CAPACITY,
                "initial_soc_helper": HELPER_EV_INITIAL_SOC,
                "soc_correction_helper": HELPER_EV_SOC_CORRECTION,
                "target_soc_helper": HELPER_EV_TARGET_SOC,
            }
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler(config_entry)

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Eveus integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage basic options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_MODEL,
                        default=self.config_entry.data.get(CONF_MODEL, MODEL_16A),
                    ): vol.In(MODELS),
                }
            ),
        )

class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""

class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""

class InvalidInput(HomeAssistantError):
    """Error to indicate missing or invalid input_number entities."""
