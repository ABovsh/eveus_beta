"""Config flow for Eveus."""
from __future__ import annotations

import logging
import asyncio
from typing import Any

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

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    try:
        session = aiohttp_client.async_get_clientsession(hass)
        timeout = aiohttp.ClientTimeout(total=10)

        async with session.post(
            f"http://{data[CONF_HOST]}/main",
            auth=aiohttp.BasicAuth(data[CONF_USERNAME], data[CONF_PASSWORD]),
            timeout=timeout,
        ) as response:
            if response.status == 401:
                raise InvalidAuth
            response.raise_for_status()
            
            result = await response.json()
            if not isinstance(result, dict) or "state" not in result:
                raise CannotConnect
            
            return {"title": f"Eveus Charger ({data[CONF_HOST]})"}

    except aiohttp.ClientResponseError as err:
        if err.status == 401:
            raise InvalidAuth from err
        raise CannotConnect from err
    except (asyncio.TimeoutError, aiohttp.ClientError) as err:
        raise CannotConnect from err
    except Exception as err:
        _LOGGER.error("Unexpected error: %s", str(err))
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

                await self.async_set_unique_id(user_input[CONF_HOST])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["title"],
                    data=user_input
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
            errors=errors
        )

class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""

class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
