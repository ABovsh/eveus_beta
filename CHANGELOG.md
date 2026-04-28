# Changelog

## 4.0.0 - 2026-04-28

Version 4.0.0 is a major internal modernization release. It keeps existing entity names and unique IDs intact, so current users can update without rebuilding dashboards or automations.

### Added

- Added Home Assistant reconfigure support for updating charger IP address, credentials, and model after setup.
- Added downloadable diagnostics with sensitive fields redacted.
- Added a dedicated automated test suite covering config validation, coordinator polling, diagnostics, command payloads, sensor mappings, entity IDs, and utility calculations.
- Added this changelog for GitHub releases.

### Changed

- Replaced the custom polling loop with Home Assistant's `DataUpdateCoordinator`.
- Moved runtime objects to typed `ConfigEntry.runtime_data`, following current Home Assistant best practices.
- Improved setup validation so unreachable IP addresses, invalid credentials, malformed responses, and non-Eveus JSON responses fail before an integration entry is created.
- Normalized stored hosts from URL-style input such as `http://192.168.1.50/main` to `192.168.1.50`.
- Reworked entity setup to use coordinator-backed entities and entity descriptions while preserving unique IDs.
- Improved default device-page organization within Home Assistant's built-in buckets:
  - Controls remain under Configuration.
  - Device health/status entities remain under Diagnostic.
  - User-facing measurements, energy, cost, rate, and SOC values remain under Sensors.
- Updated the minimum supported Home Assistant version to 2024.4.

### Fixed

- Fixed Home Assistant translation validation for number entity state attributes.
- Fixed the previous behavior where an integration entry could be created for an unreachable or unrelated device.
- Fixed stale entity update plumbing by letting Home Assistant manage coordinator listeners.
- Kept the existing `Stop Charging` semantics unchanged: turning it on enables the charger-side stop-charge option.

### Notes for HACS Publishing

- The integration folder must remain `custom_components/eveus` because the manifest domain is `eveus`.
- HACS repository description and topics are configured in GitHub repository settings, not in this project tree.
- The HACS brands check requires adding the integration to the Home Assistant brands repository.

## 3.0.3

- Added multi-device support.
- Added 48A model support.
- Improved restart safety for switches and number controls.
- Added optimistic UI behavior for controls.
- Improved offline handling and connection quality reporting.
- Refactored the codebase while preserving existing functionality.
- Fixed multiple setup, network, billing, SOC, and translation issues.

