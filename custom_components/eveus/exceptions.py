"""Exceptions for Eveus integration."""
from homeassistant.exceptions import HomeAssistantError

class EveusError(HomeAssistantError):
    """Base class for Eveus errors."""

class EveusConnectionError(EveusError):
    """Error to indicate connection issues."""

class EveusCommandError(EveusError):
    """Error to indicate command execution issues."""

class EveusAuthError(EveusError):
    """Error to indicate authentication issues."""
