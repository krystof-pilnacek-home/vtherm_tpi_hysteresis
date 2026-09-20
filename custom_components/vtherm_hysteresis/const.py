"""Constants for the vtherm_hysteresis integration."""

from __future__ import annotations

DOMAIN = "vtherm_hysteresis"
NAME = "Versatile Thermostat Hysteresis"

CONF_TARGET_VTHERM = "target_vtherm_unique_id"
CONF_PROP_FUNCTION = "proportional_function"
CONF_HYSTERESIS_ON = "hysteresis_on"
CONF_HYSTERESIS_OFF = "hysteresis_off"
CONF_MAX_ON_PERCENT = "max_on_percent"
CONF_MIN_ON_PERCENT = "min_on_percent"

DEFAULT_HYSTERESIS_ON = 0.3
DEFAULT_HYSTERESIS_OFF = 0.3
DEFAULT_MAX_ON_PERCENT = 1.0
DEFAULT_MIN_ON_PERCENT = 0.0

DEFAULT_OPTIONS: dict[str, float] = {
    CONF_HYSTERESIS_ON: DEFAULT_HYSTERESIS_ON,
    CONF_HYSTERESIS_OFF: DEFAULT_HYSTERESIS_OFF,
    CONF_MAX_ON_PERCENT: DEFAULT_MAX_ON_PERCENT,
    CONF_MIN_ON_PERCENT: DEFAULT_MIN_ON_PERCENT,
}

PROP_FUNCTION_HYSTERESIS = "hysteresis"

DATA_FACTORY_REGISTERED = "factory_registered"

STORAGE_VERSION = 1
STORAGE_KEY = "vtherm_hysteresis.{}"
