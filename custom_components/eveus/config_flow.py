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
from homeassistant.helpers import aiohttp_client, entity_registry
from homeassistant.helpers.entity_registry import EntityRegistry

from .const import (
    DOMAIN,
    MODEL_16A,
    MODEL_32A,
    CONF_MODEL,
    MODELS,
    CONF_BATTERY_CAPACITY,
    CONF_INITIAL_SOC,
    CONF_SOC_CORRECTION,
    CONF_TARGET_SOC,
    DEFAULT_BATTERY_CAPACITY,
    DEFAULT_INITIAL_SOC,
    DEFAULT_SOC_CORRECTION,
    DEFAULT_TARGET_SOC,
    MIN_BATTERY_CAPACITY,
    MAX_BATTERY_CAPACITY,
    MIN_SOC,
    MAX_SOC,
    MIN_CORRECTION,
    MAX_CORRECTION,
    API_ENDPOINT_MAIN,
    COMMAND_TIMEOUT,
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
        vol.Required(CONF_MODEL, default=MODEL_16A): vol.In(MODELS),
        vol.Required(CONF_BATTERY_CAPACITY, default=DEFAULT_BATTERY_CAPACITY): vol.All(
            vol.Coerce(float), 
            vol.Range(min=MIN_BATTERY_CAPACITY, max=MAX_BATTERY_CAPACITY)
        ),
        vol.Required(CONF_INITIAL_SOC, default=DEFAULT_INITIAL_SOC): vol.All(
            vol.Coerce(float),
            vol.Range(min=MIN_SOC, max=MAX_SOC)
        ),
        vol.Required(CONF_SOC_CORRECTION, default=DEFAULT_SOC_CORRECTION): vol.All(
            vol.Coerce(float),
            vol.Range(min=MIN_CORRECTION, max=MAX_CORRECTION)
        ),
        vol.Required(CONF_TARGET_SOC, default=DEFAULT_TARGET_SOC): vol.All(
            vol.Coerce(float),
            vol.Range(min=MIN_SOC, max=MAX_SOC)
        ),
    }
)

HELPER_ENTITIES = {
    HELPER_EV_BATTERY_CAPACITY: {
        "name": "EV Battery Capacity",
        "icon": "mdi:car-battery",
        "unit": "kWh",
        "conf_key": CONF_BATTERY_CAPACITY,
        "min": MIN_BATTERY_CAPACITY,
        "max": MAX_BATTERY_CAPACITY,
        "step": 1,
        "mode": "slider",
    },
    HELPER_EV_INITIAL_SOC: {
        "name": "Initial EV State of Charge",
        "icon": "mdi:battery-charging-40",
        "unit": "%",
        "conf_key": CONF_INITIAL_SOC,
        "min": MIN_SOC,
        "max": MAX_SOC,
        "step": 1,
        "mode": "slider",
    },
    HELPER_EV_SOC_CORRECTION: {
        "name": "Charging Efficiency Loss",
        "icon": "mdi:chart-bell-curve",
        "unit": "%",
        "conf_key": CONF_SOC_CORRECTION,
        "min": MIN_CORRECTION,
        "max": MAX_CORRECTION,
        "step": 0.1,
        "mode": "box",
    },
    HELPER_EV_TARGET_SOC: {
        "name": "Target SOC",
        "icon": "mdi:battery-charging-high",
        "unit": "%",
        "conf_key": CONF_TARGET_SOC,
        "min": MIN_SOC,
        "max": MAX_SOC,
        "step": 10,
        "mode": "slider",
    },
}

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
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
            
            return {
                "title": f"Eveus EV Charger ({data[CONF_HOST]})",
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
        _LOGGER.error("Unexpected error: %s", str(err))
        raise CannotConnect from err

class EveusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Eveus."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                await self.async_set_unique_id(f"eveus_{user_input[CONF_HOST]}")
                self._abort_if_unique_id_configured()
                
                info = await validate_input(self.hass, user_input)
                
                # Create helper entities
                await self._create_helper_entities(user_input)
                
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
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def _create_helper_entities(self, user_input: dict[str, Any]) -> None:
        """Create helper entities if they don't exist."""
        from homeassistant.components.input_number import DOMAIN as INPUT_NUMBER_DOMAIN
        from homeassistant.components.input_number import async_setup_entry
        from homeassistant.helpers import entity_registry as er
    
        ent_reg = er.async_get(self.hass)
        created_helpers = []
    
        for entity_id, config in HELPER_ENTITIES.items():
            if not ent_reg.async_get(entity_id):
                _LOGGER.debug("Creating helper entity: %s", entity_id)
                try:
                    await self.hass.config_entries.async_add_entry(
                        config_entry=ConfigEntry(
                            version=1,
                            domain=INPUT_NUMBER_DOMAIN,
                            title=config["name"],
                            data={
                                "name": config["name"],
                                "min": config["min"],
                                "max": config["max"],
                                "step": config["step"],
                                "mode": config["mode"],
                                "icon": config["icon"],
                                "unit_of_measurement": config["unit"],
                                "initial": user_input[config["conf_key"]],
                            },
                            source=config_entries.SOURCE_USER,
                        )
                    )
                    created_helpers.append(entity_id)
                except Exception as err:
                    _LOGGER.error("Failed to create helper %s: %s", entity_id, str(err))
                    # Cleanup any created helpers on failure
                    for helper in created_helpers:
                        try:
                            await ent_reg.async_remove(helper)
                        except Exception:
                            pass
                    raise

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return EveusOptionsFlowHandler(config_entry)

class EveusOptionsFlowHandler(config_entries.OptionsFlow):
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
