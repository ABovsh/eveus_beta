"""Support for Eveus sensors."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .sensor_registry import get_sensor_definitions
from .ev_sensors import (
    EVSocKwhSensor,
    EVSocPercentSensor,
    TimeToTargetSocSensor,
)
from .common import EveusSensorBase
from .utils import get_safe_value

_LOGGER = logging.getLogger(__name__)

# Define InputEntitiesStatusSensor directly in this file
class InputEntitiesStatusSensor(EveusSensorBase):
    """Sensor that monitors the status of required input entities."""

    ENTITY_NAME = "Input Entities Status"
    _attr_icon = "mdi:clipboard-check"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, updater) -> None:
        """Initialize the input status sensor."""
        super().__init__(updater)
        self._state = "Unknown"
        self._missing_entities = []
        self._invalid_entities = []
        self._attr_extra_state_attributes = {}
        
        # List of required input entities
        self._required_inputs = [
            "input_number.ev_initial_soc",
            "input_number.ev_battery_capacity",
            "input_number.ev_soc_correction",
            "input_number.ev_target_soc"
        ]

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        self.async_schedule_update_ha_state(True)
        self._check_inputs()

    def _check_inputs(self) -> None:
        """Check all required input entities."""
        self._missing_entities = []
        self._invalid_entities = []

        for entity_id in self._required_inputs:
            state = self.hass.states.get(entity_id)
            if state is None:
                self._missing_entities.append(entity_id)
                continue

            # Check if the entity has a valid value
            try:
                value = float(state.state)
                if value < 0:  # Simple validation
                    self._invalid_entities.append(entity_id)
            except (ValueError, TypeError):
                self._invalid_entities.append(entity_id)

        # Update the status
        if self._missing_entities:
            self._state = f"Missing {len(self._missing_entities)} Inputs"
        elif self._invalid_entities:
            self._state = f"Invalid {len(self._invalid_entities)} Inputs"
        else:
            self._state = "OK"

        # Update attributes
        self._attr_extra_state_attributes = {
            "missing_entities": self._missing_entities,
            "invalid_entities": self._invalid_entities,
            "required_entities": self._required_inputs,
            "status_details": self._get_status_details()
        }

    def _get_status_details(self) -> dict[str, Any]:
        """Get detailed status for each required entity."""
        details = {}
        for entity_id in self._required_inputs:
            state = self.hass.states.get(entity_id)
            if state is None:
                details[entity_id] = "Missing"
            else:
                try:
                    value = float(state.state)
                    if value < 0:
                        details[entity_id] = f"Invalid: {state.state}"
                    else:
                        details[entity_id] = f"OK: {state.state}"
                except (ValueError, TypeError):
                    details[entity_id] = f"Invalid: {state.state}"
        return details

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        self._check_inputs()  # Check on every state request
        return self._state

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eveus sensors."""
    data = hass.data[DOMAIN][entry.entry_id]
    updater = data["updater"]

    # Create sensors from definitions
    sensor_definitions = get_sensor_definitions()
    sensors = [definition.create_sensor(updater) for definition in sensor_definitions]
    
    # Add EV-specific calculated sensors
    ev_sensors = [
        EVSocKwhSensor(updater),
        EVSocPercentSensor(updater),
        TimeToTargetSocSensor(updater),
        InputEntitiesStatusSensor(updater),  # Using renamed class
    ]
    
    # Add all sensors
    async_add_entities(sensors + ev_sensors)
