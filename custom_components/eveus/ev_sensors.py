"""Support for Eveus EV-specific sensors."""
from __future__ import annotations

import logging
import traceback
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy

from .common import EveusSensorBase
from .utils import get_safe_value, validate_required_values, calculate_remaining_time

_LOGGER = logging.getLogger(__name__)

class EVSocKwhSensor(EveusSensorBase):
    """Sensor for state of charge in kWh."""
    
    ENTITY_NAME = "SOC Energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:battery-charging"
    _attr_suggested_display_precision = 1
    _attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> float | None:
        """Calculate and return state of charge in kWh."""
        _LOGGER.debug("SOC Energy sensor calculation started")
        try:
            # Log all required input entities and their values
            _LOGGER.debug("Checking input entities existence")
            entities_to_check = {
                "input_number.ev_initial_soc": self.hass.states.get("input_number.ev_initial_soc"),
                "input_number.ev_battery_capacity": self.hass.states.get("input_number.ev_battery_capacity"),
                "input_number.ev_soc_correction": self.hass.states.get("input_number.ev_soc_correction")
            }
            
            for entity_id, state_obj in entities_to_check.items():
                if state_obj is None:
                    _LOGGER.error("Entity %s does not exist", entity_id)
                else:
                    _LOGGER.debug("Entity %s exists, state: %s", entity_id, state_obj.state)
            
            # Get input values with detailed logging
            initial_soc = get_safe_value(
                self.hass.states.get("input_number.ev_initial_soc"),
                converter=float
            )
            _LOGGER.debug("initial_soc value: %s", initial_soc)
            
            max_capacity = get_safe_value(
                self.hass.states.get("input_number.ev_battery_capacity"),
                converter=float
            )
            _LOGGER.debug("max_capacity value: %s", max_capacity)
            
            correction = get_safe_value(
                self.hass.states.get("input_number.ev_soc_correction"),
                converter=float
            )
            _LOGGER.debug("correction value: %s", correction)
            
            energy_charged = get_safe_value(self._updater.data, "IEM1", float, default=0)
            _LOGGER.debug("energy_charged (IEM1) value: %s", energy_charged)
            _LOGGER.debug("IEM1 attribute exists in updater data: %s", "IEM1" in self._updater.data)

            if not validate_required_values(initial_soc, max_capacity, correction):
                _LOGGER.error("Missing required values for SOC calculation: initial_soc=%s, max_capacity=%s, correction=%s", 
                             initial_soc, max_capacity, correction)
                return None

            if initial_soc < 0 or initial_soc > 100 or max_capacity <= 0:
                _LOGGER.error("Invalid values for SOC calculation: initial_soc=%s, max_capacity=%s",
                             initial_soc, max_capacity)
                return None

            # Calculation details
            initial_kwh = (initial_soc / 100) * max_capacity
            _LOGGER.debug("Calculated initial energy: %s kWh", initial_kwh)
            
            efficiency = (1 - correction / 100)
            _LOGGER.debug("Calculated efficiency factor: %s", efficiency)
            
            charged_kwh = energy_charged * efficiency
            _LOGGER.debug("Calculated charged energy: %s kWh", charged_kwh)
            
            total_kwh = initial_kwh + charged_kwh
            _LOGGER.debug("Calculated total energy: %s kWh", total_kwh)
            
            result = round(max(0, min(total_kwh, max_capacity)), 2)
            _LOGGER.info("SOC Energy calculation result: %s kWh", result)
            return result

        except Exception as err:
            _LOGGER.error("Error calculating SOC in kWh: %s", err)
            _LOGGER.debug("Traceback: %s", traceback.format_exc())
            return None


class EVSocPercentSensor(EveusSensorBase):
    """Sensor for state of charge percentage."""
    
    ENTITY_NAME = "SOC Percent"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:battery-charging"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    @property
    def native_value(self) -> float | None:
        """Return the state of charge percentage."""
        _LOGGER.debug("SOC Percent sensor calculation started")
        try:
            # Log all required input entities
            _LOGGER.debug("Checking SOC Energy sensor")
            energy_entity_id = "sensor.eveus_ev_charger_soc_energy"
            energy_state = self.hass.states.get(energy_entity_id)
            
            if energy_state is None:
                _LOGGER.error("SOC Energy sensor does not exist: %s", energy_entity_id)
            else:
                _LOGGER.debug("SOC Energy exists, state: %s", energy_state.state)
            
            # Get energy value from SOC kWh sensor
            soc_kwh = get_safe_value(energy_state, converter=float)
            _LOGGER.debug("SOC Energy value: %s", soc_kwh)
            
            max_capacity = get_safe_value(
                self.hass.states.get("input_number.ev_battery_capacity"),
                converter=float
            )
            _LOGGER.debug("max_capacity value: %s", max_capacity)
            
            # Fallback to direct calculation if SOC energy sensor is unavailable
            if soc_kwh is None:
                _LOGGER.debug("SOC Energy unavailable, falling back to direct calculation")
                
                # Directly calculate from IEM1 and initial SOC
                initial_soc = get_safe_value(
                    self.hass.states.get("input_number.ev_initial_soc"),
                    converter=float
                )
                _LOGGER.debug("initial_soc value: %s", initial_soc)
                
                correction = get_safe_value(
                    self.hass.states.get("input_number.ev_soc_correction"),
                    converter=float
                )
                _LOGGER.debug("correction value: %s", correction)
                
                energy_charged = get_safe_value(self._updater.data, "IEM1", float, default=0)
                _LOGGER.debug("energy_charged (IEM1) value: %s", energy_charged)
                
                if not validate_required_values(initial_soc, max_capacity, correction):
                    _LOGGER.error("Missing required values for direct SOC percent calculation")
                    return initial_soc  # Return initial SOC as fallback
                    
                efficiency = (1 - correction / 100)
                charged_kwh = energy_charged * efficiency
                initial_kwh = (initial_soc / 100) * max_capacity
                soc_kwh = initial_kwh + charged_kwh
                
                _LOGGER.debug("Direct SOC calculation: %s kWh", soc_kwh)
            
            if not validate_required_values(soc_kwh, max_capacity) or max_capacity <= 0:
                _LOGGER.error("Missing or invalid values for SOC percentage calculation")
                return None

            percentage = round((soc_kwh / max_capacity * 100), 0)
            result = max(0, min(percentage, 100))
            _LOGGER.info("SOC Percent calculation result: %s%%", result)
            return result
            
        except Exception as err:
            _LOGGER.error("Error calculating SOC percentage: %s", err)
            _LOGGER.debug("Traceback: %s", traceback.format_exc())
            return None


class TimeToTargetSocSensor(EveusSensorBase):
    """Time to target SOC sensor."""
    
    ENTITY_NAME = "Time to Target SOC"
    _attr_icon = "mdi:timer"

    @property
    def native_value(self) -> str:
        """Calculate and return formatted time to target."""
        _LOGGER.debug("Time to Target SOC sensor calculation started")
        try:
            # Log all input entities
            _LOGGER.debug("Checking input entities")
            entities_to_check = {
                "sensor.eveus_ev_charger_soc_percent": self.hass.states.get("sensor.eveus_ev_charger_soc_percent"),
                "input_number.ev_target_soc": self.hass.states.get("input_number.ev_target_soc"),
                "input_number.ev_battery_capacity": self.hass.states.get("input_number.ev_battery_capacity"),
                "input_number.ev_soc_correction": self.hass.states.get("input_number.ev_soc_correction"),
            }
            
            for entity_id, state_obj in entities_to_check.items():
                if state_obj is None:
                    _LOGGER.error("Entity %s does not exist", entity_id)
                else:
                    _LOGGER.debug("Entity %s exists, state: %s", entity_id, state_obj.state)
            
            _LOGGER.debug("Checking powerMeas in updater data: %s", "powerMeas" in self._updater.data)
            
            # Get input values
            percent_entity_id = "sensor.eveus_ev_charger_soc_percent"
            current_soc = get_safe_value(
                self.hass.states.get(percent_entity_id),
                converter=float
            )
            _LOGGER.debug("current_soc value from %s: %s", percent_entity_id, current_soc)
            
            target_soc = get_safe_value(
                self.hass.states.get("input_number.ev_target_soc"),
                converter=float
            )
            _LOGGER.debug("target_soc value: %s", target_soc)
            
            battery_capacity = get_safe_value(
                self.hass.states.get("input_number.ev_battery_capacity"),
                converter=float
            )
            _LOGGER.debug("battery_capacity value: %s", battery_capacity)
            
            correction = get_safe_value(
                self.hass.states.get("input_number.ev_soc_correction"),
                converter=float
            )
            _LOGGER.debug("correction value: %s", correction)
            
            power_meas = get_safe_value(self._updater.data, "powerMeas", float, default=0)
            _LOGGER.debug("power_meas value: %s", power_meas)
            
            # If SOC percent is not available, try to calculate it directly
            if current_soc is None:
                _LOGGER.debug("SOC Percent unavailable, trying alternatives")
                
                # Try to get SOC energy
                soc_kwh = get_safe_value(
                    self.hass.states.get("sensor.eveus_ev_charger_soc_energy"),
                    converter=float
                )
                _LOGGER.debug("SOC Energy value: %s", soc_kwh)
                
                if soc_kwh is not None and battery_capacity is not None and battery_capacity > 0:
                    current_soc = (soc_kwh / battery_capacity) * 100
                    _LOGGER.debug("Calculated current_soc from energy: %s%%", current_soc)
                else:
                    # Fallback to initial SOC plus charged energy
                    initial_soc = get_safe_value(
                        self.hass.states.get("input_number.ev_initial_soc"),
                        converter=float
                    )
                    _LOGGER.debug("initial_soc value: %s", initial_soc)
                    
                    energy_charged = get_safe_value(self._updater.data, "IEM1", float, default=0)
                    _LOGGER.debug("energy_charged (IEM1) value: %s", energy_charged)
                    
                    if initial_soc is not None and battery_capacity is not None and battery_capacity > 0:
                        efficiency = (1 - correction / 100) if correction is not None else 0.925
                        charged_percent = (energy_charged * efficiency / battery_capacity) * 100
                        current_soc = initial_soc + charged_percent
                        _LOGGER.debug("Fallback current_soc calculation: %s%%", current_soc)

            if not validate_required_values(current_soc, target_soc, battery_capacity):
                _LOGGER.error("Missing required values for time to target calculation")
                return "unavailable"

            result = calculate_remaining_time(
                current_soc,
                target_soc,
                power_meas,
                battery_capacity,
                correction if correction is not None else 7.5
            )
            
            _LOGGER.info("Time to target calculation result: %s", result)
            return result

        except Exception as err:
            _LOGGER.error("Error calculating time to target: %s", err)
            _LOGGER.debug("Traceback: %s", traceback.format_exc())
            return "unavailable"
