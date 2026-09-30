"""Tests for the reference hysteresis controller."""

from vtherm_tpi_hysteresis.hysteresis.controller import (
    HysteresisController,
)


def test_heat_hysteresis_activates_below_activation_threshold() -> None:
    """Heating must activate below the activation threshold."""
    controller = HysteresisController(hysteresis_on=0.3, hysteresis_off=0.5)

    on_percent = controller.calculate(target_temp=20.0, current_temp=19.7, hvac_mode="heat")

    assert on_percent == 1.0
    assert controller.is_active is True
    assert controller.last_reason == "below_activation_threshold"


def test_heat_hysteresis_deactivates_above_deactivation_threshold() -> None:
    """Heating must deactivate above the deactivation threshold."""
    controller = HysteresisController(hysteresis_on=0.3, hysteresis_off=0.5)
    controller.restore_state({"is_active": True, "hvac_mode": "heat", "last_reason": "manual"})

    on_percent = controller.calculate(target_temp=20.0, current_temp=20.5, hvac_mode="heat")

    assert on_percent == 0.0
    assert controller.is_active is False
    assert controller.last_reason == "above_deactivation_threshold"


def test_hysteresis_keeps_previous_heat_state_inside_band() -> None:
    """The relay state must be preserved inside the hysteresis band."""
    controller = HysteresisController(hysteresis_on=0.3, hysteresis_off=0.5)
    controller.restore_state({"is_active": True, "hvac_mode": "heat", "last_reason": "manual"})

    on_percent = controller.calculate(target_temp=20.0, current_temp=20.2, hvac_mode="heat")

    assert on_percent == 1.0
    assert controller.is_active is True
    assert controller.last_reason == "hold_in_band"


def test_cool_hysteresis_activates_above_activation_threshold() -> None:
    """Cooling must activate above the activation threshold."""
    controller = HysteresisController(hysteresis_on=0.3, hysteresis_off=0.5)

    on_percent = controller.calculate(target_temp=20.0, current_temp=20.3, hvac_mode="cool")

    assert on_percent == 1.0
    assert controller.is_active is True
    assert controller.last_reason == "above_activation_threshold"


def test_cool_hysteresis_deactivates_below_deactivation_threshold() -> None:
    """Cooling must deactivate below the deactivation threshold."""
    controller = HysteresisController(hysteresis_on=0.3, hysteresis_off=0.5)
    controller.restore_state({"is_active": True, "hvac_mode": "cool", "last_reason": "manual"})

    on_percent = controller.calculate(target_temp=20.0, current_temp=19.5, hvac_mode="cool")

    assert on_percent == 0.0
    assert controller.is_active is False
    assert controller.last_reason == "below_deactivation_threshold"


def test_hysteresis_accepts_vt_positional_calculate_signature() -> None:
    """The controller must accept the positional call shape used by VT."""
    controller = HysteresisController(hysteresis_on=0.3, hysteresis_off=0.5)

    on_percent = controller.calculate(20.0, 20.3, None, None, "cool")

    assert on_percent == 1.0
    assert controller.is_active is True
    assert controller.last_reason == "above_activation_threshold"


def test_hysteresis_diagnostics_expose_tracking_attributes() -> None:
    """Diagnostics must expose the latest relay decision."""
    controller = HysteresisController(hysteresis_on=0.3, hysteresis_off=0.5)

    controller.calculate(target_temp=20.0, current_temp=20.3, hvac_mode="cool")

    assert controller.get_diagnostics() == {
        "algorithm": "on_off",
        "is_active": True,
        "hvac_mode": "cool",
        "on_percent": 1.0,
        "last_reason": "above_activation_threshold",
        "activation_threshold": 20.3,
        "deactivation_threshold": 19.5,
        "hysteresis_on": 0.3,
        "hysteresis_off": 0.5,
        "max_on_percent": 1.0,
        "min_on_percent": 0.0,
    }


# ---------------------------------------------------------------------------
# Composable algorithm under the hysteresis overlay
# ---------------------------------------------------------------------------


def test_on_off_algorithm_used_while_active() -> None:
    """The on_off preset must reproduce the historical relay behaviour."""
    controller = HysteresisController(hysteresis_on=0.3, hysteresis_off=0.5)
    on_percent = controller.calculate(target_temp=20.0, current_temp=19.7, hvac_mode="heat")
    assert on_percent == 1.0
    assert controller.get_diagnostics()["algorithm"] == "on_off"


def test_on_off_algorithm_respects_custom_power_limits() -> None:
    """max/min on_percent must still bound the on_off preset output."""
    controller = HysteresisController(
        hysteresis_on=0.3, hysteresis_off=0.5, max_on_percent=0.7, min_on_percent=0.1
    )
    assert controller.calculate(target_temp=20.0, current_temp=19.7, hvac_mode="heat") == 0.7
    assert controller.calculate(target_temp=20.0, current_temp=20.5, hvac_mode="heat") == 0.1


def test_degenerate_band_runs_algorithm_without_hysteresis() -> None:
    """Zero thresholds remove the band: no hold region around the setpoint."""
    controller = HysteresisController(hysteresis_on=0.0, hysteresis_off=0.0)
    # below the setpoint -> activate
    assert controller.calculate(target_temp=20.0, current_temp=19.9, hvac_mode="heat") == 1.0
    # exactly at the setpoint -> still activating (activation wins ties)
    assert controller.calculate(target_temp=20.0, current_temp=20.0, hvac_mode="heat") == 1.0
    # above the setpoint -> deactivate immediately, no band to hold within
    assert controller.calculate(target_temp=20.0, current_temp=20.1, hvac_mode="heat") == 0.0
    assert controller.last_reason == "above_deactivation_threshold"


def test_degenerate_band_cool_mirrors_without_hysteresis() -> None:
    """Cool mode with a degenerate band deactivates right past the setpoint."""
    controller = HysteresisController(hysteresis_on=0.0, hysteresis_off=0.0)
    assert controller.calculate(target_temp=21.0, current_temp=21.1, hvac_mode="cool") == 1.0
    assert controller.calculate(target_temp=21.0, current_temp=21.0, hvac_mode="cool") == 1.0
    assert controller.calculate(target_temp=21.0, current_temp=20.9, hvac_mode="cool") == 0.0


def test_unknown_algorithm_falls_back_to_on_off() -> None:
    """A typo in the algorithm name must never leave the plugin uncontrolled."""
    controller = HysteresisController(
        hysteresis_on=0.3, hysteresis_off=0.5, algorithm="no_such_algo"
    )
    assert controller.get_diagnostics()["algorithm"] == "on_off"
    assert controller.calculate(target_temp=20.0, current_temp=19.7, hvac_mode="heat") == 1.0


def test_algorithm_receives_temperatures_for_future_presets() -> None:
    """The controller must record inputs so temperature-based presets work."""
    controller = HysteresisController(hysteresis_on=0.3, hysteresis_off=0.5)
    controller.calculate(target_temp=20.0, current_temp=19.7, ext_temp=15.0, hvac_mode="heat")
    state = controller._state
    assert state.last_target_temp == 20.0
    assert state.last_current_temp == 19.7
    assert state.last_ext_temp == 15.0
