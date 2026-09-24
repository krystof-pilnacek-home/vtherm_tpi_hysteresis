"""Unit tests for the TpiHysteresisHandler (VT plugin lifecycle).

Uses MagicMock thermostats and hass (vtherm_pellet_stove test style): no
running Home Assistant instance is required.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from vtherm_tpi_hysteresis.const import (
    CONF_HYSTERESIS_OFF,
    CONF_HYSTERESIS_ON,
    CONF_TARGET_VTHERM,
    CONF_TPI_COEF_EXT,
    CONF_TPI_COEF_INT,
    DEFAULT_OPTIONS,
    DOMAIN,
    SPECIFIC_STATES_KEY,
)
from vtherm_tpi_hysteresis.handler import (
    TpiHysteresisHandler,
    _PropAlgoProxy,
)

# ---------------------------------------------------------------------------
# Mock infrastructure
# ---------------------------------------------------------------------------


def _make_entry(data: dict, options: dict | None = None, unique_id: str = DOMAIN):
    entry = MagicMock()
    entry.data = dict(data)
    entry.options = dict(options) if options is not None else {}
    entry.unique_id = unique_id
    return entry


def _make_hass(entries: list | None = None):
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=entries or [])

    def _create_task(coro, **kwargs):
        if asyncio.iscoroutine(coro):
            coro.close()
        return MagicMock()

    hass.async_create_task = MagicMock(side_effect=_create_task)
    return hass


def _make_thermostat(
    hass,
    *,
    unique_id: str = "vt_test",
    name: str = "Test VTherm",
    target_temperature: float | None = 21.0,
    current_temperature: float | None = 20.0,
    current_outdoor_temperature: float | None = 15.0,
    vtherm_hvac_mode: str = "heat",
):
    thermostat = MagicMock()
    thermostat.hass = hass
    thermostat.unique_id = unique_id
    thermostat.name = name
    thermostat.target_temperature = target_temperature
    thermostat.current_temperature = current_temperature
    thermostat.current_outdoor_temperature = current_outdoor_temperature
    thermostat.vtherm_hvac_mode = vtherm_hvac_mode
    thermostat.prop_algorithm = None
    thermostat.cycle_scheduler = None
    thermostat.is_device_active = False
    thermostat.async_underlying_entity_turn_off = AsyncMock()
    thermostat.async_control_heating = AsyncMock(return_value=True)
    thermostat.update_custom_attributes = MagicMock()
    thermostat.async_write_ha_state = MagicMock()
    return thermostat


def _make_scheduler():
    scheduler = MagicMock()
    scheduler.start_cycle = AsyncMock()
    scheduler.register_cycle_start_callback = MagicMock()
    scheduler.register_cycle_end_callback = MagicMock()
    return scheduler


# ---------------------------------------------------------------------------
# init_algorithm / effective config
# ---------------------------------------------------------------------------


class TestInitAlgorithm:
    """init_algorithm builds the controller and exposes it to VT."""

    async def test_defaults_without_entries(self):
        hass = _make_hass([])
        thermostat = _make_thermostat(hass)
        handler = TpiHysteresisHandler(thermostat)
        handler.init_algorithm()
        controller = handler._controller
        assert controller.hysteresis_on == DEFAULT_OPTIONS[CONF_HYSTERESIS_ON]
        assert controller.hysteresis_off == DEFAULT_OPTIONS[CONF_HYSTERESIS_OFF]
        assert controller.coef_int == DEFAULT_OPTIONS[CONF_TPI_COEF_INT]
        assert controller.coef_ext == DEFAULT_OPTIONS[CONF_TPI_COEF_EXT]
        assert thermostat.prop_algorithm is handler._prop_proxy

    async def test_global_entry_overrides_defaults(self):
        hass = _make_hass([_make_entry({CONF_HYSTERESIS_ON: 0.7}, unique_id=DOMAIN)])
        thermostat = _make_thermostat(hass)
        handler = TpiHysteresisHandler(thermostat)
        handler.init_algorithm()
        assert handler._controller.hysteresis_on == 0.7
        assert handler._controller.hysteresis_off == DEFAULT_OPTIONS[CONF_HYSTERESIS_OFF]

    async def test_per_thermostat_entry_wins_over_global(self):
        global_entry = _make_entry({CONF_HYSTERESIS_ON: 0.7}, unique_id=DOMAIN)
        per_entry = _make_entry({CONF_TARGET_VTHERM: "vt_test", CONF_HYSTERESIS_ON: 1.2})
        hass = _make_hass([global_entry, per_entry])
        thermostat = _make_thermostat(hass)
        handler = TpiHysteresisHandler(thermostat)
        handler.init_algorithm()
        assert handler._controller.hysteresis_on == 1.2

    async def test_options_layer_over_data(self):
        entry = _make_entry(
            {CONF_TARGET_VTHERM: "vt_test", CONF_HYSTERESIS_ON: 0.7},
            options={CONF_HYSTERESIS_ON: 0.9},
        )
        hass = _make_hass([entry])
        thermostat = _make_thermostat(hass)
        handler = TpiHysteresisHandler(thermostat)
        handler.init_algorithm()
        assert handler._controller.hysteresis_on == 0.9

    async def test_other_thermostat_entries_ignored(self):
        entry = _make_entry(
            {CONF_TARGET_VTHERM: "vt_other", CONF_HYSTERESIS_ON: 3.0},
            unique_id=f"{DOMAIN}-vt_other",
        )
        hass = _make_hass([entry])
        thermostat = _make_thermostat(hass)
        handler = TpiHysteresisHandler(thermostat)
        handler.init_algorithm()
        assert handler._controller.hysteresis_on == DEFAULT_OPTIONS[CONF_HYSTERESIS_ON]


# ---------------------------------------------------------------------------
# prop_algorithm proxy (spurious recalculate guard)
# ---------------------------------------------------------------------------


class TestPropAlgoProxy:
    """The proxy blocks recalculate() from mutating the band state."""

    def _armed(self):
        hass = _make_hass([])
        thermostat = _make_thermostat(hass)
        handler = TpiHysteresisHandler(thermostat)
        handler.init_algorithm()
        controller = handler._controller
        controller.calculate(21.0, 20.0, 15.0, hvac_mode="heat")
        return controller, thermostat.prop_algorithm

    def test_proxy_is_read_only(self):
        controller, proxy = self._armed()
        assert isinstance(proxy, _PropAlgoProxy)
        assert controller.is_active is True
        # spurious recalculate-style call must not change the band state
        out = proxy.calculate(21.0, 23.0, 15.0, 0.0, "heat")
        assert controller.is_active is True
        assert out == pytest.approx(1.0)  # still returns a sensible value

    def test_proxy_exposes_on_percent(self):
        controller, proxy = self._armed()
        assert proxy.on_percent == pytest.approx(1.0)
        assert proxy.calculated_on_percent == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# control_heating
# ---------------------------------------------------------------------------


class TestControlHeating:
    """The delegated control iteration commits via the cycle scheduler."""

    def _handler(self, hvac_mode="heat", current=20.0, target=21.0, outdoor=15.0):
        hass = _make_hass([])
        thermostat = _make_thermostat(
            hass,
            vtherm_hvac_mode=hvac_mode,
            current_temperature=current,
            target_temperature=target,
            current_outdoor_temperature=outdoor,
        )
        handler = TpiHysteresisHandler(thermostat)
        handler.init_algorithm()
        return handler, thermostat

    async def test_activation_sends_start_cycle(self):
        handler, thermostat = self._handler()
        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)
        await handler.control_heating()
        # raw TPI = 1.0*1 + 0.1*6 = 1.6 -> clamp 1.0
        scheduler.start_cycle.assert_awaited_once()
        args = scheduler.start_cycle.await_args
        assert args.args[0] == "heat"
        assert args.args[1] == pytest.approx(1.0)

    async def test_hold_in_band_tapers_output(self):
        handler, thermostat = self._handler(current=20.5)
        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)
        await handler.control_heating()  # 0.5 deficit is inside the dead band
        assert handler._controller.is_active is False
        # activate at a real 1.0+ deficit
        thermostat.current_temperature = 19.9
        await handler.control_heating()
        assert scheduler.start_cycle.await_count == 2
        on = scheduler.start_cycle.await_args.args[1]
        assert on == pytest.approx(1.0)
        # taper inside the band: raw = 1.0*0.2 + 0.1*6 = 0.8
        thermostat.current_temperature = 20.8
        await handler.control_heating()
        on = scheduler.start_cycle.await_args.args[1]
        assert on == pytest.approx(0.8)
        assert handler._controller.last_reason == "hold_in_band"

    async def test_deactivation_sends_zero(self):
        handler, thermostat = self._handler()
        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)
        await handler.control_heating()
        assert handler._controller.is_active is True
        thermostat.current_temperature = 21.5
        await handler.control_heating()
        assert handler._controller.is_active is False
        on = scheduler.start_cycle.await_args.args[1]
        assert on == 0.0

    async def test_hvac_off_turns_device_off(self):
        handler, thermostat = self._handler()
        await handler.control_heating()
        assert handler._controller.is_active is True
        thermostat.vtherm_hvac_mode = "off"
        thermostat.is_device_active = True
        await handler.control_heating()
        assert handler._controller.is_active is False
        thermostat.async_underlying_entity_turn_off.assert_awaited_once()

    async def test_should_publish_intermediate_on_change_only(self):
        handler, thermostat = self._handler()
        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)
        await handler.control_heating()
        assert handler.should_publish_intermediate() is True
        # same temperatures -> no change -> do not republish
        await handler.control_heating()
        assert handler.should_publish_intermediate() is False

    async def test_no_scheduler_falls_back_to_thermostat_scheduler(self):
        handler, thermostat = self._handler()
        fallback = _make_scheduler()
        thermostat.cycle_scheduler = fallback
        await handler.control_heating()
        fallback.start_cycle.assert_awaited_once()

    async def test_persists_state_after_iteration(self):
        handler, thermostat = self._handler()
        await handler.control_heating()
        # hass.async_create_task was called for the Store save
        assert thermostat.hass.async_create_task.called

    async def test_update_attributes_populates_specific_states(self):
        handler, thermostat = self._handler()
        attributes = {"specific_states": {}}
        thermostat._attr_extra_state_attributes = attributes
        await handler.control_heating()
        handler.update_attributes()
        assert SPECIFIC_STATES_KEY in attributes["specific_states"]
        diag = attributes["specific_states"][SPECIFIC_STATES_KEY]
        assert diag["is_active"] is True
        assert diag["hysteresis_on"] == 1.0

    async def test_update_attributes_without_attributes_dict_is_noop(self):
        handler, thermostat = self._handler()
        thermostat._attr_extra_state_attributes = None
        handler.update_attributes()  # must not raise

    async def test_control_before_init_is_noop(self):
        hass = _make_hass([])
        thermostat = _make_thermostat(hass)
        handler = TpiHysteresisHandler(thermostat)
        await handler.control_heating()  # must not raise


# ---------------------------------------------------------------------------
# Lifecycle hooks
# ---------------------------------------------------------------------------


class TestLifecycleHooks:
    """async_startup / on_state_changed / remove wiring."""

    async def test_async_startup_triggers_control(self):
        hass = _make_hass([])
        thermostat = _make_thermostat(hass)
        handler = TpiHysteresisHandler(thermostat)
        handler.init_algorithm()
        await handler.async_startup()
        thermostat.async_control_heating.assert_awaited_once_with(force=True)

    async def test_on_state_changed_triggers_control(self):
        hass = _make_hass([])
        thermostat = _make_thermostat(hass)
        handler = TpiHysteresisHandler(thermostat)
        handler.init_algorithm()
        await handler.on_state_changed(True)
        thermostat.async_control_heating.assert_awaited_once_with(force=True)

    async def test_remove_persists_state(self):
        hass = _make_hass([])
        thermostat = _make_thermostat(hass)
        handler = TpiHysteresisHandler(thermostat)
        handler.init_algorithm()
        handler._controller.calculate(21.0, 20.0, hvac_mode="heat")
        handler.remove()
        assert hass.async_create_task.called

    async def test_on_scheduler_ready_registers_cycle_callbacks(self):
        hass = _make_hass([])
        thermostat = _make_thermostat(hass)
        handler = TpiHysteresisHandler(thermostat)
        handler.init_algorithm()
        scheduler = _make_scheduler()
        handler.on_scheduler_ready(scheduler)
        assert scheduler.register_cycle_start_callback.called
        assert scheduler.register_cycle_end_callback.called
        assert handler._scheduler is scheduler
