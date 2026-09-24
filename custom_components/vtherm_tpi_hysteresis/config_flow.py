"""Config flow for vtherm_tpi_hysteresis."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_HYSTERESIS_OFF,
    CONF_HYSTERESIS_ON,
    CONF_MAX_ON_PERCENT,
    CONF_MIN_ON_PERCENT,
    CONF_TARGET_VTHERM,
    CONF_TPI_COEF_EXT,
    CONF_TPI_COEF_INT,
    DEFAULT_OPTIONS,
    DOMAIN,
)


def build_options_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build the TPI hysteresis defaults schema."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_HYSTERESIS_ON,
                default=defaults[CONF_HYSTERESIS_ON],
                description={
                    "suggested_value": defaults[CONF_HYSTERESIS_ON],
                },
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
                description={"suggested_value": defaults[CONF_HYSTERESIS_OFF]},
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0,
                    max=5.0,
                    step=0.01,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_TPI_COEF_INT,
                default=defaults[CONF_TPI_COEF_INT],
                description={"suggested_value": defaults[CONF_TPI_COEF_INT]},
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0,
                    max=20.0,
                    step=0.01,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_TPI_COEF_EXT,
                default=defaults[CONF_TPI_COEF_EXT],
                description={"suggested_value": defaults[CONF_TPI_COEF_EXT]},
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0,
                    max=20.0,
                    step=0.01,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_MIN_ON_PERCENT,
                default=defaults[CONF_MIN_ON_PERCENT],
                description={"suggested_value": defaults[CONF_MIN_ON_PERCENT]},
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0,
                    max=1.0,
                    step=0.01,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_MAX_ON_PERCENT,
                default=defaults[CONF_MAX_ON_PERCENT],
                description={"suggested_value": defaults[CONF_MAX_ON_PERCENT]},
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0,
                    max=1.0,
                    step=0.01,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
    )


def build_user_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build the TPI hysteresis per-thermostat schema."""
    schema: dict[Any, Any] = {
        vol.Required(CONF_TARGET_VTHERM): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=CLIMATE_DOMAIN)
        )
    }
    schema.update(build_options_schema(defaults).schema)
    return vol.Schema(schema)


class TpiHysteresisConfigFlow(ConfigFlow, domain=DOMAIN):
    """Manage TPI hysteresis plugin config entries."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Create default plugin settings on first install."""
        del user_input
        if not self._async_current_entries():
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="TPI Hysteresis defaults",
                data=dict(DEFAULT_OPTIONS),
            )
        return await self.async_step_thermostat()

    async def async_step_global(self, user_input: dict[str, Any] | None = None):
        """Handle the global defaults entry."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="TPI Hysteresis defaults", data=user_input)
        return self.async_show_form(
            step_id="global",
            data_schema=build_options_schema(DEFAULT_OPTIONS),
        )

    async def async_step_thermostat(self, user_input: dict[str, Any] | None = None):
        """Handle the per-thermostat entry."""
        if user_input is not None:
            entity_id = user_input.get(CONF_TARGET_VTHERM)
            registry = er.async_get(self.hass)
            reg_entry = registry.async_get(entity_id) if entity_id else None
            if reg_entry is None or reg_entry.unique_id is None:
                return self.async_show_form(
                    step_id="thermostat",
                    data_schema=build_user_schema(DEFAULT_OPTIONS),
                    errors={CONF_TARGET_VTHERM: "invalid_entity"},
                )
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
            data_schema=build_user_schema(DEFAULT_OPTIONS),
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return TpiHysteresisOptionsFlow(config_entry)


class TpiHysteresisOptionsFlow(OptionsFlow):
    """Edit TPI hysteresis plugin defaults."""

    def __init__(self, config_entry) -> None:
        """Store the config entry being edited."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Handle the options flow."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        defaults = dict(DEFAULT_OPTIONS)
        defaults.update(self._config_entry.options or self._config_entry.data)
        return self.async_show_form(
            step_id="init",
            data_schema=build_options_schema(defaults),
        )
