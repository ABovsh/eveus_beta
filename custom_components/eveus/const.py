"""Constants for Eveus integration."""
from datetime import timedelta

DOMAIN = "eveus"
SCAN_INTERVAL = timedelta(seconds=30)

MODEL_16A = "16A"
MODEL_32A = "32A"
MODELS = [MODEL_16A, MODEL_32A]
MODEL_MAX_CURRENT = {
    MODEL_16A: 16,
    MODEL_32A: 32,
}
MIN_CURRENT = 8

CONF_MODEL = "model"

REQUIRED_HELPERS = [
    "input_number.ev_battery_capacity",
    "input_number.ev_initial_soc",
    "input_number.ev_soc_correction",
    "input_number.ev_target_soc",
]

CHARGING_STATES = {
    0: "Startup",
    1: "System Test",
    2: "Standby",
    3: "Connected",
    4: "Charging",
    5: "Charge Complete",
    6: "Paused",
    7: "Error"
}

ERROR_STATES = {
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

NORMAL_SUBSTATES = {
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
