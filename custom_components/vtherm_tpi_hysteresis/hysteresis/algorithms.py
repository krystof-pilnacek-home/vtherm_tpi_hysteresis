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


#: Registry of preset algorithms selectable by name. The ``tpi`` preset is
#: deliberately not registered yet: it lands with the TPI follow-up once it
#: honors the hysteresis overlay (is_active) and the cooling-mode signs.
ALGORITHMS: dict[str, Algorithm] = {
    OnOffAlgorithm.name: OnOffAlgorithm(),
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
