"""Automatic input entity creation for Eveus integration."""
import logging
import asyncio
from typing import Dict, Any, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import async_get_platforms
from homeassistant.components.input_number import (
    DOMAIN as INPUT_NUMBER_DOMAIN,
    InputNumber,
    async_setup_entry,
)
from homeassistant.components.persistent_notification import async_create as async_create_notification

_LOGGER = logging.getLogger(__name__)

# Define the required input entities
REQUIRED_INPUTS = {
    "input_number.ev_battery_capacity": {
        "name": "EV Battery Capacity",
        "min": 10,
        "max": 160,
        "step": 1,
        "initial": 80,
        "unit_of_measurement": "kWh",
        "mode": "slider",
        "icon": "mdi:car-battery",
    },
    "input_number.ev_initial_soc": {
        "name": "Initial EV State of Charge",
        "min": 0,
        "max": 100,
        "step": 1,
        "initial": 20,
        "unit_of_measurement": "%",
        "mode": "slider",
        "icon": "mdi:battery-charging-40",
    },
    "input_number.ev_soc_correction": {
        "name": "Charging Efficiency Loss",
        "min": 0,
        "max": 15,
        "step": 0.1,
        "initial": 7.5,
        "unit_of_measurement": "%",
        "mode": "slider",
        "icon": "mdi:chart-bell-curve",
    },
    "input_number.ev_target_soc": {
        "name": "Target SOC",
        "min": 0,
        "max": 100,
        "step": 10,
        "initial": 80,
        "unit_of_measurement": "%",
        "mode": "slider",
        "icon": "mdi:battery-charging-high",
    },
}

async def check_and_create_inputs(hass: HomeAssistant) -> List[str]:
    """Check and create missing input entities."""
    _LOGGER.debug("Checking for required input entities")
    
    # Keep track of created entities for logging
    created_entities = []
    missing_entities = []
    
    # Check for existence of each required entity
    for entity_id, config in REQUIRED_INPUTS.items():
        if hass.states.get(entity_id) is None:
            missing_entities.append(entity_id)
            _LOGGER.info("Required entity %s does not exist, will create", entity_id)
    
    if not missing_entities:
        _LOGGER.debug("All required input entities exist")
        return []
    
    # Create a notification to inform the user
    notification_message = (
        f"Eveus integration is creating {len(missing_entities)} required input entities: "
        f"{', '.join([entity_id.split('.')[1] for entity_id in missing_entities])}"
    )
    await async_create_notification(
        hass,
        notification_message,
        title="Eveus Integration Setup",
        notification_id="eveus_input_creation",
    )
    
    # Create each missing entity
    for entity_id in missing_entities:
        config = REQUIRED_INPUTS[entity_id]
        entity_name = entity_id.split(".")[1]  # Extract the name part from the entity_id
        
        _LOGGER.info("Creating input entity: %s", entity_id)
        try:
            # Use the input_number.create service
            await hass.services.async_call(
                INPUT_NUMBER_DOMAIN,
                "set_value",
                {
                    "entity_id": entity_id,
                    "value": config["initial"],
                },
                blocking=False,
                context={"source": "eveus_integration"},
            )
            
            # Create the input_number configuration
            input_config = {
                "name": config["name"],
                "min": config["min"],
                "max": config["max"],
                "step": config["step"],
                "initial": config["initial"],
                "unit_of_measurement": config.get("unit_of_measurement"),
                "mode": config.get("mode", "slider"),
                "icon": config.get("icon"),
            }
            
            # Add the entity to configuration.yaml via storage
            await async_create_input_number(hass, entity_name, input_config)
            
            # Track created entities
            created_entities.append(entity_id)
            _LOGGER.info("Successfully created input entity: %s", entity_id)
            
            # Add a small delay to avoid overwhelming Home Assistant
            await asyncio.sleep(0.5)
        
        except Exception as err:
            _LOGGER.error("Failed to create input entity %s: %s", entity_id, err)
    
    # Show success notification if entities were created
    if created_entities:
        success_message = (
            f"Eveus integration created {len(created_entities)} required input entities. "
            f"You may need to adjust their values in Settings > Devices & Services > Helpers."
        )
        await async_create_notification(
            hass,
            success_message,
            title="Eveus Integration Setup Complete",
            notification_id="eveus_input_creation_success",
        )
        
        # Force Home Assistant to reload entities
        await asyncio.sleep(1)
        await hass.helpers.entity_component.async_update_entity(hass, "input_number")
    
    return created_entities

async def async_create_input_number(
    hass: HomeAssistant, name: str, config: Dict[str, Any]
) -> Optional[str]:
    """Create an input number entity with the given configuration."""
    try:
        # Check if the entity already exists to avoid duplicates
        registry = er.async_get(hass)
        if registry.async_get_entity_id(INPUT_NUMBER_DOMAIN, "input_number", name):
            _LOGGER.warning("Input entity %s already exists, skipping creation", name)
            return None
            
        # Filter out None values
        config = {k: v for k, v in config.items() if v is not None}
        
        # Create the input_number configuration in storage
        await hass.services.async_call(
            "input_number",
            "reload",
            {},
            blocking=True,
            context={"source": "eveus_integration"},
        )
        
        # Create the entity using the input_number component's own methods
        await hass.async_add_executor_job(
            hass.components.input_number.async_setup, 
            hass, 
            {INPUT_NUMBER_DOMAIN: {name: config}}
        )
        
        # Reload to ensure the entity is available
        await hass.services.async_call(
            "input_number",
            "reload",
            {},
            blocking=True,
            context={"source": "eveus_integration"},
        )
        
        entity_id = f"input_number.{name}"
        _LOGGER.debug("Successfully created input number: %s", entity_id)
        return entity_id
    
    except Exception as err:
        _LOGGER.error("Error creating input_number %s: %s", name, err)
        return None
