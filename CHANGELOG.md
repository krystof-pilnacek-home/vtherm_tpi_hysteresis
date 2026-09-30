# Changelog

## [0.5.0]

Review hardening of the composable regulation (PR #6):

- The `tpi` placeholder preset is no longer registered: the `algorithm`
  dropdown only offers `on_off` until the TPI follow-up (#4) lands with
  a preset that honors the hysteresis overlay and the cooling-mode signs.
- `normalize_hvac_mode` matches exact modes: `heat_cool` (auto) is no
  longer misclassified as `cool` by the `endswith` chain, and unsupported
  modes (`dry`, `fan_only`, ...) normalize to None.
- `min_on_percent` no longer applies when the controller is not
  regulating (HVAC off, unsupported mode, missing temperature): the duty
  request is 0 in those states instead of the configured floor.
- The config flow rejects `min_on_percent > max_on_percent` with a form
  error (`min_greater_than_max`) instead of silently swapping the values.
- The per-thermostat config flow now pre-fills the form with the
  configured global defaults instead of the factory defaults.
- Persistence saves only when the controller state actually changes
  (write amplification fix) and logs save errors instead of raising.
- `_reload_hysteresis_vtherms` gathers reloads with
  `return_exceptions=True` and logs failures instead of aborting the
  remaining reloads.
- `register_algorithm` logs a warning when replacing an existing preset.
- Version metadata synchronized (manifest, pyproject) and `uv.lock`
  committed for reproducible CI.
- New brand assets: a PID control-loop diagram in VTherm colors.
- OptionsFlow uses the modern `config_entry` property.
- Dropped dead code: unused `_clamp` in `algorithms.py`, the unused
  `AlgorithmFn` alias, and the unreachable `async_step_global` step.

## [0.4.0]

feat: composable regulation - preset algorithm under hysteresis overlay

- New `hysteresis/algorithms.py` preset registry: `on_off` (the historical
  relay behaviour, default) and a `tpi` placeholder reserved for a
  follow-up. `register_algorithm()` is the extension point.
- The hysteresis controller becomes an overlay over the composed
  algorithm: the band decides whether to regulate, the algorithm decides
  how much power to request (clamped into
  `[min_on_percent, max_on_percent]`).
- New `algorithm` config option (global defaults and per-thermostat)
  with a dropdown of registered presets; the selected preset is exposed
  in the diagnostics payload.
- With `hysteresis_on = hysteresis_off = 0` the band degenerates: plain
  on/off regulation without hysteresis.
- Real-hass test suite: unit tests, config-flow/init integration tests
  and 16 e2e tests through the public HA APIs with a fake VTherm
  mirroring the ThermostatProp plugin lifecycle.

## [0.1.0]

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