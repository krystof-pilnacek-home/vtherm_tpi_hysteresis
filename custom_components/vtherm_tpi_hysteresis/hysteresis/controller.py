"""Discrete hysteresis controller used by the plugin handler.

The controller composes a preset algorithm (see ``algorithms.py``) under an
optional hysteresis overlay:

* while regulation is active, ``on_percent`` comes from the algorithm;
* the hysteresis band (``hysteresis_on`` / ``hysteresis_off``) decides when
  regulation activates, deactivates, or holds its previous state;
* with both thresholds at 0 the band degenerates and the plain algorithm
  runs without hysteresis (regulate exactly until the setpoint is met).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .algorithms import get_algorithm

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class HysteresisState:
    """Persisted state for the hysteresis controller."""

    is_active: bool = False
    hvac_mode: str | None = None
    last_reason: str = "idle"
    activation_threshold: float | None = None
    deactivation_threshold: float | None = None
    last_target_temp: float | None = None
    last_current_temp: float | None = None
    last_ext_temp: float | None = None


def normalize_hvac_mode(hvac_mode: object) -> str | None:
    """Return a normalized HVAC mode name.

    Matching is exact: ``heat_cool`` must not be classified as ``cool``
    (the ``endswith`` chain upstream inherited did exactly that), and
    unsupported modes (``dry``, ``fan_only``, ...) return None so the
    controller can treat them explicitly.
    """
    value = str(hvac_mode).lower()
    if value in ("heat", "cool", "off"):
        return value
    return None


class HysteresisController:
    """Simple relay controller with separate on and off thresholds."""

    def __init__(
        self,
        hysteresis_on: float,
        hysteresis_off: float,
        max_on_percent: float = 1.0,
        min_on_percent: float = 0.0,
        coef_int: float = 1.0,
        coef_ext: float = 0.1,
        algorithm: str = "on_off",
        state: HysteresisState | None = None,
    ) -> None:
        """Store the thresholds, algorithm and initial relay state."""
        self._hysteresis_on = hysteresis_on
        self._hysteresis_off = hysteresis_off
        self._max_on_percent = max_on_percent
        self._min_on_percent = min_on_percent
        self._coef_int = coef_int
        self._coef_ext = coef_ext
        self._algorithm = get_algorithm(algorithm)
        self._state = state or HysteresisState()
        if self._min_on_percent > self._max_on_percent:
            _LOGGER.warning(
                "min_on_percent (%s) is greater than max_on_percent (%s); "
                "check the plugin configuration",
                self._min_on_percent,
                self._max_on_percent,
            )

    @property
    def on_percent(self) -> float:
        """Return the duty request expected by the VT cycle scheduler.

        When the controller is not in a supported, regulating state
        (HVAC off, unsupported mode, or missing temperatures) the duty
        request is 0 regardless of ``min_on_percent``: the floor is a
        regulation parameter, not a device-always-on override.
        """
        if self._state.last_reason in (
            "hvac_off",
            "unsupported_hvac_mode",
            "missing_temperature",
        ):
            return 0.0
        return self._clamp(
            self._algorithm(
                self._state.hvac_mode or "off",
                self._state.last_target_temp,
                self._state.last_current_temp,
                self._state.last_ext_temp,
                {
                    "is_active": self._state.is_active,
                    "max_on_percent": self._max_on_percent,
                    "min_on_percent": self._min_on_percent,
                    "coef_int": self._coef_int,
                    "coef_ext": self._coef_ext,
                },
            )
        )

    def _clamp(self, value: float) -> float:
        """Clamp an algorithm request into [min_on_percent, max_on_percent]."""
        low = min(self._min_on_percent, self._max_on_percent)
        high = max(self._min_on_percent, self._max_on_percent)
        return max(low, min(high, value))

    @property
    def calculated_on_percent(self) -> float:
        """Alias expected by VT internals (safety manager, etc.)."""
        return self.on_percent

    @property
    def is_active(self) -> bool:
        """Return the current relay state."""
        return self._state.is_active

    @property
    def hysteresis_on(self) -> float:
        """Return the threshold distance used to activate regulation."""
        return self._hysteresis_on

    @property
    def hysteresis_off(self) -> float:
        """Return the threshold distance used to deactivate regulation."""
        return self._hysteresis_off

    @property
    def last_reason(self) -> str:
        """Return a short explanation of the last state decision."""
        return self._state.last_reason

    def get_diagnostics(self) -> dict[str, object]:
        """Return the diagnostics payload exposed on the thermostat."""
        return {
            "algorithm": self._algorithm.name,
            "is_active": self._state.is_active,
            "hvac_mode": self._state.hvac_mode,
            "on_percent": self.on_percent,
            "last_reason": self._state.last_reason,
            "activation_threshold": self._state.activation_threshold,
            "deactivation_threshold": self._state.deactivation_threshold,
            "hysteresis_on": self._hysteresis_on,
            "hysteresis_off": self._hysteresis_off,
            "max_on_percent": self._max_on_percent,
            "min_on_percent": self._min_on_percent,
            "coef_int": self._coef_int,
            "coef_ext": self._coef_ext,
        }

    def restore_state(self, data: dict[str, object] | None) -> None:
        """Restore the persisted relay state."""
        if not data:
            return

        is_active = data.get("is_active")
        if isinstance(is_active, bool):
            self._state.is_active = is_active

        hvac_mode = data.get("hvac_mode")
        if isinstance(hvac_mode, str):
            self._state.hvac_mode = normalize_hvac_mode(hvac_mode)

        last_reason = data.get("last_reason")
        if isinstance(last_reason, str):
            self._state.last_reason = last_reason

    def save_state(self) -> dict[str, object]:
        """Serialize the relay state for Home Assistant storage."""
        return {
            "is_active": self._state.is_active,
            "hvac_mode": self._state.hvac_mode,
            "last_reason": self._state.last_reason,
        }

    def calculate(
        self,
        target_temp: float | None,
        current_temp: float | None,
        ext_temp: float | None = None,
        *_args: object,
        hvac_mode: object = None,
        **_kwargs: object,
    ) -> float:
        """Apply the hysteresis law and return the resulting on_percent."""
        if hvac_mode is None and len(_args) >= 2:
            hvac_mode = _args[1]

        mode = normalize_hvac_mode(hvac_mode)
        self._state.hvac_mode = mode
        self._state.activation_threshold = None
        self._state.deactivation_threshold = None

        if mode == "off":
            self._state.is_active = False
            self._state.last_reason = "hvac_off"
            return self.on_percent

        if mode not in ("heat", "cool"):
            self._state.is_active = False
            self._state.last_reason = "unsupported_hvac_mode"
            return self.on_percent

        if target_temp is None or current_temp is None:
            self._state.is_active = False
            self._state.last_reason = "missing_temperature"
            return self.on_percent

        self._state.last_target_temp = target_temp
        self._state.last_current_temp = current_temp
        self._state.last_ext_temp = ext_temp

        if mode == "heat":
            activation_threshold = target_temp - self._hysteresis_on
            deactivation_threshold = target_temp + self._hysteresis_off
            should_activate = current_temp <= activation_threshold
            should_deactivate = current_temp >= deactivation_threshold
            active_reason = "below_activation_threshold"
            inactive_reason = "above_deactivation_threshold"
        else:
            activation_threshold = target_temp + self._hysteresis_on
            deactivation_threshold = target_temp - self._hysteresis_off
            should_activate = current_temp >= activation_threshold
            should_deactivate = current_temp <= deactivation_threshold
            active_reason = "above_activation_threshold"
            inactive_reason = "below_deactivation_threshold"

        self._state.activation_threshold = activation_threshold
        self._state.deactivation_threshold = deactivation_threshold

        if should_activate:
            self._state.is_active = True
            self._state.last_reason = active_reason
        elif should_deactivate:
            self._state.is_active = False
            self._state.last_reason = inactive_reason
        else:
            self._state.last_reason = "hold_in_band"

        return self.on_percent

    async def on_cycle_started(
        self,
        on_time_sec: float,
        off_time_sec: float,
        on_percent: float,
        hvac_mode: str,
    ) -> None:
        """Handle the cycle start callback exposed by the VT scheduler.

        The simple hysteresis example does not need cycle-start feedback, but
        the method is kept as a documented extension point because advanced
        controllers can use it to capture the command effectively committed by
        the scheduler at the beginning of a cycle.
        """
        del on_time_sec
        del off_time_sec
        del on_percent
        del hvac_mode

    async def on_cycle_completed(
        self,
        e_eff: float | None = None,
        elapsed_ratio: float = 1.0,
        cycle_duration_min: float | None = None,
        **_kw: object,
    ) -> None:
        """Handle the cycle completion callback exposed by the VT scheduler.

        SmartPI uses this hook to observe the effective power really applied on
        the cycle through `e_eff`. The hysteresis example does not consume that
        information, but the method is intentionally present so developers can
        document or extend the plugin around realized power feedback.
        """
        del e_eff
        del elapsed_ratio
        del cycle_duration_min
