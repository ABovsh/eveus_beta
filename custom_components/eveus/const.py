# File: custom_components/eveus/const.py
"""Constants for the Eveus integration."""
from datetime import timedelta
from typing import Final, Set

DOMAIN: Final = "eveus"

# Update intervals
UPDATE_INTERVAL_CHARGING: Final = timedelta(seconds=10)
UPDATE_INTERVAL_IDLE: Final = timedelta(seconds=60)
UPDATE_INTERVAL_ERROR: Final = timedelta(seconds=30)

# Configuration
CONF_MODEL: Final = "model"

# Temperature thresholds
TEMP_WARNING_BOX: Final = 60
TEMP_CRITICAL_BOX: Final = 80
TEMP_WARNING_PLUG: Final = 50
TEMP_CRITICAL_PLUG: Final = 65

# Battery voltage thresholds
BATTERY_VOLTAGE_MIN: Final = 2.0
BATTERY_VOLTAGE_MAX: Final = 3.3
BATTERY_VOLTAGE_WARNING: Final = 2.7
BATTERY_VOLTAGE_CRITICAL: Final = 2.5

# API rate limiting
MIN_COMMAND_INTERVAL: Final = 1.0  # seconds
MAX_COMMANDS_PER_MINUTE: Final = 30
COMMAND_COOLDOWN: Final = 2.0  # seconds

# Error handling
MAX_RETRIES: Final = 3
RETRY_BASE_DELAY: Final = 1.0  # seconds
MAX_RETRY_DELAY: Final = 30.0  # seconds
COMMAND_TIMEOUT: Final = 5.0
STATE_CACHE_TTL: Final = 2.0  # seconds

# API Endpoints
API_ENDPOINT_MAIN: Final = "/main"
API_ENDPOINT_EVENT: Final = "/pageEvent"

# Required helper entities
HELPER_EV_BATTERY_CAPACITY: Final = "input_number.ev_battery_capacity"
HELPER_EV_INITIAL_SOC: Final = "input_number.ev_initial_soc"
HELPER_EV_SOC_CORRECTION: Final = "input_number.ev_soc_correction"
HELPER_EV_TARGET_SOC: Final = "input_number.ev_target_soc"

# Command Parameters
CMD_EVSE_ENABLED: Final = "evseEnabled"
CMD_ONE_CHARGE: Final = "oneCharge"
CMD_RESET_COUNTER: Final = "rstEM1"

# State attributes
ATTR_VOLTAGE: Final = "voltMeas1"
ATTR_CURRENT: Final = "curMeas1"
ATTR_POWER: Final = "powerMeas"
ATTR_SESSION_ENERGY: Final = "sessionEnergy"
ATTR_TOTAL_ENERGY: Final = "totalEnergy"
ATTR_SESSION_TIME: Final = "sessionTime"
ATTR_STATE: Final = "state"
ATTR_SUBSTATE: Final = "subState"
ATTR_CURRENT_SET: Final = "currentSet"
ATTR_ENABLED: Final = "evseEnabled"
ATTR_TEMPERATURE_BOX: Final = "temperature1"
ATTR_TEMPERATURE_PLUG: Final = "temperature2"
ATTR_SYSTEM_TIME: Final = "systemTime"
ATTR_COUNTER_A_ENERGY: Final = "IEM1"
ATTR_COUNTER_B_ENERGY: Final = "IEM2"
ATTR_COUNTER_A_COST: Final = "IEM1_money"
ATTR_COUNTER_B_COST: Final = "IEM2_money"
ATTR_GROUND: Final = "ground"
ATTR_BATTERY_VOLTAGE: Final = "vBat"

# State Mappings
CHARGING_STATES: Final = {
    0: "Startup",
    1: "System Test",
    2: "Standby",
    3: "Connected",
    4: "Charging",
    5: "Charge Complete",
    6: "Paused",
    7: "Error"
}

ERROR_STATES: Final = {
    0: "No Error",
    1: "Grounding Error",
    2: "Current Leak High",
    3: "Relay Error",
    4: "Current Leak Low",
    5: "Box Overheat",
    6: "Plug Overheat",
    7: "Pilot Error",
    8: "Low Voltage",
    9: "Diode Error",
    10: "Overcurrent",
    11: "Interface Timeout",
    12: "Software Failure",
    13: "GFCI Test Failure",
    14: "High Voltage"
}

NORMAL_SUBSTATES: Final = {
    0: "No Limits",
    1: "Limited by User",
    2: "Energy Limit",
    3: "Time Limit",
    4: "Cost Limit",
    5: "Schedule 1 Limit",
    6: "Schedule 1 Energy Limit",
    7: "Schedule 2 Limit",
    8: "Schedule 2 Energy Limit",
    9: "Waiting for Activation",
    10: "Paused by Adaptive Mode"
}

# Required state fields validation
REQUIRED_STATE_FIELDS: Final[set[str]] = {
    "evseEnabled",
    "state",
    "subState", 
    "currentSet",
    "curDesign",
    "ground",
    "temperature1",
    "temperature2",
    "powerMeas",
    "voltMeas1",
    "curMeas1",
    "sessionEnergy",
    "totalEnergy",
    "sessionTime",
    "IEM1",
    "IEM2",
    "IEM1_money",
    "IEM2_money",
    "vBat"
}

# Persistent session storage
PERSISTENT_SESSION_DATA: Final[set[str]] = {
    "sessionEnergy",
    "sessionTime",
    "sessionMoney",
    "totalEnergy",
    "IEM1",
    "IEM2",
    "IEM1_money",
    "IEM2_money"
}
