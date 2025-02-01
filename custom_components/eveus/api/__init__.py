"""API package for Eveus integration."""
from .client import EveusClient
from .models import DeviceInfo, DeviceState
from .exceptions import (
    EveusError,
    CannotConnect,
    InvalidAuth,
    CommandError,
    ValidationError,
    TimeoutError,
)

__all__ = [
    "EveusClient",
    "DeviceInfo",
    "DeviceState",
    "EveusError",
    "CannotConnect",
    "InvalidAuth",
    "CommandError",
    "ValidationError",
    "TimeoutError",
]
