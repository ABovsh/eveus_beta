"""Energy-related sensors."""
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfPower,
)

from .base import BaseNumericSensor

class EveusEnergySensor(BaseNumericSensor):
    """Base energy sensor."""
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 1

class EveusVoltageSensor(BaseNumericSensor):
    """Voltage sensor implementation."""
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:lightning-bolt"
    _attr_suggested_display_precision = 0

    def get_value_from_state(self) -> float:
        """Get voltage value."""
        return self._client.state.voltage

class EveusCurrentSensor(BaseNumericSensor):
    """Current sensor implementation."""
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:current-ac"
    
    def get_value_from_state(self) -> float:
        """Get current value."""
        return self._client.state.current

class EveusPowerSensor(BaseNumericSensor):
    """Power sensor implementation."""
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:flash"
    
    def get_value_from_state(self) -> float:
        """Get power value."""
        return self._client.state.power
