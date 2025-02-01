"""Data models for Eveus."""
from dataclasses import dataclass
from typing import Any, Optional

@dataclass
class DeviceState:
    """Device state information."""
    state: int
    substate: int
    enabled: bool
    voltage: float
    current: float
    power: float
    session_energy: float
    total_energy: float
    temperature_box: float
    temperature_plug: float
    current_set: int
    ground: bool
    battery_voltage: float
    system_time: int
    counter_a_energy: float
    counter_b_energy: float
    counter_a_cost: float
    counter_b_cost: float
    session_time: int
    one_charge: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeviceState":
        """Create instance from API response."""
        return cls(
            state=data.get("state", 0),
            substate=data.get("subState", 0),
            enabled=data.get("evseEnabled", 0) == 1,
            voltage=float(data.get("voltMeas1", 0)),
            current=float(data.get("curMeas1", 0)),
            power=float(data.get("powerMeas", 0)),
            session_energy=float(data.get("sessionEnergy", 0)),
            total_energy=float(data.get("totalEnergy", 0)),
            temperature_box=float(data.get("temperature1", 0)),
            temperature_plug=float(data.get("temperature2", 0)),
            current_set=int(data.get("currentSet", 0)),
            ground=data.get("ground", 0) == 1,
            battery_voltage=float(data.get("vBat", 0)),
            system_time=int(data.get("systemTime", 0)),
            counter_a_energy=float(data.get("IEM1", 0)),
            counter_b_energy=float(data.get("IEM2", 0)),
            counter_a_cost=float(data.get("IEM1_money", 0)),
            counter_b_cost=float(data.get("IEM2_money", 0)),
            session_time=int(data.get("sessionTime", 0)),
            one_charge=data.get("oneCharge", 0) == 1
        )
