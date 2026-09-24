"""Constants for the vtherm_tpi_hysteresis integration."""

from __future__ import annotations

DOMAIN = "vtherm_tpi_hysteresis"
NAME = "VTherm TPI Hysteresis"

#: Name used to register the algorithm factory in VThermAPI.
PROP_FUNCTION_TPI_HYSTERESIS = "tpi_hysteresis_regulation"

#: Key in a VTherm config entry holding the proportional function name.
CONF_PROP_FUNCTION = "proportional_function"

#: Unique ID of the target VTherm (absent for the global defaults entry).
CONF_TARGET_VTHERM = "target_vtherm_unique_id"

# -- Hysteresis band ---------------------------------------------------------
#: Start heating when current_temp <= target - hysteresis_on (deg C).
CONF_HYSTERESIS_ON = "hysteresis_on"
#: Stop heating when current_temp >= target + hysteresis_off (deg C).
CONF_HYSTERESIS_OFF = "hysteresis_off"

# -- TPI coefficients ---------------------------------------------------------
#: Internal TPI coefficient applied to (target - current).
CONF_TPI_COEF_INT = "tpi_coef_int"
#: External TPI coefficient applied to (target - outdoor).
CONF_TPI_COEF_EXT = "tpi_coef_ext"

# -- Output limits -----------------------------------------------------------
#: Lower clamp for the on_percent output while active.
CONF_MIN_ON_PERCENT = "min_on_percent"
#: Upper clamp for the on_percent output.
CONF_MAX_ON_PERCENT = "max_on_percent"

# -- Defaults (issue #1: stove setup) ----------------------------------------
DEFAULT_HYSTERESIS_ON: float = 1.0
DEFAULT_HYSTERESIS_OFF: float = 0.5
DEFAULT_TPI_COEF_INT: float = 1.0
DEFAULT_TPI_COEF_EXT: float = 0.1
DEFAULT_MIN_ON_PERCENT: float = 0.0
DEFAULT_MAX_ON_PERCENT: float = 1.0

DEFAULT_OPTIONS: dict[str, float] = {
    CONF_HYSTERESIS_ON: DEFAULT_HYSTERESIS_ON,
    CONF_HYSTERESIS_OFF: DEFAULT_HYSTERESIS_OFF,
    CONF_TPI_COEF_INT: DEFAULT_TPI_COEF_INT,
    CONF_TPI_COEF_EXT: DEFAULT_TPI_COEF_EXT,
    CONF_MIN_ON_PERCENT: DEFAULT_MIN_ON_PERCENT,
    CONF_MAX_ON_PERCENT: DEFAULT_MAX_ON_PERCENT,
}

# -- Internal data keys ------------------------------------------------------
DATA_FACTORY_REGISTERED = "factory_registered"

STORAGE_VERSION = 1
STORAGE_KEY = "vtherm_tpi_hysteresis.{}"

#: Key under thermostat extra-state attributes where diagnostics are exposed.
SPECIFIC_STATES_KEY = "tpi_hysteresis"
