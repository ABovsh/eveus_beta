"""API package for Eveus integration."""
from .models import DeviceInfo, DeviceState
from .exceptions import (
    EveusError,
    CannotConnect,
    InvalidAuth,
    CommandError,
    ValidationError,
    TimeoutError,
)
from .client import EveusClient

__all__ = [
    "DeviceInfo",
    "DeviceState", 
    "EveusClient",
    "EveusError",
    "CannotConnect",
    "InvalidAuth",
    "CommandError",
    "ValidationError",
    "TimeoutError",
]
