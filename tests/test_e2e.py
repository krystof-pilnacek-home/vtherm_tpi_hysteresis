"""End-to-end tests for the composable regulation plugin.

The fake VTherm (``tests/fake_vtherm.py``) mirrors the VTherm
``ThermostatProp`` plugin lifecycle (factory resolution via VThermAPI,
init_algorithm, async_added_to_hass, async_startup, control iteration
delegation to the handler's ``control_heating``, scheduler binding,
persistence via HA Store, spurious pre-call on the prop_algorithm proxy).

The e2e tests drive everything through public HA APIs only
(climate.set_temperature / set_hvac_mode services and entity state),
following the stove_controller test conventions.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vtherm_tpi_hysteresis.const import (
    CONF_HYSTERESIS_OFF,
    CONF_HYSTERESIS_ON,
    CONF_MAX_ON_PERCENT,
    CONF_MIN_ON_PERCENT,
    CONF_PROP_FUNCTION,
    CONF_TARGET_VTHERM,
    DEFAULT_OPTIONS,
    DOMAIN,
    PROP_FUNCTION_TPI_HYSTERESIS,
)

#: Key under thermostat extra-state attributes where upstream publishes
#: the plugin diagnostics.
SPECIFIC_STATES_KEY = "hysteresis"

pytest_plugins = "pytest_homeassistant_custom_component"

VT_DOMAIN = "versatile_thermostat"
CLIMATE = "climate.fake_vtherm"

TEST_HYSTERESIS_ON = 1.0
TEST_HYSTERESIS_OFF = 0.5
TEST_OUTDOOR = 15.0


# ===========================================================================
# Fixtures
# ===========================================================================


async def _setup_integration(
    hass: HomeAssistant,
    *,
    outdoor: float = TEST_OUTDOOR,
    plugin_options: dict | None = None,
):
    """Set up the plugin's global-defaults entry and the fake VTherm."""
    data = dict(DEFAULT_OPTIONS)
    data[CONF_HYSTERESIS_ON] = TEST_HYSTERESIS_ON
    data[CONF_HYSTERESIS_OFF] = TEST_HYSTERESIS_OFF
    if plugin_options:
        data.update(plugin_options)
    plugin_entry = MockConfigEntry(
        domain=DOMAIN,
        data=data,
        unique_id=DOMAIN,
        entry_id="plugin_global",
        version=1,
    )
    plugin_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(plugin_entry.entry_id)
    await hass.async_block_till_done()

    vt_entry = MockConfigEntry(
        domain=VT_DOMAIN,
        data={
            CONF_PROP_FUNCTION: PROP_FUNCTION_TPI_HYSTERESIS,
            "hvac_mode": "heat",
        },
        unique_id="fake_vtherm_uid",
        entry_id="vt_entry",
        version=1,
    )
    vt_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(vt_entry.entry_id)
    await hass.async_block_till_done()

    entity = vt_entry.runtime_data
    assert entity is not None, "fake VTherm entity was not created"
    entity._current_outdoor_temperature = outdoor
    # Startup: the fake VTherm binds the scheduler and runs the first control
    await entity.async_startup()
    await hass.async_block_till_done()
    return entity


@pytest.fixture
async def vtherm(hass, hass_config_dir, enable_custom_integrations):
    """Fake VTherm thermostat driven by the tpi_hysteresis_regulation plugin."""
    entity = await _setup_integration(hass)
    yield entity
    # teardown: persist handler state via remove() like VTherm's
    # remove_thermostat does
    if entity._algo_handler is not None:
        entity._algo_handler.remove()
    await hass.async_block_till_done()


def diagnostics(hass: HomeAssistant) -> dict:
    """Read the plugin diagnostics from the climate entity attributes."""
    state = hass.states.get(CLIMATE)
    assert state is not None
    specific = state.attributes.get("specific_states", {})
    return specific.get(SPECIFIC_STATES_KEY, {})


async def set_room_temp(entity, hass: HomeAssistant, value: float) -> None:
    """Simulate a room temperature sensor update."""
    await entity.async_update_current_temperature(value)
    await hass.async_block_till_done()


async def set_setpoint(hass: HomeAssistant, target: float) -> None:
    """Change the setpoint via the climate.set_temperature service."""
    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": CLIMATE, "temperature": target},
        blocking=True,
    )
    await hass.async_block_till_done()


async def set_mode(hass: HomeAssistant, mode: str) -> None:
    """Change the HVAC mode via the climate.set_hvac_mode service."""
    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": CLIMATE, "hvac_mode": mode},
        blocking=True,
    )
    await hass.async_block_till_done()


# ===========================================================================
# Group 1: band edges with the default on_off algorithm
# ===========================================================================


class TestBandEdges:
    """Band-edge behavior with the 0.3 / 0.3 thresholds."""

    async def test_valve_stays_closed_inside_dead_band(self, hass, vtherm):
        """Below-threshold deficit never activates regulation."""
        await set_setpoint(hass, 21.0)
        # 0.5 deficit: inside the dead band, never activated -> stays off
        await set_room_temp(vtherm, hass, 20.5)
        diag = diagnostics(hass)
        assert diag["is_active"] is False
        assert diag["on_percent"] == 0.0
        assert diag["last_reason"] == "hold_in_band"
        assert vtherm.is_device_active is False

    async def test_activation_goes_full_power(self, hass, vtherm):
        """At the activation threshold the on_off preset requests 100%."""
        await set_setpoint(hass, 21.0)
        await set_room_temp(vtherm, hass, 20.0)
        diag = diagnostics(hass)
        assert diag["is_active"] is True
        assert diag["algorithm"] == "on_off"
        assert diag["on_percent"] == pytest.approx(1.0)
        assert diag["last_reason"] == "below_activation_threshold"

    async def test_deactivation_forces_zero(self, hass, vtherm):
        """Above the deactivation threshold the output is forced to 0."""
        await set_setpoint(hass, 21.0)
        await set_room_temp(vtherm, hass, 20.0)
        assert diagnostics(hass)["is_active"] is True
        await set_room_temp(vtherm, hass, 21.5)
        diag = diagnostics(hass)
        assert diag["is_active"] is False
        assert diag["on_percent"] == 0.0
        assert diag["last_reason"] == "above_deactivation_threshold"

    async def test_rearm_after_deactivation(self, hass, vtherm):
        """After deactivation the valve re-arms at the activation edge."""
        await set_setpoint(hass, 21.0)
        await set_room_temp(vtherm, hass, 21.5)
        assert diagnostics(hass)["is_active"] is False
        await set_room_temp(vtherm, hass, 20.0)
        assert diagnostics(hass)["is_active"] is True


# ===========================================================================
# Group 2: hold-in-band relay memory
# ===========================================================================


class TestHoldInBand:
    """Hold-state semantics: relay memory inside the band."""

    async def test_active_holds_full_power_inside_band(self, hass, vtherm):
        """While held active the on_off preset keeps requesting max."""
        await set_setpoint(hass, 21.0)
        await set_room_temp(vtherm, hass, 20.0)
        assert diagnostics(hass)["is_active"] is True
        # 0.2 deficit: inside the band, state held
        await set_room_temp(vtherm, hass, 20.8)
        diag = diagnostics(hass)
        assert diag["is_active"] is True
        assert diag["on_percent"] == pytest.approx(1.0)
        assert diag["last_reason"] == "hold_in_band"

    async def test_inactive_stays_off_inside_band(self, hass, vtherm):
        """A never-activated controller stays off inside the band."""
        await set_setpoint(hass, 21.0)
        await set_room_temp(vtherm, hass, 20.5)
        diag = diagnostics(hass)
        assert diag["is_active"] is False
        assert diag["on_percent"] == 0.0
        assert diag["last_reason"] == "hold_in_band"

    async def test_no_flap_across_band_edges(self, hass, vtherm):
        """Walking up then down through the band must not flap the relay."""
        await set_setpoint(hass, 21.0)
        # activate
        await set_room_temp(vtherm, hass, 19.9)
        assert diagnostics(hass)["is_active"] is True
        # walk up inside the band: stays active all the way
        for temp in (20.5, 20.8, 21.0, 21.2):
            await set_room_temp(vtherm, hass, temp)
            assert diagnostics(hass)["is_active"] is True, temp
        # past the upper edge: off
        await set_room_temp(vtherm, hass, 21.6)
        assert diagnostics(hass)["is_active"] is False
        # walk back down inside the band: stays off all the way
        for temp in (21.4, 21.0, 20.8, 20.2):
            await set_room_temp(vtherm, hass, temp)
            assert diagnostics(hass)["is_active"] is False, temp


# ===========================================================================
# Group 3: degenerate band - on_off without hysteresis
# ===========================================================================


class TestNoHysteresis:
    """Zero thresholds remove the band: pure on_off to the setpoint."""

    async def test_zero_band_regulates_exactly_to_setpoint(
        self, hass, hass_config_dir, enable_custom_integrations
    ):
        entity = await _setup_integration(
            hass,
            plugin_options={CONF_HYSTERESIS_ON: 0.0, CONF_HYSTERESIS_OFF: 0.0},
        )
        try:
            await set_setpoint(hass, 21.0)
            await set_room_temp(entity, hass, 20.9)
            assert diagnostics(hass)["is_active"] is True
            # above the setpoint: deactivates immediately, no hold band
            await set_room_temp(entity, hass, 21.1)
            diag = diagnostics(hass)
            assert diag["is_active"] is False
            assert diag["last_reason"] == "above_deactivation_threshold"
        finally:
            if entity._algo_handler is not None:
                entity._algo_handler.remove()


# ===========================================================================
# Group 4: HVAC modes
# ===========================================================================


class TestHvacModes:
    """HVAC mode handling through the public service API."""

    async def test_hvac_off_deactivates_and_turns_device_off(self, hass, vtherm):
        await set_setpoint(hass, 21.0)
        await set_room_temp(vtherm, hass, 20.0)
        assert diagnostics(hass)["is_active"] is True
        await set_mode(hass, "off")
        diag = diagnostics(hass)
        assert diag["is_active"] is False
        assert diag["last_reason"] == "hvac_off"
        assert vtherm.is_device_active is False

    async def test_cool_mode_mirrors_band(self, hass, vtherm):
        """Cool mode activates above target + hysteresis_on."""
        await set_mode(hass, "cool")
        await set_setpoint(hass, 21.0)
        await set_room_temp(vtherm, hass, 22.0)
        diag = diagnostics(hass)
        assert diag["is_active"] is True
        assert diag["on_percent"] == pytest.approx(1.0)
        await set_room_temp(vtherm, hass, 20.5)
        assert diagnostics(hass)["is_active"] is False


# ===========================================================================
# Group 5: lifecycle - scheduler, persistence, proxy
# ===========================================================================


class TestLifecycle:
    """Plugin lifecycle integration with the fake VTherm runtime."""

    async def test_scheduler_receives_start_cycle(self, hass, vtherm):
        """The handler forwards (hvac_mode, on_percent) to the scheduler."""
        await set_setpoint(hass, 21.0)
        await set_room_temp(vtherm, hass, 20.0)
        log = vtherm.cycle_scheduler.cycle_log
        assert log, "scheduler never received a start_cycle"
        assert log[-1] == ("heat", pytest.approx(1.0))

    async def test_handler_restart_restores_band_state(self, hass, vtherm):
        """A restarted handler restores is_active from the HA Store."""
        await set_setpoint(hass, 21.0)
        await set_room_temp(vtherm, hass, 20.0)
        assert diagnostics(hass)["is_active"] is True

        handler = vtherm._algo_handler
        new_handler = type(handler)(vtherm)
        new_handler.init_algorithm()
        await new_handler.async_added_to_hass()

        diag = new_handler._controller.get_diagnostics()
        assert diag["is_active"] is True
        assert diag["algorithm"] == "on_off"

    async def test_prop_algorithm_is_the_controller(self, hass, vtherm):
        """prop_algorithm exposes the live controller to VTherm internals.

        Upstream exposes the controller directly; VTherm's recalculate()
        pre-call can therefore flip the band state before the authoritative
        control iteration - identical to the upstream plugin.
        """
        await set_setpoint(hass, 21.0)
        await set_room_temp(vtherm, hass, 20.9)
        assert diagnostics(hass)["is_active"] is False
        algo = vtherm.prop_algorithm
        assert algo is not None
        # pre-call below the activation threshold (21.0 - 1.0) activates the
        # band state and returns full power
        assert algo.calculate(21.0, 19.9, 15.0, None, "heat") == 1.0
        # the authoritative iteration at 20.9 is in-band: without the
        # pre-call it would stay inactive, with it the active state holds
        await vtherm.async_control_heating()
        diag = diagnostics(hass)
        assert diag["is_active"] is True
        assert diag["last_reason"] == "hold_in_band"


# ===========================================================================
# Group 6: per-thermostat override
# ===========================================================================


class TestPerThermostatOverride:
    """Per-thermostat entries override global defaults."""

    async def test_override_applies_to_matching_thermostat(
        self, hass, hass_config_dir, enable_custom_integrations
    ):
        plugin_global = MockConfigEntry(
            domain=DOMAIN,
            data=dict(DEFAULT_OPTIONS),
            unique_id=DOMAIN,
            entry_id="plugin_global",
            version=1,
        )
        plugin_global.add_to_hass(hass)

        plugin_override = MockConfigEntry(
            domain=DOMAIN,
            data={
                **dict(DEFAULT_OPTIONS),
                CONF_TARGET_VTHERM: "fake_vtherm_uid",
                CONF_HYSTERESIS_ON: 2.0,
            },
            unique_id=f"{DOMAIN}-fake_vtherm_uid",
            entry_id="plugin_override",
            version=1,
        )
        plugin_override.add_to_hass(hass)

        assert await hass.config_entries.async_setup(plugin_global.entry_id)
        await hass.async_block_till_done()

        vt_entry = MockConfigEntry(
            domain=VT_DOMAIN,
            data={
                CONF_PROP_FUNCTION: PROP_FUNCTION_TPI_HYSTERESIS,
                "hvac_mode": "heat",
            },
            unique_id="fake_vtherm_uid",
            entry_id="vt_entry",
            version=1,
        )
        vt_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(vt_entry.entry_id)
        await hass.async_block_till_done()

        entity = vt_entry.runtime_data
        await entity.async_startup()
        await hass.async_block_till_done()

        try:
            # Override: hysteresis_on = 2.0 -> a 1.0 deficit no longer activates
            await set_setpoint(hass, 21.0)
            await set_room_temp(entity, hass, 20.0)
            assert diagnostics(hass)["is_active"] is False
            # 2.0 deficit activates
            await set_room_temp(entity, hass, 19.0)
            diag = diagnostics(hass)
            assert diag["is_active"] is True
            assert diag["hysteresis_on"] == pytest.approx(2.0)
            # deactivation at 21 + 0.5 (global default still applies)
            await set_room_temp(entity, hass, 21.5)
            assert diagnostics(hass)["is_active"] is False
        finally:
            if entity._algo_handler is not None:
                entity._algo_handler.remove()


# ===========================================================================
# Group 7: algorithm option end to end
# ===========================================================================


class TestAlgorithmOption:
    """The algorithm config option flows through to the controller."""

    async def test_default_is_on_off(self, hass, vtherm):
        await set_setpoint(hass, 21.0)
        await set_room_temp(vtherm, hass, 20.0)
        assert diagnostics(hass)["algorithm"] == "on_off"

    async def test_custom_power_limits_via_options(
        self, hass, hass_config_dir, enable_custom_integrations
    ):
        entity = await _setup_integration(
            hass,
            plugin_options={CONF_MAX_ON_PERCENT: 0.7, CONF_MIN_ON_PERCENT: 0.1},
        )
        try:
            await set_setpoint(hass, 21.0)
            await set_room_temp(entity, hass, 20.0)
            diag = diagnostics(hass)
            assert diag["is_active"] is True
            assert diag["on_percent"] == pytest.approx(0.7)
            await set_room_temp(entity, hass, 21.5)
            assert diagnostics(hass)["on_percent"] == pytest.approx(0.1)
        finally:
            if entity._algo_handler is not None:
                entity._algo_handler.remove()
