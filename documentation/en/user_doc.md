# Hysteresis

## Purpose

This integration exposes a basic heating and cooling hysteresis controller to Versatile Thermostat through the external algorithm API.

It is intentionally simple and is meant to serve as a reference implementation for developers who want to plug another algorithm into VT.

The plugin composes a preset algorithm under an optional hysteresis overlay: the overlay decides *whether* to regulate, the algorithm decides *how much* power to request while regulating.

## Parameters

### Algorithm

The preset algorithm used while regulation is active. `on_off` (default) reproduces the historical relay behaviour: `max_on_percent` while active, `min_on_percent` while inactive. The `tpi` preset applies proportional TPI control while regulation is active: `on_percent = clamp(coef_int * (target - current) + coef_ext * (target - outdoor), min_on_percent, max_on_percent)` in heat mode, with the deltas mirrored in cool mode. While inactive it requests `min_on_percent`. The `algorithm` option lists all registered presets.

With `hysteresis_on` and `hysteresis_off` both at `0` the hysteresis band degenerates and the algorithm regulates up to the setpoint directly (plain on/off or proportional control).

### Activation delta

In heat mode, the controller requests active regulation when the room temperature drops below `target - hysteresis_on`.

In cool mode, the controller requests active regulation when the room temperature rises above `target + hysteresis_on`.

### Deactivation delta

In heat mode, the controller requests inactive regulation when the room temperature rises above `target + hysteresis_off`.

In cool mode, the controller requests inactive regulation when the room temperature drops below `target - hysteresis_off`.

### Active power (`max_on_percent`)

The duty-cycle fraction sent to the cycle scheduler when regulation is active. A value of `1.0` means 100 % (default). Reduce this to cap the active command sent to the underlying device.

Range: `0.0` – `1.0`. Default: `1.0`.

### Inactive power (`min_on_percent`)

The duty-cycle fraction sent to the cycle scheduler when regulation is inactive. A value of `0.0` means completely off (default). Set a non-zero value to keep a valve partially open while the relay is inactive.

Range: `0.0` – `1.0`. Default: `0.0`.

### Internal coefficient (`coef_int`)

Weight of the room-temperature deficit (`target - current` in heat mode) in the `tpi` preset. Only used when `algorithm` is `tpi`.

Default: `1.0`.

### External coefficient (`coef_ext`)

Weight of the outdoor-temperature deficit (`target - outdoor` in heat mode) in the `tpi` preset. Only used when `algorithm` is `tpi`; without an outdoor sensor the external term is `0`.

Default: `0.1`.

## Tracking attributes

The controller exposes its latest decision under `specific_states.hysteresis`:

- `algorithm`
- `is_active`
- `hvac_mode`
- `on_percent`
- `last_reason`
- `activation_threshold`
- `deactivation_threshold`
- `hysteresis_on`
- `hysteresis_off`
- `max_on_percent`
- `min_on_percent`
- `coef_int`
- `coef_ext`

## Configuration modes

The config flow supports two scopes:

- global defaults applied when no thermostat-specific plugin entry exists
- thermostat-specific settings bound to one VT entity

## Persistence

The relay state is stored in Home Assistant storage so the controller can resume with a consistent band state after a restart.
