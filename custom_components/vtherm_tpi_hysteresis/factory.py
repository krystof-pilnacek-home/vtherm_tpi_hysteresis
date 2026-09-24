"""Factory for the tpi_hysteresis_regulation proportional algorithm plugin."""

from __future__ import annotations

from vtherm_api.interfaces import (
    InterfacePropAlgorithmFactory,
    InterfacePropAlgorithmHandler,
    InterfaceThermostatRuntime,
)

from .const import PROP_FUNCTION_TPI_HYSTERESIS
from .handler import TpiHysteresisHandler


class TpiHysteresisFactory(InterfacePropAlgorithmFactory):
    """Create TPI + hysteresis handlers for VT runtime thermostats."""

    @property
    def name(self) -> str:
        """Return the TPI hysteresis proportional function identifier."""
        return PROP_FUNCTION_TPI_HYSTERESIS

    def create(
        self,
        thermostat: InterfaceThermostatRuntime,
    ) -> InterfacePropAlgorithmHandler:
        """Create a handler bound to the runtime thermostat."""
        return TpiHysteresisHandler(thermostat)
