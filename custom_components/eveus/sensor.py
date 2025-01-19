# File: custom_components/eveus/sensor.py
"""Support for Eveus sensors with improved error handling and state management."""
from __future__ import annotations

import time
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Any, Final

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.event import async_track_time_interval, async_call_later
from homeassistant.util import dt as dt_util
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfPower,
    UnitOfEnergy,
    UnitOfTemperature,
    UnitOfTime,
    PERCENTAGE,
    EVENT_HOMEASSISTANT_START,
)

from .const import (
    DOMAIN,
    CHARGING_STATES,
    ERROR_STATES,
    NORMAL_SUBSTATES,
    ATTR_VOLTAGE,
    ATTR_CURRENT,
    ATTR_POWER,
    ATTR_SESSION_ENERGY,
    ATTR_TOTAL_ENERGY,
    ATTR_SESSION_TIME,
    ATTR_STATE,
    ATTR_SUBSTATE,
    ATTR_CURRENT_SET,
    ATTR_ENABLED,
    ATTR_TEMPERATURE_BOX,
    ATTR_TEMPERATURE_PLUG,
    ATTR_SYSTEM_TIME,
    ATTR_COUNTER_A_ENERGY,
    ATTR_COUNTER_B_ENERGY,
    ATTR_COUNTER_A_COST,
    ATTR_COUNTER_B_COST,
    ATTR_GROUND,
    ATTR_BATTERY_VOLTAGE,
    HELPER_EV_BATTERY_CAPACITY,
    HELPER_EV_INITIAL_SOC,
    HELPER_EV_SOC_CORRECTION,
    HELPER_EV_TARGET_SOC,
    TEMP_WARNING_BOX,
    TEMP_CRITICAL_BOX,
    TEMP_WARNING_PLUG,
    TEMP_CRITICAL_PLUG,
    BATTERY_VOLTAGE_WARNING,
    BATTERY_VOLTAGE_CRITICAL,
    BATTERY_VOLTAGE_MIN,
    BATTERY_VOLTAGE_MAX,
)

_LOGGER = logging.getLogger(__name__)

class BaseEveusSensor(SensorEntity, RestoreEntity):
    """Base sensor with improved error handling."""

    _attr_has_entity_name: Final = True
    _attr_should_poll = False
    _attr_entity_registry_enabled_default: Final = True
    _translation_prefix = "sensor"
    _max_retry_attempts = 3
    _retry_delay = 5.0

    def __init__(self, session_manager, name: str) -> None:
        """Initialize the sensor."""
        self._session_manager = session_manager
        self._attr_name = name
        self._attr_unique_id = f"{session_manager._host}_{name}"
        self.entity_id = f"sensor.eveus_{name.lower().replace(' ', '_')}"
        self._previous_value = None
        self._restored = False
        self._error_count = 0
        self._last_update = None
        self.hass = session_manager.hass

    async def async_added_to_hass(self) -> None:
        """Handle entity added to Home Assistant."""
        await super().async_added_to_hass()
        
        # Restore previous state
        last_state = await self.async_get_last_state()
        if last_state:
            self._attr_native_value = last_state.state
            self._previous_value = last_state.state
            self._restored = True

        # Register entity with session manager
        await self._session_manager.register_entity(self)
        
        # Request initial state
        await self._update_state()

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity removal."""
        await self._session_manager.unregister_entity(self)

    async def _update_state(self) -> None:
        """Update state with retry logic."""
        attempts = 0
        while attempts < self._max_retry_attempts:
            try:
                state = await self._session_manager.get_state()
                self._handle_state_update(state)
                self._error_count = 0
                self._last_update = dt_util.utcnow()
                return
                
            except Exception as err:
                attempts += 1
                self._error_count += 1
                _LOGGER.error(
                    "Error updating %s (attempt %d/%d): %s",
                    self.name,
                    attempts,
                    self._max_retry_attempts,
                    err
                )
                if attempts < self._max_retry_attempts:
                    await asyncio.sleep(self._retry_delay)

        _LOGGER.error(
            "Failed to update %s after %d attempts",
            self.name,
            self._max_retry_attempts
        )

    def _handle_state_update(self, state: dict) -> None:
        """Handle state update from device."""
        raise NotImplementedError

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._session_manager.available

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._session_manager._host)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": self._session_manager.model,
            "sw_version": self._session_manager.firmware_version,
            "serial_number": self._session_manager.station_id,
            "configuration_url": f"http://{self._session_manager._host}",
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return {
            "error_count": self._error_count,
            "last_update": dt_util.as_local(
                dt_util.utc_from_timestamp(self._last_update)
            ).isoformat() if isinstance(self._last_update, (int, float)) else None,
            "restored": self._restored,
        }
        if self._previous_value is not None:
            attrs["previous_value"] = self._previous_value
        return attrs

class BaseNumericSensor(BaseEveusSensor):
    """Base numeric sensor with validation."""

    _attr_suggested_display_precision: Final = 1
    _attribute: str = None
    _min_value: float = float('-inf')
    _max_value: float = float('inf')
    _warning_threshold: float | None = None
    _critical_threshold: float | None = None

    def _handle_state_update(self, state: dict) -> None:
        """Update numeric sensor state with validation."""
        try:
            value = state.get(self._attribute)
            if value is None:
                if not self._restored:
                    self._attr_native_value = None
                return

            value = float(value)
            if not self._validate_value(value):
                return

            self._attr_native_value = round(value, self._attr_suggested_display_precision)
            self._previous_value = self._attr_native_value
            self._restored = False

            self._check_thresholds(value)

        except (TypeError, ValueError) as err:
            self._error_count += 1
            _LOGGER.error(
                "Error converting value for %s: %s",
                self.name,
                str(err)
            )

    def _validate_value(self, value: float) -> bool:
        """Validate value is within defined range."""
        if not self._min_value <= value <= self._max_value:
            _LOGGER.warning(
                "%s value out of range [%f, %f]: %f",
                self.name,
                self._min_value,
                self._max_value,
                value
            )
            return False
        return True

    def _check_thresholds(self, value: float) -> None:
        """Check warning and critical thresholds."""
        if self._critical_threshold is not None and value >= self._critical_threshold:
            self._notify_warning(
                f"{self.name} value critically high: {value}",
                "critical"
            )
        elif self._warning_threshold is not None and value >= self._warning_threshold:
            self._notify_warning(
                f"{self.name} value high: {value}",
                "warning"
            )

    async def _notify_warning(self, message: str, level: str = "warning") -> None:
        """Send notification for warning conditions."""
        notification_id = f"eveus_{self.entity_id}_{level}"
        
        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": f"Eveus {level.title()}",
                "message": message,
                "notification_id": notification_id
            }
        )

class EveusTemperatureSensor(BaseNumericSensor):
    """Temperature sensor with configurable thresholds."""
    
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _min_value = -20
    _max_value = 100

    def __init__(self, session_manager, name: str, attribute: str, warning_temp: float, critical_temp: float) -> None:
        """Initialize temperature sensor."""
        super().__init__(session_manager, name)
        self._attribute = attribute
        self._warning_threshold = warning_temp
        self._critical_threshold = critical_temp

class EveusBoxTemperatureSensor(EveusTemperatureSensor):
    """Box temperature sensor."""

    def __init__(self, session_manager, name: str) -> None:
        """Initialize box temperature sensor."""
        super().__init__(
            session_manager,
            name,
            ATTR_TEMPERATURE_BOX,
            TEMP_WARNING_BOX,
            TEMP_CRITICAL_BOX
        )

class EveusPlugTemperatureSensor(EveusTemperatureSensor):
    """Plug temperature sensor."""

    def __init__(self, session_manager, name: str) -> None:
        """Initialize plug temperature sensor."""
        super().__init__(
            session_manager,
            name,
            ATTR_TEMPERATURE_PLUG,
            TEMP_WARNING_PLUG,
            TEMP_CRITICAL_PLUG
        )

class EveusBatteryVoltageSensor(BaseNumericSensor):
    """Battery voltage sensor with warnings."""

    _attribute = ATTR_BATTERY_VOLTAGE
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _min_value = BATTERY_VOLTAGE_MIN
    _max_value = BATTERY_VOLTAGE_MAX
    _warning_threshold = BATTERY_VOLTAGE_WARNING
    _critical_threshold = BATTERY_VOLTAGE_CRITICAL

    def _check_thresholds(self, value: float) -> None:
        """Check battery voltage thresholds."""
        if value <= self._critical_threshold:
            self._notify_warning(
                f"Battery voltage critically low: {value}V",
                "critical"
            )
        elif value <= self._warning_threshold:
            self._notify_warning(
                f"Battery voltage low: {value}V",
                "warning"
            )

class EveusCurrentSensor(BaseNumericSensor):
    """Current sensor with model validation."""

    _attribute = ATTR_CURRENT
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def _validate_value(self, value: float) -> bool:
        """Validate current against device model."""
        if not super()._validate_value(value):
            return False
            
        max_current = self._session_manager.capabilities.get("max_current", 16)
        if value > max_current:
            _LOGGER.warning(
                "Current exceeds device model limit (%sA): %sA",
                max_current,
                value
            )
            return False
            
        return True

class EveusCurrentSetSensor(BaseNumericSensor):
    """Current set sensor implementation."""
    
    _attribute = ATTR_CURRENT_SET
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, session_manager, name: str) -> None:
        super().__init__(session_manager, name)
        self._min_value = float(session_manager.capabilities.get("min_current", 8))
        self._max_value = float(session_manager.capabilities.get("max_current", 16))

class EveusVoltageSensor(BaseNumericSensor):
    """Voltage sensor implementation."""
    
    _attribute = ATTR_VOLTAGE
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _min_value = 180
    _max_value = 260

class EveusPowerSensor(BaseNumericSensor):
    """Power measurement sensor implementation."""
    
    _attribute = ATTR_POWER
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _min_value = 0
    _max_value = 7400  # 32A * 230V

class EveusEnergySensor(BaseNumericSensor):
    """Energy measurement sensor base class."""
    
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _min_value = 0

class EveusSessionEnergySensor(EveusEnergySensor):
    """Session energy sensor implementation."""
    _attribute = ATTR_SESSION_ENERGY

class EveusTotalEnergySensor(EveusEnergySensor):
    """Total energy sensor implementation."""
    _attribute = ATTR_TOTAL_ENERGY

class EveusCounterEnergySensor(EveusEnergySensor):
    """Base class for energy counter sensors."""

    def _handle_state_update(self, state: dict) -> None:
        """Handle state update."""
        try:
            value = state.get(self._attribute)
            if value in (None, "", "null"):
                if not self._restored:
                    self._attr_native_value = None
                return

            value = float(value)
            if not self._validate_value(value):
                return

            self._attr_native_value = round(value, 2)
            self._previous_value = self._attr_native_value
            self._restored = False

        except (TypeError, ValueError) as err:
            self._error_count += 1
            _LOGGER.error(
                "Error converting value for %s: %s",
                self.name,
                str(err)
            )

class EveusCounterAEnergySensor(EveusCounterEnergySensor):
    """Counter A energy sensor implementation."""
    _attribute = ATTR_COUNTER_A_ENERGY

class EveusCounterBEnergySensor(EveusCounterEnergySensor):
    """Counter B energy sensor implementation."""
    _attribute = ATTR_COUNTER_B_ENERGY

class EveusEnergyCostSensor(BaseNumericSensor):
   """Base class for energy cost sensors."""

   _attr_native_unit_of_measurement = "₴"
   _attr_state_class = SensorStateClass.TOTAL_INCREASING
   _attr_suggested_display_precision = 1
   _min_value = 0

   def _validate_value(self, value: float) -> bool:
       """Validate cost value with energy verification."""
       if not super()._validate_value(value):
           return False
           
       # Get corresponding energy value
       energy_attr = ATTR_COUNTER_A_ENERGY if self._attribute == ATTR_COUNTER_A_COST else ATTR_COUNTER_B_ENERGY
       energy = float(self._session_manager._state_cache.get(energy_attr, 0))
       
       if energy == 0 and value > 0:
           _LOGGER.warning(
               "Cost present (%s) but no energy recorded",
               value
           )
           return False
           
       return True

   @property
   def extra_state_attributes(self) -> dict[str, Any]:
       """Return additional state attributes."""
       attrs = super().extra_state_attributes
       if self._attr_native_value is not None:
           try:
               counter_letter = "A" if self._attribute == ATTR_COUNTER_A_COST else "B"
               energy = self.hass.states.get(
                   f"sensor.{self._session_manager._host}_counter_{counter_letter}_energy"
               )
               if energy and energy.state not in ('unknown', 'unavailable'):
                   attrs["rate"] = round(
                       self._attr_native_value / float(energy.state),
                       2
                   )
                   attrs["counter"] = counter_letter
           except (TypeError, ValueError, ZeroDivisionError):
               pass
       return attrs

class EveusCounterACostSensor(EveusEnergyCostSensor):
   """Counter A cost sensor implementation."""
   _attribute = ATTR_COUNTER_A_COST

class EveusCounterBCostSensor(EveusEnergyCostSensor):
   """Counter B cost sensor implementation."""
   _attribute = ATTR_COUNTER_B_COST

# Class update in sensor.py:
class EveusCommunicationSensor(BaseEveusSensor):
    """Enhanced communication quality sensor."""

    def __init__(self, session_manager, name: str) -> None:
        """Initialize communication sensor."""
        super().__init__(session_manager, name)
        self._attr_device_class = SensorDeviceClass.DURATION
        self._attr_native_unit_of_measurement = "s"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:wifi-check"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    def _handle_state_update(self, state: dict) -> None:
        """Handle state update with delay detection."""
        try:
            last_update = self._session_manager._last_state_update
            if not last_update:
                self._attr_native_value = 0
                return

            current_time = time.time()
            self._attr_native_value = int(current_time - last_update)

            self._attr_extra_state_attributes = {
                "available": self._session_manager.available,
                "error_count": self._session_manager._error_count,
                "last_update": dt_util.utc_from_timestamp(last_update).isoformat() if last_update else None,
                "status": "Connected" if self._session_manager.available else "Disconnected"
            }

        except Exception as err:
            self._error_count += 1
            _LOGGER.error("Error updating communication state: %s", str(err))
            
class EveusStateSensor(BaseEveusSensor):
   """State sensor implementation."""

   _attr_entity_category = EntityCategory.DIAGNOSTIC

   def _handle_state_update(self, state: dict) -> None:
       """Handle charging state update."""
       try:
           state_code = int(state.get(ATTR_STATE, -1))
           if state_code not in CHARGING_STATES:
               _LOGGER.warning("Unknown charging state code: %d", state_code)
               self._attr_native_value = "Unknown"
               return
           
           self._attr_native_value = CHARGING_STATES[state_code]
           self._attr_extra_state_attributes = {
               **self.extra_state_attributes,
               "state_code": state_code,
               "is_charging": state_code == 4,
               "has_error": state_code == 7,
           }

       except (TypeError, ValueError) as err:
           self._error_count += 1
           _LOGGER.error(
               "Error processing charging state: %s",
               str(err)
           )
           self._attr_native_value = "Error"

class EveusSubstateSensor(BaseEveusSensor):
   """Substate sensor implementation."""

   _attr_entity_category = EntityCategory.DIAGNOSTIC

   def _handle_state_update(self, state: dict) -> None:
       """Handle substate update with enhanced error detection."""
       try:
           state_code = int(state.get(ATTR_STATE, -1))
           substate_code = int(state.get(ATTR_SUBSTATE, -1))

           if state_code == 7:  # Error state
               if substate_code not in ERROR_STATES:
                   _LOGGER.warning("Unknown error state: %d", substate_code)
                   self._attr_native_value = "Unknown Error"
               else:
                   self._attr_native_value = ERROR_STATES[substate_code]
                   if substate_code > 0:
                       _LOGGER.error(
                           "Charger error detected: %s",
                           self._attr_native_value
                       )
           else:
               if substate_code not in NORMAL_SUBSTATES:
                   _LOGGER.warning("Unknown substate: %d", substate_code)
                   self._attr_native_value = "Unknown State"
               else:
                   self._attr_native_value = NORMAL_SUBSTATES[substate_code]

           self._attr_extra_state_attributes = {
               **self.extra_state_attributes,
               "state_code": state_code,
               "substate_code": substate_code,
               "is_error": state_code == 7,
               "requires_attention": substate_code > 0 and state_code == 7,
           }

       except (TypeError, ValueError) as err:
           self._error_count += 1
           _LOGGER.error(
               "Error processing substate: %s",
               str(err)
           )
           self._attr_native_value = "Error"

class EveusEnabledSensor(BaseEveusSensor):
   """Enabled state sensor implementation."""

   _attribute = ATTR_ENABLED
   _attr_entity_category = EntityCategory.DIAGNOSTIC
   _attr_device_class = SensorDeviceClass.ENUM
   _attr_options = ["Yes", "No", "Unknown"]

   def _handle_state_update(self, state: dict) -> None:
       """Handle enabled state update."""
       try:
           value = state.get(self._attribute)
           if value is None:
               self._attr_native_value = "Unknown"
           else:
               self._attr_native_value = "Yes" if int(value) == 1 else "No"
       except (TypeError, ValueError) as err:
           self._error_count += 1
           _LOGGER.error(
               "Error processing enabled state: %s",
               str(err)
           )
           self._attr_native_value = "Unknown"

class EveusGroundSensor(BaseEveusSensor):
   """Ground connection sensor implementation."""

   _attribute = ATTR_GROUND
   _attr_entity_category = EntityCategory.DIAGNOSTIC
   _attr_device_class = SensorDeviceClass.ENUM
   _attr_options = ["Connected", "Not Connected", "Unknown"]

   def _handle_state_update(self, state: dict) -> None:
       """Handle ground status update."""
       try:
           value = state.get(self._attribute)
           if value is None:
               self._attr_native_value = "Unknown"
           else:
               is_connected = int(value) == 1
               self._attr_native_value = "Connected" if is_connected else "Not Connected"
               if not is_connected:
                   _LOGGER.warning("Ground connection issue detected")
                   self._notify_warning(
                       "Ground connection issue detected",
                       "warning"
                   )
       except (TypeError, ValueError) as err:
           self._error_count += 1
           _LOGGER.error(
               "Error processing ground state: %s",
               str(err)
           )
           self._attr_native_value = "Unknown"

class EveusSystemTimeSensor(BaseEveusSensor):
   """System time sensor implementation."""

   _attribute = ATTR_SYSTEM_TIME
   _attr_icon = "mdi:clock"

   def _handle_state_update(self, state: dict) -> None:
       """Handle system time update."""
       try:
           timestamp = int(state.get(self._attribute, 0))
           if timestamp == 0:
               raise ValueError("Invalid timestamp")

           # Convert timestamp to datetime
           # Subtract 2 hours to adjust from device's GMT+2
           local_time = datetime.fromtimestamp(timestamp - 7200)
           
           # Format in 24h format
           self._attr_native_value = local_time.strftime("%H:%M")
           
           self._attr_extra_state_attributes = {
               **self.extra_state_attributes,
               "raw_timestamp": timestamp,
               "full_datetime": local_time.strftime("%Y-%m-%d %H:%M:%S"),
               "date": local_time.strftime("%Y-%m-%d")
           }
           
       except (TypeError, ValueError, OSError) as err:
           self._error_count += 1
           _LOGGER.error("Error processing system time: %s", str(err))
           self._attr_native_value = None

class EveusSessionTimeSensor(BaseEveusSensor):
   """Session time sensor implementation."""

   _attribute = ATTR_SESSION_TIME
   _attr_device_class = SensorDeviceClass.DURATION
   _attr_native_unit_of_measurement = UnitOfTime.SECONDS
   _attr_state_class = SensorStateClass.MEASUREMENT

   def _handle_state_update(self, state: dict) -> None:
       """Handle session time update."""
       try:
           seconds = int(state.get(self._attribute, 0))
           if seconds < 0:
               _LOGGER.warning("Negative session time: %d seconds", seconds)
               return
               
           self._attr_native_value = seconds

           # Calculate formatted time
           days = seconds // 86400
           hours = (seconds % 86400) // 3600
           minutes = (seconds % 3600) // 60

           if days > 0:
               formatted_time = f"{days}d {hours:02d}h {minutes:02d}m"
           elif hours > 0:
               formatted_time = f"{hours}h {minutes:02d}m"
           else:
               formatted_time = f"{minutes}m"

           self._attr_extra_state_attributes = {
               **self.extra_state_attributes,
               "formatted_time": formatted_time,
               "days": days,
               "hours": hours,
               "minutes": minutes,
           }

       except (TypeError, ValueError) as err:
           self._error_count += 1
           _LOGGER.error("Error processing session time: %s", str(err))
           self._attr_native_value = 0

class EVSocKwhSensor(BaseEveusSensor):
   """EV State of Charge energy sensor implementation."""

   _attr_device_class = SensorDeviceClass.ENERGY
   _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
   _attr_state_class = SensorStateClass.TOTAL
   _attr_suggested_display_precision = 1

   def _handle_state_update(self, state: dict) -> None:
       """Calculate and update SOC in kWh."""
       try:
           initial_soc = float(self.hass.states.get(HELPER_EV_INITIAL_SOC).state)
           max_capacity = float(self.hass.states.get(HELPER_EV_BATTERY_CAPACITY).state)
           energy_charged = float(state.get(ATTR_COUNTER_A_ENERGY, 0))
           correction = float(self.hass.states.get(HELPER_EV_SOC_CORRECTION).state)

           # Validate inputs
           if not (0 <= initial_soc <= 100 and max_capacity > 0 and 0 <= correction <= 10):
               _LOGGER.error("Invalid input parameters for SOC calculation")
               return

           initial_kwh = (initial_soc / 100) * max_capacity
           efficiency = (1 - correction / 100)
           charged_kwh = energy_charged * efficiency
           total_kwh = initial_kwh + charged_kwh

           # Ensure result is within valid range
           self._attr_native_value = max(0, min(total_kwh, max_capacity))

           # Store calculation details in attributes
           self._attr_extra_state_attributes = {
               **self.extra_state_attributes,
               "initial_soc_kwh": round(initial_kwh, 2),
               "energy_charged": round(energy_charged, 2),
               "efficiency": round(efficiency, 3),
               "charging_losses": round(energy_charged * (correction / 100), 2),
               "max_capacity": max_capacity,
           }

       except (TypeError, ValueError, AttributeError) as err:
           self._error_count += 1
           _LOGGER.error("Error calculating SOC: %s", str(err))
           if not self._restored:
               self._attr_native_value = None

class EVSocPercentSensor(BaseEveusSensor):
   """EV State of Charge percentage sensor implementation."""

   _attr_device_class = SensorDeviceClass.BATTERY
   _attr_native_unit_of_measurement = PERCENTAGE
   _attr_state_class = SensorStateClass.MEASUREMENT
   _attr_suggested_display_precision = 0

   def _handle_state_update(self, state: dict) -> None:
       """Calculate and update SOC percentage."""
       try:
           battery_capacity = self.hass.states.get(HELPER_EV_BATTERY_CAPACITY)
           if not battery_capacity or battery_capacity.state in ('unknown', 'unavailable'):
               raise ValueError("Battery capacity helper unavailable")

           initial_soc = self.hass.states.get(HELPER_EV_INITIAL_SOC)
           if not initial_soc or initial_soc.state in ('unknown', 'unavailable'):
               raise ValueError("Initial SOC helper unavailable")

           energy_charged = float(state.get(ATTR_COUNTER_A_ENERGY, 0))
           
           correction = self.hass.states.get(HELPER_EV_SOC_CORRECTION)
           if not correction or correction.state in ('unknown', 'unavailable'):
               raise ValueError("SOC correction helper unavailable")

           # Calculate SOC
           max_capacity = float(battery_capacity.state)
           initial_soc_value = float(initial_soc.state)
           correction_factor = float(correction.state)

           # Calculate energy added considering losses
           efficiency = (1 - correction_factor / 100)
           energy_added = energy_charged * efficiency

           # Calculate total energy and percentage
           initial_energy = (initial_soc_value / 100) * max_capacity
           total_energy = initial_energy + energy_added
           percentage = (total_energy / max_capacity) * 100

           # Ensure percentage is within valid range
           self._attr_native_value = max(0, min(round(percentage), 100))
           
           # Add detailed attributes
           self._attr_extra_state_attributes = {
               **self.extra_state_attributes,
               "initial_soc": initial_soc_value,
               "energy_charged": round(energy_charged, 2),
               "energy_added": round(energy_added, 2),
               "efficiency": round(efficiency * 100, 1),
               "max_capacity": max_capacity,
               "current_energy": round(total_energy, 2),
               "available_capacity": round(max_capacity - total_energy, 2)
           }

       except Exception as err:
           self._error_count += 1
           _LOGGER.error("Error calculating SOC percentage: %s", str(err))
           if not self._restored:
               self._attr_native_value = None

class TimeToTargetSocSensor(BaseEveusSensor):
   """Time to target SOC sensor implementation."""

   def _handle_state_update(self, state: dict) -> None:
       """Calculate and update time to target SOC."""
       try:
           # Check if charging
           state_code = int(state.get(ATTR_STATE, -1))
           if state_code != 4:  # Not charging
               charging_state = CHARGING_STATES.get(state_code, "Unknown")
               self._attr_native_value = f"Not charging ({charging_state})"
               self._attr_extra_state_attributes = {
                   **self.extra_state_attributes,
                   "state": charging_state,
                   "charging_active": False,
               }
               return

           # Get current and target values
           soc_state = self.hass.states.get(f"sensor.{self._session_manager._host}_soc_percent")
           if not soc_state or soc_state.state in ('unknown', 'unavailable'):
               self._attr_native_value = "Unknown SOC state"
               return

           current_soc = float(soc_state.state)
           target_soc_helper = self.hass.states.get(HELPER_EV_TARGET_SOC)
           if not target_soc_helper or target_soc_helper.state in ('unknown', 'unavailable'):
               self._attr_native_value = "Unknown target SOC"
               return

           target_soc = float(target_soc_helper.state)

           if current_soc >= target_soc:
               self._attr_native_value = "Target reached"
               self._attr_extra_state_attributes = {
                   **self.extra_state_attributes,
                   "target_reached": True,
                   "current_soc": current_soc,
                   "target_soc": target_soc,
               }
               return

           power_meas = float(state.get(ATTR_POWER, 0))
           if power_meas < 100:  # Minimum power threshold
               self._attr_native_value = f"Insufficient power ({power_meas:.0f}W)"
               self._attr_extra_state_attributes = {
                   **self.extra_state_attributes,
                   "power_too_low": True,
                   "current_power": power_meas,
               }
               return

           # Calculate remaining time
           battery_capacity = float(self.hass.states.get(HELPER_EV_BATTERY_CAPACITY).state)
           correction = float(self.hass.states.get(HELPER_EV_SOC_CORRECTION).state)

           remaining_kwh = (target_soc - current_soc) * battery_capacity / 100
           efficiency = (1 - correction / 100)
           power_kw = power_meas * efficiency / 1000
           total_minutes = round(remaining_kwh / power_kw * 60)

           # Format time string
           if total_minutes < 1:
               self._attr_native_value = "Less than 1m"
           else:
               days = int(total_minutes // 1440)
               hours = int((total_minutes % 1440) // 60)
               minutes = int(total_minutes % 60)

               parts = []
               if days > 0:
                   parts.append(f"{days}d")
               if hours > 0:
                   parts.append(f"{hours}h")
               if minutes > 0:
                   parts.append(f"{minutes}m")
                   
               self._attr_native_value = " ".join(parts)

           # Store calculation details in attributes
           self._attr_extra_state_attributes = {
               **self.extra_state_attributes,
               "current_soc": current_soc,
               "target_soc": target_soc,
               "charging_power": power_meas,
               "efficiency": efficiency,
               "remaining_kwh": round(remaining_kwh, 2),
               "estimated_minutes": total_minutes,
               "charging_active": True,
               "power_sufficient": True,
           }

       except Exception as err:
           self._error_count += 1
           _LOGGER.error("Error calculating time to target: %s", str(err))
           self._attr_native_value = "Calculation error"
           self._attr_extra_state_attributes = {
               **self.extra_state_attributes,
               "error": str(err),
               "charging_active": False,
           }

async def async_setup_entry(
   hass: HomeAssistant,
   entry: ConfigEntry,
   async_add_entities: AddEntitiesCallback,
) -> None:
   """Set up Eveus sensors."""
   session_manager = hass.data[DOMAIN][entry.entry_id]["session_manager"]

   sensors = [
       EveusCommunicationSensor(session_manager, "Communication"),
       EveusVoltageSensor(session_manager, "Voltage"),
       EveusCurrentSensor(session_manager, "Current"),
       EveusPowerSensor(session_manager, "Power"),
       EveusCurrentSetSensor(session_manager, "Current Set"),
       EveusSessionEnergySensor(session_manager, "Session Energy"),
       EveusTotalEnergySensor(session_manager, "Total Energy"),
       EveusStateSensor(session_manager, "State"),
       EveusSubstateSensor(session_manager, "Substate"),
       EveusEnabledSensor(session_manager, "Enabled"),
       EveusGroundSensor(session_manager, "Ground"),
       EveusBoxTemperatureSensor(session_manager, "Box Temperature"),
       EveusPlugTemperatureSensor(session_manager, "Plug Temperature"),
       EveusBatteryVoltageSensor(session_manager, "Battery Voltage"),
       EveusSystemTimeSensor(session_manager, "System Time"),
       EveusSessionTimeSensor(session_manager, "Session Time"),
       EveusCounterAEnergySensor(session_manager, "Counter A Energy"),
       EveusCounterBEnergySensor(session_manager, "Counter B Energy"),
       EveusCounterACostSensor(session_manager, "Counter A Cost"),
       EveusCounterBCostSensor(session_manager, "Counter B Cost"),
       EVSocKwhSensor(session_manager, "SOC Energy"),
       EVSocPercentSensor(session_manager, "SOC Percent"),
       TimeToTargetSocSensor(session_manager, "Time to Target"),
   ]

   # Store entity references
   hass.data[DOMAIN][entry.entry_id]["entities"]["sensor"] = {
       sensor.unique_id: sensor for sensor in sensors
   }

   # Get initial state for update interval
   try:
       state = await session_manager.get_state(force_refresh=True)
       charging_state = int(state.get("state", 2))
       interval = timedelta(seconds=10 if charging_state == 4 else 120)
   except Exception:
       interval = timedelta(seconds=120)

   async def async_update_sensors(*_) -> None:
       """Update all sensors efficiently."""
       if not hass.is_running:
           return

       try:
           # Get state once for all sensors
           state = await session_manager.get_state(force_refresh=True)
           
           # Update entities in batches
           batch_size = 5
           for i in range(0, len(sensors), batch_size):
               batch = sensors[i:i + batch_size]
               
               for sensor in batch:
                   try:
                       sensor._handle_state_update(state)
                       sensor.async_write_ha_state()
                   except Exception as err:
                       _LOGGER.error(
                           "Error updating sensor %s: %s",
                           sensor.name,
                           str(err),
                           exc_info=True
                       )
               
               await asyncio.sleep(0.1)
                   
       except Exception as err:
           _LOGGER.error("Failed to update sensors: %s", err)

       # Adjust update interval based on charging state
       try:
           charging_state = int(state.get("state", 2))
           new_interval = timedelta(seconds=10 if charging_state == 4 else 120)
           
           if new_interval != interval:
               async_track_time_interval(
                   hass,
                   async_update_sensors,
                   new_interval
               )
       except Exception as err:
           _LOGGER.error("Failed to adjust update interval: %s", err)

   # Add entities first
   async_add_entities(sensors, update_before_add=True)

   # Setup initial update
   if not hass.is_running:
       hass.bus.async_listen_once(
           EVENT_HOMEASSISTANT_START,
           async_update_sensors
       )
   else:
       await async_update_sensors()

   # Schedule periodic updates
   async_track_time_interval(
       hass,
       async_update_sensors,
       interval
   )
