"""Constants for the Eveus integration."""
from datetime import timedelta
from typing import Final

DOMAIN: Final = "eveus"
SCAN_INTERVAL = timedelta(seconds=30)

# Model constants
MODEL_16A: Final = "16A"
MODEL_32A: Final = "32A"
MODELS: Final = [MODEL_16A, MODEL_32A]
MODEL_MAX_CURRENT: Final = {
    MODEL_16A: 16,
    MODEL_32A: 32,
}
MIN_CURRENT: Final = 8

# Configuration
CONF_MODEL: Final = "model"

# API Attributes
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

# API Endpoints
API_ENDPOINT_MAIN: Final = "/main"
API_ENDPOINT_EVENT: Final = "/pageEvent"

# Command Parameters
CMD_EVSE_ENABLED: Final = "evseEnabled"
CMD_ONE_CHARGE: Final = "oneCharge" 
CMD_RESET_COUNTER: Final = "rstEM1"

# Error Handling
MAX_RETRIES: Final = 3
RETRY_DELAY: Final = 2
COMMAND_TIMEOUT: Final = 5
UPDATE_TIMEOUT: Final = 10
MIN_UPDATE_INTERVAL: Final = 2
MIN_COMMAND_INTERVAL: Final = 1

# Helper Entities
HELPER_EV_BATTERY_CAPACITY: Final = "input_number.ev_battery_capacity"
HELPER_EV_INITIAL_SOC: Final = "input_number.ev_initial_soc"
HELPER_EV_SOC_CORRECTION: Final = "input_number.ev_soc_correction"
HELPER_EV_TARGET_SOC: Final = "input_number.ev_target_soc"

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
