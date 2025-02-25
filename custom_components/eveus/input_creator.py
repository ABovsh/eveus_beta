"""Automatic input entity creation for Eveus integration."""
import logging
import asyncio
import os
from typing import Dict, Any, List, Optional, Set

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.util import slugify
from homeassistant.const import (
    CONF_NAME, 
    CONF_ICON,
    ATTR_ENTITY_ID,
    CONF_UNIT_OF_MEASUREMENT,
)
from homeassistant.components.input_number import (
    DOMAIN as INPUT_NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
    ATTR_VALUE,
)

_LOGGER = logging.getLogger(__name__)

# Define the required input entities
REQUIRED_INPUTS = {
    "ev_battery_capacity": {
        "name": "EV Battery Capacity",
        "min": 10,
        "max": 160,
        "step": 1,
        "initial": 80,
        "unit_of_measurement": "kWh",
        "mode": "slider",
        "icon": "mdi:car-battery",
    },
    "ev_initial_soc": {
        "name": "Initial EV State of Charge",
        "min": 0,
        "max": 100,
        "step": 1,
        "initial": 20,
        "unit_of_measurement": "%",
        "mode": "slider",
        "icon": "mdi:battery-charging-40",
    },
    "ev_soc_correction": {
        "name": "Charging Efficiency Loss",
        "min": 0,
        "max": 15,
        "step": 0.1,
        "initial": 7.5,
        "unit_of_measurement": "%",
        "mode": "slider",
        "icon": "mdi:chart-bell-curve",
    },
    "ev_target_soc": {
        "name": "Target SOC",
        "min": 0,
        "max": 100,
        "step": 5,
        "initial": 80,
        "unit_of_measurement": "%",
        "mode": "slider",
        "icon": "mdi:battery-charging-high",
    },
}

async def check_and_create_inputs(hass: HomeAssistant) -> List[str]:
    """Check for required input entities and create any that are missing."""
    _LOGGER.debug("Checking for required input entities")
    
    # Find missing entities
    missing_entities = []
    for input_id in REQUIRED_INPUTS:
        entity_id = f"input_number.{input_id}"
        if hass.states.get(entity_id) is None:
            missing_entities.append(input_id)
            _LOGGER.info("Required entity %s does not exist, will create", entity_id)
    
    if not missing_entities:
        _LOGGER.debug("All required input entities exist")
        return []
    
    # Create a notification using service call
    if missing_entities:
        notification_message = (
            f"Eveus integration is creating {len(missing_entities)} required input entities: "
            f"{', '.join(missing_entities)}"
        )
        try:
            await hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "message": notification_message,
                    "title": "Eveus Integration Setup",
                    "notification_id": "eveus_input_creation"
                },
                blocking=False
            )
        except Exception as err:
            _LOGGER.error("Failed to create notification: %s", err)
    
    # Try all available methods in order of preference
    created_entities = []
    
    # Method 1: Try using the storage method (most reliable)
    created = await create_via_storage(hass, missing_entities)
    if created:
        created_entities.extend([f"input_number.{e}" for e in created])
        missing_entities = [e for e in missing_entities if e not in created]

    # Method 2: Try using the input_helper service
    if missing_entities:
        created = await create_via_service(hass, missing_entities)
        if created:
            created_entities.extend([f"input_number.{e}" for e in created])
            missing_entities = [e for e in missing_entities if e not in created]
    
    # For any remaining entities, provide manual instructions
    if missing_entities:
        await provide_manual_instructions(hass, missing_entities)
    
    # Show success notification if entities were created
    if created_entities:
        success_message = (
            f"Eveus integration created {len(created_entities)} required input entities: "
            f"{', '.join(created_entities)}. "
            f"Please set appropriate values for your EV in Settings > Devices & Services > Helpers."
        )
        try:
            await hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "message": success_message,
                    "title": "Eveus Integration Setup Complete",
                    "notification_id": "eveus_input_creation_success"
                },
                blocking=False
            )
        except Exception as err:
            _LOGGER.error("Failed to create success notification: %s", err)
    
    return created_entities

async def create_via_service(hass: HomeAssistant, missing_entities: List[str]) -> List[str]:
    """Create input entities using the helper service."""
    _LOGGER.debug("Attempting to create entities via helper service")
    created = []
    
    try:
        for input_id in missing_entities:
            config = REQUIRED_INPUTS[input_id]
            entity_id = f"input_number.{input_id}"
            
            # Try to call the input_number.create service if available
            if "create" in hass.services.async_services().get(INPUT_NUMBER_DOMAIN, {}):
                try:
                    await hass.services.async_call(
                        INPUT_NUMBER_DOMAIN,
                        "create",
                        {
                            "id": input_id,
                            "name": config["name"],
                            "min": config["min"],
                            "max": config["max"],
                            "step": config["step"],
                            "initial": config["initial"],
                            "unit_of_measurement": config.get("unit_of_measurement"),
                            "icon": config.get("icon"),
                            "mode": config.get("mode", "slider"),
                        },
                        blocking=True,
                    )
                    
                    # Verify the entity was created
                    await asyncio.sleep(0.5)
                    if hass.states.get(entity_id) is not None:
                        created.append(input_id)
                        _LOGGER.info("Created %s via service", entity_id)
                        
                        # Set the initial value
                        await hass.services.async_call(
                            INPUT_NUMBER_DOMAIN,
                            SERVICE_SET_VALUE,
                            {
                                ATTR_ENTITY_ID: entity_id,
                                ATTR_VALUE: config["initial"],
                            },
                            blocking=True,
                        )
                except Exception as err:
                    _LOGGER.warning("Failed to create %s via service: %s", entity_id, err)
    
    except Exception as err:
        _LOGGER.error("Error creating entities via service: %s", err)
    
    return created

async def create_via_storage(hass: HomeAssistant, missing_entities: List[str]) -> List[str]:
    """Create input entities via the helpers storage system."""
    _LOGGER.debug("Attempting to create entities via storage")
    created = []
    
    try:
        # Use Home Assistant's storage system
        store = Store(hass, 1, "core.config_entries")
        data = await store.async_load() or {}
        
        # Get all existing helpers
        helpers_store = Store(hass, 1, "core.helpers")
        helpers_data = await helpers_store.async_load() or {}
        
        if "helpers" not in helpers_data:
            helpers_data["helpers"] = {}
            
        # Add missing entities to storage
        for input_id in missing_entities:
            config = REQUIRED_INPUTS[input_id]
            unique_id = f"input_number.{input_id}"
            
            # Create the helper entry
            helper_entry = {
                "name": config["name"],
                "icon": config.get("icon"),
                "initial": config["initial"],
                "min": config["min"],
                "max": config["max"],
                "step": config["step"],
                "mode": config.get("mode", "slider"),
            }
            
            if "unit_of_measurement" in config:
                helper_entry["unit_of_measurement"] = config["unit_of_measurement"]
            
            # Add to the helpers
            helpers_data["helpers"][unique_id] = helper_entry
            created.append(input_id)
        
        # Save the updated storage
        if created:
            await helpers_store.async_save(helpers_data)
            _LOGGER.info("Created %d helpers via storage", len(created))
            
            # Force Home Assistant to reload helpers
            await hass.services.async_call(
                "input_number",
                "reload",
                {},
                blocking=True,
            )
            
            # Give Home Assistant time to process
            await asyncio.sleep(1)
    
    except Exception as err:
        _LOGGER.error("Failed to create entities via storage: %s", err)
    
    return created

async def provide_manual_instructions(hass: HomeAssistant, missing_entities: List[str]) -> None:
    """Provide manual instructions for creating required entities."""
    _LOGGER.debug("Providing manual instructions for entity creation")
    
    # Build the configuration YAML for the user to manually add
    config_yaml = "input_number:\n"
    for input_id in missing_entities:
        config_yaml += f"  {input_id}:\n"
        for key, value in REQUIRED_INPUTS[input_id].items():
            config_yaml += f"    {key}: {value}\n"
    
    manual_message = (
        "Eveus integration could not automatically create the following required input entities:\n"
        f"{', '.join(missing_entities)}\n\n"
        "Please add the following configuration to your configuration.yaml manually:\n\n"
        f"```yaml\n{config_yaml}```\n\n"
        "After adding this configuration, restart Home Assistant.\n\n"
        "Alternatively, you can create these input helpers manually through "
        "Settings > Devices & Services > Helpers."
    )
    
    try:
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "message": manual_message,
                "title": "Manual Configuration Required for Eveus",
                "notification_id": "eveus_manual_config"
            },
            blocking=False
        )
    except Exception as err:
        _LOGGER.error("Failed to create manual instructions notification: %s", err)
    
    _LOGGER.warning("Could not automatically create input entities, provided manual instructions")
