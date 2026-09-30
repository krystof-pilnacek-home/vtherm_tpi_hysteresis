"""Preset regulation algorithms composed under the hysteresis overlay.

An algorithm is a small callable that maps the regulation inputs to an
on_percent duty request. The hysteresis overlay decides *whether* to
regulate (activate / deactivate / hold); the algorithm decides *how much*
power to request while regulating.

Algorithms are registered in the ALGORITHMS registry and selected by name
via the ``algorithm`` config option. ``on_off`` is the historical relay
behaviour of the plugin and the current default.
"""

from __future__ import annotations

import logging
from typing import Protocol

_LOGGER = logging.getLogger(__name__)


class Algorithm(Protocol):
    """Structural type of a named preset algorithm."""

    name: str

    def __call__(
        self,
        hvac_mode: str,
        target_temp: float | None,
        current_temp: float | None,
        ext_temp: float | None,
        params: dict[str, float],
    ) -> float:
        """Return the raw on_percent request for the current inputs."""


class TpiAlgorithm:
    """Proportional TPI control law while regulation is active.

    ``on_percent = coef_int * (target - current) + coef_ext * (target - outdoor)``
    in heat mode, with the deltas mirrored in cool mode. While regulation is
    inactive the request is ``min_on_percent``. The hysteresis overlay is
    unchanged: this preset only replaces the flat ``max_on_percent`` request
    of ``on_off`` while the overlay keeps regulation active.
    """

    name = "tpi"

    def __call__(
        self,
        hvac_mode: str,
        target_temp: float | None,
        current_temp: float | None,
        ext_temp: float | None,
        params: dict[str, float],
    ) -> float:
        if not params.get("is_active", 0.0):
            return params["min_on_percent"]
        if target_temp is None or current_temp is None:
            return params["min_on_percent"]
        coef_int = params.get("coef_int", 1.0)
        coef_ext = params.get("coef_ext", 0.1)
        delta_int = target_temp - current_temp
        delta_ext = (target_temp - ext_temp) if ext_temp is not None else 0.0
        if hvac_mode == "cool":
            delta_int = -delta_int
            delta_ext = -delta_ext
        return coef_int * delta_int + coef_ext * delta_ext


class OnOffAlgorithm:
    """Historical relay behaviour: full power while active, floor when not.

    This is the algorithm the plugin has always used: while regulation is
    active the duty request is ``max_on_percent`` (default 1.0), otherwise
    ``min_on_percent`` (default 0.0). It ignores the temperatures.
    """

    name = "on_off"

    def __call__(
        self,
        hvac_mode: str,
        target_temp: float | None,
        current_temp: float | None,
        ext_temp: float | None,
        params: dict[str, float],
    ) -> float:
        del hvac_mode, target_temp, current_temp, ext_temp
        active = params.get("is_active", 0.0)
        if active:
            return params["max_on_percent"]
        return params["min_on_percent"]


#: Registry of preset algorithms selectable by name.
ALGORITHMS: dict[str, Algorithm] = {
    OnOffAlgorithm.name: OnOffAlgorithm(),
    TpiAlgorithm.name: TpiAlgorithm(),
}


def get_algorithm(name: str) -> Algorithm:
    """Return the preset algorithm registered under ``name``.

    Unknown names fall back to on_off so a typo in the configuration never
    leaves the thermostat without a control law.
    """
    algorithm = ALGORITHMS.get(name)
    if algorithm is None:
        return ALGORITHMS[OnOffAlgorithm.name]
    return algorithm


def register_algorithm(algorithm: Algorithm) -> None:
    """Register a custom preset algorithm (extension point for the DSL).

    Logs a warning when the name is already taken so a colliding
    integration cannot silently replace a preset for every thermostat.
    """
    if algorithm.name in ALGORITHMS:
        _LOGGER.warning(
            "Algorithm preset '%s' is already registered and will be replaced by %s",
            algorithm.name,
            type(algorithm).__name__,
        )
    ALGORITHMS[algorithm.name] = algorithm
