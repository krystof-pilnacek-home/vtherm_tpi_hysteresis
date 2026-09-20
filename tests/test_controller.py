"""Tests for the reference hysteresis controller."""

from custom_components.vtherm_hysteresis.hysteresis.controller import (
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
