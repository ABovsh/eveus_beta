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
from .common import EveusSensorBase

_LOGGER = logging.getLogger(__name__)

# Define the required input entities
REQUIRED_INPUTS = [
    "input_number.ev_initial_soc",
    "input_number.ev_battery_capacity",
    "input_number.ev_soc_correction",
    "input_number.ev_target_soc"
]

class EVSocKwhSensor(EveusSensorBase):
    """Sensor for state of charge in kWh."""
    
    ENTITY_NAME = "SOC Energy"
    _attr_icon = "mdi:battery-charging"
    
    @property
    def native_value(self) -> float | None:
        """Return state of charge in kWh."""
        # Check for required entities
        for entity_id in ["input_number.ev_initial_soc", "input_number.ev_battery_capacity", "input_number.ev_soc_correction"]:
            if self.hass.states.get(entity_id) is None:
                return f"Missing {entity_id}"
        
        # Get values from input entities
        initial_soc = self.hass.states.get("input_number.ev_initial_soc")
        max_capacity = self.hass.states.get("input_number.ev_battery_capacity")
        
        # Calculate SOC in kWh
        try:
            soc_kwh = (float(initial_soc.state) / 100) * float(max_capacity.state)
            return round(soc_kwh, 1)
        except (ValueError, TypeError, AttributeError):
            return "Invalid inputs"

class EVSocPercentSensor(EveusSensorBase):
    """Sensor for state of charge percentage."""
    
    ENTITY_NAME = "SOC Percent"
    _attr_icon = "mdi:battery-charging"
    
    @property
    def native_value(self) -> float | None:
        """Return the state of charge percentage."""
        # Check for required entities
        if self.hass.states.get("input_number.ev_initial_soc") is None:
            return "Missing input_number.ev_initial_soc"
        
        # Return initial SOC directly
        initial_soc = self.hass.states.get("input_number.ev_initial_soc")
        try:
            return float(initial_soc.state)
        except (ValueError, TypeError, AttributeError):
            return "Invalid initial SOC"

class TimeToTargetSocSensor(EveusSensorBase):
    """Time to target SOC sensor."""
    
    ENTITY_NAME = "Time to Target SOC"
    _attr_icon = "mdi:timer"
    
    @property
    def native_value(self) -> str:
        """Calculate and return formatted time to target."""
        # Check if we're charging
        power = self._updater.data.get("powerMeas", 0)
        if power <= 0:
            return "Not charging"
            
        # Check for required entities
        for entity_id in REQUIRED_INPUTS:
            if self.hass.states.get(entity_id) is None:
                return f"Missing {entity_id}"
        
        return "Calculating..."

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

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        self._check_inputs()
        return self._state

    def _check_inputs(self) -> None:
        """Check all required input entities."""
        self._missing_entities = []
        self._invalid_entities = []

        for entity_id in REQUIRED_INPUTS:
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
            "required_entities": REQUIRED_INPUTS,
            "helper_creation_instructions": self._get_helper_instructions()
        }

    def _get_helper_instructions(self) -> str:
        """Get instructions for creating missing helpers."""
        if not self._missing_entities:
            return "All required input helpers exist"
            
        return (
            "Create these input helpers in Settings > Devices & Services > Helpers:\n"
            "- input_number.ev_battery_capacity: Your EV's battery capacity in kWh\n"
            "- input_number.ev_initial_soc: The initial state of charge percentage\n"
            "- input_number.ev_soc_correction: Efficiency loss during charging\n"
            "- input_number.ev_target_soc: Target state of charge for charging completion"
        )

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
        InputEntitiesStatusSensor(updater),
    ]
    
    # Add all sensors
    async_add_entities(sensors + ev_sensors)
