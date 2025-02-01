"""Validation utilities for Eveus."""
from typing import Any
from homeassistant.core import HomeAssistant
from ..const import REQUIRED_HELPERS

async def validate_helper_entities(hass: HomeAssistant) -> bool:
    """Validate that required helper entities exist."""
    for entity_id in REQUIRED_HELPERS:
        if not hass.states.get(entity_id):
            return False
    return True

def validate_response(response: dict[str, Any], command: str, value: Any) -> bool:
    """Validate command response."""
    if not isinstance(response, dict):
        return False
    
    try:
        if command == "evseEnabled":
            return response.get("evseEnabled") == value
        elif command == "oneCharge":
            return response.get("oneCharge") == value
        elif command == "rstEM1":
            return True
    except Exception:
        return False
    
    return False
