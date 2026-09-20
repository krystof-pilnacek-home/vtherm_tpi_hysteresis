# Technical documentation

## Architecture

The repository mirrors the structure of a complete external algorithm integration:

- `__init__.py` registers the algorithm factory in `VThermAPI`
- `factory.py` exposes the identifier used by VT to instantiate the handler
- `handler.py` implements the runtime lifecycle expected by `InterfacePropAlgorithmHandler`
- `hysteresis/controller.py` contains the isolated control law
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

## Scheduler interaction

The controller does not switch hardware directly. It computes an `on_percent` and forwards that request to the VT cycle scheduler:

- `max_on_percent` is sent when heat or cool regulation is active (default `1.0`)
- `min_on_percent` is sent when heat or cool regulation is inactive (default `0.0`)

Both values are configurable per thermostat so that users can cap active power at 80 % or keep a valve slightly open when regulation is inactive.

## Published diagnostics

The handler publishes a compact diagnostics payload under `specific_states.hysteresis` with the relay state, normalized HVAC mode, requested `on_percent`, latest decision reason and thresholds used by the latest calculation.
