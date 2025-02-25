# Eveus EV Charger Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
![Version](https://img.shields.io/badge/version-1.2.0-blue)
![Stability](https://img.shields.io/badge/stability-stable-green)

This custom integration provides comprehensive monitoring and control of Eveus EV chargers in Home Assistant, featuring advanced state tracking, current control, energy monitoring, and intelligent State of Charge calculation.

## Features

### 🔌 Basic Monitoring
- Real-time voltage, current, and power monitoring
- Session and total energy tracking
- Temperature monitoring (box and plug)
- Ground connection safety monitoring
- Battery voltage monitoring
- Energy counters with cost tracking (in ₴)

### 🚗 Advanced EV Features
- Accurate State of Charge monitoring (kWh and percentage)
- Dynamic time-to-target calculation
- Charging efficiency calculation
- Comprehensive session time tracking
- Automatic error recovery with exponential backoff

### 🎮 Control Features
- Dynamic charging current control (8-16A or 8-32A based on model)
- Start/Stop charging control
- One charge mode support
- Counter reset functionality
- Current adjustment with safety limits

### 📊 Network Resilience
- Connection quality monitoring 
- Automatic retry with exponential backoff
- Session state caching for stability
- Detailed error tracking and recovery
- Optimized polling frequency based on charging state

## Prerequisites

### Required Helper Entities
Before installing the integration, you must create these helper entities in Home Assistant:

<details>
<summary><b>Click to expand helper entity setup instructions</b></summary>

1. Go to Settings → Devices & Services → Helpers
2. Click the "+ CREATE HELPER" button
3. Choose "Number"
4. Create each of these helpers with the exact input_number names:

```yaml
input_number:
  ev_battery_capacity:
    name: "EV Battery Capacity"
    min: 10
    max: 160
    step: 1
    unit_of_measurement: "kWh"
    mode: slider      # Optional but recommended
    icon: mdi:car-battery
    # Initial value should match your EV's battery capacity

  ev_initial_soc:
    name: "Initial EV State of Charge"
    min: 0
    max: 100
    step: 1
    unit_of_measurement: "%"
    mode: slider      # Optional but recommended
    icon: mdi:battery-charging-40
    # Set this before each charging session

  ev_soc_correction:
    name: "Charging Efficiency Loss"
    min: 0
    max: 10
    step: 0.1
    initial: 7.5     # Default efficiency loss
    unit_of_measurement: "%"
    mode: slider      # Optional but recommended
    icon: mdi:chart-bell-curve
    # Adjust based on your observed charging efficiency

  ev_target_soc:
    name: "Target SOC"
    min: 80
    max: 100
    step: 10
    initial: 80      # Default target
    unit_of_measurement: "%"
    mode: slider      # Optional but recommended
    icon: mdi:battery-charging-high
    # Adjust based on your charging needs
```

Alternatively, you can add these helpers via YAML by adding the above configuration to your `configuration.yaml`.
</details>

> **Important**: The integration will verify these helpers exist during setup and display an error if any are missing or incorrectly configured.

## Installation

### Method 1: HACS (Recommended)
1. Add this repository to HACS as a custom repository:
   ```
   Repository: https://github.com/ABovsh/eveus
   Category: Integration
   ```
2. Click Install
3. Restart Home Assistant

### Method 2: Manual Installation
1. Download the repository
2. Copy the `custom_components/eveus` directory to your Home Assistant's `custom_components` folder
3. Restart Home Assistant

## Configuration

### Initial Setup
1. Create all required helper entities as described in Prerequisites
2. Go to Configuration → Integrations
3. Click "+ Add Integration"
4. Search for "Eveus"
5. Enter the following details:
   - IP Address
   - Username
   - Password
   - Charger Model (16A or 32A)

## Troubleshooting

### Advanced Debugging

If you're experiencing issues with the SOC calculations or other sensors, follow these debugging steps:

#### 1. Enable Enhanced Logging

Add the following to your `configuration.yaml` file:

```yaml
logger:
  default: info
  logs:
    custom_components.eveus.ev_sensors: debug
    custom_components.eveus.utils: debug
    custom_components.eveus.sensor: debug
    custom_components.eveus: warning
```

Restart Home Assistant and check the logs for detailed information about sensor calculations.

#### 2. Use the Diagnostic Template

Copy and paste this template into Developer Tools > Template to get a comprehensive diagnostic report:

```yaml
{# Debug template for Eveus SOC Sensors #}
{% set debug_data = {
    'inputs': {
        'initial_soc': states('input_number.ev_initial_soc'),
        'battery_capacity': states('input_number.ev_battery_capacity'),
        'soc_correction': states('input_number.ev_soc_correction'),
        'target_soc': states('input_number.ev_target_soc')
    },
    'sensors': {
        'iem1': states('sensor.eveus_ev_charger_counter_a_energy'),
        'soc_energy': states('sensor.eveus_ev_charger_soc_energy'),
        'soc_percent': states('sensor.eveus_ev_charger_soc_percent'),
        'time_to_target': states('sensor.eveus_ev_charger_time_to_target_soc'),
        'power': states('sensor.eveus_ev_charger_power')
    }
} %}

{# Calculation Preparation #}
{% set initial_soc       = debug_data.inputs.initial_soc|float(0) %}
{% set battery_capacity  = debug_data.inputs.battery_capacity|float(0) %}
{% set soc_correction    = debug_data.inputs.soc_correction|float(0) %}
{% set energy_charged    = debug_data.sensors.iem1|float(0) %}

{# Validity Check #}
{% set input_valid = (
    initial_soc != 0 and
    battery_capacity != 0 and
    energy_charged != 'unknown' and
    energy_charged != 'unavailable'
) %}

{# Calculations #}
{% if input_valid %}
  {% set initial_kwh = (initial_soc / 100) * battery_capacity %}
  {% set efficiency  = (1 - soc_correction / 100) %}
  {% set charged_kwh = energy_charged * efficiency %}
  {% set total_kwh   = initial_kwh + charged_kwh %}

  {% set soc_energy  = total_kwh|round(2) %}
  {% set soc_percent = ((total_kwh / battery_capacity) * 100)|round(0) %}
{% else %}
  {% set soc_energy  = 'Cannot calculate - missing inputs' %}
  {% set soc_percent = 'Cannot calculate - missing inputs' %}
{% endif %}

### Eveus SOC Sensor Debug Report ###

## Required Input Entities ##
{% for name, value in debug_data.inputs.items() %}
- input_number.ev_{{ name }}: {{ value }}
{% endfor %}

## Sensor Values ##
{% for name, value in debug_data.sensors.items() %}
- {{ name }}: {{ value }}
{% endfor %}

## Entity Existence Check ##
{% set check_entities = [
  'input_number.ev_initial_soc',
  'input_number.ev_battery_capacity',
  'input_number.ev_soc_correction',
  'input_number.ev_target_soc',
  'sensor.eveus_ev_charger_counter_a_energy',
  'sensor.eveus_ev_charger_power'
] %}
{% for entity_id in check_entities %}
- {{ entity_id }}: {{ states(entity_id) != 'unknown' and states(entity_id) != 'unavailable' }}
{% endfor %}

## Expected Values ##
- Expected SOC Energy: {{ soc_energy }}
- Expected SOC Percent: {{ soc_percent }}

## Calculation Details ##
{% if input_valid %}
Initial SOC: {{ initial_soc }}%
Battery Capacity: {{ battery_capacity }} kWh
Efficiency Correction: {{ soc_correction }}%
Energy Charged: {{ energy_charged }} kWh
Initial Energy: {{ initial_kwh }} kWh
Efficiency Factor: {{ efficiency }}
Charged Energy (with efficiency): {{ charged_kwh }} kWh
Total Energy: {{ total_kwh }} kWh
{% else %}
Cannot perform calculations due to missing inputs.
{% endif %}
```

#### 3. Common Issues and Solutions

| Issue | Possible Solution |
|-------|-------------------|
| SOC sensors show "unknown" | Verify all required helper entities are created with exact names |
| "Missing input entity" error | Check that all input_number entities exist and have valid values |
| Automation errors | Update entity names in automations to match integration's naming pattern (eveus_ev_charger_*) |
| Connection failures | Verify network connectivity, check IP address, username, and password |
| Incorrect SOC calculations | Set initial SOC to match your EV's current charge level |

#### 4. Reset Procedure

If you encounter persistent issues:
1. Remove the integration
2. Restart Home Assistant
3. Delete any remaining eveus entities (if any)
4. Add the integration again
5. Recreate any missing input_number entities

## Creating Automations and Controls

### Example Automations

<details>
<summary><b>Set charging current based on solar production</b></summary>

```yaml
automation:
  - alias: "Set Eveus charging current based on solar production"
    description: "Adjust EV charging current based on available solar power"
    trigger:
      - platform: state
        entity_id: sensor.solar_power
        for:
          seconds: 30
    condition:
      - condition: state
        entity_id: switch.eveus_ev_charger_stop_charging
        state: "on"
    action:
      - service: number.set_value
        target:
          entity_id: number.eveus_ev_charger_charging_current
        data:
          # Calculate optimal current based on solar production
          value: >
            {% set solar_power = states('sensor.solar_power')|float(0) %}
            {% set voltage = states('sensor.eveus_ev_charger_voltage')|float(230) %}
            {% set max_current = 16 %}
            {% set calculated_current = (solar_power / voltage)|int %}
            {% if calculated_current < 7 %}
              {% set current = 7 %}
            {% elif calculated_current > max_current %}
              {% set current = max_current %}
            {% else %}
              {% set current = calculated_current %}
            {% endif %}
            {{ current }}
```
</details>

<details>
<summary><b>Notify when charging complete</b></summary>

```yaml
automation:
  - alias: "Notify when EV charging complete"
    description: "Send notification when EV reaches target SOC"
    trigger:
      - platform: numeric_state
        entity_id: sensor.eveus_ev_charger_soc_percent
        above: input_number.ev_target_soc
    condition:
      - condition: state
        entity_id: sensor.eveus_ev_charger_state
        state: "Charging"
    action:
      - service: notify.mobile_app
        data:
          title: "EV Charging Complete"
          message: >
            Your EV has reached {{ states('sensor.eveus_ev_charger_soc_percent') }}% 
            ({{ states('sensor.eveus_ev_charger_soc_energy') }} kWh).
            Total energy used: {{ states('sensor.eveus_ev_charger_session_energy') }} kWh.
      - service: switch.turn_off
        target:
          entity_id: switch.eveus_ev_charger_stop_charging
```
</details>

## Support and Contributions

- For bugs and feature requests, please open an issue on GitHub.
- Contributions to improve the integration are welcome! Please submit a pull request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
