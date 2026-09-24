"""End-to-end tests for the vtherm_tpi_hysteresis plugin.

These tests drive the plugin ONLY through the Home Assistant-facing API
(stove_controller test conventions, test_e2e_final.py style):

- climate.set_temperature / climate.set_hvac_mode services for setpoint and
  mode changes;
- temperature updates through the fake VTherm's public update hooks, which
  mirror what VTherm does on temperature-sensor state changes (recalculate()
  pre-call on the prop_algorithm proxy + control iteration via the handler);
- controller observations via hass.states.

No private plugin methods are called and no private attributes are asserted
on, except the diagnostics payload which VTherm exposes publicly as
``specific_states.tpi_hysteresis`` in the climate entity attributes.

The VTherm side is a real ClimateEntity (tests/fake_vtherm.py) that
implements the same plugin lifecycle as VTherm's ThermostatProp: factory
resolution via VThermAPI, init_algorithm, async_added_to_hass,
on_scheduler_ready, async_startup, control_heating delegation,
update_custom_attributes.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vtherm_tpi_hysteresis.const import (
    CONF_HYSTERESIS_ON,
    CONF_PROP_FUNCTION,
    CONF_TARGET_VTHERM,
    CONF_TPI_COEF_EXT,
    CONF_TPI_COEF_INT,
    DEFAULT_OPTIONS,
    DOMAIN,
    PROP_FUNCTION_TPI_HYSTERESIS,
    SPECIFIC_STATES_KEY,
)

pytest_plugins = "pytest_homeassistant_custom_component"

VT_DOMAIN = "versatile_thermostat"
CLIMATE = "climate.fake_vtherm"

# Issue #1 defaults used by the fixtures
TEST_HYSTERESIS_ON = 1.0
TEST_HYSTERESIS_OFF = 0.5
TEST_COEF_INT = 1.0
TEST_COEF_EXT = 0.1
TEST_OUTDOOR = 15.0


# ===========================================================================
# Fixtures
# ===========================================================================


async def _setup_integration(hass: HomeAssistant, *, outdoor: float = TEST_OUTDOOR):
    """Set up the plugin's global-defaults entry and the fake VTherm."""
    plugin_entry = MockConfigEntry(
        domain=DOMAIN,
        data=dict(DEFAULT_OPTIONS),
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
# Group 1: activation / deactivation thresholds (issue #1 checklist)
# ===========================================================================


class TestBandEdges:
    """Band-edge behavior with the issue #1 defaults (1.0 / 0.5)."""

    async def test_valve_stays_closed_until_full_deficit(self, hass, vtherm):
        """Zone valve stays 0 until a real 1.0 degC deficit."""
        await set_setpoint(hass, 21.0)
        # 0.9 deficit: inside the dead band, never activated -> stays off
        await set_room_temp(vtherm, hass, 20.1)
        diag = diagnostics(hass)
        assert diag["is_active"] is False
        assert diag["on_percent"] == 0.0
        assert diag["last_reason"] == "hold_in_band"
        assert vtherm.is_device_active is False

    async def test_activation_starts_near_full_power(self, hass, vtherm):
        """At 1.0 deficit the TPI output starts at ~100%."""
        await set_setpoint(hass, 21.0)
        await set_room_temp(vtherm, hass, 20.0)
        diag = diagnostics(hass)
        assert diag["is_active"] is True
        assert diag["last_reason"] == "below_activation_threshold"
        # raw TPI = 1.0*1.0 + 0.1*(21-15) = 1.6 -> clamped to 1.0
        assert diag["on_percent"] == pytest.approx(1.0)
        assert diag["raw_tpi"] == pytest.approx(1.6)
        assert vtherm.is_device_active is True

    async def test_forced_zero_above_off_threshold(self, hass, vtherm):
        """Forced 0 above target + hysteresis_off."""
        await set_setpoint(hass, 21.0)
        await set_room_temp(vtherm, hass, 20.0)
        assert diagnostics(hass)["is_active"] is True
        # 21.5 >= 21.0 + 0.5 -> deactivate
        await set_room_temp(vtherm, hass, 21.5)
        diag = diagnostics(hass)
        assert diag["is_active"] is False
        assert diag["on_percent"] == 0.0
        assert diag["last_reason"] == "above_deactivation_threshold"
        assert vtherm.is_device_active is False

    async def test_rearms_only_at_minus_one(self, hass, vtherm):
        """After deactivation, re-arm only at target - hysteresis_on."""
        await set_setpoint(hass, 21.0)
        await set_room_temp(vtherm, hass, 20.0)
        await set_room_temp(vtherm, hass, 21.5)
        assert diagnostics(hass)["is_active"] is False
        # descending back into the band -> stays off
        await set_room_temp(vtherm, hass, 20.4)
        assert diagnostics(hass)["is_active"] is False
        # re-arm exactly at the activation threshold
        await set_room_temp(vtherm, hass, 20.0)
        assert diagnostics(hass)["is_active"] is True


# ===========================================================================
# Group 2: hold-in-band dynamics (the "dynamic" TPI part)
# ===========================================================================


class TestHoldInBand:
    """Hold-state semantics: relay memory with proportional tapering."""

    async def test_proportional_taper_near_setpoint(self, hass, vtherm):
        """Active controller tapers output as the room nears the setpoint."""
        await set_setpoint(hass, 21.0)
        await set_room_temp(vtherm, hass, 20.0)
        assert diagnostics(hass)["on_percent"] == pytest.approx(1.0)
        # 0.5 deficit inside the band: held active, tapered
        await set_room_temp(vtherm, hass, 20.5)
        diag = diagnostics(hass)
        assert diag["is_active"] is True
        assert diag["last_reason"] == "hold_in_band"
        # raw = 1.0*0.5 + 0.1*6.0 = 1.1 -> clamped 1.0 (ext still pushes up)
        assert diag["on_percent"] == pytest.approx(1.0)
        # 0.2 deficit: raw = 0.2 + 0.6 = 0.8
        await set_room_temp(vtherm, hass, 20.8)
        diag = diagnostics(hass)
        assert diag["is_active"] is True
        assert diag["on_percent"] == pytest.approx(0.8)

    async def test_inactive_stays_off_inside_band(self, hass, vtherm):
        """Previously inactive + in band -> stays at 0."""
        await set_setpoint(hass, 21.0)
        await set_room_temp(vtherm, hass, 20.1)
        assert diagnostics(hass)["is_active"] is False
        # drift up and back down inside the band: never activates
        await set_room_temp(vtherm, hass, 20.9)
        assert diagnostics(hass)["is_active"] is False
        await set_room_temp(vtherm, hass, 20.2)
        assert diagnostics(hass)["is_active"] is False
        assert diagnostics(hass)["on_percent"] == 0.0

    async def test_taper_valley_no_flap_across_band_edges(self, hass, vtherm):
        """Small oscillations around the band edges do not flap the state.

        Issue #1: the central boiler feature must see a stable demand across
        band edges. The hold-in-band semantics mean only true threshold
        crossings change the active state.
        """
        await set_setpoint(hass, 21.0)
        await set_room_temp(vtherm, hass, 20.0)
        active_states = []
        # oscillate between 0.4 and 0.6 deficit (both inside the band)
        for temp in (20.6, 20.4, 20.6, 20.5, 20.55):
            await set_room_temp(vtherm, hass, temp)
            active_states.append(diagnostics(hass)["is_active"])
        assert active_states == [True] * 5


# ===========================================================================
# Group 3: HVAC mode handling
# ===========================================================================


class TestHvacModes:
    """HVAC off turns the device off; cool mode mirrors the law."""

    async def test_hvac_off_deactivates_device(self, hass, vtherm):
        await set_setpoint(hass, 21.0)
        await set_room_temp(vtherm, hass, 20.0)
        assert vtherm.is_device_active is True
        await set_mode(hass, "off")
        diag = diagnostics(hass)
        assert diag["is_active"] is False
        assert diag["on_percent"] == 0.0
        assert diag["last_reason"] == "hvac_off"
        assert vtherm.is_device_active is False

    async def test_cool_mode_mirrors(self, hass, vtherm):
        """Cool mode: activate above target + hysteresis_on."""
        await set_mode(hass, "cool")
        await set_setpoint(hass, 21.0)
        # 22.0 >= 21.0 + 1.0 -> activate.  Cool TPI: coef_int*(cur - tgt)
        # + coef_ext*(ext - tgt) = 1.0 + 0.1*(15-21) = 0.4 (cold outdoor
        # reduces cooling demand).
        await set_room_temp(vtherm, hass, 22.0)
        diag = diagnostics(hass)
        assert diag["is_active"] is True
        assert diag["last_reason"] == "above_activation_threshold"
        assert diag["on_percent"] == pytest.approx(0.4)
        assert diag["raw_tpi"] == pytest.approx(0.4)
        # 20.5 <= 21.0 - 0.5 -> deactivate
        await set_room_temp(vtherm, hass, 20.5)
        diag = diagnostics(hass)
        assert diag["is_active"] is False
        assert diag["last_reason"] == "below_deactivation_threshold"


# ===========================================================================
# Group 4: lifecycle, persistence, scheduler
# ===========================================================================


class TestLifecycle:
    """Handler lifecycle: scheduler wiring, persistence across restart."""

    async def test_scheduler_receives_cycle_starts(self, hass, vtherm):
        """The cycle scheduler is driven with (hvac_mode, on_percent)."""
        await set_setpoint(hass, 21.0)
        await set_room_temp(vtherm, hass, 20.0)
        scheduler = vtherm.cycle_scheduler
        assert scheduler.cycle_log, "scheduler never received a cycle"
        mode, on_percent = scheduler.cycle_log[-1]
        assert mode == "heat"
        assert on_percent == pytest.approx(1.0)

    async def test_band_state_survives_handler_restart(self, hass, vtherm):
        """Restart restores the band state (issue #1 checklist)."""
        await set_setpoint(hass, 21.0)
        await set_room_temp(vtherm, hass, 20.0)
        assert diagnostics(hass)["is_active"] is True

        # Simulate a VTherm reload: a new handler over the same thermostat.
        # The persisted state was saved via the HA Store after the last
        # control iteration.
        await hass.async_block_till_done()
        from vtherm_tpi_hysteresis.factory import TpiHysteresisFactory

        new_handler = TpiHysteresisFactory().create(vtherm)
        new_handler.init_algorithm()
        await new_handler.async_added_to_hass()
        vtherm._algo_handler = new_handler
        await new_handler.async_startup()

        # In-band temperature: the restored band state must hold active
        await set_room_temp(vtherm, hass, 20.5)
        diag = diagnostics(hass)
        assert diag["is_active"] is True
        assert diag["on_percent"] == pytest.approx(1.0)

    async def test_spurious_recalculate_does_not_mutate_band(self, hass, vtherm):
        """VTherm calls prop_algorithm.calculate on every sensor update
        before the authoritative control iteration. The proxy makes that
        call a no-op for the band state."""
        await set_setpoint(hass, 21.0)
        await set_room_temp(vtherm, hass, 20.0)
        assert diagnostics(hass)["is_active"] is True

        # A spurious recalculate with a temperature far above the deactivation
        # threshold must NOT flip the band state. VTherm's recalculate() calls
        # prop_algorithm.calculate(...) on the proxy, which is a read-only no-op.
        proxy = vtherm.prop_algorithm
        proxy.calculate(
            vtherm.target_temperature,
            23.0,
            vtherm.current_outdoor_temperature,
            None,
            vtherm.vtherm_hvac_mode,
        )
        # The proxy must not have mutated the controller's committed state:
        # the next real control iteration recomputes from actual data.
        await set_room_temp(vtherm, hass, 20.6)
        diag = diagnostics(hass)
        assert diag["is_active"] is True
        assert diag["on_percent"] == pytest.approx(1.0)
        del proxy


# ===========================================================================
# Group 5: per-thermostat overrides
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
                CONF_TPI_COEF_INT: 0.5,
                CONF_TPI_COEF_EXT: 0.0,
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

        # Override: hysteresis_on = 2.0 -> a 1.0 deficit no longer activates
        await set_setpoint(hass, 21.0)
        await set_room_temp(entity, hass, 20.0)
        assert diagnostics(hass)["is_active"] is False
        # 2.0 deficit activates with coef_int 0.5 -> 0.5*2.0 = 1.0
        await set_room_temp(entity, hass, 19.0)
        diag = diagnostics(hass)
        assert diag["is_active"] is True
        assert diag["hysteresis_on"] == pytest.approx(2.0)
        assert diag["on_percent"] == pytest.approx(1.0)
        # deactivation at 21 + 0.5 (global default still applies for off)
        await set_room_temp(entity, hass, 21.5)
        assert diagnostics(hass)["is_active"] is False
