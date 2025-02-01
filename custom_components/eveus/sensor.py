"""Support for Eveus sensors."""
from __future__ import annotations

import logging
import asyncio
import time
from datetime import datetime
from typing import Any, Callable, Optional

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.components.text import TextEntity
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

#region Helper Functions
def format_duration(seconds: int) -> str:
    """Format duration in seconds to human-readable string."""
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60

    if days > 0:
        return f"{days}d {hours:02d}h {minutes:02d}m"
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"
#endregion

#region Core Components
class EveusUpdater:
    """Central data updater for Eveus system."""
    
    def __init__(self, host: str, username: str, password: str, hass: HomeAssistant) -> None:
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
        self._error_count = 0
        self._max_errors = 3

    def register_sensor(self, sensor: "EveusSensor") -> None:
        self._sensors.append(sensor)

    @property
    def data(self) -> dict:
        return self._data

    @property
    def available(self) -> bool:
        return self._available

    @property
    def last_update(self) -> float:
        return self._last_update

    async def async_start_updates(self) -> None:
        if self._update_task is None:
            self._update_task = asyncio.create_task(self._update_loop())

    async def _update_loop(self) -> None:
        while True:
            try:
                await self._update()
                await asyncio.sleep(SCAN_INTERVAL.total_seconds())
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Error in update loop: %s", str(err))
                await asyncio.sleep(SCAN_INTERVAL.total_seconds())

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10, connect=5)
            connector = aiohttp.TCPConnector(limit=1, force_close=True)
            self._session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return self._session

    async def _update(self) -> None:
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
                    except Exception as sensor_err:
                        _LOGGER.error("Error updating sensor %s: %s", sensor.name, str(sensor_err))

        except Exception as err:
            self._error_count += 1
            self._available = self._error_count < self._max_errors
            _LOGGER.error("Error updating data: %s", str(err))

    async def async_shutdown(self) -> None:
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        if self._session and not self._session.closed:
            await self._session.close()

class EveusSensor(SensorEntity, RestoreEntity):
    """Configurable base sensor class."""
    
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_registry_enabled_default = True
    _attr_entity_registry_visible_default = True

    def __init__(
        self,
        updater: EveusUpdater,
        name: str,
        key: str,
        device_class: SensorDeviceClass = None,
        native_unit: str = None,
        state_class: SensorStateClass = None,
        icon: str = None,
        precision: int = 2,
        mapper: Callable[[dict], Any] = None,
        entity_category: EntityCategory = None
    ):
        self._updater = updater
        self._key = key
        self._mapper = mapper
        self._previous_value = None
        self._attr_name = name
        self._attr_unique_id = f"{updater._host}_{name.lower().replace(' ', '_')}"
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = native_unit
        self._attr_state_class = state_class
        self._attr_icon = icon
        self._attr_suggested_display_precision = precision
        self._attr_entity_category = entity_category
        updater.register_sensor(self)

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._updater._host)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": f"Eveus ({self._updater._host})",
            "sw_version": self._updater.data.get("verFWMain", "Unknown"),
            "hw_version": self._updater.data.get("verHW", "Unknown"),
        }

    @property
    def native_value(self) -> Any:
        if self._mapper:
            return self._mapper(self._updater.data)
            
        try:
            value = float(self._updater.data.get(self._key, 0))
            self._previous_value = value
            return round(value, self._attr_suggested_display_precision)
        except (TypeError, ValueError):
            return self._previous_value

    @property
    def available(self) -> bool:
        return self._updater.available

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "last_update": self._updater.last_update,
            "host": self._updater._host,
            **({} if self._previous_value is None else {"previous_value": self._previous_value})
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if state := await self.async_get_last_state():
            if state.state not in ('unknown', 'unavailable'):
                self._previous_value = state.state
        await self._updater.async_start_updates()

#endregion

#region Specialized Components
class EveusTimeSensor(EveusSensor):
    """Time duration sensor with formatted attribute."""
    
    def __init__(self, updater: EveusUpdater, name: str, key: str):
        super().__init__(
            updater=updater,
            name=name,
            key=key,
            device_class=SensorDeviceClass.DURATION,
            native_unit=UnitOfTime.SECONDS,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:timer",
            precision=0
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = super().extra_state_attributes
        try:
            attrs["formatted_time"] = format_duration(int(self.native_value))
        except (TypeError, ValueError):
            attrs["formatted_time"] = "0m"
        return attrs

class EveusCounterSensor(EveusSensor):
    """Unified counter sensor for energy/cost."""
    
    def __init__(self, updater: EveusUpdater, counter_id: str, measurement: str, key: str):
        super().__init__(
            updater=updater,
            name=f"Counter {counter_id} {measurement}",
            key=key,
            device_class=SensorDeviceClass.ENERGY if measurement == "Energy" else None,
            native_unit=UnitOfEnergy.KILO_WATT_HOUR if measurement == "Energy" else "₴",
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon="mdi:counter" if measurement == "Energy" else "mdi:currency-uah",
            precision=1 if measurement == "Energy" else 0
        )

class EVSocSensor(EveusSensor):
    """State of Charge sensor with calculation logic."""
    
    def __init__(self, updater: EveusUpdater, is_percent: bool):
        unit = "%" if is_percent else UnitOfEnergy.KILO_WATT_HOUR
        super().__init__(
            updater=updater,
            name="SOC Percent" if is_percent else "SOC Energy",
            key="IEM1",
            device_class=SensorDeviceClass.BATTERY if is_percent else SensorDeviceClass.ENERGY,
            native_unit=unit,
            state_class=SensorStateClass.MEASUREMENT if is_percent else SensorStateClass.TOTAL,
            icon="mdi:battery-charging",
            precision=0
        )

    @property
    def native_value(self) -> float | None:
        try:
            params = {
                'initial': float(self.hass.states.get("input_number.ev_initial_soc").state),
                'capacity': float(self.hass.states.get("input_number.ev_battery_capacity").state),
                'charged': float(self._updater.data.get(self._key, 0)),
                'correction': float(self.hass.states.get("input_number.ev_soc_correction").state)
            }

            if params['initial'] < 0 or params['initial'] > 100 or params['capacity'] <= 0:
                return None

            efficiency = 1 - params['correction'] / 100
            initial_kwh = (params['initial'] / 100) * params['capacity']
            total_kwh = initial_kwh + (params['charged'] * efficiency)

            if "Percent" in self.name:
                return min(max(round((total_kwh / params['capacity']) * 100, 0), 0), 100)
            return round(max(0, min(total_kwh, params['capacity'])), 2)

        except (TypeError, ValueError, AttributeError):
            return None

class TimeToTargetSensor(TextEntity, RestoreEntity):
    """Time remaining to target SOC sensor."""
    
    _attr_icon = "mdi:timer"
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, updater: EveusUpdater):
        self._updater = updater
        self._attr_name = "Time to Target"
        self._attr_unique_id = f"{updater._host}_time_to_target"

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._updater._host)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus"
        }

    @property
    def native_value(self) -> str:
        try:
            params = {
                'current': float(self.hass.states.get("sensor.eveus_ev_charger_soc_percent").state),
                'target': float(self.hass.states.get("input_number.ev_target_soc").state),
                'power': float(self._updater.data.get(ATTR_POWER, 0)),
                'capacity': float(self.hass.states.get("input_number.ev_battery_capacity").state),
                'correction': float(self.hass.states.get("input_number.ev_soc_correction").state)
            }

            remaining_kwh = (params['target'] - params['current']) * params['capacity'] / 100
            power_kw = params['power'] * (1 - params['correction']/100) / 1000
            
            return "-" if power_kw <= 0 else format_duration(
                int((remaining_kwh / power_kw) * 3600)
            )

        except (TypeError, ValueError, AttributeError):
            return "-"

    @property
    def available(self) -> bool:
        return self._updater.available

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "last_update": self._updater.last_update,
            "host": self._updater._host
        }
#endregion

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up all Eveus sensors."""
    updater = EveusUpdater(
        host=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        hass=hass,
    )

    sensors = [
        # Basic measurements
        EveusSensor(updater, "Voltage", ATTR_VOLTAGE,
                   SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT,
                   SensorStateClass.MEASUREMENT, "mdi:lightning-bolt", 0),
        
        EveusSensor(updater, "Current", ATTR_CURRENT,
                   SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE,
                   SensorStateClass.MEASUREMENT, "mdi:current-ac", 1),
        
        EveusSensor(updater, "Power", ATTR_POWER,
                   SensorDeviceClass.POWER, UnitOfPower.WATT,
                   SensorStateClass.MEASUREMENT, "mdi:flash", 0),

        # Diagnostic sensors
        EveusSensor(updater, "State", ATTR_STATE,
                   mapper=lambda d: CHARGING_STATES.get(d.get(ATTR_STATE), "Unknown"),
                   entity_category=EntityCategory.DIAGNOSTIC),
        
        EveusSensor(updater, "Substate", ATTR_SUBSTATE,
                   mapper=lambda d: (
                       ERROR_STATES.get(d.get(ATTR_SUBSTATE), "Unknown Error") 
                       if d.get(ATTR_STATE) == 7 
                       else NORMAL_SUBSTATES.get(d.get(ATTR_SUBSTATE), "Unknown State")
                   ), entity_category=EntityCategory.DIAGNOSTIC),

        # Temperature sensors
        EveusSensor(updater, "Box Temperature", ATTR_TEMPERATURE_BOX,
                   SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS,
                   SensorStateClass.MEASUREMENT, "mdi:thermometer", 0),
        
        EveusSensor(updater, "Plug Temperature", ATTR_TEMPERATURE_PLUG,
                   SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS,
                   SensorStateClass.MEASUREMENT, "mdi:thermometer-high", 0),

        # Time-based sensors
        EveusTimeSensor(updater, "Session Time", ATTR_SESSION_TIME),

        # Counter sensors
        EveusCounterSensor(updater, "A", "Energy", ATTR_COUNTER_A_ENERGY),
        EveusCounterSensor(updater, "B", "Energy", ATTR_COUNTER_B_ENERGY),
        EveusCounterSensor(updater, "A", "Cost", ATTR_COUNTER_A_COST),
        EveusCounterSensor(updater, "B", "Cost", ATTR_COUNTER_B_COST),

        # SOC sensors
        EVSocSensor(updater, is_percent=False),
        EVSocSensor(updater, is_percent=True),

        # Time to Target
        TimeToTargetSensor(updater)
    ]

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(entry.entry_id, {"entities": {}})
    hass.data[DOMAIN][entry.entry_id]["entities"]["sensor"] = {
        sensor.unique_id: sensor for sensor in sensors
    }

    async_add_entities(sensors)
