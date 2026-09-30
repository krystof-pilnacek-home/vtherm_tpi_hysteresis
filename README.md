# Versatile Thermostat TPI Hysteresis

<p align="center">
  <strong>Composable external regulation algorithm for Versatile Thermostat</strong>
</p>

This repository provides a regulation plugin for Versatile Thermostat that composes a **preset algorithm** (how much power while regulating) with an **optional hysteresis overlay** (whether to regulate at all).

Algorithm plugins are intended to replace the onboard TPI. They are limited to `over_switch`, `over_valve` and `over_climate` with valve control underlyings.

## What this repository provides

- Registration of an external proportional algorithm through `vtherm_api`
- Full Home Assistant integration packaging with `manifest.json`, `config_flow.py`, translations and HACS metadata
- Per-thermostat and global plugin configuration entries
- A handler that implements the complete `InterfacePropAlgorithmHandler` contract
- Persistence of algorithm state with Home Assistant storage
- A preset algorithm registry so new algorithms (TPI, DSL) can be added without touching the hysteresis overlay

## Control law

The plugin composes two independent decisions:

1. **Hysteresis overlay** — decides *whether* regulation is active, according to the active HVAC mode:
   - heat: activates when `current_temperature <= target_temperature - hysteresis_on`, deactivates when `current_temperature >= target_temperature + hysteresis_off`
   - cool: activates when `current_temperature >= target_temperature + hysteresis_on`, deactivates when `current_temperature <= target_temperature - hysteresis_off`
   - inside the band, the previous relay state is kept
2. **Algorithm** — decides *how much* power to request while regulation is active. The `on_off` preset (default, identical to the historical relay behaviour) requests `max_on_percent` while active and `min_on_percent` while inactive. The `tpi` preset applies proportional TPI control: `on_percent = clamp(coef_int * (target - current) + coef_ext * (target - outdoor), min_on_percent, max_on_percent)` while active (deltas mirrored in cool mode; `coef_int`/`coef_ext` default to `1.0`/`0.1`).

With both thresholds at `0` the hysteresis band degenerates and the algorithm regulates up to the setpoint directly (on/off or proportional control without hysteresis).

The result is translated to the VT cycle scheduler as a clamped `on_percent`.

### Regulation variants

| Variant | `algorithm` | `hysteresis_on`/`hysteresis_off` |
| --- | --- | --- |
| Relay with hysteresis (default, upstream behaviour) | `on_off` | `> 0` |
| Plain on/off | `on_off` | `0` |
| TPI with hysteresis | `tpi` | `> 0` |
| Plain TPI | `tpi` | `0` |

## Installation

### Via HACS

1. Add the repository to HACS as an integration.
2. Install the repository.
3. Restart Home Assistant.
4. Add the `Versatile Thermostat TPI Hysteresis` integration from Settings / Devices & Services / Add an Integration.
5. Select the `tpi_hysteresis_regulation` algorithm in your VTherm configuration.
6. Select either global defaults or a thermostat-specific configuration in the plugin's integration page.

### Manual installation

1. Copy `custom_components/vtherm_tpi_hysteresis` to your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Add the integration from the UI.

## Repository structure

- `custom_components/vtherm_tpi_hysteresis/`: Home Assistant integration code
- `documentation/en/`: English user and technical documentation
- `.github/workflows/`: validation and CI
- `tests/`: unit, integration and end-to-end test suite

## Documentation

- [User documentation](documentation/en/user_doc.md)
- [Technical documentation](documentation/en/technical_doc.md)

## License

Apache-2.0
