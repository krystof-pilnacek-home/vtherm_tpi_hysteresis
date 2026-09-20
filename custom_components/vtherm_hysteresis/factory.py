"""Factory for the Hysteresis proportional algorithm plugin."""

from __future__ import annotations

from vtherm_api.interfaces import (
    InterfacePropAlgorithmFactory,
    InterfacePropAlgorithmHandler,
    InterfaceThermostatRuntime,
)

from .const import PROP_FUNCTION_HYSTERESIS
from .handler import HysteresisHandler


class HysteresisHandlerFactory(InterfacePropAlgorithmFactory):
    """Create Hysteresis handlers for VT runtime thermostats."""

    @property
    def name(self) -> str:
        """Return the Hysteresis proportional function identifier."""
        return PROP_FUNCTION_HYSTERESIS

    def create(
        self,
        thermostat: InterfaceThermostatRuntime,
    ) -> InterfacePropAlgorithmHandler:
        """Create a handler bound to the runtime thermostat."""
        return HysteresisHandler(thermostat)
