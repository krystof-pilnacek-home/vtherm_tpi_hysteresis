# Technical documentation — `vtherm_tpi_hysteresis`

> External plugin for **Versatile Thermostat (VTherm)** providing a new proportional
> regulation algorithm named **`tpi_hysteresis_regulation`**: TPI dynamics gated by a
> full hysteresis band around the setpoint.
>
> Audience: developers and maintainers of the plugin.

## 1. Position in the VTherm plugin architecture

The plugin registers an `InterfacePropAlgorithmFactory` named
`tpi_hysteresis_regulation` in the shared `VThermAPI` (package `vtherm_api`, the public
API of Versatile Thermostat ≥ 10.0). VTherm's `ThermostatProp` resolves the factory at
thermostat creation and again at `async_startup()`, then drives the returned handler
through the `InterfacePropAlgorithmHandler` lifecycle:

| Lifecycle call | Our implementation |
| --- | --- |
| `init_algorithm()` | merge effective config (defaults ← global entry ← per-thermostat entry), build the pure controller, expose a **read-only proxy** as `thermostat.prop_algorithm` |
| `async_added_to_hass()` | restore persisted band state from the HA `Store` |
| `on_scheduler_ready(scheduler)` | store the cycle scheduler, register the controller's documented cycle callbacks |
| `async_startup()` | align with the current HVAC state via `on_state_changed(True)` |
| `control_heating(timestamp, force)` | the **authoritative** control iteration: compute `on_percent`, forward to the cycle scheduler, turn the device off on HVAC off, persist state, publish diagnostics |
| `should_publish_intermediate()` | True only when the committed `on_percent` actually changed (or `force`) |
| `update_attributes()` | expose diagnostics under `specific_states["tpi_hysteresis"]` |
| `remove()` | persist the band state via `hass.async_create_task(store.async_save(...))` |

### The `recalculate()` guard

VTherm's `ThermostatProp.recalculate()` calls `prop_algorithm.calculate(...)` on every
temperature-sensor update **before** `async_control_heating()` reaches our handler. A
naive controller assigned directly to `prop_algorithm` would mutate its band hold state
from that spurious pre-call. The handler therefore assigns a `_PropAlgoProxy` instead:
`calculate()` on the proxy is a no-op that returns the last committed value, while
`on_percent` / `calculated_on_percent` remain readable at any time. The only mutating
`calculate()` is the one inside `control_heating()`. (Pattern from
`vtherm_pellet_stove`'s `_PropAlgoProxy`.)

## 2. Layering

```
custom_components/vtherm_tpi_hysteresis/
├── manifest.json            # requires versatile_thermostat
├── __init__.py              # factory registration + reload logic (pellet-stove pattern)
├── factory.py               # TpiHysteresisFactory(name="tpi_hysteresis_regulation")
├── config_flow.py           # global defaults + per-thermostat options (KipK pattern)
├── const.py                 # defaults: hysteresis_on 1.0, hysteresis_off 0.5,
│                            # coef_int 1.0, coef_ext 0.1, min/max 0/1
├── handler.py               # TpiHysteresisHandler — VT lifecycle wrapper
├── tpi_hysteresis/
│   └── controller.py        # pure control law, no HA imports, unit-testable
└── translations/en.json, cs.json
```

The controller (`tpi_hysteresis/controller.py`) is a pure class over plain floats —
no Home Assistant imports — mirroring the KipK separation so the control law is
unit-testable standalone and reusable.

## 3. Control law

Heat mode, with `target` = VTherm setpoint:

- `current ≤ target − hysteresis_on` → active, output
  `clamp(coef_int·(target − current) + coef_ext·(target − outdoor), min_on, max_on)`
- `current ≥ target + hysteresis_off` → inactive, output `0`
- in between → **hold** previous state; if held active, the TPI value keeps being
  recomputed each iteration (proportional taper inside the band)

Cool mode mirrors every comparison (`delta_temp = current − target`,
`delta_ext = outdoor − target`). HVAC `off` and unsupported modes deactivate;
missing temperatures deactivate with `last_reason = "missing_temperature"`.

All state transitions land in `last_reason` (e.g. `below_activation_threshold`,
`hold_in_band`, `above_deactivation_threshold`, `hvac_off`) which is exposed in
the diagnostics payload.

`save_state()` / `restore_state()` serialize only the band state (`is_active`,
`hvac_mode`, `last_reason`); persistence goes through
`Store(hass, 1, "vtherm_tpi_hysteresis.<slugified-name>")` after every control
iteration and on `remove()`.

## 4. Registration and reload semantics

`__init__.py` follows `vtherm_pellet_stove`'s authoritative pattern:

1. `_register_factory(hass)` is idempotent, tracked under
   `hass.data[DOMAIN]["factory_registered"]`, and warns when `VThermAPI` is
   unavailable (VT not set up yet).
2. `async_setup_entry` skips VT reloads during initial HA startup (`CoreState.running`
   check) to avoid disturbing state restore.
3. **The reload pitfall:** reloading VTherm entries can destroy and recreate the
   `VThermAPI` instance with an *empty* algorithm registry. After any VT reload,
   the plugin drops its registration flag, re-registers the factory on the
   (possibly new) API, and calls `api.init_vtherm_links(entry_id)` for each
   reloaded entry so entities that previously raised "Unknown proportional
   function" get a second chance.
4. Options updates reload only the affected VT entries: a per-thermostat entry
   change reloads only its target; a global-defaults change skips VTherms that
   have their own override entry.

## 5. Scope boundary

No min on/off durations, no safety cut-off, no power-level piloting. Those live in
`stove_controller` (min-ON/min-OFF at the stove relay) and existing HA automations
(26 °C safety cutoff). This plugin is a pure valve-position algorithm.

## 6. Test architecture

- `tests/test_controller.py` — pure control law, no HA imports.
- `tests/test_handler.py` — lifecycle with MagicMock hass/thermostat (pellet-stove
  test style), including the read-only proxy contract.
- `tests/test_config_flow.py` — real HA test instance, integration copied into a
  temp config dir (`hass_config_dir` override).
- `tests/test_init.py` — registration/reload semantics including the
  `VThermAPI.reset_vtherm_api()` recreation pitfall.
- `tests/test_e2e.py` — a real `ClimateEntity` fake VTherm
  (`tests/fake_vtherm.py`) implementing the same plugin lifecycle as VTherm's
  `ThermostatProp`; driven only through public HA APIs (climate services,
  temperature-sensor update hooks, state machine), in the `stove_controller`
  `test_e2e_final.py` conventions.
