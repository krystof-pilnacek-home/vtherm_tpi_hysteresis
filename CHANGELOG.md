# Changelog

## 0.1.0 (2026-09-24)

Initial release.

- `tpi_hysteresis_regulation` proportional algorithm for Versatile Thermostat:
  TPI dynamics gated by a full hysteresis band (below-setpoint dead band +
  above-setpoint hold), with hold-state relay memory inside the band and
  proportional tapering while held active.
- Heat/cool mode support with VTherm enum-tolerant mode normalization.
- Global defaults + per-thermostat override config entries (KipK pattern),
  options flow, EN/CS translations.
- HA Store persistence of the band state across restarts.
- Factory registration in `VThermAPI` with the pellet-stove reload pattern
  (re-register + `init_vtherm_links` retry after VT entry reloads).
- Read-only `prop_algorithm` proxy so VTherm's `recalculate()` pre-call
  cannot mutate the band state outside the authoritative control iteration.
- Test suite: 87 tests including 13 e2e tests with a real ClimateEntity fake
  VTherm.
