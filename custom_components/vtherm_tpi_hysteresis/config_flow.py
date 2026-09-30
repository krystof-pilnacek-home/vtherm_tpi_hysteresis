"""Config flow for vtherm_tpi_hysteresis."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_ALGORITHM,
    CONF_COEF_EXT,
    CONF_COEF_INT,
    CONF_HYSTERESIS_OFF,
    CONF_HYSTERESIS_ON,
    CONF_MAX_ON_PERCENT,
    CONF_MIN_ON_PERCENT,
    CONF_TARGET_VTHERM,
    DEFAULT_OPTIONS,
    DOMAIN,
)
from .hysteresis.algorithms import ALGORITHMS


def _validate_options(user_input: dict[str, Any]) -> dict[str, str]:
    """Return per-field errors for an options payload, empty when valid."""
    errors: dict[str, str] = {}
    min_on = user_input.get(CONF_MIN_ON_PERCENT)
    max_on = user_input.get(CONF_MAX_ON_PERCENT)
    if min_on is not None and max_on is not None and float(min_on) > float(max_on):
        errors[CONF_MAX_ON_PERCENT] = "min_greater_than_max"
    return errors


def build_options_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build the Hysteresis defaults schema."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_ALGORITHM,
                default=defaults[CONF_ALGORITHM],
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=sorted(ALGORITHMS),
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_HYSTERESIS_ON,
                default=defaults[CONF_HYSTERESIS_ON],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0,
                    max=5.0,
                    step=0.01,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_HYSTERESIS_OFF,
                default=defaults[CONF_HYSTERESIS_OFF],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0,
                    max=5.0,
                    step=0.01,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_MAX_ON_PERCENT,
                default=defaults[CONF_MAX_ON_PERCENT],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0,
                    max=1.0,
                    step=0.01,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_MIN_ON_PERCENT,
                default=defaults[CONF_MIN_ON_PERCENT],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0,
                    max=1.0,
                    step=0.01,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_COEF_INT,
                default=defaults[CONF_COEF_INT],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0,
                    max=20.0,
                    step=0.01,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_COEF_EXT,
                default=defaults[CONF_COEF_EXT],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0,
                    max=20.0,
                    step=0.01,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
    )


def build_user_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build the Hysteresis per-thermostat schema."""
    schema = {
        vol.Required(CONF_TARGET_VTHERM): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=CLIMATE_DOMAIN)
        )
    }
    schema.update(build_options_schema(defaults).schema)
    return vol.Schema(schema)


def _global_defaults(hass) -> dict[str, Any]:
    """Return the configured global defaults, or DEFAULT_OPTIONS."""
    defaults = dict(DEFAULT_OPTIONS)
    global_entry = next(
        (entry for entry in hass.config_entries.async_entries(DOMAIN) if entry.unique_id == DOMAIN),
        None,
    )
    if global_entry is not None:
        defaults.update(global_entry.data)
        defaults.update(global_entry.options)
    return defaults


class HysteresisConfigFlow(ConfigFlow, domain=DOMAIN):
    """Manage Hysteresis plugin config entries."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Create default plugin settings on first install."""
        del user_input
        if not self._async_current_entries():
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="Hysteresis defaults",
                data=dict(DEFAULT_OPTIONS),
            )
        return await self.async_step_thermostat()

    async def async_step_thermostat(self, user_input: dict[str, Any] | None = None):
        """Handle the per-thermostat entry."""
        defaults = _global_defaults(self.hass)
        if user_input is not None:
            errors = _validate_options(user_input)
            entity_id = user_input.get(CONF_TARGET_VTHERM)
            registry = er.async_get(self.hass)
            reg_entry = registry.async_get(str(entity_id)) if entity_id else None
            if reg_entry is None or reg_entry.unique_id is None:
                errors[CONF_TARGET_VTHERM] = "invalid_entity"
            if not errors:
                assert reg_entry is not None
                target_unique_id = reg_entry.unique_id
                await self.async_set_unique_id(f"{DOMAIN}-{target_unique_id}")
                self._abort_if_unique_id_configured()

                data = dict(user_input)
                data[CONF_TARGET_VTHERM] = target_unique_id
                state = self.hass.states.get(str(entity_id))
                title = state.name if state is not None else str(entity_id)
                return self.async_create_entry(title=str(title), data=data)
            return self.async_show_form(
                step_id="thermostat",
                data_schema=build_user_schema({**defaults, **user_input}),
                errors=errors,
            )
        return self.async_show_form(
            step_id="thermostat",
            data_schema=build_user_schema(defaults),
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return HysteresisOptionsFlow()


class HysteresisOptionsFlow(OptionsFlow):
    """Edit Hysteresis plugin defaults."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Handle the options flow."""
        if user_input is not None:
            errors = _validate_options(user_input)
            if errors:
                return self.async_show_form(
                    step_id="init",
                    data_schema=build_options_schema(user_input),
                    errors=errors,
                )
            return self.async_create_entry(title="", data=user_input)

        defaults = dict(DEFAULT_OPTIONS)
        config_entry = self.config_entry
        defaults.update(config_entry.options or config_entry.data)
        return self.async_show_form(
            step_id="init",
            data_schema=build_options_schema(defaults),
        )
