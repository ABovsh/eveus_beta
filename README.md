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
- Energy counters with cost tracking (in UAH)

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

### Available Entities

<details>
<summary><b>Click to see all available sensors and controls</b></summary>

#### Basic Sensors:
| Entity | Name | Description | Unit |
|--------|------|-------------|------|
| sensor.eveus_ev_charger_voltage | Voltage | Current voltage | V |
| sensor.eveus_ev_charger_current | Current | Charging current | A |
| sensor.eveus_ev_charger_power | Power | Charging power | W |
| sensor.eveus_ev_charger_session_energy | Session Energy | Energy used in session | kWh |
| sensor.eveus_ev_charger_total_energy | Total Energy | Total energy delivered | kWh |
| sensor.eveus_ev_charger_counter_a_energy | Counter A Energy | Energy counter A | kWh |
| sensor.eveus_ev_charger_counter_b_energy | Counter B Energy | Energy counter B | kWh |
| sensor.eveus_ev_charger_counter_a_cost | Counter A Cost | Cost counter A | ₴ |
| sensor.eveus_ev_charger_counter_b_cost | Counter B Cost | Cost counter B | ₴ |

#### SOC Sensors:
| Entity | Name | Description | Unit |
|--------|------|-------------|------|
| sensor.eveus_ev_charger_soc_energy | SOC Energy | Current battery charge | kWh |
| sensor.eveus_ev_charger_soc_percent | SOC Percent | Current battery charge | % |
| sensor.eveus_ev_charger_time_to_target | Time to Target | Time until target SOC | - |

#### Diagnostic Sensors:
| Entity | Name | Description |
|--------|------|-------------|
| sensor.eveus_ev_charger_state | State | Charger state |
| sensor.eveus_ev_charger_substate | Substate | Detailed status |
| sensor.eveus_ev_charger_ground | Ground | Ground connection status |
| sensor.eveus_ev_charger_connection_quality | Connection Quality | Network connection quality |

#### Temperature Sensors:
| Entity | Name | Description | Unit |
|--------|------|-------------|------|
| sensor.eveus_ev_charger_box_temperature | Box Temperature | Internal temperature | °C |
| sensor.eveus_ev_charger_plug_temperature | Plug Temperature | Plug temperature | °C |

#### Rate Sensors:
| Entity | Name | Description | Unit |
|--------|------|-------------|------|
| sensor.eveus_ev_charger_primary_rate_cost | Primary Rate Cost | Primary rate cost | UAH/kWh |
| sensor.eveus_ev_charger_active_rate_cost | Active Rate Cost | Currently active rate | UAH/kWh |
| sensor.eveus_ev_charger_rate_2_cost | Rate 2 Cost | Secondary rate cost | UAH/kWh |
| sensor.eveus_ev_charger_rate_3_cost | Rate 3 Cost | Tertiary rate cost | UAH/kWh |
| sensor.eveus_ev_charger_rate_2_status | Rate 2 Status | Rate 2 enabled status | - |
| sensor.eveus_ev_charger_rate_3_status | Rate 3 Status | Rate 3 enabled status | - |

#### Controls:
| Entity | Name | Description |
|--------|------|-------------|
| number.eveus_ev_charger_charging_current | Charging Current | Control charging current (8-16A/32A) |
| switch.eveus_ev_charger_stop_charging | Stop Charging | Control charging state |
| switch.eveus_ev_charger_one_charge | One Charge | Enable one charge mode |
| switch.eveus_ev_charger_reset_counter_a | Reset Counter A | Reset energy counter A |
</details>

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

### Dashboard Card Examples

<details>
<summary><b>EV Charging Status Card</b></summary>

```yaml
type: vertical-stack
cards:
  - type: entities
    title: EV Charging Status
    entities:
      - entity: sensor.eveus_ev_charger_state
      - entity: sensor.eveus_ev_charger_power
      - entity: sensor.eveus_ev_charger_current
      - entity: number.eveus_ev_charger_charging_current
        name: Current Limit
      - entity: sensor.eveus_ev_charger_soc_percent
        name: State of Charge
      - entity: sensor.eveus_ev_charger_time_to_target
        name: Time to Target
      - entity: sensor.eveus_ev_charger_session_energy
        name: Session Energy
  
  - type: gauge
    entity: sensor.eveus_ev_charger_soc_percent
    name: EV Battery
    min: 0
    max: 100
    severity:
      green: 80
      yellow: 50
      red: 20
```
</details>

## Troubleshooting

### Common Issues and Solutions

1. **Connection Problems**
   - Verify your EV charger is on the same network as Home Assistant
   - Check that you can reach the charger's IP address from the Home Assistant host
   - Ensure the username and password are correct

2. **SOC Calculation Issues**
   - Make sure all required helper entities are created with the exact names shown
   - Verify your EV's battery capacity is correctly set
   - Reset initial SOC before each new charging session

3. **Reset Procedure**
   If the integration behaves unexpectedly:
   - Restart the Home Assistant service
   - If issues persist, remove and re-add the integration
   - Check the Home Assistant logs for any errors related to the Eveus integration

### Logs and Debugging

For detailed logging, add the following to your `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.eveus: debug
```

## Support and Contributions

- For bugs and feature requests, please open an issue on GitHub.
- Contributions to improve the integration are welcome! Please submit a pull request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
