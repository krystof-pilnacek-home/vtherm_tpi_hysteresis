"""Fake versatile_thermostat integration for e2e tests.

Implements the minimal subset of the real VTherm's
``ThermostatProp``/``ThermostatOverSwitch`` lifecycle that the plugin
interacts with, mirroring ``thermostat_prop.py`` from the VTherm core:

- resolves the proportional algorithm factory from ``VThermAPI`` at entity
  creation and again at ``async_startup`` (retry when the plugin loads
  after VT, exactly like ``_init_algorithm_handler``);
- exposes the ``InterfaceThermostatRuntime`` surface (target / current /
  outdoor temperatures, hvac mode, ``prop_algorithm`` slot, cycle
  scheduler);
- delegates the control iteration to the handler's ``control_heating()``;
- publishes the plugin diagnostics via ``update_custom_attributes()``.

The entity is a real Home Assistant ``ClimateEntity`` so e2e tests drive
everything through the HA state machine and services, never private
methods.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from vtherm_api.vtherm_api import VThermAPI
from vtherm_tpi_hysteresis.const import (
    PROP_FUNCTION_TPI_HYSTERESIS,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = "versatile_thermostat"


class FakeCycleScheduler:
    """Cycle scheduler stand-in mirroring VTherm's InterfaceCycleScheduler."""

    def __init__(self) -> None:
        self.is_cycle_running = False
        self.cycle_log: list[tuple[str, float]] = []
        self._cycle_start_callbacks: list[Any] = []
        self._cycle_end_callbacks: list[Any] = []

    def register_cycle_start_callback(self, callback: Any) -> None:
        self._cycle_start_callbacks.append(callback)

    def register_cycle_end_callback(self, callback: Any) -> None:
        self._cycle_end_callbacks.append(callback)

    async def start_cycle(self, hvac_mode: Any, on_percent: float, force: bool = False) -> None:
        self.is_cycle_running = on_percent > 0
        self.cycle_log.append((str(hvac_mode), on_percent))

    async def cancel_cycle(self) -> None:
        self.is_cycle_running = False


class FakeVThermClimate(ClimateEntity):
    """Climate entity exercising the plugin lifecycle like ThermostatProp."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Fake VTherm"
    _attr_unique_id = "fake_vtherm_uid"
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF]
    _attr_temperature_unit = "°C"
    _attr_target_temperature_step = 0.1
    _attr_min_temp = 5
    _attr_max_temp = 35
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the fake thermostat from its config entry."""
        self._entry = entry
        self._attr_extra_state_attributes: dict[str, Any] = {"specific_states": {}}
        # Start in the middle of the band (inactive) like a room drifting
        # slightly below setpoint; tests then drive real temperature steps.
        self._current_temperature: float | None = 20.5
        self._current_outdoor_temperature: float | None = 15.0
        self._target_temperature: float | None = 21.0
        self._vtherm_hvac_mode = entry.data.get("hvac_mode", HVACMode.HEAT)
        self._prop_algorithm: Any = None
        self._algo_handler: Any = None
        self._cycle_scheduler = FakeCycleScheduler()
        self._is_device_active = False

    # -- runtime surface consumed by the plugin handler -----------------------

    @property
    def vtherm_hvac_mode(self) -> str:
        return self._vtherm_hvac_mode

    @property
    def current_temperature(self) -> float | None:
        return self._current_temperature

    @property
    def current_outdoor_temperature(self) -> float | None:
        return self._current_outdoor_temperature

    @property
    def target_temperature(self) -> float | None:
        return self._target_temperature

    @property
    def is_device_active(self) -> bool:
        return self._is_device_active

    @property
    def cycle_scheduler(self) -> FakeCycleScheduler:
        return self._cycle_scheduler

    async def async_underlying_entity_turn_off(self) -> None:
        """VTherm turns underlying devices off on hvac off."""
        self._is_device_active = False
        self.async_write_ha_state()

    @property
    def prop_algorithm(self) -> Any:
        return self._prop_algorithm

    @prop_algorithm.setter
    def prop_algorithm(self, value: Any) -> None:
        self._prop_algorithm = value

    @property
    def hvac_mode(self) -> HVACMode | None:
        return self._vtherm_hvac_mode

    @property
    def hvac_action(self) -> HVACAction | None:
        if self._vtherm_hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        return HVACAction.HEATING if self._is_device_active else HVACAction.IDLE

    # -- VTherm lifecycle (mirrors ThermostatProp / base_thermostat) ---------

    def _init_algorithm_handler(self) -> bool:
        """Resolve the handler factory from VThermAPI, like ThermostatProp."""
        api = VThermAPI.get_vtherm_api(self.hass)
        factory = (
            api.get_prop_algorithm(PROP_FUNCTION_TPI_HYSTERESIS)
            if api is not None and hasattr(api, "get_prop_algorithm")
            else None
        )
        if factory is not None:
            self._algo_handler = factory.create(self)
            self._algo_handler.init_algorithm()
            return True
        _LOGGER.warning("%s - External proportional algorithm not yet registered", self.entity_id)
        return False

    async def async_added_to_hass(self) -> None:
        """Run when entity is added: create the handler, restore state."""
        if self._algo_handler is None:
            self._init_algorithm_handler()
        if self._algo_handler is not None:
            await self._algo_handler.async_added_to_hass()
        # register in the climate component's entity list so service calls work
        self.async_write_ha_state()

    async def async_startup(self) -> None:
        """Startup after HA is ready: retry handler init, bind scheduler."""
        if self._algo_handler is None and not self._init_algorithm_handler():
            return
        self._algo_handler.on_scheduler_ready(self._cycle_scheduler)
        await self._algo_handler.async_startup()

    async def async_control_heating(self, timestamp=None, force: bool = False) -> bool:
        """Run one control iteration through the plugin handler."""
        if self._algo_handler is None:
            if not self._init_algorithm_handler():
                return False
        await self._algo_handler.control_heating(timestamp, force)
        algo = self._prop_algorithm
        on_percent = getattr(algo, "calculated_on_percent", 0.0) if algo else 0.0
        self._is_device_active = bool(on_percent and on_percent > 0)
        return True

    def update_custom_attributes(self) -> None:
        """Refresh extra state attributes including plugin diagnostics."""
        if self._algo_handler is not None and hasattr(self._algo_handler, "update_attributes"):
            self._algo_handler.update_attributes()
        self.async_write_ha_state()

    def recalculate(self) -> None:
        """Mirror ThermostatProp.recalculate: spurious pre-call on the proxy."""
        if self._prop_algorithm and hasattr(self._prop_algorithm, "calculate"):
            self._prop_algorithm.calculate(
                self.target_temperature,
                self._current_temperature,
                self._current_outdoor_temperature,
                None,
                self._vtherm_hvac_mode,
            )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Handle climate.set_temperature service calls."""
        if (temp := kwargs.get("temperature")) is not None:
            self._target_temperature = float(temp)
        await self.async_control_heating(force=True)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Handle climate.set_hvac_mode service calls."""
        self._vtherm_hvac_mode = hvac_mode
        await self.async_control_heating(force=True)

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_update_current_temperature(self, value: float) -> None:
        """Test hook: new room temperature then a control iteration."""
        self._current_temperature = float(value)
        # VTherm calls recalculate() on sensor updates before controlling.
        self.recalculate()
        await self.async_control_heating()
        self.async_write_ha_state()

    async def async_update_outdoor_temperature(self, value: float) -> None:
        """Test hook: new outdoor temperature then a control iteration."""
        self._current_outdoor_temperature = float(value)
        await self.async_control_heating()
        self.async_write_ha_state()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a fake VTherm climate entity from a config entry."""
    from homeassistant.components.climate import DATA_COMPONENT
    from homeassistant.helpers.entity_component import EntityComponent

    component: EntityComponent[ClimateEntity] = hass.data[DATA_COMPONENT]
    entity = FakeVThermClimate(entry)
    await component.async_add_entities([entity])
    entry.runtime_data = entity
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the fake VTherm entry."""
    entity: FakeVThermClimate | None = entry.runtime_data
    if entity is not None and hasattr(entity, "_algo_handler") and entity._algo_handler:
        entity._algo_handler.remove()
    return True
