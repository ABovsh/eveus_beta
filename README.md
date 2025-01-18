# Eveus EV Charger Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
![Version](https://img.shields.io/badge/version-1.2.0-blue)
![Stability](https://img.shields.io/badge/stability-stable-green)
![HomeAssistant](https://img.shields.io/badge/HomeAssistant-2024.1.0-blue)

A comprehensive Home Assistant integration for Eveus EV chargers, providing advanced monitoring, control, and energy management features.

## Features

### 🔌 Basic Monitoring
- Real-time voltage, current, and power monitoring
- Session and total energy tracking
- Temperature monitoring for box and plug
- Ground connection safety monitoring
- Battery voltage monitoring
- Energy counters with cost tracking

### 🚗 Advanced EV Features
- Accurate State of Charge monitoring (kWh and percentage)
- Dynamic time-to-target calculation
- Charging efficiency calculation
- Comprehensive session time tracking
- Automatic error recovery

### 🎮 Control Features
- Dynamic charging current control (8-16A or 8-32A based on model)
- Start/Stop charging control
- One charge mode support
- Counter reset functionality
- Current adjustment with safety limits

## Prerequisites

### Required Helper Entities
Before installing the integration, create these helper entities:

1. Navigate to: **Settings** → **Devices & Services** → **Helpers**
2. Click "+ CREATE HELPER"
3. Select "Number"
4. Create each helper with the exact names:

```yaml
- Name: `EV Battery Capacity`
- Minimum: 10
- Maximum: 160
- Step Size: 1
- Unit: kWh
- Mode: slider

- Name: `Initial EV State of Charge`
- Minimum: 0
- Maximum: 100
- Step Size: 1
- Unit: %
- Mode: slider

- Name: `SOC Correction Factor`
- Minimum: 0
- Maximum: 10
- Step Size: 0.1
- Initial: 7.5
- Unit: %
- Mode: slider

- Name: `Target SOC`
- Minimum: 80
- Maximum: 100
- Step Size: 10
- Initial: 80
- Unit: %
- Mode: slider

### Integration Setup
1. Go to **Settings** → **Devices & Services**
2. Click "+ ADD INTEGRATION"
3. Search for "Eveus"
4. Enter required information:
   - IP Address: Your charger's IP
   - Username: Your login
   - Password: Your password
   - Model: 16A or 32A
```

## Installation

### HACS (Recommended)
1. Add this repository to HACS:
   ```
   https://github.com/ABovsh/eveus
   ```
2. Search for "Eveus" in HACS store
3. Click Install
4. Restart Home Assistant

### Manual
1. Download this repository
2. Copy `custom_components/eveus` to your `config/custom_components/` directory
3. Restart Home Assistant

## Configuration

### Initial Setup
1. Ensure all required helper entities are created
2. Go to Configuration → Integrations
3. Click "+ Add Integration"
4. Search for "Eveus"
5. Enter:
   - IP Address
   - Username
   - Password
   - Charger Model (16A/32A)

### Entity Reference

Basic Sensors:
| Entity | Name | Description | Unit |
|--------|------|-------------|------|
| sensor.eveus_voltage | Voltage | Current voltage | V |
| sensor.eveus_current | Current | Charging current | A |
| sensor.eveus_power | Power | Charging power | W |
| sensor.eveus_session_energy | Session Energy | Energy used in session | kWh |
| sensor.eveus_total_energy | Total Energy | Total energy delivered | kWh |
| sensor.eveus_counter_a_energy | Counter A Energy | Energy counter A | kWh |
| sensor.eveus_counter_b_energy | Counter B Energy | Energy counter B | kWh |
| sensor.eveus_counter_a_cost | Counter A Cost | Cost counter A | ₴ |
| sensor.eveus_counter_b_cost | Counter B Cost | Cost counter B | ₴ |

SOC Sensors:
| Entity | Name | Description | Unit |
|--------|------|-------------|------|
| sensor.eveus_soc_energy | SOC Energy | Current battery charge | kWh |
| sensor.eveus_soc_percent | SOC Percent | Current battery charge | % |
| sensor.eveus_time_to_target | Time to Target | Time until target SOC | - |

Diagnostic Sensors:
| Entity | Name | Description |
|--------|------|-------------|
| sensor.eveus_state | State | Charger state |
| sensor.eveus_substate | Substate | Detailed status |
| sensor.eveus_ground | Ground | Ground connection status |
| sensor.eveus_enabled | Enabled | Charging enabled status |

Temperature Sensors:
| Entity | Name | Description | Unit |
|--------|------|-------------|------|
| sensor.eveus_box_temperature | Box Temperature | Internal temperature | °C |
| sensor.eveus_plug_temperature | Plug Temperature | Plug temperature | °C |

Controls:
| Entity | Name | Description |
|--------|------|-------------|
| number.eveus_charging_current | Charging Current | Control charging current |
| switch.eveus_stop_charging | Stop Charging | Control charging state |
| switch.eveus_one_charge | One Charge | Enable one charge mode |
| switch.eveus_reset_counter_a | Reset Counter A | Reset energy counter |

## Usage

### Before Charging
1. Set EV battery capacity
2. Set initial State of Charge
3. Adjust efficiency correction if needed
4. Set target SOC

### During Charging
1. Monitor charging progress via SOC sensors
2. Use time to target for completion estimate
3. Adjust current if needed
4. Monitor temperatures and status

### After Charging
1. Reset Counter A for new session
2. Check total energy usage
3. Verify charging efficiency

### Service Calls
Available services:
```yaml
eveus.reset_counter_a:
  description: Reset energy counter A to zero

eveus.enable_charging:
  description: Enable charging process

eveus.disable_charging:
  description: Disable charging process

eveus.set_charging_current:
  description: Set charging current
  fields:
    current:
      description: Current in amperes (8-32A)
      example: 16
```

## Troubleshooting

### Common Issues
1. Connection Problems:
   - Verify charger IP address
   - Check network connectivity
   - Ensure proper credentials

2. Helper Entity Issues:
   - Verify all helpers exist
   - Check value ranges
   - Ensure proper configuration

3. State Issues:
   - Check charger status
   - Verify current settings
   - Monitor error states

### Debug Logging
Add to configuration.yaml:
```yaml
logger:
  default: warning
  logs:
    custom_components.eveus: debug
```

## Support

For bugs and feature requests, open an issue on GitHub: [Issues](https://github.com/ABovsh/eveus/issues)

## Contributing

1. Fork the repository
2. Create feature branch
3. Commit changes
4. Create pull request

## License

This project is licensed under the MIT License - see LICENSE file for details.

## Acknowledgments

- Home Assistant Community
- HACS Team
- All contributors

## Version History

See [Changelog](https://github.com/ABovsh/eveus/blob/main/CHANGELOG.md)
