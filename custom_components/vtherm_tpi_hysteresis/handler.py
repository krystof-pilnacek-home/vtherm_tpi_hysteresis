"""TPI + hysteresis algorithm handler for the VTherm plugin runtime."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.storage import Store
from homeassistant.util import slugify

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
    SPECIFIC_STATES_KEY,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .tpi_hysteresis.controller import (
    HVAC_MODE_OFF,
    TpiHysteresisController,
    normalize_hvac_mode,
)

if TYPE_CHECKING:
    from vtherm_api.interfaces import InterfaceCycleScheduler, InterfaceThermostatRuntime

_LOGGER = logging.getLogger(__name__)

#: Minimum on_percent delta that justifies republishing an intermediate state.
_PUBLISH_EPSILON = 0.001


class _PropAlgoProxy:
    """Read-only proxy exposing the controller's on_percent to VTherm.

    VTherm's ``ThermostatProp.recalculate()`` calls
    ``prop_algorithm.calculate()`` on every temperature-sensor update
    **before** ``async_control_heating()`` reaches our handler.  That spurious
    first call would mutate the band's hold state outside of the authoritative
    control iteration.  Placing this proxy as ``prop_algorithm`` instead of the
    controller keeps ``recalculate()`` a no-op for the band state machine while
    still letting VTherm read ``on_percent`` / ``calculated_on_percent`` at any
    time.  The authoritative ``calculate()`` call is the one made in
    ``TpiHysteresisHandler.control_heating()``.
    """

    def __init__(self, controller: TpiHysteresisController) -> None:
        self._controller = controller

    @property
    def on_percent(self) -> float | None:
        return self._controller.on_percent

    @property
    def calculated_on_percent(self) -> float:
        return self._controller.calculated_on_percent

    def calculate(self, *_args: Any, **_kwargs: Any) -> float:
        """No-op: the authoritative calculation lives in control_heating()."""
        return self._controller.calculated_on_percent


class TpiHysteresisHandler:
    """Handler implementing the VT external proportional algorithm lifecycle."""

    def __init__(self, thermostat: InterfaceThermostatRuntime) -> None:
        """Bind the handler to a VT thermostat runtime object."""
        self._thermostat = thermostat
        self._store: Store | None = None
        self._controller: TpiHysteresisController | None = None
        self._prop_proxy: _PropAlgoProxy | None = None
        self._should_publish_intermediate = True
        self._last_committed_on_percent = 0.0
        self._scheduler: InterfaceCycleScheduler | None = None

    # -- InterfacePropAlgorithmHandler contract ------------------------------

    def init_algorithm(self) -> None:
        """Read the effective config, build the controller, expose it to VT.

        VT calls this method right after constructing the handler.
        """
        thermostat = self._thermostat
        config = self._get_effective_config()
        safe_name = slugify(thermostat.name)
        self._store = Store(thermostat.hass, STORAGE_VERSION, STORAGE_KEY.format(safe_name))
        self._controller = TpiHysteresisController(
            hysteresis_on=float(config[CONF_HYSTERESIS_ON]),
            hysteresis_off=float(config[CONF_HYSTERESIS_OFF]),
            coef_int=float(config[CONF_TPI_COEF_INT]),
            coef_ext=float(config[CONF_TPI_COEF_EXT]),
            min_on_percent=float(config[CONF_MIN_ON_PERCENT]),
            max_on_percent=float(config[CONF_MAX_ON_PERCENT]),
        )
        self._prop_proxy = _PropAlgoProxy(self._controller)
        thermostat.prop_algorithm = self._prop_proxy

    async def async_added_to_hass(self) -> None:
        """Restore the persisted band state from the HA Store."""
        if self._store is None or self._controller is None:
            return
        try:
            data = await self._store.async_load()
            if data:
                self._controller.restore_state(data)
                self._last_committed_on_percent = self._controller.calculated_on_percent
        except Exception as err:  # pragma: no cover - defensive logging path
            _LOGGER.error("%s - Failed to load TPI hysteresis state: %s", self._thermostat, err)

    async def async_startup(self) -> None:
        """Align the handler with the current HVAC state after VT startup."""
        await self.on_state_changed(True)

    def remove(self) -> None:
        """Persist the current band state and release resources."""
        thermostat = self._thermostat
        if self._store is not None and self._controller is not None:
            thermostat.hass.async_create_task(self._store.async_save(self._controller.save_state()))

    def on_scheduler_ready(self, scheduler: InterfaceCycleScheduler) -> None:
        """Receive the VT cycle scheduler once it is available.

        The controller exposes documented no-op cycle callbacks
        (``on_cycle_started`` / ``on_cycle_completed``) so the scaffold shows
        where cycle start, cycle completion and realized power feedback are
        bridged for more advanced algorithms.
        """
        self._scheduler = scheduler
        if self._controller is not None:
            scheduler.register_cycle_start_callback(self._controller.on_cycle_started)
            scheduler.register_cycle_end_callback(self._controller.on_cycle_completed)

    def should_publish_intermediate(self) -> bool:
        """Return True when VT may publish the current intermediate state."""
        return self._should_publish_intermediate

    def update_attributes(self) -> None:
        """Expose TPI hysteresis diagnostics on the thermostat entity.

        The diagnostics land under
        ``specific_states["tpi_hysteresis"]`` in the climate entity's
        extra state attributes.
        """
        if self._controller is None:
            return
        attributes = getattr(self._thermostat, "_attr_extra_state_attributes", None)
        if not isinstance(attributes, dict):
            return
        specific_states = attributes.get("specific_states")
        if not isinstance(specific_states, dict):
            return
        specific_states[SPECIFIC_STATES_KEY] = self._controller.get_diagnostics()

    async def control_heating(self, timestamp=None, force: bool = False) -> None:
        """Execute one control iteration.

        VT delegates all external proportional calculations to this method.
        The handler computes an ``on_percent`` from the pure controller and
        forwards it to the cycle scheduler.
        """
        del timestamp
        thermostat = self._thermostat
        controller = self._controller
        if controller is None:
            return

        hvac_mode = thermostat.vtherm_hvac_mode
        mode = normalize_hvac_mode(hvac_mode)

        controller.calculate(
            target_temp=thermostat.target_temperature,
            current_temp=thermostat.current_temperature,
            ext_current_temp=thermostat.current_outdoor_temperature,
            hvac_mode=hvac_mode,
        )

        if mode == HVAC_MODE_OFF:
            self._should_publish_intermediate = self._last_committed_on_percent != 0.0
            if thermostat.is_device_active:
                await thermostat.async_underlying_entity_turn_off()
        else:
            self._should_publish_intermediate = (
                force
                or abs(controller.calculated_on_percent - self._last_committed_on_percent)
                > _PUBLISH_EPSILON
            )
            scheduler = self._scheduler or thermostat.cycle_scheduler
            if scheduler is not None:
                await scheduler.start_cycle(
                    hvac_mode,
                    controller.calculated_on_percent,
                    force=force or self._should_publish_intermediate,
                )

        self._last_committed_on_percent = controller.calculated_on_percent
        thermostat.update_custom_attributes()
        thermostat.async_write_ha_state()
        if self._store is not None:
            thermostat.hass.async_create_task(self._store.async_save(controller.save_state()))

    async def on_state_changed(self, changed: bool) -> None:
        """React to thermostat state changes with a fresh control iteration."""
        del changed
        await self._thermostat.async_control_heating(force=True)

    # -- Internal helpers ------------------------------------------------------

    def _get_effective_config(self) -> dict[str, Any]:
        """Return the merged plugin configuration for this thermostat.

        Layering: DEFAULT_OPTIONS <- global entry (``unique_id == DOMAIN``)
        <- per-thermostat entry (``CONF_TARGET_VTHERM == thermostat.unique_id``),
        with ``entry.data`` then ``entry.options`` applied on top.
        """
        thermostat = self._thermostat
        config: dict[str, Any] = dict(DEFAULT_OPTIONS)
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
