"""Discrete hysteresis controller used by the plugin handler."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class HysteresisState:
    """Persisted state for the hysteresis controller."""

    is_active: bool = False
    hvac_mode: str | None = None
    last_reason: str = "idle"
    activation_threshold: float | None = None
    deactivation_threshold: float | None = None


def normalize_hvac_mode(hvac_mode: object) -> str | None:
    """Return a normalized HVAC mode name."""
    value = str(hvac_mode).lower()
    if value.endswith("heat"):
        return "heat"
    if value.endswith("cool"):
        return "cool"
    if value.endswith("off"):
        return "off"
    return None


class HysteresisController:
    """Simple relay controller with separate on and off thresholds."""

    def __init__(
        self,
        hysteresis_on: float,
        hysteresis_off: float,
        max_on_percent: float = 1.0,
        min_on_percent: float = 0.0,
        state: HysteresisState | None = None,
    ) -> None:
        """Store the thresholds and initial relay state."""
        self._hysteresis_on = hysteresis_on
        self._hysteresis_off = hysteresis_off
        self._max_on_percent = max_on_percent
        self._min_on_percent = min_on_percent
        self._state = state or HysteresisState()

    @property
    def on_percent(self) -> float:
        """Return the duty request expected by the VT cycle scheduler."""
        return self._max_on_percent if self._state.is_active else self._min_on_percent

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
        *_args: object,
        hvac_mode: object = None,
        **_kwargs: object,
    ) -> float:
        """Apply the relay hysteresis law and return the resulting on_percent."""
        if hvac_mode is None and len(_args) >= 3:
            hvac_mode = _args[2]

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
