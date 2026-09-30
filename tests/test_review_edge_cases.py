"""Tests for the adversarial-review edge cases (PR #6 review)."""

from __future__ import annotations

import pytest
from vtherm_tpi_hysteresis.hysteresis.algorithms import (
    ALGORITHMS,
    get_algorithm,
    register_algorithm,
)
from vtherm_tpi_hysteresis.hysteresis.controller import (
    HysteresisController,
    normalize_hvac_mode,
)


def test_normalize_hvac_mode_matches_exact_modes() -> None:
    """Only heat/cool/off normalize; anything else is unsupported."""
    assert normalize_hvac_mode("heat") == "heat"
    assert normalize_hvac_mode("cool") == "cool"
    assert normalize_hvac_mode("off") == "off"
    assert normalize_hvac_mode("heat_cool") is None
    assert normalize_hvac_mode("dry") is None
    assert normalize_hvac_mode("fan_only") is None
    assert normalize_hvac_mode(None) is None


def test_heat_cool_mode_is_not_treated_as_cooling() -> None:
    """auto/heat_cool must not flip the band into cooling arithmetic."""
    controller = HysteresisController(hysteresis_on=0.3, hysteresis_off=0.3)
    on_percent = controller.calculate(target_temp=20.0, current_temp=19.0, hvac_mode="heat_cool")
    assert on_percent == 0.0
    assert controller.is_active is False
    assert controller.last_reason == "unsupported_hvac_mode"


def test_tpi_preset_is_not_registered() -> None:
    """The tpi placeholder must not be selectable until follow-up #4."""
    assert sorted(ALGORITHMS) == ["on_off"]
    controller = HysteresisController(hysteresis_on=0.3, hysteresis_off=0.3, algorithm="tpi")
    assert controller.get_diagnostics()["algorithm"] == "on_off"


def test_get_algorithm_unknown_name_falls_back_to_on_off() -> None:
    assert get_algorithm("no_such_preset").name == "on_off"


def test_register_algorithm_warns_on_collision(caplog: pytest.LogCaptureFixture) -> None:
    """Re-registering a preset name must not pass silently."""

    class Replacement:
        name = "on_off"

        def __call__(self, hvac_mode, target_temp, current_temp, ext_temp, params):
            return 0.0

    original = ALGORITHMS["on_off"]
    try:
        with caplog.at_level("WARNING", logger="vtherm_tpi_hysteresis.hysteresis.algorithms"):
            register_algorithm(Replacement())
        assert "already registered" in caplog.text
        assert isinstance(ALGORITHMS["on_off"], Replacement)
    finally:
        ALGORITHMS["on_off"] = original


def test_unsupported_mode_ignores_min_on_percent_floor() -> None:
    """Unsupported modes must not run the device at the configured floor."""
    controller = HysteresisController(hysteresis_on=0.3, hysteresis_off=0.3, min_on_percent=0.2)
    on_percent = controller.calculate(target_temp=20.0, current_temp=25.0, hvac_mode="dry")
    assert on_percent == 0.0
    assert controller.last_reason == "unsupported_hvac_mode"


def test_hvac_off_ignores_min_on_percent_floor() -> None:
    """HVAC off must produce zero duty even with a nonzero floor."""
    controller = HysteresisController(hysteresis_on=0.3, hysteresis_off=0.3, min_on_percent=0.2)
    on_percent = controller.calculate(target_temp=20.0, current_temp=19.0, hvac_mode="off")
    assert on_percent == 0.0
    assert controller.last_reason == "hvac_off"


def test_missing_temperature_ignores_min_on_percent_floor() -> None:
    """Missing temperatures must produce zero duty even with a floor."""
    controller = HysteresisController(hysteresis_on=0.3, hysteresis_off=0.3, min_on_percent=0.2)
    on_percent = controller.calculate(target_temp=None, current_temp=19.0, hvac_mode="heat")
    assert on_percent == 0.0
    assert controller.last_reason == "missing_temperature"


def test_supported_inactive_state_still_applies_floor() -> None:
    """The floor still applies while resting in a supported mode."""
    controller = HysteresisController(hysteresis_on=0.3, hysteresis_off=0.3, min_on_percent=0.2)
    controller.calculate(target_temp=20.0, current_temp=20.1, hvac_mode="heat")
    assert controller.is_active is False
    assert controller.last_reason == "hold_in_band"
    assert controller.on_percent == 0.2


def test_inverted_power_limits_do_not_silently_swap(caplog: pytest.LogCaptureFixture) -> None:
    """min > max logs a warning instead of silently swapping."""
    with caplog.at_level("WARNING", logger="vtherm_tpi_hysteresis.hysteresis.controller"):
        HysteresisController(
            hysteresis_on=0.3,
            hysteresis_off=0.3,
            max_on_percent=0.1,
            min_on_percent=0.9,
        )
    assert "min_on_percent" in caplog.text
