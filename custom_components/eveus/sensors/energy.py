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

class EveusCounterEnergySensor(EveusEnergySensor):
    """Base counter energy sensor."""
    _attr_icon = "mdi:counter"

class EveusCounterCostSensor(BaseNumericSensor):
    """Base counter cost sensor."""
    _attr_native_unit_of_measurement = "₴"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:currency-uah"
    _attr_suggested_display_precision = 0

class EveusCounterAEnergySensor(EveusCounterEnergySensor):
    """Counter A energy sensor."""
    
    def __init__(self, client) -> None:
        """Initialize the sensor."""
        super().__init__(client)
        self._attr_name = "Counter A Energy"
        self._attr_unique_id = f"{client._device_info.identifier}_counter_a_energy"

    def get_value_from_state(self) -> float:
        """Get counter A energy."""
        return self._client.state.counter_a_energy

class EveusCounterBEnergySensor(EveusCounterEnergySensor):
    """Counter B energy sensor."""
    
    def __init__(self, client) -> None:
        """Initialize the sensor."""
        super().__init__(client)
        self._attr_name = "Counter B Energy"
        self._attr_unique_id = f"{client._device_info.identifier}_counter_b_energy"

    def get_value_from_state(self) -> float:
        """Get counter B energy."""
        return self._client.state.counter_b_energy

class EveusCounterACostSensor(EveusCounterCostSensor):
    """Counter A cost sensor."""
    
    def __init__(self, client) -> None:
        """Initialize the sensor."""
        super().__init__(client)
        self._attr_name = "Counter A Cost"
        self._attr_unique_id = f"{client._device_info.identifier}_counter_a_cost"

    def get_value_from_state(self) -> float:
        """Get counter A cost."""
        return self._client.state.counter_a_cost

class EveusCounterBCostSensor(EveusCounterCostSensor):
    """Counter B cost sensor."""
    
    def __init__(self, client) -> None:
        """Initialize the sensor."""
        super().__init__(client)
        self._attr_name = "Counter B Cost"
        self._attr_unique_id = f"{client._device_info.identifier}_counter_b_cost"

    def get_value_from_state(self) -> float:
        """Get counter B cost."""
        return self._client.state.counter_b_cost
