"""Eveus API exceptions."""
from homeassistant.exceptions import HomeAssistantError

class EveusError(HomeAssistantError):
    """Base class for Eveus errors."""

class CannotConnect(EveusError):
    """Error to indicate we cannot connect."""

class InvalidAuth(EveusError):
    """Error to indicate there is invalid auth."""

class CommandError(EveusError):
    """Error executing a command."""

class ValidationError(EveusError):
    """Error validating response."""

class TimeoutError(EveusError):
    """Timeout error."""
