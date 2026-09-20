# Versatile Thermostat Hysteresis

[Lire la version française](README.fr.md)

<p align="center">
  <strong>Reference external algorithm integration for Versatile Thermostat</strong>
</p>

This repository provides a simple hysteresis-based heating and cooling algorithm packaged as an external integration for Versatile Thermostat.

Plugins algorithm are intended to replace the onboard TPI. They so are limited to over_switch, over_valve and climate with valve control underlyings.


## What this repository demonstrates

- Registration of an external proportional algorithm through `vtherm_api`
- Full Home Assistant integration packaging with `manifest.json`, `config_flow.py`, translations and HACS metadata
- Per-thermostat and global plugin configuration entries
- A minimal handler that implements the complete `InterfacePropAlgorithmHandler` contract
- Persistence of algorithm state with Home Assistant storage

## Control law

The algorithm applies a classic relay hysteresis according to the active HVAC mode:

- in heat mode, regulation activates when `current_temperature <= target_temperature - hysteresis_on`
- in heat mode, regulation deactivates when `current_temperature >= target_temperature + hysteresis_off`
- in cool mode, regulation activates when `current_temperature >= target_temperature + hysteresis_on`
- in cool mode, regulation deactivates when `current_temperature <= target_temperature - hysteresis_off`
- inside the band, the previous relay state is kept

The result is then translated to the VT cycle scheduler as `on_percent = max_on_percent` (active regulation) or `on_percent = min_on_percent` (inactive regulation). Both values are configurable; defaults are `1.0` and `0.0` respectively.

## Installation

### Via HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=KipK&repository=vtherm_hysteresis&category=Integration)

1. Add the repository to HACS as an integration.
2. Install the repository.
3. Restart Home Assistant.
4. Add the `Versatile Thermostat Hysteresis` integration from the Settings / Devices & Services / Add an Integration
5. Select Husteresis algorithm in your VTherm underlyings configuration.
6. Select either global defaults or a thermostat-specific configuration in vtherm-hysteresis integration page.

### Manual installation

1. Copy `custom_components/vtherm_hysteresis` to your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Add the integration from the UI.

## Repository structure

- `custom_components/vtherm_hysteresis/`: Home Assistant integration code
- `documentation/en/`: English user and technical documentation
- `documentation/fr/`: French user and technical documentation
- `.github/workflows/`: validation, test and release examples

## Documentation

- [User documentation](documentation/en/vtherm_hysteresis.md)
- [Technical documentation](documentation/en/technical_doc.md)

## License

The repository owner must define the license terms applied to this scaffold.
