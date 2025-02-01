"""Support for Eveus sensors."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Callable

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

class EveusDeviceBase:
    """Base class for Eveus devices."""

    def __init__(self, host: str) -> None:
        """Initialize the base device."""
        self._host = host

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._host)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": f"Eveus ({self._host})",
            "sw_version": getattr(self, "_updater", {}).data.get("verFWMain", "Unknown"),
            "hw_version": getattr(self, "_updater", {}).data.get("verHW", "Unknown"),
        }

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

class EveusUpdater:
    """Central data updater for Eveus system."""
    
    def __init__(
        self, 
        host: str, 
        username: str, 
        password: str, 
        hass: HomeAssistant
    ) -> None:
        """Initialize the updater."""
        self._host = host
        self._username = username
        self._password = password
        self._hass = hass
        self._data: dict = {}
        self._available = True
        self._session: aiohttp.ClientSession | None = None
        self._sensors: list = []
        self._update_task: asyncio.Task | None = None
        self._last_update = time.time()
        self._error_count = 0
        self._max_errors = 3
        self._update_lock = asyncio.Lock()

    def register_sensor(self, sensor: "EveusSensorBase") -> None:
        """Register a sensor for updates."""
        self._sensors.append(sensor)

    @property
    def data(self) -> dict:
        """Return current data."""
        return self._data

    @property
    def available(self) -> bool:
        """Return availability status."""
        return self._available

    @property
    def last_update(self) -> float:
        """Return last update timestamp."""
        return self._last_update

    async def async_start_updates(self) -> None:
        """Start the update loop."""
        if self._update_task is None:
            self._update_task = asyncio.create_task(self._update_loop())

    async def _update_loop(self) -> None:
        """Run the update loop."""
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
        """Get or create client session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10, connect=5)
            connector = aiohttp.TCPConnector(limit=1, force_close=True)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector
            )
        return self._session

    async def _update(self) -> None:
        """Update data from the device."""
        async with self._update_lock:
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
                            _LOGGER.error(
                                "Error updating sensor %s: %s",
                                sensor.name,
                                str(sensor_err)
                            )

            except Exception as err:
                self._error_count += 1
                self._available = self._error_count < self._max_errors
                _LOGGER.error("Error updating data: %s", str(err))

    async def async_shutdown(self) -> None:
        """Shut down the updater."""
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        if self._session and not self._session.closed:
            await self._session.close()

class EveusSensorBase(SensorEntity, RestoreEntity, EveusDeviceBase):
    """Base sensor class for Eveus sensors."""
    
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_registry_enabled_default = True
    _attr_entity_registry_visible_default = True

    def __init__(
        self,
        updater: EveusUpdater,
        name: str,
        key: str,
        device_class: SensorDeviceClass | None = None,
        native_unit: str | None = None,
        state_class: SensorStateClass | None = None,
        icon: str | None = None,
        precision: int = 2,
        entity_category: EntityCategory | None = None
    ) -> None:
        """Initialize the base sensor."""
        super().__init__(updater._host)
        self._updater = updater
        self._key = key
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
    def native_value(self) -> float | None:
        """Return the sensor value."""
        try:
            value = float(self._updater.data.get(self._key, 0))
            self._previous_value = value
            return round(value, self._attr_suggested_display_precision)
        except (TypeError, ValueError):
            return self._previous_value

    @property
    def available(self) -> bool:
        """Return availability status."""
        return self._updater.available

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return {
            "last_update": self._updater.last_update,
            "host": self._updater._host,
            **(
                {} if self._previous_value is None 
                else {"previous_value": self._previous_value}
            )
        }

    async def async_added_to_hass(self) -> None:
        """Handle entity added to hass."""
        await super().async_added_to_hass()
        if state := await self.async_get_last_state():
            if state.state not in ('unknown', 'unavailable'):
                self._previous_value = state.state
        await self._updater.async_start_updates()

class EveusStringSensor(SensorEntity, RestoreEntity):
    """Sensor class for string-based values."""
    
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_registry_enabled_default = True
    _attr_entity_registry_visible_default = True

    def __init__(
        self,
        updater: EveusUpdater,
        name: str,
        key: str,
        mapper: Callable[[dict], str],
        icon: str = None,
        entity_category: EntityCategory = None
    ):
        """Initialize the string sensor."""
        self._updater = updater
        self._key = key
        self._mapper = mapper
        self._previous_value = None
        self._attr_name = name
        self._attr_unique_id = f"{updater._host}_{name.lower().replace(' ', '_')}"
        self._attr_icon = icon
        self._attr_entity_category = entity_category
        updater.register_sensor(self)

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
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        try:
            value = self._mapper(self._updater.data)
            self._previous_value = value
            return value
        except (TypeError, ValueError, KeyError) as err:
            _LOGGER.debug("Error mapping value for %s: %s", self.name, str(err))
            return self._previous_value if self._previous_value else "Unknown"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._updater.available

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {
            "last_update": self._updater.last_update,
            "host": self._updater._host,
            **({} if self._previous_value is None else {"previous_value": self._previous_value})
        }

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        if state := await self.async_get_last_state():
            if state.state not in ('unknown', 'unavailable'):
                self._previous_value = state.state
        await self._updater.async_start_updates()
        
class EveusTimeSensor(EveusSensorBase):
    """Time duration sensor with formatted attribute."""
    
    def __init__(self, updater: EveusUpdater, name: str, key: str) -> None:
        """Initialize the time sensor."""
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
        """Return additional state attributes."""
        attrs = super().extra_state_attributes
        try:
            attrs["formatted_time"] = format_duration(int(self.native_value))
        except (TypeError, ValueError):
            attrs["formatted_time"] = "0m"
        return attrs

class EveusCounterSensor(EveusSensorBase):
    """Unified counter sensor for energy/cost."""
    
    def __init__(
        self,
        updater: EveusUpdater,
        counter_id: str,
        measurement: str,
        key: str
    ) -> None:
        """Initialize the counter sensor."""
        super().__init__(
            updater=updater,
            name=f"Counter {counter_id} {measurement}",
            key=key,
            device_class=(
                SensorDeviceClass.ENERGY if measurement == "Energy" else None
            ),
            native_unit=(
                UnitOfEnergy.KILO_WATT_HOUR if measurement == "Energy" else "₴"
            ),
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon=(
                "mdi:counter" if measurement == "Energy" else "mdi:currency-uah"
            ),
            precision=(1 if measurement == "Energy" else 0)
        )


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
            current = float(self.hass.states.get("sensor.eveus_ev_charger_soc_percent").state)
            target = float(self.hass.states.get("input_number.ev_target_soc").state)
            power = float(self._updater.data.get(ATTR_POWER, 0))
            capacity = float(self.hass.states.get("input_number.ev_battery_capacity").state)
            correction = float(self.hass.states.get("input_number.ev_soc_correction").state)

            remaining = (target - current) * capacity / 100
            power_kw = power * (1 - correction/100) / 1000
            
            if power_kw <= 0:
                return "-"

            return format_duration(int((remaining / power_kw) * 3600))

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
        # Numeric sensors
        EveusSensorBase(updater, "Voltage", ATTR_VOLTAGE,
                       SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT,
                       SensorStateClass.MEASUREMENT, "mdi:lightning-bolt", 0),
        
        EveusSensorBase(updater, "Current", ATTR_CURRENT,
                       SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE,
                       SensorStateClass.MEASUREMENT, "mdi:current-ac", 1),
        
        EveusSensorBase(updater, "Power", ATTR_POWER,
                       SensorDeviceClass.POWER, UnitOfPower.WATT,
                       SensorStateClass.MEASUREMENT, "mdi:flash", 0),

        # String-based state sensors
        EveusStringSensor(updater, "State", ATTR_STATE,
            mapper=lambda d: CHARGING_STATES.get(d.get(ATTR_STATE), "Unknown"),
            icon="mdi:information",
            entity_category=EntityCategory.DIAGNOSTIC
        ),
        
        EveusStringSensor(updater, "Substate", ATTR_SUBSTATE,
            mapper=lambda d: (
                ERROR_STATES.get(d.get(ATTR_SUBSTATE), "Unknown Error") 
                if d.get(ATTR_STATE) == 7 
                else NORMAL_SUBSTATES.get(d.get(ATTR_SUBSTATE), "Unknown State")
            ),
            icon="mdi:information",
            entity_category=EntityCategory.DIAGNOSTIC
        ),

        # Temperature sensors
        EveusSensorBase(updater, "Box Temperature", ATTR_TEMPERATURE_BOX,
                       SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS,
                       SensorStateClass.MEASUREMENT, "mdi:thermometer", 0),
        
        EveusSensorBase(updater, "Plug Temperature", ATTR_TEMPERATURE_PLUG,
                       SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS,
                       SensorStateClass.MEASUREMENT, "mdi:thermometer-high", 0),

        # Time-based sensors
        EveusTimeSensor(updater, "Session Time", ATTR_SESSION_TIME),

        # Counter sensors
        EveusCounterSensor(updater, "A", "Energy", ATTR_COUNTER_A_ENERGY),
        EveusCounterSensor(updater, "B", "Energy", ATTR_COUNTER_B_ENERGY),
        EveusCounterSensor(updater, "A", "Cost", ATTR_COUNTER_A_COST),
        EveusCounterSensor(updater, "B", "Cost", ATTR_COUNTER_B_COST),

        # Time to Target
        TimeToTargetSensor(updater)
    ]

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(entry.entry_id, {"entities": {}})
    hass.data[DOMAIN][entry.entry_id]["entities"]["sensor"] = {
        sensor.unique_id: sensor for sensor in sensors
    }

    async_add_entities(sensors)
