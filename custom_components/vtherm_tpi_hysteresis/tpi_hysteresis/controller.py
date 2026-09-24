"""TPI + hysteresis proportional controller used by the plugin handler.

Combines proportional TPI dynamics with a full hysteresis band around the
setpoint, including a below-setpoint dead band:

* below ``target - hysteresis_on`` (heat mode) the controller activates and
  outputs the clamped TPI value ``coef_int * (target - current) +
  coef_ext * (target - outdoor)``;
* above ``target + hysteresis_off`` it deactivates and outputs 0;
* inside the band it holds the previous active/inactive state.  When held
  active, the TPI value keeps being recomputed so the output tapers down
  proportionally as the room approaches the setpoint instead of slamming
  shut.

Cool mode mirrors every comparison.
"""

from __future__ import annotations

from dataclasses import dataclass

HVAC_MODE_HEAT = "heat"
HVAC_MODE_COOL = "cool"
HVAC_MODE_OFF = "off"
SUPPORTED_HVAC_MODES = (HVAC_MODE_HEAT, HVAC_MODE_COOL)


def normalize_hvac_mode(hvac_mode: object) -> str | None:
    """Return a normalized HVAC mode name.

    Accepts plain strings (``"heat"``) and VTherm enum-like objects whose
    ``str()`` representation ends with the mode name (``"VThermHvacMode.HEAT"``,
    ``"VThermHvacMode_HEAT"``).
    """
    value = str(hvac_mode).lower()
    if value.endswith("heat") and not value.endswith("heat_cool"):
        return HVAC_MODE_HEAT
    if value.endswith("cool") and not value.endswith("heat_cool"):
        return HVAC_MODE_COOL
    if value.endswith("off"):
        return HVAC_MODE_OFF
    return None


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp ``value`` into ``[minimum, maximum]``."""
    if minimum > maximum:
        minimum, maximum = maximum, minimum
    return max(minimum, min(maximum, value))


@dataclass(slots=True)
class TpiHysteresisState:
    """Persisted state for the TPI + hysteresis controller."""

    is_active: bool = False
    hvac_mode: str | None = None
    last_reason: str = "idle"
    activation_threshold: float | None = None
    deactivation_threshold: float | None = None
    last_raw_tpi: float = 0.0
    last_on_percent: float = 0.0
    last_current_temp: float | None = None
    last_target_temp: float | None = None
    last_ext_temp: float | None = None


class TpiHysteresisController:
    """Proportional TPI controller gated by a hysteresis band."""

    def __init__(
        self,
        hysteresis_on: float,
        hysteresis_off: float,
        coef_int: float = 1.0,
        coef_ext: float = 0.1,
        min_on_percent: float = 0.0,
        max_on_percent: float = 1.0,
        state: TpiHysteresisState | None = None,
    ) -> None:
        """Store the band thresholds and TPI coefficients."""
        self._hysteresis_on = hysteresis_on
        self._hysteresis_off = hysteresis_off
        self._coef_int = coef_int
        self._coef_ext = coef_ext
        self._min_on_percent = min_on_percent
        self._max_on_percent = max_on_percent
        self._state = state or TpiHysteresisState()

    # -- properties expected by the VTherm runtime -------------------------

    @property
    def on_percent(self) -> float:
        """Return the current duty request.

        ``None`` is returned before the first successful calculation with
        valid temperatures so the cycle scheduler does not touch an
        already-active device at startup (mirrors the built-in TPI algorithm).
        """
        if self._state.last_current_temp is None or self._state.last_target_temp is None:
            return None  # type: ignore[return-value]
        return self._state.last_on_percent

    @property
    def calculated_on_percent(self) -> float:
        """Alias expected by VTherm internals (safety manager, etc.)."""
        value = self.on_percent
        return 0.0 if value is None else value

    @property
    def is_active(self) -> bool:
        """Return whether the controller is inside the active region."""
        return self._state.is_active

    @property
    def hvac_mode(self) -> str | None:
        """Return the last normalized HVAC mode seen by the controller."""
        return self._state.hvac_mode

    @property
    def last_reason(self) -> str:
        """Return a short explanation of the last state decision."""
        return self._state.last_reason

    @property
    def last_raw_tpi(self) -> float:
        """Return the last unclamped TPI value."""
        return self._state.last_raw_tpi

    @property
    def hysteresis_on(self) -> float:
        """Return the threshold distance used to activate regulation."""
        return self._hysteresis_on

    @property
    def hysteresis_off(self) -> float:
        """Return the threshold distance used to deactivate regulation."""
        return self._hysteresis_off

    @property
    def coef_int(self) -> float:
        """Return the TPI internal coefficient."""
        return self._coef_int

    @property
    def coef_ext(self) -> float:
        """Return the TPI external coefficient."""
        return self._coef_ext

    # -- diagnostics / persistence -----------------------------------------

    def get_diagnostics(self) -> dict[str, object]:
        """Return the diagnostics payload exposed on the thermostat."""
        return {
            "is_active": self._state.is_active,
            "hvac_mode": self._state.hvac_mode,
            "on_percent": self.calculated_on_percent,
            "raw_tpi": self._state.last_raw_tpi,
            "last_reason": self._state.last_reason,
            "activation_threshold": self._state.activation_threshold,
            "deactivation_threshold": self._state.deactivation_threshold,
            "hysteresis_on": self._hysteresis_on,
            "hysteresis_off": self._hysteresis_off,
            "coef_int": self._coef_int,
            "coef_ext": self._coef_ext,
            "min_on_percent": self._min_on_percent,
            "max_on_percent": self._max_on_percent,
        }

    def save_state(self) -> dict[str, object]:
        """Serialize the band state for Home Assistant storage."""
        return {
            "is_active": self._state.is_active,
            "hvac_mode": self._state.hvac_mode,
            "last_reason": self._state.last_reason,
        }

    def restore_state(self, data: dict[str, object] | None) -> None:
        """Restore the persisted band state."""
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

    # -- control law ---------------------------------------------------------

    def _calculate_tpi(
        self,
        target_temp: float,
        current_temp: float,
        ext_temp: float | None,
        mode: str,
    ) -> float:
        """Return the raw (unclamped) TPI value for the given mode."""
        if mode == HVAC_MODE_COOL:
            delta_temp = current_temp - target_temp
            delta_ext = (ext_temp - target_temp) if ext_temp is not None else 0.0
        else:
            delta_temp = target_temp - current_temp
            delta_ext = (target_temp - ext_temp) if ext_temp is not None else 0.0
        return self._coef_int * delta_temp + self._coef_ext * delta_ext

    def calculate(
        self,
        target_temp: float | None,
        current_temp: float | None,
        ext_current_temp: float | None = None,
        *_args: object,
        hvac_mode: object = None,
        **_kwargs: object,
    ) -> float | None:
        """Apply the TPI + hysteresis law and return the resulting on_percent.

        VTherm core calls ``prop_algorithm.calculate(target, current, ext,
        slope, hvac_mode, ...)``; with this signature the mode lands on the
        second variadic argument.
        """
        if hvac_mode is None and len(_args) >= 2:
            hvac_mode = _args[1]
        mode = normalize_hvac_mode(hvac_mode)
        self._state.hvac_mode = mode

        if mode == HVAC_MODE_OFF:
            self._deactivate("hvac_off")
            return self.calculated_on_percent

        if mode not in SUPPORTED_HVAC_MODES:
            self._deactivate("unsupported_hvac_mode")
            return self.calculated_on_percent

        if target_temp is None or current_temp is None:
            self._deactivate("missing_temperature")
            return self.calculated_on_percent

        self._state.last_current_temp = current_temp
        self._state.last_target_temp = target_temp
        self._state.last_ext_temp = ext_current_temp

        if mode == HVAC_MODE_HEAT:
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

        if not self._state.is_active:
            self._state.last_raw_tpi = self._calculate_tpi(
                target_temp, current_temp, ext_current_temp, mode
            )
            self._state.last_on_percent = 0.0
        else:
            raw = self._calculate_tpi(target_temp, current_temp, ext_current_temp, mode)
            self._state.last_raw_tpi = raw
            self._state.last_on_percent = clamp(raw, self._min_on_percent, self._max_on_percent)
        return self._state.last_on_percent

    def _deactivate(self, reason: str) -> None:
        """Force the controller inactive with the given reason."""
        self._state.is_active = False
        self._state.last_reason = reason
        self._state.last_on_percent = 0.0
        self._state.last_raw_tpi = 0.0
        self._state.activation_threshold = None
        self._state.deactivation_threshold = None

    # -- cycle scheduler callbacks (documented extension points) -------------

    async def on_cycle_started(
        self,
        on_time_sec: float,
        off_time_sec: float,
        on_percent: float,
        hvac_mode: str,
    ) -> None:
        """Handle the cycle start callback exposed by the VT scheduler."""
        del on_time_sec, off_time_sec, on_percent, hvac_mode

    async def on_cycle_completed(
        self,
        e_eff: float | None = None,
        elapsed_ratio: float = 1.0,
        cycle_duration_min: float | None = None,
        **_kw: object,
    ) -> None:
        """Handle the cycle completion callback exposed by the VT scheduler."""
        del e_eff, elapsed_ratio, cycle_duration_min
