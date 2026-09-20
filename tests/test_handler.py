"""Tests for the hysteresis handler cycle forcing behavior."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vtherm_hysteresis.handler import HysteresisHandler
from custom_components.vtherm_hysteresis.hysteresis.controller import HysteresisController


def _make_thermostat() -> MagicMock:
    """Create a minimal thermostat runtime mock for handler tests."""
    thermostat = MagicMock()
    thermostat.vtherm_hvac_mode = "heat"
    thermostat.target_temperature = 20.0
    thermostat.current_temperature = 20.0
    thermostat.cycle_scheduler = None
    thermostat.update_custom_attributes = MagicMock()
    thermostat.async_write_ha_state = MagicMock()
    thermostat.hass = MagicMock()
    thermostat.hass.async_create_task = MagicMock()
    thermostat._attr_extra_state_attributes = {"specific_states": {}}
    return thermostat


@pytest.mark.asyncio
async def test_control_heating_forces_cycle_restart_below_lower_threshold() -> None:
    """A lower-threshold crossing must force an immediate new cycle."""
    thermostat = _make_thermostat()
    thermostat.current_temperature = 19.6
    scheduler = AsyncMock()

    controller = HysteresisController(hysteresis_on=0.3, hysteresis_off=0.5)
    handler = HysteresisHandler(thermostat)
    handler._controller = controller
    handler._scheduler = scheduler

    await handler.control_heating(force=False)

    scheduler.start_cycle.assert_awaited_once_with("heat", 1.0, force=True)
    assert handler.should_publish_intermediate() is True
    assert controller.is_active is True
    assert controller.last_reason == "below_activation_threshold"


@pytest.mark.asyncio
async def test_control_heating_forces_cycle_restart_above_upper_threshold() -> None:
    """An upper-threshold crossing must force an immediate new cycle."""
    thermostat = _make_thermostat()
    thermostat.current_temperature = 20.6
    scheduler = AsyncMock()

    controller = HysteresisController(hysteresis_on=0.3, hysteresis_off=0.5)
    controller.restore_state({"is_active": True, "hvac_mode": "heat", "last_reason": "manual"})

    handler = HysteresisHandler(thermostat)
    handler._controller = controller
    handler._scheduler = scheduler

    await handler.control_heating(force=False)

    scheduler.start_cycle.assert_awaited_once_with("heat", 0.0, force=True)
    assert handler.should_publish_intermediate() is True
    assert controller.is_active is False
    assert controller.last_reason == "above_deactivation_threshold"


@pytest.mark.asyncio
async def test_control_heating_forces_cool_cycle_restart_above_activation_threshold() -> None:
    """A cooling activation crossing must force an immediate new cycle."""
    thermostat = _make_thermostat()
    thermostat.vtherm_hvac_mode = "cool"
    thermostat.current_temperature = 20.4
    scheduler = AsyncMock()

    controller = HysteresisController(hysteresis_on=0.3, hysteresis_off=0.5)
    handler = HysteresisHandler(thermostat)
    handler._controller = controller
    handler._scheduler = scheduler

    await handler.control_heating(force=False)

    scheduler.start_cycle.assert_awaited_once_with("cool", 1.0, force=True)
    assert handler.should_publish_intermediate() is True
    assert controller.is_active is True
    assert controller.last_reason == "above_activation_threshold"


@pytest.mark.asyncio
async def test_control_heating_forces_cool_cycle_restart_below_deactivation_threshold() -> None:
    """A cooling deactivation crossing must force an immediate new cycle."""
    thermostat = _make_thermostat()
    thermostat.vtherm_hvac_mode = "cool"
    thermostat.current_temperature = 19.4
    scheduler = AsyncMock()

    controller = HysteresisController(hysteresis_on=0.3, hysteresis_off=0.5)
    controller.restore_state({"is_active": True, "hvac_mode": "cool", "last_reason": "manual"})

    handler = HysteresisHandler(thermostat)
    handler._controller = controller
    handler._scheduler = scheduler

    await handler.control_heating(force=False)

    scheduler.start_cycle.assert_awaited_once_with("cool", 0.0, force=True)
    assert handler.should_publish_intermediate() is True
    assert controller.is_active is False
    assert controller.last_reason == "below_deactivation_threshold"


def test_update_attributes_exposes_hysteresis_diagnostics() -> None:
    """The handler must publish Hysteresis tracking attributes."""
    thermostat = _make_thermostat()
    controller = HysteresisController(hysteresis_on=0.3, hysteresis_off=0.5)
    controller.calculate(target_temp=20.0, current_temp=20.4, hvac_mode="cool")

    handler = HysteresisHandler(thermostat)
    handler._controller = controller

    handler.update_attributes()

    assert thermostat._attr_extra_state_attributes["specific_states"]["hysteresis"][
        "last_reason"
    ] == "above_activation_threshold"
    assert thermostat._attr_extra_state_attributes["specific_states"]["hysteresis"][
        "is_active"
    ] is True
