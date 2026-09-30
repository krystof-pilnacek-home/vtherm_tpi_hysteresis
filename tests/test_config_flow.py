"""Tests for the vtherm_tpi_hysteresis config flow and options flow."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.selector import SelectSelector
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vtherm_tpi_hysteresis.const import (
    CONF_ALGORITHM,
    CONF_HYSTERESIS_OFF,
    CONF_HYSTERESIS_ON,
    CONF_MAX_ON_PERCENT,
    CONF_MIN_ON_PERCENT,
    CONF_TARGET_VTHERM,
    DEFAULT_ALGORITHM,
    DEFAULT_OPTIONS,
    DOMAIN,
)

pytest_plugins = "pytest_homeassistant_custom_component"


async def setup_climate_entity(hass, entity_id: str = "climate.test_thermostat"):
    """Register a climate entity in the entity registry and state machine."""
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    registry.async_get_or_create(
        domain="climate",
        platform="versatile_thermostat",
        unique_id="uid-test-thermostat",
        suggested_object_id="test_thermostat",
    )
    hass.states.async_set(entity_id, "heat", {"friendly_name": "Test Thermostat"})
    await hass.async_block_till_done()
    return entity_id


async def test_first_user_step_creates_global_defaults(
    hass, hass_config_dir, enable_custom_integrations
):
    """First config entry becomes the global defaults entry."""
    await setup_climate_entity(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Hysteresis defaults"
    assert result["data"] == dict(DEFAULT_OPTIONS)
    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].unique_id == DOMAIN


async def test_second_user_step_shows_thermostat_form(
    hass, hass_config_dir, enable_custom_integrations
):
    """With the global entry present, the user step shows the thermostat form."""
    MockConfigEntry(domain=DOMAIN, data=dict(DEFAULT_OPTIONS), unique_id=DOMAIN).add_to_hass(hass)
    await setup_climate_entity(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "thermostat"


async def test_thermostat_step_creates_per_thermostat_entry(
    hass, hass_config_dir, enable_custom_integrations
):
    """Per-thermostat entry stores the VTherm unique_id."""
    MockConfigEntry(domain=DOMAIN, data=dict(DEFAULT_OPTIONS), unique_id=DOMAIN).add_to_hass(hass)
    entity_id = await setup_climate_entity(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TARGET_VTHERM: entity_id,
            CONF_HYSTERESIS_ON: 1.5,
            CONF_HYSTERESIS_OFF: 0.7,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Test Thermostat"
    assert result["data"][CONF_TARGET_VTHERM] == "uid-test-thermostat"
    assert result["data"][CONF_HYSTERESIS_ON] == 1.5
    assert result["data"][CONF_HYSTERESIS_OFF] == 0.7

    entry = hass.config_entries.async_entries(DOMAIN)[1]
    assert entry.unique_id == f"{DOMAIN}-uid-test-thermostat"


async def test_thermostat_step_invalid_entity_error(
    hass, hass_config_dir, enable_custom_integrations
):
    """A non-registered entity id re-shows the form with an error."""
    MockConfigEntry(domain=DOMAIN, data=dict(DEFAULT_OPTIONS), unique_id=DOMAIN).add_to_hass(hass)
    await setup_climate_entity(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TARGET_VTHERM: "climate.nope"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_TARGET_VTHERM: "invalid_entity"}


async def test_thermostat_step_rejects_inverted_power_limits(
    hass, hass_config_dir, enable_custom_integrations
):
    """min_on_percent > max_on_percent re-shows the form with an error."""
    MockConfigEntry(domain=DOMAIN, data=dict(DEFAULT_OPTIONS), unique_id=DOMAIN).add_to_hass(hass)
    entity_id = await setup_climate_entity(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TARGET_VTHERM: entity_id,
            CONF_MIN_ON_PERCENT: 0.9,
            CONF_MAX_ON_PERCENT: 0.1,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_MAX_ON_PERCENT: "min_greater_than_max"}


async def test_options_flow_rejects_inverted_power_limits(
    hass, hass_config_dir, enable_custom_integrations
):
    """The options flow also rejects min_on_percent > max_on_percent."""
    entry = MockConfigEntry(domain=DOMAIN, data=dict(DEFAULT_OPTIONS), unique_id=DOMAIN)
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_MIN_ON_PERCENT: 0.8, CONF_MAX_ON_PERCENT: 0.2},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_MAX_ON_PERCENT: "min_greater_than_max"}


async def test_thermostat_form_prefills_global_defaults(
    hass, hass_config_dir, enable_custom_integrations
):
    """The per-thermostat form defaults come from the global entry."""
    global_data = dict(DEFAULT_OPTIONS)
    global_data[CONF_HYSTERESIS_ON] = 1.0
    global_data[CONF_HYSTERESIS_OFF] = 0.5
    MockConfigEntry(domain=DOMAIN, data=global_data, unique_id=DOMAIN).add_to_hass(hass)
    await setup_climate_entity(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    schema_keys = {str(k): k for k in result["data_schema"].schema}
    assert schema_keys[CONF_HYSTERESIS_ON].default() == 1.0
    assert schema_keys[CONF_HYSTERESIS_OFF].default() == 0.5


async def test_options_flow_updates_entry(hass, hass_config_dir, enable_custom_integrations):
    """The options flow edits the stored options."""
    entry = MockConfigEntry(domain=DOMAIN, data=dict(DEFAULT_OPTIONS), unique_id=DOMAIN)
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_HYSTERESIS_ON: 1.2,
            CONF_HYSTERESIS_OFF: 0.6,
            CONF_ALGORITHM: "on_off",
            CONF_MIN_ON_PERCENT: 0.0,
            CONF_MAX_ON_PERCENT: 1.0,
        },
    )
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_HYSTERESIS_ON] == 1.2
    assert entry.options[CONF_ALGORITHM] == DEFAULT_ALGORITHM


async def test_algorithm_in_options_schema(hass, hass_config_dir, enable_custom_integrations):
    """The options flow offers the algorithm dropdown with registered presets."""
    entry = MockConfigEntry(domain=DOMAIN, data=dict(DEFAULT_OPTIONS), unique_id=DOMAIN)
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    schema = result["data_schema"]
    algorithm_key = next(k for k in schema.schema if str(k) == CONF_ALGORITHM)
    selector = schema.schema[algorithm_key]
    assert isinstance(selector, SelectSelector)
    options = selector.config["options"]
    assert "on_off" in options
    assert DEFAULT_ALGORITHM in options
