"""Fixtures for vtherm_tpi_hysteresis tests.

The pure-controller and handler unit tests run against MagicMock hass /
thermostat objects (vtherm_pellet_stove test style).  The config-flow, init
and e2e tests use the real HomeAssistant test instance from
pytest-homeassistant-custom-component with the integration copied into a
temporary config dir, mirroring the stove_controller test conventions.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import shutil
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from vtherm_tpi_hysteresis.const import DOMAIN

# Enable the HACC plugin (hass fixture, enable_custom_integrations, ...)
pytest_plugins = ("pytest_homeassistant_custom_component",)


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance for handler unit tests."""
    hass = MagicMock()
    hass.data = {}
    hass.states = MagicMock()
    hass.services = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[])

    def _create_task(coro, **kwargs):
        if asyncio.iscoroutine(coro):
            coro.close()
        return MagicMock()

    hass.async_create_task = MagicMock(side_effect=_create_task)
    return hass


def make_mock_entry(
    data: dict[str, Any],
    options: dict[str, Any] | None = None,
    unique_id: str = DOMAIN,
) -> MagicMock:
    """Create a mock ConfigEntry for config-resolution tests."""
    entry = MagicMock()
    entry.data = dict(data)
    entry.options = dict(options) if options is not None else {}
    entry.unique_id = unique_id
    return entry


@pytest.fixture
def make_thermostat():
    """Factory fixture: MagicMock InterfaceThermostatRuntime."""
    created: list[MagicMock] = []

    def _make(
        hass: MagicMock,
        *,
        unique_id: str = "vt_test",
        name: str = "Test VTherm",
        target_temperature: float | None = 21.0,
        current_temperature: float | None = 20.0,
        current_outdoor_temperature: float | None = 15.0,
        vtherm_hvac_mode: str = "heat",
    ) -> MagicMock:
        thermostat = MagicMock()
        thermostat.hass = hass
        thermostat.unique_id = unique_id
        thermostat.name = name
        thermostat.target_temperature = target_temperature
        thermostat.current_temperature = current_temperature
        thermostat.current_outdoor_temperature = current_outdoor_temperature
        thermostat.vtherm_hvac_mode = vtherm_hvac_mode
        thermostat.prop_algorithm = None
        thermostat.cycle_scheduler = None
        thermostat.is_device_active = False
        thermostat.async_underlying_entity_turn_off = AsyncMock()
        thermostat.async_control_heating = AsyncMock(return_value=True)
        thermostat.update_custom_attributes = MagicMock()
        thermostat.async_write_ha_state = MagicMock()
        created.append(thermostat)
        return thermostat

    yield _make
    created.clear()


@pytest.fixture
def hass_config_dir(hass_tmp_config_dir):
    """Override hass_config_dir to include custom_components with the plugin.

    Also installs the fake ``versatile_thermostat`` integration (dependency of
    the plugin) from tests/fake_vtherm.py, plus the config_flow stub HA needs
    to set up a config entry.
    """
    config_dir = pathlib.Path(hass_tmp_config_dir)
    custom_components_dir = config_dir / "custom_components"
    custom_components_dir.mkdir(parents=True, exist_ok=True)
    repo_root = pathlib.Path(__file__).parent.parent
    shutil.copytree(
        repo_root / "custom_components" / DOMAIN,
        custom_components_dir / DOMAIN,
        dirs_exist_ok=True,
    )
    # Fake versatile_thermostat integration (dependency of the plugin).
    vt_dir = custom_components_dir / "versatile_thermostat"
    vt_dir.mkdir(parents=True, exist_ok=True)
    fake_src = pathlib.Path(__file__).parent / "fake_vtherm.py"
    shutil.copyfile(fake_src, vt_dir / "__init__.py")
    # HA requires a config_flow platform to set up a config entry.
    (vt_dir / "config_flow.py").write_text(
        '"""Config flow for the fake versatile_thermostat."""\n'
        "from homeassistant.config_entries import ConfigFlow\n\n\n"
        "class FakeVThermConfigFlow(ConfigFlow, domain='versatile_thermostat'):\n"
        '    """Fake config flow: not user-facing, tests add entries directly."""\n\n'
        "    async def async_step_user(self, user_input=None):\n"
        "        return self.async_create_entry(title='Fake VTherm', data={})\n",
        encoding="utf-8",
    )
    (vt_dir / "manifest.json").write_text(
        json.dumps(
            {
                "domain": "versatile_thermostat",
                "name": "Versatile Thermostat",
                "version": "0.0.0",
                "codeowners": ["@test"],
                "dependencies": ["climate"],
                "iot_class": "calculated",
            }
        ),
        encoding="utf-8",
    )
    if str(custom_components_dir) not in sys.path:
        sys.path.insert(0, str(custom_components_dir))
    return str(config_dir)
