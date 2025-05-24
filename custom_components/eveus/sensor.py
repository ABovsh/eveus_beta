"""Optimized sensor setup with factory pattern and minimal code."""
from __future__ import annotations

import logging
from typing import List

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .sensor_definitions import get_sensor_specifications
from .ev_sensors import (
    EVSocKwhSensor,
    EVSocPercentSensor,
    TimeToTargetSocSensor,
    InputEntitiesStatusSensor,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Eveus sensors with optimized factory pattern."""
    try:
        # Get updater from stored data
        data = hass.data[DOMAIN][entry.entry_id]
        updater = data["updater"]
        
        if not updater:
            _LOGGER.error("No updater found for entry %s", entry.entry_id)
            return

        # Create all sensors efficiently using factory pattern
        sensors = []
        
        # Create standard sensors from specifications
        sensor_specs = get_sensor_specifications()
        standard_sensors = [spec.create_sensor(updater) for spec in sensor_specs]
        sensors.extend(standard_sensors)
        
        # Create EV-specific optimized sensors
        ev_sensors = [
            EVSocKwhSensor(updater),
            EVSocPercentSensor(updater),
            TimeToTargetSocSensor(updater),
            InputEntitiesStatusSensor(updater),
        ]
        sensors.extend(ev_sensors)
        
        # Register entities in data store for tracking
        if "entities" not in data:
            data["entities"] = {}
        
        data["entities"]["sensor"] = {
            sensor.unique_id: sensor for sensor in sensors
        }
        
        # Add all sensors at once for efficiency
        async_add_entities(sensors, update_before_add=False)
        
        _LOGGER.info(
            "Successfully created %d sensors (%d standard, %d EV-specific) for %s",
            len(sensors),
            len(standard_sensors),
            len(ev_sensors),
            entry.title
        )
        
    except Exception as err:
        _LOGGER.error("Error setting up sensors for %s: %s", entry.title, err, exc_info=True)
        raise
