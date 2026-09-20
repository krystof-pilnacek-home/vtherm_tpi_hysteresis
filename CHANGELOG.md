# Changelog

## 0.1.0

- Initial scaffold of the Versatile Thermostat Hysteresis integration

## [0.1.1]

- replace vtherm api to main repo



## [0.1.4]

switch to official vtherm_api package

## [0.1.5]

Align prop handler state change hook with changed flag API

## [0.1.6]

remove vtherm_api dependency ( use VT installed one )

## [0.2.0]

feat: bind hysteresis plugin config entry to VTherm device

Add device registry binding so VTherm thermostats using the hysteresis
algorithm appear under the integration panel, grouped by their applied
config entry (global defaults or dedicated).

## [0.3.0]

feat: Add symmetric heat/cool control
- Use a neutral active relay state
- Support cool-mode activation/deactivation thresholds
- Expose hysteresis diagnostics attributes
- Update tests, translations, and documentation

## [0.3.1]

- Fix Hysteresis config entry device ownership cleanup for HA >= 2026.8.0