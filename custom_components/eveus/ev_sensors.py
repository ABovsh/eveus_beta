"""Support for Eveus EV-specific sensors."""
from __future__ import annotations

import logging
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
        try:
            # Get input values
            initial_soc = get_safe_value(
                self.hass.states.get("input_number.ev_initial_soc"),
                converter=float
            )
            max_capacity = get_safe_value(
                self.hass.states.get("input_number.ev_battery_capacity"),
                converter=float
            )
            correction = get_safe_value(
                self.hass.states.get("input_number.ev_soc_correction"),
                converter=float
            )
            energy_charged = get_safe_value(self._updater.data, "IEM1", float, default=0)

            _LOGGER.debug(
                "SOC Energy calculation inputs: initial_soc=%s, max_capacity=%s, correction=%s, energy_charged=%s",
                initial_soc, max_capacity, correction, energy_charged
            )

            if not validate_required_values(initial_soc, max_capacity, correction):
                _LOGGER.warning("Missing required values for SOC calculation: Please check input_number helpers")
                return None

            if initial_soc < 0 or initial_soc > 100 or max_capacity <= 0:
                _LOGGER.warning("Invalid values for SOC calculation: initial_soc=%s, max_capacity=%s",
                               initial_soc, max_capacity)
                return None

            initial_kwh = (initial_soc / 100) * max_capacity
            efficiency = (1 - correction / 100)
            charged_kwh = energy_charged * efficiency
            total_kwh = initial_kwh + charged_kwh
            
            result = round(max(0, min(total_kwh, max_capacity)), 2)
            _LOGGER.debug("SOC Energy calculation result: %s kWh", result)
            return result

        except Exception as err:
            _LOGGER.error("Error calculating SOC in kWh: %s", err, exc_info=True)
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
        try:
            # Get energy from SOC kWh sensor directly
            energy_entity_id = "sensor.eveus_ev_charger_soc_energy"
            soc_kwh = get_safe_value(
                self.hass.states.get(energy_entity_id),
                converter=float
            )
            max_capacity = get_safe_value(
                self.hass.states.get("input_number.ev_battery_capacity"),
                converter=float
            )
            
            _LOGGER.debug(
                "SOC Percent calculation inputs: soc_kwh=%s, max_capacity=%s from %s",
                soc_kwh, max_capacity, energy_entity_id
            )
            
            # Fallback to direct calculation if SOC energy sensor is unavailable
            if soc_kwh is None:
                # Directly calculate from IEM1
                initial_soc = get_safe_value(
                    self.hass.states.get("input_number.ev_initial_soc"),
                    converter=float
                )
                correction = get_safe_value(
                    self.hass.states.get("input_number.ev_soc_correction"),
                    converter=float
                )
                energy_charged = get_safe_value(self._updater.data, "IEM1", float, default=0)
                
                if not validate_required_values(initial_soc, max_capacity, correction):
                    _LOGGER.warning("Missing required values for direct SOC percent calculation")
                    return None
                    
                efficiency = (1 - correction / 100)
                charged_kwh = energy_charged * efficiency
                initial_kwh = (initial_soc / 100) * max_capacity
                soc_kwh = initial_kwh + charged_kwh
                
                _LOGGER.debug("Direct SOC calculation: %s kWh", soc_kwh)
            
            if not validate_required_values(soc_kwh, max_capacity) or max_capacity <= 0:
                _LOGGER.warning("Missing or invalid values for SOC percentage calculation")
                return None

            percentage = round((soc_kwh / max_capacity * 100), 0)
            result = max(0, min(percentage, 100))
            _LOGGER.debug("SOC Percent calculation result: %s%%", result)
            return result
            
        except Exception as err:
            _LOGGER.error("Error calculating SOC percentage: %s", err, exc_info=True)
            return None


class TimeToTargetSocSensor(EveusSensorBase):
    """Time to target SOC sensor."""
    
    ENTITY_NAME = "Time to Target SOC"
    _attr_icon = "mdi:timer"

    @property
    def native_value(self) -> str:
        """Calculate and return formatted time to target."""
        try:
            percent_entity_id = "sensor.eveus_ev_charger_soc_percent"
            current_soc = get_safe_value(
                self.hass.states.get(percent_entity_id),
                converter=float
            )
            target_soc = get_safe_value(
                self.hass.states.get("input_number.ev_target_soc"),
                converter=float
            )
            battery_capacity = get_safe_value(
                self.hass.states.get("input_number.ev_battery_capacity"),
                converter=float
            )
            correction = get_safe_value(
                self.hass.states.get("input_number.ev_soc_correction"),
                converter=float
            )
            power_meas = get_safe_value(self._updater.data, "powerMeas", float, default=0)

            _LOGGER.debug(
                "Time to Target calculation inputs: current_soc=%s from %s, target_soc=%s, power=%s",
                current_soc, percent_entity_id, target_soc, power_meas
            )
            
            # If SOC percent is not available, try to calculate it directly
            if current_soc is None:
                # Try to get SOC energy
                soc_kwh = get_safe_value(
                    self.hass.states.get("sensor.eveus_ev_charger_soc_energy"),
                    converter=float
                )
                
                if soc_kwh is not None and battery_capacity is not None and battery_capacity > 0:
                    current_soc = (soc_kwh / battery_capacity) * 100
                    _LOGGER.debug("Calculated current_soc from energy: %s%%", current_soc)
                else:
                    # Fallback to initial SOC plus charged energy
                    initial_soc = get_safe_value(
                        self.hass.states.get("input_number.ev_initial_soc"),
                        converter=float
                    )
                    energy_charged = get_safe_value(self._updater.data, "IEM1", float, default=0)
                    
                    if initial_soc is not None and battery_capacity is not None and battery_capacity > 0:
                        efficiency = (1 - correction / 100) if correction is not None else 0.925
                        charged_percent = (energy_charged * efficiency / battery_capacity) * 100
                        current_soc = initial_soc + charged_percent
                        _LOGGER.debug("Fallback current_soc calculation: %s%%", current_soc)

            if not validate_required_values(current_soc, target_soc, battery_capacity):
                _LOGGER.warning("Missing required values for time to target calculation")
                return "unavailable"

            result = calculate_remaining_time(
                current_soc,
                target_soc,
                power_meas,
                battery_capacity,
                correction if correction is not None else 7.5
            )
            
            _LOGGER.debug("Time to target calculation result: %s", result)
            return result

        except Exception as err:
            _LOGGER.error("Error calculating time to target: %s", err, exc_info=True)
            return "unavailable"
