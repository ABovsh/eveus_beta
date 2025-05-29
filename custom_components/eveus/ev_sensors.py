"""Optimized EV-specific sensors with smart caching and performance improvements."""
from __future__ import annotations

import logging
import time
from typing import Any, Optional, Dict, Set
from functools import lru_cache
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.entity import EntityCategory

from .common import EveusSensorBase
from .utils import get_safe_value, calculate_remaining_time, format_duration

_LOGGER = logging.getLogger(__name__)

@dataclass
class InputEntityCache:
    """Cache for input entity values with timestamps."""
    initial_soc: Optional[float] = None
    battery_capacity: Optional[float] = None
    soc_correction: Optional[float] = None
    target_soc: Optional[float] = None
    timestamp: float = 0
    
    def is_valid(self, ttl: float = 30) -> bool:
        """Check if cache is still valid."""
        return time.time() - self.timestamp < ttl
    
    def update(self, **kwargs):
        """Update cache values."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.timestamp = time.time()

class CachedSOCCalculator:
    """High-performance SOC calculator with intelligent caching."""
    
    def __init__(self, cache_ttl: int = 30):
        self.cache_ttl = cache_ttl
        self._input_cache = InputEntityCache()
        self._soc_kwh_cache: Optional[float] = None
        self._soc_percent_cache: Optional[float] = None
        self._cache_timestamp = 0
        
    def _update_input_cache(self, hass: HomeAssistant) -> bool:
        """Update input entity cache if needed."""
        if self._input_cache.is_valid(self.cache_ttl):
            return True
            
        try:
            # Batch read all input entities
            entities = {
                'initial_soc': hass.states.get("input_number.ev_initial_soc"),
                'battery_capacity': hass.states.get("input_number.ev_battery_capacity"),
                'soc_correction': hass.states.get("input_number.ev_soc_correction"),
                'target_soc': hass.states.get("input_number.ev_target_soc")
            }
            
            # Check if any entities are missing
            missing = [k for k, v in entities.items() if v is None]
            if missing:
                _LOGGER.debug("Missing input entities: %s", missing)
                return False
            
            # Update cache with all values at once
            updates = {}
            for key, entity in entities.items():
                try:
                    updates[key] = float(entity.state)
                except (ValueError, TypeError):
                    _LOGGER.warning("Invalid value for %s: %s", key, entity.state)
                    return False
                    
            self._input_cache.update(**updates)
            return True
            
        except Exception as err:
            _LOGGER.error("Error updating input cache: %s", err)
            return False
    
    @lru_cache(maxsize=32)
    def _calculate_soc_kwh_cached(self, initial_soc: float, capacity: float, 
                                 energy_charged: float, correction: float) -> float:
        """Cached SOC calculation in kWh."""
        initial_kwh = (initial_soc / 100) * capacity
        efficiency = (1 - correction / 100)
        charged_kwh = energy_charged * efficiency
        total_kwh = initial_kwh + charged_kwh
        return round(max(0, min(total_kwh, capacity)), 2)
    
    def get_soc_kwh(self, hass: HomeAssistant, energy_charged: float) -> Optional[float]:
        """Get SOC in kWh with caching."""
        if not self._update_input_cache(hass):
            return None
            
        try:
            return self._calculate_soc_kwh_cached(
                self._input_cache.initial_soc,
                self._input_cache.battery_capacity,
                energy_charged,
                self._input_cache.soc_correction or 7.5
            )
        except Exception as err:
            _LOGGER.error("Error calculating SOC kWh: %s", err)
            return None
    
    def get_soc_percent(self, hass: HomeAssistant, energy_charged: float) -> Optional[float]:
        """Get SOC percentage with caching."""
        soc_kwh = self.get_soc_kwh(hass, energy_charged)
        if soc_kwh is None or not self._input_cache.battery_capacity:
            return self._input_cache.initial_soc or 0
            
        percentage = (soc_kwh / self._input_cache.battery_capacity) * 100
        return round(max(0, min(percentage, 100)), 0)
    
    def get_time_to_target(self, hass: HomeAssistant, power_meas: float, energy_charged: float) -> str:
        """Calculate time to target SOC with improved state handling."""
        if not self._update_input_cache(hass):
            return "Unavailable"
            
        try:
            # Get current SOC percentage using provided energy_charged
            current_soc = self.get_soc_percent(hass, energy_charged)
            
            if current_soc is None:
                return "Unavailable"
                
            return calculate_remaining_time(
                current_soc=current_soc,
                target_soc=self._input_cache.target_soc or 80,
                power_meas=power_meas,
                battery_capacity=self._input_cache.battery_capacity,
                correction=self._input_cache.soc_correction or 7.5
            )
        except Exception as err:
            _LOGGER.error("Error calculating time to target: %s", err)
            return "Unavailable"
    
    def invalidate_cache(self):
        """Force cache invalidation."""
        self._input_cache.timestamp = 0
        self._calculate_soc_kwh_cached.cache_clear()

# Global calculator instance for reuse across sensors
_soc_calculator = CachedSOCCalculator()

class EVSocKwhSensor(EveusSensorBase):
    """Optimized SOC energy sensor with smart caching."""
    
    ENTITY_NAME = "SOC Energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:battery-charging"
    _attr_suggested_display_precision = 1
    _attr_state_class = SensorStateClass.TOTAL
    
    def __init__(self, updater) -> None:
        """Initialize optimized SOC sensor."""
        super().__init__(updater)
        self._stop_listen = None
        self._last_update_time = 0
        self._cached_value = None
        
    async def async_added_to_hass(self) -> None:
        """Handle entity addition with optimized event tracking.""" 
        await super().async_added_to_hass()
        
        # Track only essential input changes
        self._stop_listen = async_track_state_change_event(
            self.hass,
            [
                "input_number.ev_initial_soc",
                "input_number.ev_battery_capacity", 
                "input_number.ev_soc_correction"
            ],
            self._on_input_changed
        )

    @callback
    def _on_input_changed(self, event: Event) -> None:
        """Handle input changes efficiently."""
        # Invalidate calculator cache
        _soc_calculator.invalidate_cache()
        
        # Rate limit updates
        current_time = time.time()
        if current_time - self._last_update_time > 1:  # Max 1 update per second
            self._last_update_time = current_time
            self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up event listeners."""
        if self._stop_listen:
            self._stop_listen()

    @property
    def native_value(self) -> Optional[float]:
        """Get SOC in kWh using optimized calculator."""
        try:
            energy_charged = get_safe_value(self._updater.data, "IEM1", float, default=0)
            result = _soc_calculator.get_soc_kwh(self.hass, energy_charged)
            
            if result is not None:
                self._cached_value = result
                
            return result
            
        except Exception as err:
            _LOGGER.error("Error in SOC Energy calculation: %s", err)
            return self._cached_value  # Return cached value on error

class EVSocPercentSensor(EveusSensorBase):
    """Optimized SOC percentage sensor."""
    
    ENTITY_NAME = "SOC Percent"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:battery-charging"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    
    def __init__(self, updater) -> None:
        """Initialize optimized SOC percent sensor."""
        super().__init__(updater)
        self._stop_listen = None
        self._last_update_time = 0
        self._cached_value = None
        
    async def async_added_to_hass(self) -> None:
        """Handle entity addition."""
        await super().async_added_to_hass()
        
        # Track input changes and SOC energy sensor
        self._stop_listen = async_track_state_change_event(
            self.hass,
            [
                "input_number.ev_initial_soc",
                "input_number.ev_battery_capacity",
                "input_number.ev_soc_correction",
                "sensor.eveus_ev_charger_soc_energy"
            ],
            self._on_input_changed
        )

    @callback
    def _on_input_changed(self, event: Event) -> None:
        """Handle input changes with rate limiting."""
        current_time = time.time()
        if current_time - self._last_update_time > 1:
            self._last_update_time = current_time
            self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up event listeners."""
        if self._stop_listen:
            self._stop_listen()

    @property
    def native_value(self) -> Optional[float]:
        """Get SOC percentage using optimized calculator."""
        try:
            energy_charged = get_safe_value(self._updater.data, "IEM1", float, default=0)
            result = _soc_calculator.get_soc_percent(self.hass, energy_charged)
            
            if result is not None:
                self._cached_value = result
                
            return result
            
        except Exception as err:
            _LOGGER.error("Error in SOC Percent calculation: %s", err)
            return self._cached_value or 0  # Return cached or 0 on error

class TimeToTargetSocSensor(EveusSensorBase):
    """Optimized time to target SOC sensor with improved state handling."""
    
    ENTITY_NAME = "Time to Target SOC"
    _attr_icon = "mdi:timer"
    
    def __init__(self, updater) -> None:
        """Initialize optimized time to target sensor."""
        super().__init__(updater)
        self._stop_listen = None
        self._last_update_time = 0
        self._cached_value = "Unavailable"
        
    async def async_added_to_hass(self) -> None:
        """Handle entity addition."""
        await super().async_added_to_hass()
        
        # Track relevant input changes
        self._stop_listen = async_track_state_change_event(
            self.hass,
            [
                "input_number.ev_target_soc",
                "input_number.ev_battery_capacity",
                "input_number.ev_soc_correction",
                "sensor.eveus_ev_charger_soc_percent"
            ],
            self._on_input_changed
        )

    @callback 
    def _on_input_changed(self, event: Event) -> None:
        """Handle input changes with rate limiting."""
        current_time = time.time()
        if current_time - self._last_update_time > 2:  # Rate limit to every 2 seconds
            self._last_update_time = current_time
            self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up event listeners."""
        if self._stop_listen:
            self._stop_listen()

    @property
    def native_value(self) -> str:
        """Calculate time to target with proper state handling."""
        try:
            power_meas = get_safe_value(self._updater.data, "powerMeas", float, default=0)
            energy_charged = get_safe_value(self._updater.data, "IEM1", float, default=0)
            
            # Use the calculator which now handles all states properly
            result = _soc_calculator.get_time_to_target(self.hass, power_meas, energy_charged)
            self._cached_value = result
            return result
            
        except Exception as err:
            _LOGGER.error("Error calculating time to target: %s", err)
            return self._cached_value

class InputEntitiesStatusSensor(EveusSensorBase):
    """Optimized input status monitoring sensor."""
    
    ENTITY_NAME = "Input Entities Status"
    _attr_icon = "mdi:clipboard-check"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    
    # Required inputs specification
    REQUIRED_INPUTS = {
        "input_number.ev_battery_capacity": {
            "name": "EV Battery Capacity",
            "min": 10, "max": 160, "step": 1, "initial": 80,
            "unit_of_measurement": "kWh", "mode": "slider",
            "icon": "mdi:car-battery"
        },
        "input_number.ev_initial_soc": {
            "name": "Initial EV State of Charge", 
            "min": 0, "max": 100, "step": 1, "initial": 20,
            "unit_of_measurement": "%", "mode": "slider",
            "icon": "mdi:battery-charging-40"
        },
        "input_number.ev_soc_correction": {
            "name": "Charging Efficiency Loss",
            "min": 0, "max": 15, "step": 0.1, "initial": 7.5,
            "unit_of_measurement": "%", "mode": "slider", 
            "icon": "mdi:chart-bell-curve"
        },
        "input_number.ev_target_soc": {
            "name": "Target SOC",
            "min": 0, "max": 100, "step": 5, "initial": 80,
            "unit_of_measurement": "%", "mode": "slider",
            "icon": "mdi:battery-charging-high"
        }
    }
    
    def __init__(self, updater) -> None:
        """Initialize optimized input status sensor."""
        super().__init__(updater)
        self._state = "Unknown"
        self._missing_entities: Set[str] = set()
        self._invalid_entities: Set[str] = set()
        self._last_check_time = 0
        self._check_interval = 30  # Check every 30 seconds
        
    @property
    def native_value(self) -> str:
        """Get input status with caching."""
        current_time = time.time()
        
        # Rate limit status checks
        if current_time - self._last_check_time > self._check_interval:
            self._check_inputs()
            self._last_check_time = current_time
            
        return self._state
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Get optimized status attributes.""" 
        attrs = {
            "missing_entities": list(self._missing_entities),
            "invalid_entities": list(self._invalid_entities),
            "required_count": len(self.REQUIRED_INPUTS),
            "missing_count": len(self._missing_entities),
            "invalid_count": len(self._invalid_entities),
            "status_summary": self._get_status_summary(),
        }
        
        # Only include configuration help if there are missing entities
        if self._missing_entities:
            attrs["configuration_help"] = self._get_configuration_help()
            
        return attrs
    
    def _check_inputs(self) -> None:
        """Efficiently check all required inputs."""
        self._missing_entities.clear()
        self._invalid_entities.clear()
        
        for entity_id in self.REQUIRED_INPUTS:
            state = self.hass.states.get(entity_id)
            
            if state is None:
                self._missing_entities.add(entity_id)
                continue
                
            # Validate entity value
            try:
                value = float(state.state)
                if value < 0:  # Simple validation
                    self._invalid_entities.add(entity_id)
            except (ValueError, TypeError):
                self._invalid_entities.add(entity_id)
        
        # Update status efficiently
        if self._missing_entities:
            self._state = f"Missing {len(self._missing_entities)} Inputs"
        elif self._invalid_entities:
            self._state = f"Invalid {len(self._invalid_entities)} Inputs"
        else:
            self._state = "OK"
    
    def _get_status_summary(self) -> Dict[str, Any]:
        """Get concise status summary."""
        return {
            entity_id: "Missing" if entity_id in self._missing_entities 
                      else "Invalid" if entity_id in self._invalid_entities 
                      else "OK"
            for entity_id in self.REQUIRED_INPUTS
        }
    
    def _get_configuration_help(self) -> Dict[str, str]:
        """Get configuration help for missing entities."""
        if not self._missing_entities:
            return None
            
        help_text = {}
        for entity_id in self._missing_entities:
            config = self.REQUIRED_INPUTS[entity_id]
            input_name = entity_id.split(".", 1)[1]
            help_text[entity_id] = (
                f"{input_name}:\n"
                f"  name: '{config['name']}'\n" 
                f"  min: {config['min']}\n"
                f"  max: {config['max']}\n"
                f"  step: {config['step']}\n"
                f"  initial: {config['initial']}\n"
                f"  unit_of_measurement: '{config['unit_of_measurement']}'\n"
                f"  mode: {config['mode']}\n"
                f"  icon: '{config['icon']}'"
            )
        
        return help_text
