"""Config flow for Eveus."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    MODEL_16A,
    MODEL_32A,
    CONF_MODEL,
    MODELS,
)
from .mixins import SessionMixin, ValidationMixin, ErrorHandlingMixin

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

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Eveus."""

    VERSION = 1

    def __init__(self):
        """Initialize config flow."""
        self._session_handler = None

    async def _validate_input(self, data: dict[str, Any]) -> dict[str, Any]:
        """Validate the user input allows us to connect."""
        # Validate helper entities
        for entity_id in REQUIRED_HELPERS:
            if not self.hass.states.get(entity_id):
                raise InvalidInput

        # Create session handler
        session_handler = EveusConfigFlowHandler(
            data[CONF_HOST],
            data[CONF_USERNAME],
            data[CONF_PASSWORD],
            self.hass
        )

        # Test connection
        if not await session_handler.test_connection():
            raise CannotConnect

        return {"title": f"Eveus Charger ({data[CONF_HOST]})"}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                info = await self._validate_input(user_input)
                return self.async_create_entry(
                    title=info["title"],
                    data=user_input
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
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

class EveusConfigFlowHandler(SessionMixin, ValidationMixin, ErrorHandlingMixin):
    """Config flow connection test handler."""
    
    def __init__(self, host: str, username: str, password: str, hass: HomeAssistant):
        """Initialize handler."""
        super().__init__(host, username, password)
        self.hass = hass

    async def test_connection(self) -> bool:
        """Test connection to Eveus device."""
        try:
            result = await self.async_api_call("main")
            return bool(result and isinstance(result, dict) and "state" in result)
        except Exception as err:
            await self.handle_error(err, "Connection test failed")
            return False

class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""

class InvalidInput(HomeAssistantError):
    """Error to indicate missing input_number entities."""
