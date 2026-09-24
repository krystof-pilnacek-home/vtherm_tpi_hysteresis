"""Unit tests for the pure TPI + hysteresis controller.

These tests require no Home Assistant imports: the controller is a pure
control law over plain floats (KipK separation).
"""

from __future__ import annotations

from typing import Any

import pytest
from vtherm_tpi_hysteresis.tpi_hysteresis.controller import (
    HVAC_MODE_COOL,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    TpiHysteresisController,
    clamp,
    normalize_hvac_mode,
)

# Issue #1 defaults for the stove setup
HYST_ON = 1.0
HYST_OFF = 0.5
COEF_INT = 1.0
COEF_EXT = 0.1


def make_controller(**overrides) -> TpiHysteresisController:
    """Create a controller with the issue #1 stove defaults."""
    kwargs: dict[str, Any] = {
        "hysteresis_on": HYST_ON,
        "hysteresis_off": HYST_OFF,
        "coef_int": COEF_INT,
        "coef_ext": COEF_EXT,
        "min_on_percent": 0.0,
        "max_on_percent": 1.0,
    }
    kwargs.update(overrides)
    return TpiHysteresisController(**kwargs)


# ---------------------------------------------------------------------------
# normalize_hvac_mode
# ---------------------------------------------------------------------------


class TestNormalizeHvacMode:
    """Tests for HVAC mode normalization (KipK-style enum tolerance)."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("heat", HVAC_MODE_HEAT),
            ("HEAT", HVAC_MODE_HEAT),
            ("cool", HVAC_MODE_COOL),
            ("off", HVAC_MODE_OFF),
            ("VThermHvacMode_HEAT", HVAC_MODE_HEAT),
            ("VThermHvacMode.HEAT", HVAC_MODE_HEAT),
            ("VThermHvacMode_COOL", HVAC_MODE_COOL),
            ("VThermHvacMode_OFF", HVAC_MODE_OFF),
            ("auto", None),
            ("heat_cool", None),
            (None, None),
        ],
    )
    def test_normalization(self, value, expected):
        assert normalize_hvac_mode(value) == expected

    def test_off_constant(self):
        assert normalize_hvac_mode("off") == HVAC_MODE_OFF
        assert normalize_hvac_mode("VThermHvacMode_OFF") == HVAC_MODE_OFF


# ---------------------------------------------------------------------------
# Heat mode: activation / deactivation / hold-in-band
# ---------------------------------------------------------------------------


class TestHeatModeBand:
    """Heat-mode band transitions (issue #1 verification checklist)."""

    def test_initial_state_is_inactive(self):
        c = make_controller()
        assert c.is_active is False
        assert c.last_reason == "idle"

    def test_activation_at_target_minus_hysteresis_on(self):
        """Zone valve stays closed until a real 1.0 degC deficit."""
        c = make_controller()
        on = c.calculate(target_temp=21.0, current_temp=20.0, hvac_mode="heat")
        assert c.is_active is True
        assert c.last_reason == "below_activation_threshold"
        # 1.0 * (21-20) + 0.1 * (21-ext); ext unknown -> 0
        assert on == pytest.approx(1.0)

    def test_no_activation_inside_dead_band(self):
        """Below-setpoint dead band: 0.9 degC deficit does not activate."""
        c = make_controller()
        on = c.calculate(target_temp=21.0, current_temp=20.1, hvac_mode="heat")
        assert c.is_active is False
        assert on == 0.0
        assert c.last_reason == "hold_in_band"

    def test_deactivation_at_target_plus_hysteresis_off(self):
        c = make_controller()
        c.calculate(21.0, 19.0, hvac_mode="heat")
        assert c.is_active is True
        on = c.calculate(21.0, 21.5, hvac_mode="heat")
        assert c.is_active is False
        assert on == 0.0
        assert c.last_reason == "above_deactivation_threshold"

    def test_hold_active_inside_band_tapers_proportionally(self):
        """Once active, TPI keeps computing inside the band (dynamic part)."""
        c = make_controller()
        # activate at 1.0 deficit -> ~100%
        assert c.calculate(21.0, 20.0, hvac_mode="heat") == pytest.approx(1.0)
        # warm up into the band: 0.5 deficit -> 50%
        on = c.calculate(21.0, 20.5, hvac_mode="heat")
        assert c.is_active is True
        assert c.last_reason == "hold_in_band"
        assert on == pytest.approx(0.5)
        # near setpoint: 0.2 deficit -> 20%
        on = c.calculate(21.0, 20.8, hvac_mode="heat")
        assert c.is_active is True
        assert on == pytest.approx(0.2)

    def test_hold_inactive_inside_band_stays_off(self):
        """Previously inactive + in band -> stay at 0 (relay memory)."""
        c = make_controller()
        # in band, never activated
        assert c.calculate(21.0, 20.1, hvac_mode="heat") == 0.0
        # move deeper into the band (still inside)
        assert c.calculate(21.0, 20.9, hvac_mode="heat") == 0.0
        assert c.is_active is False
        assert c.last_reason == "hold_in_band"

    def test_full_cycle_down_then_rearm(self):
        """Activate -> taper -> deactivate -> re-arm only at -1.0."""
        c = make_controller()
        assert c.calculate(21.0, 19.5, hvac_mode="heat") == pytest.approx(1.0)
        assert c.calculate(21.0, 20.6, hvac_mode="heat") == pytest.approx(0.4)
        assert c.calculate(21.0, 21.5, hvac_mode="heat") == 0.0
        assert c.is_active is False
        # 21.45 is inside the band on the way down -> stays off
        assert c.calculate(21.0, 21.45, hvac_mode="heat") == 0.0
        assert c.is_active is False
        # re-arm only at target - hysteresis_on
        assert c.calculate(21.0, 20.0, hvac_mode="heat") == pytest.approx(1.0)
        assert c.is_active is True


# ---------------------------------------------------------------------------
# TPI value correctness
# ---------------------------------------------------------------------------


class TestTpiValues:
    """TPI arithmetic with internal and external coefficients."""

    def test_ext_coefficient_contributes(self):
        c = make_controller()
        # heat: coef_int*(t-cur) + coef_ext*(t-ext) = 1.0 + 0.5 -> clamp 1.0
        on = c.calculate(21.0, 20.0, ext_current_temp=16.0, hvac_mode="heat")
        assert on == 1.0
        assert c.last_raw_tpi == pytest.approx(1.5)

    def test_clamp_to_max_on_percent(self):
        c = make_controller()
        on = c.calculate(21.0, 18.0, ext_current_temp=10.0, hvac_mode="heat")
        assert on == 1.0
        assert c.last_raw_tpi == pytest.approx(3.0 + 1.1)

    def test_clamp_to_min_on_percent(self):
        c = make_controller(min_on_percent=0.2)
        # activate at full deficit, then warm into the band while held active:
        # raw TPI (0.05) is clamped up to the minimum of 0.2
        c.calculate(21.0, 20.0, hvac_mode="heat")
        assert c.is_active is True
        on = c.calculate(21.0, 20.95, hvac_mode="heat")
        assert c.is_active is True
        assert c.last_reason == "hold_in_band"
        assert on == 0.2

    def test_max_on_percent_caps_output(self):
        c = make_controller(max_on_percent=0.6)
        on = c.calculate(21.0, 19.0, hvac_mode="heat")
        assert c.is_active is True
        assert on == 0.6

    def test_raw_tpi_visible_even_when_inactive(self):
        c = make_controller()
        c.calculate(21.0, 22.0, ext_current_temp=15.0, hvac_mode="heat")
        assert c.is_active is False
        # raw TPI = -1.0 + 0.6 -> reported but output is 0
        assert c.last_raw_tpi == pytest.approx(-0.4)
        assert c.on_percent == 0.0


# ---------------------------------------------------------------------------
# Cool mode mirror
# ---------------------------------------------------------------------------


class TestCoolModeMirror:
    """Cool mode mirrors all comparisons."""

    def test_activation_above_target_plus_hysteresis_on(self):
        c = make_controller()
        on = c.calculate(21.0, 22.0, hvac_mode="cool")
        assert c.is_active is True
        assert c.last_reason == "above_activation_threshold"
        assert on == pytest.approx(1.0)

    def test_deactivation_below_target_minus_hysteresis_off(self):
        c = make_controller()
        c.calculate(21.0, 22.5, hvac_mode="cool")
        assert c.is_active is True
        on = c.calculate(21.0, 20.5, hvac_mode="cool")
        assert c.is_active is False
        assert on == 0.0
        assert c.last_reason == "below_deactivation_threshold"

    def test_hold_active_in_band_tapers(self):
        c = make_controller()
        assert c.calculate(21.0, 22.0, hvac_mode="cool") == pytest.approx(1.0)
        on = c.calculate(21.0, 21.5, hvac_mode="cool")
        assert c.is_active is True
        assert on == pytest.approx(0.5)

    def test_hold_inactive_in_band_stays_off(self):
        c = make_controller()
        assert c.calculate(21.0, 21.9, hvac_mode="cool") == 0.0
        assert c.calculate(21.0, 21.1, hvac_mode="cool") == 0.0
        assert c.is_active is False

    def test_ext_mirrored_in_cool_mode(self):
        c = make_controller()
        # cool: coef_int*(cur-t) + coef_ext*(ext-t) = 1.0 + 0.5 -> clamp 1.0
        on = c.calculate(21.0, 22.0, ext_current_temp=26.0, hvac_mode="cool")
        assert on == 1.0
        assert c.last_raw_tpi == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# Degenerate inputs
# ---------------------------------------------------------------------------


class TestDegenerateInputs:
    """HVAC off / unsupported / missing temperatures."""

    def test_hvac_off_deactivates(self):
        c = make_controller()
        c.calculate(21.0, 20.0, hvac_mode="heat")
        assert c.is_active is True
        on = c.calculate(21.0, 20.0, hvac_mode="off")
        assert c.is_active is False
        assert on == 0.0
        assert c.last_reason == "hvac_off"

    def test_unsupported_mode_deactivates(self):
        c = make_controller()
        on = c.calculate(21.0, 20.0, hvac_mode="dry")
        assert c.is_active is False
        assert on == 0.0
        assert c.last_reason == "unsupported_hvac_mode"

    def test_missing_temperature_deactivates(self):
        c = make_controller()
        on = c.calculate(None, 20.0, hvac_mode="heat")
        assert c.is_active is False
        assert on == 0.0
        assert c.last_reason == "missing_temperature"
        on = c.calculate(21.0, None, hvac_mode="heat")
        assert on == 0.0
        assert c.last_reason == "missing_temperature"

    def test_on_percent_none_before_first_valid_calculation(self):
        """Mirror built-in TPI: None until a valid temperature pair is seen."""
        c = make_controller()
        assert c.on_percent is None
        assert c.calculated_on_percent == 0.0
        c.calculate(21.0, 20.0, hvac_mode="heat")
        assert c.on_percent == pytest.approx(1.0)

    def test_positional_hvac_mode_via_extra_args(self):
        """VTherm core calls calculate(target, current, ext, slope, mode)."""
        c = make_controller()
        on = c.calculate(21.0, 20.0, 15.0, 0.0, "heat")
        assert c.is_active is True
        # raw 1.6 -> clamp 1.0
        assert on == 1.0
        assert c.last_raw_tpi == pytest.approx(1.6)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


class TestPersistence:
    """save_state / restore_state round-trip for the storage helper."""

    def test_roundtrip_preserves_band_state(self):
        c = make_controller()
        c.calculate(21.0, 20.0, hvac_mode="heat")
        assert c.is_active is True
        data = c.save_state()

        restored = make_controller()
        assert restored.is_active is False
        restored.restore_state(data)
        assert restored.is_active is True
        assert restored.hvac_mode == "heat"
        assert restored.last_reason == "below_activation_threshold"

        # restored controller continues holding the band state
        on = restored.calculate(21.0, 20.9, hvac_mode="heat")
        assert restored.is_active is True
        assert on == pytest.approx(0.1)

    def test_restore_inactive_state(self):
        c = make_controller()
        c.calculate(21.0, 21.6, hvac_mode="heat")
        assert c.is_active is False
        data = c.save_state()
        restored = make_controller()
        restored.restore_state(data)
        assert restored.is_active is False
        # in-band -> stays off
        assert restored.calculate(21.0, 20.2, hvac_mode="heat") == 0.0

    def test_restore_none_is_noop(self):
        c = make_controller()
        c.restore_state(None)
        assert c.is_active is False
        assert c.last_reason == "idle"

    def test_restore_garbage_is_ignored(self):
        c = make_controller()
        c.restore_state({"is_active": "yes", "hvac_mode": 3, "last_reason": []})
        assert c.is_active is False
        assert c.hvac_mode is None
        assert c.last_reason == "idle"


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


class TestDiagnostics:
    """get_diagnostics payload for update_attributes."""

    def test_diagnostics_content(self):
        c = make_controller()
        c.calculate(21.0, 20.0, ext_current_temp=15.0, hvac_mode="heat")
        diag = c.get_diagnostics()
        assert diag["is_active"] is True
        assert diag["hvac_mode"] == "heat"
        assert diag["on_percent"] == pytest.approx(1.0)
        assert diag["raw_tpi"] == pytest.approx(1.6)
        assert diag["activation_threshold"] == pytest.approx(20.0)
        assert diag["deactivation_threshold"] == pytest.approx(21.5)
        assert diag["hysteresis_on"] == HYST_ON
        assert diag["hysteresis_off"] == HYST_OFF
        assert diag["coef_int"] == COEF_INT
        assert diag["coef_ext"] == COEF_EXT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestClamp:
    def test_clamp_bounds(self):
        assert clamp(1.5, 0.0, 1.0) == 1.0
        assert clamp(-0.5, 0.0, 1.0) == 0.0
        assert clamp(0.5, 0.0, 1.0) == 0.5

    def test_clamp_swapped_bounds(self):
        assert clamp(0.5, 1.0, 0.0) == 0.5
        assert clamp(2.0, 1.0, 0.0) == 1.0
