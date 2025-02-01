# File: custom_components/eveus/config_flow.py
"""Config flow for Eveus."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client

from .base import EveusBaseConnection
from .const import (
    DOMAIN,
    MODEL_16A,
    MODEL_32A,
    CONF_MODEL,
    MODELS,
)
from .exceptions import EveusConnectionError, EveusAuthError

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_MODEL, default=MODEL_16A): vol.In(MODELS),
    }
)

REQUIRED_HELPERS = [
    "input_number.ev_battery_capacity",
    "input_number.ev_initial_soc",
    "input_number.ev_soc_correction",
    "input_number.ev_target_soc",
]

async def _validate_helper_entities(hass: HomeAssistant) -> bool:
    """Validate that required helper entities exist."""
    for entity_id in REQUIRED_HELPERS:
        if not hass.states.get(entity_id):
            return False
    return True

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    if not await _validate_helper_entities(hass):
        _LOGGER.error("Required input_number entities missing")
        raise InvalidInput

    try:
        connection = EveusBaseConnection(
            host=data[CONF_HOST],
            username=data[CONF_USERNAME],
            password=data[CONF_PASSWORD],
        )
        
        # Test connection by attempting update
        await connection.async_update()
        await connection.async_close()
        
        return {"title": f"Eveus Charger ({data[CONF_HOST]})"}

    except EveusAuthError as err:
        raise InvalidAuth from err
    except EveusConnectionError as err:
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
                info = await validate_input(self.hass, user_input)
                return self.async_create_entry(
                    title=info["title"],
                    data=user_input
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
            errors=errors
        )

class CannotConnect(Exception):
    """Error to indicate we cannot connect."""

class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""

class InvalidInput(Exception):
    """Error to indicate missing input_number entities."""
