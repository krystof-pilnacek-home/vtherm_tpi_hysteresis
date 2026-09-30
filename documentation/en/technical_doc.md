# Technical documentation

## Architecture

The repository mirrors the structure of a complete external algorithm integration:

- `__init__.py` registers the algorithm factory in `VThermAPI`
- `factory.py` exposes the identifier used by VT to instantiate the handler
- `handler.py` implements the runtime lifecycle expected by `InterfacePropAlgorithmHandler`
- `hysteresis/controller.py` contains the hysteresis overlay and delegates the power request to the composed algorithm
- `hysteresis/algorithms.py` is the preset algorithm registry (`on_off`, `tpi`)
- `config_flow.py` provides global and per-thermostat configuration entries

## Interface contract

The handler implements the following methods from `vtherm_api.interfaces.InterfacePropAlgorithmHandler`:

- `init_algorithm`
- `async_added_to_hass`
- `async_startup`
- `remove`
- `control_heating`
- `on_state_changed`
- `on_scheduler_ready`
- `should_publish_intermediate`
- `update_attributes`

Each method is kept in the scaffold even when the hysteresis use case does not need complex logic, so plugin developers can see where each extension point belongs.

## Composition: algorithm under hysteresis overlay

The controller splits the regulation decision in two:

- the **hysteresis overlay** owns the relay state (activate / deactivate / hold inside the band) and exposes the thresholds in the diagnostics;
- the composed **algorithm** computes `on_percent` while regulating. The controller clamps the request into `[min_on_percent, max_on_percent]`.

An algorithm is a callable `(hvac_mode, target_temp, current_temp, ext_temp, params) -> float` registered by name in `ALGORITHMS`; `get_algorithm()` falls back to `on_off` for unknown names and `register_algorithm()` is the extension point. The `algorithm` config option selects the preset per thermostat (or via global defaults).

The `tpi` preset implements the proportional control law `coef_int * (target - current) + coef_ext * (target - outdoor)` while regulation is active, with the deltas negated in cool mode. The `coef_int` / `coef_ext` config options (defaults `1.0` / `0.1`) are passed through the controller `params` dict to the composed algorithm; when no outdoor temperature is available the external term is `0`. The hysteresis overlay is unchanged: while inactive the preset returns `min_on_percent`.

With `hysteresis_on = hysteresis_off = 0` the band degenerates and the algorithm output drives regulation directly up to the setpoint.

## Scheduler interaction

The controller does not switch hardware directly. It computes an `on_percent` and forwards that request to the VT cycle scheduler:

- while regulation is active, the composed algorithm request (clamped) is forwarded; the `on_off` preset sends `max_on_percent` (default `1.0`)
- while regulation is inactive, the clamped request is sent; the `on_off` preset sends `min_on_percent` (default `0.0`)

Both values are configurable per thermostat so that users can cap active power at 80 % or keep a valve slightly open when regulation is inactive.

## Published diagnostics

The handler publishes a compact diagnostics payload under `specific_states.hysteresis` with the selected algorithm name, relay state, normalized HVAC mode, requested `on_percent`, latest decision reason and thresholds used by the latest calculation.
