"""Input entity checker for Eveus integration."""
import logging
from typing import Dict, List

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Define the required input entities
REQUIRED_INPUTS = {
    "input_number.ev_battery_capacity": {
        "name": "EV Battery Capacity",
        "description": "Your EV's battery capacity in kWh",
        "recommended_value": "80"
    },
    "input_number.ev_initial_soc": {
        "name": "Initial EV State of Charge",
        "description": "The initial state of charge percentage when starting charging",
        "recommended_value": "20"
    },
    "input_number.ev_soc_correction": {
        "name": "Charging Efficiency Loss",
        "description": "Efficiency loss during charging, normally 5-10%",
        "recommended_value": "7.5"
    },
    "input_number.ev_target_soc": {
        "name": "Target SOC",
        "description": "Target state of charge for charging completion",
        "recommended_value": "80"
    },
}

async def check_missing_inputs(hass: HomeAssistant) -> List[str]:
    """Check for required input entities and provide guidance on missing ones."""
    _LOGGER.debug("Checking for required input entities")
    
    # Find missing entities
    missing_entities = []
    for entity_id in REQUIRED_INPUTS:
        if hass.states.get(entity_id) is None:
            missing_entities.append(entity_id)
            _LOGGER.info("Required entity %s does not exist", entity_id)
    
    if not missing_entities:
        _LOGGER.debug("All required input entities exist")
        return []
    
    # Create notification if there are missing entities
    if missing_entities:
        # Build message with instructions
        message = (
            f"Eveus integration requires {len(missing_entities)} input helpers that are missing:\n\n"
        )
        
        message += "Please create these input_number helpers:\n\n"
        
        for entity_id in missing_entities:
            info = REQUIRED_INPUTS[entity_id]
            message += f"• {info['name']} ({entity_id})\n"
            message += f"  Description: {info['description']}\n"
            message += f"  Recommended value: {info['recommended_value']}\n\n"
        
        message += "You can create these helpers in Settings → Devices & Services → Helpers → Create Helper → Number."
        
        # Show notification
        try:
            await hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "message": message,
                    "title": "Eveus Integration - Missing Input Helpers",
                    "notification_id": "eveus_missing_inputs"
                },
                blocking=False
            )
            _LOGGER.warning("Missing required input entities for Eveus integration, notification created")
        except Exception as err:
            _LOGGER.error("Failed to create notification: %s", err)
    
    return missing_entities
