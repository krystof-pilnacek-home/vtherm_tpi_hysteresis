# VTherm TPI Hysteresis

A [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat) (VTherm) plugin
algorithm that combines **proportional TPI dynamics with a full hysteresis band around the
setpoint** — including a below-setpoint dead band, which neither the built-in TPI thresholds
(both bounds above setpoint) nor the [KipK/vtherm_hysteresis](https://github.com/KipK/vtherm_hysteresis)
relay plugin (no proportional control) provide.

Built for a pellet-stove zone-valve heating system piloted by VTherm in `over_valve` mode,
sibling of the [stove_controller](https://github.com/krystof-pilnacek-home/stove_controller)
integration.

## Control law (heat mode)

With `target` = VTherm setpoint:

- **TPI active:** `current ≤ target − hysteresis_on` →
  `on_percent = clamp(coef_int × (target − current) + coef_ext × (target − outdoor), min, max)`
- **TPI disabled:** `current ≥ target + hysteresis_off` → `on_percent = 0`
- **Inside the band** `(target − hysteresis_on, target + hysteresis_off)`: **hold previous
  state** (relay memory). If previously active, keep computing TPI — the valve modulates
  down proportionally as the room approaches the setpoint instead of slamming shut; if
  previously inactive, stay at 0.

Cool mode mirrors all comparisons.

### Why this shape for the stove system

- Zone valves stay fully closed until a real 1 °C deficit → no marginal demand toggling of
  `switch.stove_demand` (helps the `stove_controller` min-ON 30 / min-OFF 25 state machine).
- Once active, TPI output starts near 100 % and tapers as the room approaches the setpoint
  → less overshoot toward the 26 °C safety cutoff than a flat 100 % relay.
- With 4 staggered zones, proportional tapering smooths aggregate demand vs. relay zones
  all snapping open/shut.

### Defaults (stove setup)

| Parameter | Default | Meaning |
| --- | --- | --- |
| `hysteresis_on` | `1.0` | °C below/above setpoint to activate |
| `hysteresis_off` | `0.5` | °C above/below setpoint to deactivate |
| `tpi_coef_int` | `1.0` | internal TPI coefficient on `(target − current)` |
| `tpi_coef_ext` | `0.1` | external TPI coefficient on `(target − outdoor)` |
| `min_on_percent` | `0.0` | lower clamp while active |
| `max_on_percent` | `1.0` | upper clamp |

## Installation

Install via [HACS](https://hacs.xyz) by adding this repository as a custom repository with
type **Integration**.

Alternatively, copy `custom_components/vtherm_tpi_hysteresis/` into your
`custom_components/` directory and restart Home Assistant.

Requires **Versatile Thermostat ≥ 10.0** (the VTherm plugin API, `vtherm_api`).

## Configuration

1. Install and set up [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat);
   configure a thermostat (e.g. `over_valve`) and set its **proportional function** to
   `tpi_hysteresis_regulation` (appears in the algorithm dropdown once this plugin is
   registered).
2. Add the integration via **Settings > Devices & Services > Add Integration**. The first
   entry creates the **global defaults**.
3. Optionally add another entry targeting a specific VTherm to **override the defaults**
   per thermostat.

The algorithm publishes diagnostics under `specific_states.tpi_hysteresis` in the climate
entity attributes (`is_active`, `on_percent`, `raw_tpi`, `last_reason`, thresholds in use).

## Scope boundary

Unlike [vtherm_pellet_stove](https://github.com/jmcollin78/vtherm_pellet_stove), this plugin
deliberately includes **no min on/off durations and no safety cut-off**. All stove-level
protections live in [stove_controller](https://github.com/krystof-pilnacek-home/stove_controller)
(min-ON 30 min / min-OFF 25 min at the stove relay) and existing HA automations (26 °C
safety cutoff). Keep pellet-stove-style guard settings of other plugins at 0 here to avoid
duplicated protection. This plugin is a **pure valve-position algorithm**.

## Development

```bash
uv sync --all-extras
uv run pytest tests/ -v --tb=short --cov=vtherm_tpi_hysteresis
uv run ruff check .
uv run mypy .
```

Test layout follows the [stove_controller](https://github.com/krystof-pilnacek-home/stove_controller)
conventions:

- `tests/test_controller.py` — pure control-law unit tests, no HA imports;
- `tests/test_handler.py` — VT plugin lifecycle with MagicMock hass/thermostat;
- `tests/test_config_flow.py`, `tests/test_init.py` — against the real HA test instance;
- `tests/test_e2e.py` — end-to-end with a real `ClimateEntity` fake VTherm implementing
  the same plugin lifecycle as VTherm's `ThermostatProp`, driven only through public HA
  APIs.

## License

Apache-2.0. Derived from the
[KipK/vtherm_hysteresis](https://github.com/KipK/vtherm_hysteresis) plugin
(imported verbatim as the first commit of this repository).
