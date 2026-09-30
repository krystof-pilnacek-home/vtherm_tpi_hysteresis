"""Hysteresis algorithm handler for the plugin runtime."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.helpers.storage import Store
from homeassistant.util import slugify

from .const import (
    CONF_ALGORITHM,
    CONF_COEF_EXT,
    CONF_COEF_INT,
    CONF_HYSTERESIS_OFF,
    CONF_HYSTERESIS_ON,
    CONF_MAX_ON_PERCENT,
    CONF_MIN_ON_PERCENT,
    CONF_TARGET_VTHERM,
    DEFAULT_ALGORITHM,
    DEFAULT_COEF_EXT,
    DEFAULT_COEF_INT,
    DEFAULT_OPTIONS,
    DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .hysteresis.controller import HysteresisController, normalize_hvac_mode

if TYPE_CHECKING:
    from vtherm_api.interfaces import (
        InterfaceCycleScheduler,
        InterfaceThermostatRuntime,
    )

_LOGGER = logging.getLogger(__name__)


class HysteresisHandler:
    """Handler implementing the VT external proportional algorithm lifecycle."""

    def __init__(self, thermostat: InterfaceThermostatRuntime) -> None:
        """Bind the handler to a VT thermostat runtime object."""
        self._thermostat = thermostat
        self._store: Store | None = None
        self._controller: HysteresisController | None = None
        self._should_publish_intermediate = True
        self._last_committed_on_percent = 0.0
        self._last_saved_state: dict[str, object] | None = None
        self._scheduler: InterfaceCycleScheduler | None = None

    def init_algorithm(self) -> None:
        """Create the algorithm instance and prepare persistence.

        VT calls this method after constructing the handler. The handler can
        read runtime configuration here and instantiate its own controller.
        """
        thermostat = self._thermostat
        config = self._get_effective_config()

        safe_name = slugify(thermostat.name)
        self._store = Store(thermostat.hass, STORAGE_VERSION, STORAGE_KEY.format(safe_name))
        self._controller = HysteresisController(
            hysteresis_on=float(config[CONF_HYSTERESIS_ON]),
            hysteresis_off=float(config[CONF_HYSTERESIS_OFF]),
            max_on_percent=float(config[CONF_MAX_ON_PERCENT]),
            min_on_percent=float(config[CONF_MIN_ON_PERCENT]),
            algorithm=str(config.get(CONF_ALGORITHM, DEFAULT_ALGORITHM)),
            coef_int=float(config.get(CONF_COEF_INT, DEFAULT_COEF_INT)),
            coef_ext=float(config.get(CONF_COEF_EXT, DEFAULT_COEF_EXT)),
        )
        thermostat.prop_algorithm = self._controller

    def _get_effective_config(self) -> dict[str, float | str]:
        """Return the merged Hysteresis configuration."""
        thermostat = self._thermostat
        config: dict[str, float | str] = dict(DEFAULT_OPTIONS)

        plugin_entries = thermostat.hass.config_entries.async_entries(DOMAIN)
        matching_entry = next(
            (
                entry
                for entry in plugin_entries
                if entry.data.get(CONF_TARGET_VTHERM) == thermostat.unique_id
            ),
            None,
        )
        global_entry = next(
            (entry for entry in plugin_entries if entry.unique_id == DOMAIN),
            None,
        )
        entry_to_apply = matching_entry or global_entry
        if entry_to_apply is not None:
            config.update(entry_to_apply.data)
            config.update(entry_to_apply.options)

        return config

    async def async_added_to_hass(self) -> None:
        """Restore persistent algorithm state.

        This hook is optional for a simple relay controller, but it is part of
        the contract and is useful to document how a plugin can keep state
        across Home Assistant restarts.
        """
        if self._store is None or self._controller is None:
            return

        try:
            data = await self._store.async_load()
            self._controller.restore_state(data)
            self._last_committed_on_percent = self._controller.on_percent
        except Exception as err:  # pragma: no cover - defensive logging path
            _LOGGER.error("%s - Failed to load Hysteresis state: %s", self._thermostat, err)

    async def async_startup(self) -> None:
        """Run startup actions after the thermostat is ready.

        SmartPI uses this hook for more advanced runtime coordination. The
        hysteresis example keeps it lightweight and simply aligns the handler
        with the current HVAC state.
        """
        await self.on_state_changed(True)

    def remove(self) -> None:
        """Release resources and persist the current controller state."""
        thermostat = self._thermostat
        if self._store is not None and self._controller is not None:
            thermostat.hass.async_create_task(self._async_save_state())

    async def _async_save_state(self) -> None:
        """Persist the controller state, tolerating a shutdown store."""
        assert self._store is not None and self._controller is not None
        try:
            self._last_saved_state = self._controller.save_state()
            await self._store.async_save(self._last_saved_state)
        except Exception as err:  # pragma: no cover - defensive logging path
            _LOGGER.error("%s - Failed to save Hysteresis state: %s", self._thermostat, err)

    def on_scheduler_ready(self, scheduler: InterfaceCycleScheduler) -> None:
        """Receive the VT cycle scheduler once it is available.

        Complex algorithms can register cycle callbacks here. The hysteresis
        example registers documented no-op callbacks so the scaffold shows where
        cycle start, cycle completion and realized power feedback are bridged.
        """
        self._scheduler = scheduler
        if self._controller is not None:
            scheduler.register_cycle_start_callback(self._controller.on_cycle_started)
            scheduler.register_cycle_end_callback(self._controller.on_cycle_completed)

    def should_publish_intermediate(self) -> bool:
        """Return True when VT may publish the current intermediate state."""
        return self._should_publish_intermediate

    def update_attributes(self) -> None:
        """Expose Hysteresis diagnostics on the thermostat."""
        if self._controller is None:
            return

        attributes = getattr(self._thermostat, "_attr_extra_state_attributes", None)
        if not isinstance(attributes, dict):
            return

        specific_states = attributes.get("specific_states")
        if not isinstance(specific_states, dict):
            return

        specific_states["hysteresis"] = self._controller.get_diagnostics()

    async def control_heating(self, timestamp=None, force: bool = False) -> None:
        """Execute one control iteration.

        VT delegates all external proportional calculations to this method. The
        handler computes an `on_percent` and forwards it to the cycle scheduler.
        """
        del timestamp
        thermostat = self._thermostat
        controller = self._controller

        if controller is None:
            return

        previous_on_percent = controller.on_percent

        if normalize_hvac_mode(thermostat.vtherm_hvac_mode) == "off":
            controller.calculate(
                target_temp=thermostat.target_temperature,
                current_temp=thermostat.current_temperature,
                hvac_mode=thermostat.vtherm_hvac_mode,
            )
            self._should_publish_intermediate = previous_on_percent != 0.0

            if thermostat.is_device_active:
                await thermostat.async_underlying_entity_turn_off()
        else:
            controller.calculate(
                target_temp=thermostat.target_temperature,
                current_temp=thermostat.current_temperature,
                ext_temp=thermostat.current_outdoor_temperature,
                hvac_mode=thermostat.vtherm_hvac_mode,
            )
            self._should_publish_intermediate = (
                force or abs(controller.on_percent - previous_on_percent) > 0.001
            )

            scheduler = self._scheduler or thermostat.cycle_scheduler
            if scheduler is not None:
                await scheduler.start_cycle(
                    thermostat.vtherm_hvac_mode,
                    controller.on_percent,
                    force=force or self._should_publish_intermediate,
                )

        self._last_committed_on_percent = controller.on_percent
        thermostat.update_custom_attributes()
        thermostat.async_write_ha_state()

        if self._store is not None and controller.save_state() != self._last_saved_state:
            thermostat.hass.async_create_task(self._async_save_state())

    async def on_state_changed(self, changed: bool) -> None:
        """React to thermostat state changes.

        SmartPI uses this for timers and learning state. The hysteresis example
        documents the same hook with a single behavior: request a fresh control
        iteration whenever VT changes a relevant state.
        """
        del changed
        await self._thermostat.async_control_heating(force=True)
