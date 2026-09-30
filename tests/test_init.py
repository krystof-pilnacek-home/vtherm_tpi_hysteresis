"""Tests for the vtherm_tpi_hysteresis integration setup and reload logic.

Runs against the real HomeAssistant test instance (stove_controller
convention).  A fake ``versatile_thermostat`` integration is installed into
the temp config dir by the ``hass_config_dir`` fixture so the plugin's
manifest dependency resolves.
"""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)
from vtherm_api.vtherm_api import VThermAPI
from vtherm_tpi_hysteresis.const import (
    CONF_HYSTERESIS_ON,
    CONF_PROP_FUNCTION,
    CONF_TARGET_VTHERM,
    DEFAULT_OPTIONS,
    DOMAIN,
    PROP_FUNCTION_TPI_HYSTERESIS,
)

pytest_plugins = "pytest_homeassistant_custom_component"

VT_DOMAIN = "versatile_thermostat"


def make_global_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data=dict(DEFAULT_OPTIONS),
        unique_id=DOMAIN,
        entry_id="global_entry",
        version=1,
    )


def make_vtherm_entry(
    unique_id: str = "vt_1",
    entry_id: str = "vt_entry_1",
    prop_function: str = PROP_FUNCTION_TPI_HYSTERESIS,
) -> MockConfigEntry:
    return MockConfigEntry(
        domain=VT_DOMAIN,
        data={CONF_PROP_FUNCTION: prop_function},
        unique_id=unique_id,
        entry_id=entry_id,
        version=1,
    )


async def test_async_setup_registers_factory(hass, hass_config_dir, enable_custom_integrations):
    """async_setup registers the factory even without config entries."""
    from homeassistant import setup

    assert await setup.async_setup_component(hass, DOMAIN, {})
    api = VThermAPI.get_vtherm_api(hass)
    factory = api.get_prop_algorithm(PROP_FUNCTION_TPI_HYSTERESIS)
    assert factory is not None
    assert factory.name == PROP_FUNCTION_TPI_HYSTERESIS


async def test_setup_entry_registers_factory_idempotently(
    hass, hass_config_dir, enable_custom_integrations
):
    """Setting up multiple entries keeps a single factory registration."""
    entry = make_global_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    per_thermostat = MockConfigEntry(
        domain=DOMAIN,
        data={**dict(DEFAULT_OPTIONS), CONF_TARGET_VTHERM: "vt_1"},
        unique_id=f"{DOMAIN}-vt_1",
        entry_id="per_1",
        version=1,
    )
    per_thermostat.add_to_hass(hass)
    assert await hass.config_entries.async_setup(per_thermostat.entry_id)
    await hass.async_block_till_done()

    api = VThermAPI.get_vtherm_api(hass)
    factories = [f for f in [api.get_prop_algorithm(PROP_FUNCTION_TPI_HYSTERESIS)] if f is not None]
    assert len(factories) == 1
    # Registration flag is tracked in hass.data
    assert hass.data[DOMAIN]["factory_registered"] is True


async def test_unload_last_entry_unregisters_factory(
    hass, hass_config_dir, enable_custom_integrations
):
    """Unloading the last plugin entry unregisters the factory."""
    entry = make_global_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    api = VThermAPI.get_vtherm_api(hass)
    assert api.get_prop_algorithm(PROP_FUNCTION_TPI_HYSTERESIS) is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert api.get_prop_algorithm(PROP_FUNCTION_TPI_HYSTERESIS) is None


async def test_unload_one_of_several_keeps_factory(
    hass, hass_config_dir, enable_custom_integrations
):
    """Unloading one of several entries keeps the factory registered."""
    entry = make_global_entry()
    entry.add_to_hass(hass)
    per_thermostat = MockConfigEntry(
        domain=DOMAIN,
        data={**dict(DEFAULT_OPTIONS), CONF_TARGET_VTHERM: "vt_1"},
        unique_id=f"{DOMAIN}-vt_1",
        entry_id="per_1",
        version=1,
    )
    per_thermostat.add_to_hass(hass)
    # Setting up any entry sets up the component (and thus both entries).
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    api = VThermAPI.get_vtherm_api(hass)
    assert api.get_prop_algorithm(PROP_FUNCTION_TPI_HYSTERESIS) is not None


async def test_options_update_reloads_matching_vtherm(
    hass, hass_config_dir, enable_custom_integrations
):
    """Options update on a per-thermostat entry reloads only that VTherm."""
    from unittest.mock import patch

    entry = make_global_entry()
    entry.add_to_hass(hass)
    per_thermostat = MockConfigEntry(
        domain=DOMAIN,
        data={
            **dict(DEFAULT_OPTIONS),
            CONF_TARGET_VTHERM: "vt_1",
            CONF_HYSTERESIS_ON: 0.5,
        },
        unique_id=f"{DOMAIN}-vt_1",
        entry_id="per_1",
        version=1,
    )
    per_thermostat.add_to_hass(hass)
    # Setting up any entry sets up the component (and thus both entries).
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state.value == "loaded"
    assert per_thermostat.state.value == "loaded"

    vt_entry = make_vtherm_entry()
    vt_entry.add_to_hass(hass)
    vt_entry_2 = make_vtherm_entry("vt_2", "vt_entry_2")
    vt_entry_2.add_to_hass(hass)
    await hass.async_block_till_done()

    with patch.object(
        hass.config_entries, "async_reload", wraps=hass.config_entries.async_reload
    ) as reload_mock:
        hass.config_entries.async_update_entry(per_thermostat, options={CONF_HYSTERESIS_ON: 1.5})
        await hass.async_block_till_done()
        # Only the matching VTherm entry is reloaded
        reloaded = [call.args[0] for call in reload_mock.await_args_list if call.args]
        assert reloaded == ["vt_entry_1"]
        assert reload_mock.await_count == 1


async def test_options_update_global_skips_overridden_vtherms(
    hass, hass_config_dir, enable_custom_integrations
):
    """Global-defaults update skips VTherms that have their own entry."""
    from unittest.mock import patch

    entry = make_global_entry()
    entry.add_to_hass(hass)
    per_thermostat = MockConfigEntry(
        domain=DOMAIN,
        data={**dict(DEFAULT_OPTIONS), CONF_TARGET_VTHERM: "vt_1"},
        unique_id=f"{DOMAIN}-vt_1",
        entry_id="per_1",
        version=1,
    )
    per_thermostat.add_to_hass(hass)
    # Setting up any entry sets up the component (and thus both entries).
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state.value == "loaded"
    assert per_thermostat.state.value == "loaded"

    # vt_1 has a per-thermostat override; vt_2 uses global defaults
    vt_overridden = make_vtherm_entry("vt_1", "vt_entry_1")
    vt_overridden.add_to_hass(hass)
    vt_global = make_vtherm_entry("vt_2", "vt_entry_2")
    vt_global.add_to_hass(hass)
    await hass.async_block_till_done()

    with patch.object(
        hass.config_entries, "async_reload", wraps=hass.config_entries.async_reload
    ) as reload_mock:
        hass.config_entries.async_update_entry(entry, options={CONF_HYSTERESIS_ON: 2.0})
        await hass.async_block_till_done()
        reloaded = [call.args[0] for call in reload_mock.await_args_list if call.args]
        assert "vt_entry_2" in reloaded
        assert "vt_entry_1" not in reloaded


async def test_factory_reregistered_after_vtherm_reload(
    hass, hass_config_dir, enable_custom_integrations
):
    """The VThermAPI-recreation pitfall: after VT reloads destroy the API
    registry, the plugin re-registers the factory and retries
    init_vtherm_links so entities get a second chance."""
    entry = make_global_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    vt_entry = make_vtherm_entry()
    vt_entry.add_to_hass(hass)

    api = VThermAPI.get_vtherm_api(hass)
    assert api.get_prop_algorithm(PROP_FUNCTION_TPI_HYSTERESIS) is not None

    # Simulate VT reload destroying and recreating the API instance
    VThermAPI.reset_vtherm_api()
    api2 = VThermAPI.get_vtherm_api(hass)
    assert api2 is not api
    assert api2.get_prop_algorithm(PROP_FUNCTION_TPI_HYSTERESIS) is None

    # Now reload the plugin options: the reload path re-registers the factory
    # on the new API instance.
    hass.config_entries.async_update_entry(entry, options={CONF_HYSTERESIS_ON: 1.2})
    await hass.async_block_till_done()
    assert api2.get_prop_algorithm(PROP_FUNCTION_TPI_HYSTERESIS) is not None
