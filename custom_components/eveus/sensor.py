"""Support for Eveus sensors."""
from __future__ import annotations
import logging
import asyncio
import time
from datetime import datetime
from typing import Any
import aiohttp
from functools import partial

from homeassistant.core import HomeAssistant 
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.restore_state import RestoreEntity
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
   CONF_HOST,
   CONF_USERNAME,
   CONF_PASSWORD,
)

from .const import (
   DOMAIN,
   SCAN_INTERVAL,
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
)

_LOGGER = logging.getLogger(__name__)

class EveusUpdater:
   """Class to handle Eveus data updates."""

   def __init__(self, host: str, username: str, password: str, hass: HomeAssistant) -> None:
       """Initialize the updater."""
       self._host = host
       self._username = username
       self._password = password
       self._hass = hass
       self._data = {}
       self._available = True
       self._session = None
       self._sensors = []
       self._update_task = None
       self._last_update = time.time()
       self._update_lock = asyncio.Lock()
       self._error_count = 0
       self._max_errors = 3

   def register_sensor(self, sensor: "BaseEveusSensor") -> None:
       """Register a sensor for updates."""
       self._sensors.append(sensor)

   @property
   def data(self) -> dict:
       """Return the latest data."""
       return self._data

   @property
   def available(self) -> bool:
       """Return if updater is available."""
       return self._available

   @property
   def last_update(self) -> float:
       """Return last update time."""
       return self._last_update

   async def async_start_updates(self) -> None:
       """Start the update loop."""
       if self._update_task is None:
           self._update_task = asyncio.create_task(self._update_loop())

   async def _update_loop(self) -> None:
       """Handle updates."""
       while True:
           try:
               await self._update()
               await asyncio.sleep(SCAN_INTERVAL.total_seconds())
           except asyncio.CancelledError:
               break
           except Exception as err:
               _LOGGER.error("Update error: %s", str(err))
               await asyncio.sleep(SCAN_INTERVAL.total_seconds())

   async def _get_session(self) -> aiohttp.ClientSession:
       """Get/create client session."""
       if self._session is None or self._session.closed:
           self._session = aiohttp.ClientSession(
               timeout=aiohttp.ClientTimeout(total=10),
               connector=aiohttp.TCPConnector(limit=1, force_close=True)
           )
       return self._session

   async def _update(self) -> None:
       """Update data."""
       try:
           session = await self._get_session()
           async with session.post(
               f"http://{self._host}/main",
               auth=aiohttp.BasicAuth(self._username, self._password),
               timeout=10
           ) as response:
               response.raise_for_status()
               self._data = await response.json()
               self._available = True
               self._last_update = time.time()
               self._error_count = 0

               for sensor in self._sensors:
                   try:
                       sensor.async_write_ha_state()
                   except Exception as err:
                       _LOGGER.error("Sensor update error: %s", str(err))

       except Exception as err:
           self._error_count += 1
           self._available = self._error_count < self._max_errors
           _LOGGER.error("Data update error: %s", str(err))

   async def async_shutdown(self) -> None:
       """Shutdown the updater."""
       if self._update_task:
           self._update_task.cancel()
           try:
               await self._update_task
           except asyncio.CancelledError:
               pass
       if self._session and not self._session.closed:
           await self._session.close()

class BaseEveusSensor(SensorEntity, RestoreEntity):
   """Base implementation for Eveus sensors."""

   _attr_has_entity_name = True
   _attr_should_poll = False
   _attr_entity_registry_enabled_default = True
   _attr_entity_registry_visible_default = True

   def __init__(self, updater: EveusUpdater) -> None:
       """Initialize the sensor."""
       self._updater = updater
       self._updater.register_sensor(self)
       self._previous_value = None

   async def async_added_to_hass(self) -> None:
       """Handle entity which will be added."""
       await super().async_added_to_hass()
       state = await self.async_get_last_state()
       if state and state.state not in ('unknown', 'unavailable'):
           try:
               self._previous_value = (
                   float(state.state) 
                   if hasattr(self, '_attr_suggested_display_precision') 
                   else state.state
               )
           except (TypeError, ValueError):
               self._previous_value = state.state
       await self._updater.async_start_updates()

   async def async_will_remove_from_hass(self) -> None:
       """Handle entity removal."""
       await self._updater.async_shutdown()

   @property
   def device_info(self) -> dict[str, Any]:
       """Return device information."""
       return {
           "identifiers": {(DOMAIN, self._updater._host)},
           "name": "Eveus EV Charger",
           "manufacturer": "Eveus",
           "model": f"Eveus ({self._updater._host})",
           "sw_version": self._updater.data.get("verFWMain", "Unknown"),
           "hw_version": self._updater.data.get("verHW", "Unknown"),
       }

   @property
   def extra_state_attributes(self) -> dict[str, Any]:
       """Return additional state attributes."""
       attrs = {
           "last_update": self._updater.last_update,
           "host": self._updater._host,
       }
       if self._previous_value is not None:
           attrs["previous_value"] = self._previous_value
       return attrs

   @property
   def available(self) -> bool:
       """Return if entity is available."""
       return self._updater.available

class NumericSensor(BaseEveusSensor):
   """Base class for numeric sensors."""
   
   _attr_suggested_display_precision = 2
   _attr_state_class = SensorStateClass.MEASUREMENT

   def __init__(self, updater: EveusUpdater, name: str, key: str, 
                unit: str = None, device_class: str = None,
                icon: str = None, precision: int = None) -> None:
       """Initialize numeric sensor."""
       super().__init__(updater)
       self._attr_name = name
       self._attr_unique_id = f"{updater._host}_{key}"
       self._key = key
       if unit:
           self._attr_native_unit_of_measurement = unit
       if device_class:
           self._attr_device_class = device_class
       if icon:
           self._attr_icon = icon
       if precision is not None:
           self._attr_suggested_display_precision = precision

   @property
   def native_value(self) -> float | None:
       """Return the sensor value."""
       try:
           value = float(self._updater.data.get(self._key, 0))
           self._previous_value = value
           return round(value, self._attr_suggested_display_precision)
       except (TypeError, ValueError):
           return self._previous_value

class EnergySensor(NumericSensor):
   """Base energy sensor."""
   def __init__(self, updater: EveusUpdater, name: str, key: str):
       """Initialize energy sensor."""
       super().__init__(
           updater=updater,
           name=name,
           key=key,
           unit=UnitOfEnergy.KILO_WATT_HOUR,
           device_class=SensorDeviceClass.ENERGY,
           precision=1
       )
       self._attr_state_class = SensorStateClass.TOTAL_INCREASING

class StateSensor(BaseEveusSensor):
   """Base state sensor."""
   _attr_entity_category = EntityCategory.DIAGNOSTIC
   
   def __init__(self, updater: EveusUpdector, name: str, key: str,
                state_map: dict, icon: str = "mdi:information"):
       """Initialize state sensor."""
       super().__init__(updater)
       self._attr_name = name
       self._attr_unique_id = f"{updator._host}_{key}"
       self._key = key
       self._state_map = state_map
       self._attr_icon = icon

   @property
   def native_value(self) -> str:
       """Return mapped state value."""
       try:
           state = self._updater.data.get(self._key)
           return self._state_map.get(state, "Unknown")
       except (TypeError, ValueError):
           return "Unknown"

class EveusGroundSensor(BaseEveusSensor):
   """Ground connection sensor."""
   _attr_entity_category = EntityCategory.DIAGNOSTIC
   _attr_icon = "mdi:power-plug"

   def __init__(self, updater: EveusUpdater) -> None:
       """Initialize ground sensor."""
       super().__init__(updater)
       self._attr_name = "Ground Connection"
       self._attr_unique_id = f"{updater._host}_ground"

   @property
   def native_value(self) -> str:
       """Return ground status."""
       try:
           return "Connected" if self._updater.data.get(ATTR_GROUND) == 1 else "Not Connected"
       except (TypeError, ValueError):
           return "Unknown"

async def async_setup_entry(
   hass: HomeAssistant,
   entry: ConfigEntry, 
   async_add_entities: AddEntitiesCallback,
) -> None:
   """Set up Eveus sensors."""
   updater = EveusUpdater(
       host=entry.data[CONF_HOST],
       username=entry.data[CONF_USERNAME],
       password=entry.data[CONF_PASSWORD],
       hass=hass,
   )

   sensors = [
       # Basic measurements
       NumericSensor(
           updater=updater,
           name="Voltage",
           key=ATTR_VOLTAGE,
           unit=UnitOfElectricPotential.VOLT,
           device_class=SensorDeviceClass.VOLTAGE,
           icon="mdi:lightning-bolt",
           precision=0
       ),
       NumericSensor(
           updater=updater,
           name="Current", 
           key=ATTR_CURRENT,
           unit=UnitOfElectricCurrent.AMPERE,
           device_class=SensorDeviceClass.CURRENT,
           icon="mdi:current-ac",
           precision=1
       ),
       NumericSensor(
           updater=updater,
           name="Power",
           key=ATTR_POWER,
           unit=UnitOfPower.WATT,
           device_class=SensorDeviceClass.POWER,
           icon="mdi:flash",
           precision=0
       ),
       NumericSensor(
           updater=updater,
           name="Current Set",
           key=ATTR_CURRENT_SET,
           unit=UnitOfElectricCurrent.AMPERE,
           device_class=SensorDeviceClass.CURRENT,
           icon="mdi:current-ac",
           precision=0
       ),
       
       # Energy sensors
       EnergySensor(updater, "Session Energy", ATTR_SESSION_ENERGY),
       EnergySensor(updater, "Total Energy", ATTR_TOTAL_ENERGY),
       EnergySensor(updater, "Counter A Energy", ATTR_COUNTER_A_ENERGY),
       EnergySensor(updater, "Counter B Energy", ATTR_COUNTER_B_ENERGY),

       # Cost sensors
       NumericSensor(
           updater=updater,
           name="Counter A Cost",
           key=ATTR_COUNTER_A_COST,
           unit="₴",
           icon="mdi:currency-uah",
           precision=0
       ),
       NumericSensor(
           updater=updater,
           name="Counter B Cost", 
           key=ATTR_COUNTER_B_COST,
           unit="₴",
           icon="mdi:currency-uah",
           precision=0
       ),

       # Temperature sensors
       NumericSensor(
           updater=updater,
           name="Box Temperature",
           key=ATTR_TEMPERATURE_BOX,
           unit=UnitOfTemperature.CELSIUS,
           device_class=SensorDeviceClass.TEMPERATURE,
           icon="mdi:thermometer",
           precision=0
       ),
       NumericSensor(
           updater=updater,
           name="Plug Temperature",
           key=ATTR_TEMPERATURE_PLUG,
           unit=UnitOfTemperature.CELSIUS,
           device_class=SensorDeviceClass.TEMPERATURE,
           icon="mdi:thermometer-high",
           precision=0
       ),

       # Battery voltage
       NumericSensor(
           updater=updater,
           name="Battery Voltage",
           key=ATTR_BATTERY_VOLTAGE,
           unit=UnitOfElectricPotential.VOLT,
           device_class=SensorDeviceClass.VOLTAGE,
           icon="mdi:battery",
           precision=1
       ),

       # State sensors
       StateSensor(updater, "State", ATTR_STATE, CHARGING_STATES),
       StateSensor(updater, "Substate", ATTR_SUBSTATE, NORMAL_SUBSTATES),
       EveusGroundSensor(updater),

       # Time sensors
       NumericSensor(
           updater=updater,
           name="Session Time",
           key=ATTR_SESSION_TIME,
           unit=UnitOfTime.SECONDS,
           device_class=SensorDeviceClass.DURATION,
           icon="mdi:timer",
           precision=0
       ),

       # Custom sensors
       EVSocKwhSensor(updater),
       EVSocPercentSensor(updater),
       TimeToTargetSocSensor(updater),
   ]

if "entities" not in hass.data[DOMAIN][entry.entry_id]:
       hass.data[DOMAIN][entry.entry_id]["entities"] = {}

   hass.data[DOMAIN][entry.entry_id]["entities"]["sensor"] = {
       sensor.unique_id: sensor for sensor in sensors
   }

   async_add_entities(sensors)

class EVSocKwhSensor(BaseEveusSensor):
   """EV State of Charge energy sensor."""
   _attr_device_class = SensorDeviceClass.ENERGY
   _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
   _attr_icon = "mdi:battery-charging"
   _attr_suggested_display_precision = 0
   _attr_state_class = SensorStateClass.TOTAL

   def __init__(self, updater: EveusUpdater) -> None:
       """Initialize the sensor."""
       super().__init__(updater)
       self._attr_name = "SOC Energy"
       self._attr_unique_id = f"{updater._host}_soc_kwh"

   @property
   def native_value(self) -> float | None:
       """Calculate and return state of charge in kWh."""
       try:
           initial_soc = float(self.hass.states.get("input_number.ev_initial_soc").state)
           max_capacity = float(self.hass.states.get("input_number.ev_battery_capacity").state)
           energy_charged = float(self._updater.data.get("IEM1", 0))
           correction = float(self.hass.states.get("input_number.ev_soc_correction").state)

           if initial_soc < 0 or initial_soc > 100 or max_capacity <= 0:
               return None

           initial_kwh = (initial_soc / 100) * max_capacity
           efficiency = (1 - correction / 100)
           charged_kwh = energy_charged * efficiency
           total_kwh = initial_kwh + charged_kwh
           
           return round(max(0, min(total_kwh, max_capacity)), 2)
       except (TypeError, ValueError, AttributeError):
           return None

class EVSocPercentSensor(BaseEveusSensor):
   """EV State of Charge percentage sensor."""
   _attr_device_class = SensorDeviceClass.BATTERY
   _attr_native_unit_of_measurement = "%"
   _attr_icon = "mdi:battery-charging"
   _attr_state_class = SensorStateClass.MEASUREMENT
   _attr_suggested_display_precision = 0

   def __init__(self, updater: EveusUpdater) -> None:
       """Initialize the sensor."""
       super().__init__(updater)
       self._attr_name = "SOC Percent"
       self._attr_unique_id = f"{updater._host}_soc_percent"

   @property
   def native_value(self) -> float | None:
       """Return the state of charge percentage."""
       try:
           soc_kwh = float(self.hass.states.get("sensor.eveus_ev_charger_soc_energy").state)
           max_capacity = float(self.hass.states.get("input_number.ev_battery_capacity").state)
           
           if soc_kwh >= 0 and max_capacity > 0:
               percentage = round((soc_kwh / max_capacity * 100), 0)
               return max(0, min(percentage, 100))
           return None
       except (TypeError, ValueError, AttributeError):
           return None

class TimeToTargetSocSensor(BaseEveusSensor):
   """Time to target SOC sensor."""
   _attr_icon = "mdi:timer"

   def __init__(self, updater: EveusUpdater) -> None:
       """Initialize the sensor."""
       super().__init__(updater)
       self._attr_name = "Time to Target"
       self._attr_unique_id = f"{updater._host}_time_to_target"

   @property
   def native_value(self) -> str:
       """Calculate and return time to target SOC."""
       try:
           if self._updater.data.get(ATTR_STATE) != 4:
               return "Not charging"

           current_soc = float(self.hass.states.get("sensor.eveus_ev_charger_soc_percent").state)
           target_soc = float(self.hass.states.get("input_number.ev_target_soc").state)
           
           if current_soc >= target_soc:
               return "Target reached"

           power_meas = float(self._updater.data.get(ATTR_POWER, 0))
           if power_meas < 100:
               return "Insufficient power"

           battery_capacity = float(self.hass.states.get("input_number.ev_battery_capacity").state)
           correction = float(self.hass.states.get("input_number.ev_soc_correction").state)

           remaining_kwh = (target_soc - current_soc) * battery_capacity / 100
           efficiency = (1 - correction / 100)
           power_kw = power_meas * efficiency / 1000
           total_minutes = round((remaining_kwh / power_kw * 60), 0)

           if total_minutes < 1:
               return "Less than 1m"

           days = int(total_minutes // 1440)
           hours = int((total_minutes % 1440) // 60)
           minutes = int(total_minutes % 60)

           if days > 0:
               return f"{days}d {hours}h {minutes}m"
           elif hours > 0:
               return f"{hours}h {minutes}m"
           return f"{minutes}m"

       except (TypeError, ValueError, AttributeError):
           return None
