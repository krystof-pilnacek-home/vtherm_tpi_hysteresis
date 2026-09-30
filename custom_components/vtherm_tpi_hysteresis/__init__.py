"""The vtherm_tpi_hysteresis integration."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CoreState, HomeAssistant
from vtherm_api.log_collector import get_vtherm_logger
from vtherm_api.vtherm_api import VThermAPI

from .const import (
    CONF_PROP_FUNCTION,
    CONF_TARGET_VTHERM,
    DATA_FACTORY_REGISTERED,
    DOMAIN,
    PROP_FUNCTION_TPI_HYSTERESIS,
)
from .device_link import cleanup_config_entry_devices
from .factory import HysteresisHandlerFactory

VT_DOMAIN = "versatile_thermostat"

_LOGGER = get_vtherm_logger(__name__)


def _ensure_domain_data(hass: HomeAssistant) -> dict[str, Any]:
    """Return the plugin data storage in hass."""
    return hass.data.setdefault(DOMAIN, {})


def _register_factory(hass: HomeAssistant) -> bool:
    """Register the Hysteresis factory in the shared VT API."""
    data = _ensure_domain_data(hass)
    if data.get(DATA_FACTORY_REGISTERED) is True:
        return True

    api = VThermAPI.get_vtherm_api(hass)
    if api is None:
        _LOGGER.warning(
            "Unable to register Hysteresis factory because VThermAPI is unavailable"
        )
        return False

    factory = HysteresisHandlerFactory()
    existing_factory = api.get_prop_algorithm(factory.name)
    if existing_factory is None:
        api.register_prop_algorithm(factory)

    data[DATA_FACTORY_REGISTERED] = True
    return True


def _unregister_factory(hass: HomeAssistant) -> None:
    """Unregister the Hysteresis factory from the shared VT API."""
    api = VThermAPI.get_vtherm_api(hass)
    if api is not None:
        api.unregister_prop_algorithm(PROP_FUNCTION_TPI_HYSTERESIS)
    _ensure_domain_data(hass)[DATA_FACTORY_REGISTERED] = False


async def _reload_hysteresis_vtherms(
    hass: HomeAssistant,
    source_entry: ConfigEntry | None = None,
) -> None:
    """Reload VT entries that currently target the Hysteresis proportional function."""
    target_unique_id = None
    reload_global_defaults = False
    if source_entry is not None:
        target_unique_id = source_entry.data.get(CONF_TARGET_VTHERM)
        reload_global_defaults = target_unique_id is None

    per_thermostat_targets = {
        entry.data.get(CONF_TARGET_VTHERM)
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.data.get(CONF_TARGET_VTHERM)
    }

    reload_tasks = []
    for entry in hass.config_entries.async_entries(VT_DOMAIN):
        if entry.data.get(CONF_PROP_FUNCTION) != PROP_FUNCTION_TPI_HYSTERESIS:
            continue

        if target_unique_id is not None:
            if entry.unique_id != target_unique_id:
                continue
        elif reload_global_defaults and entry.unique_id in per_thermostat_targets:
            continue

        reload_tasks.append(hass.config_entries.async_reload(entry.entry_id))

    if reload_tasks:
        await asyncio.gather(*reload_tasks)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up vtherm_tpi_hysteresis from YAML."""
    del config
    _register_factory(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up vtherm_tpi_hysteresis from a config entry."""
    _ensure_domain_data(hass)[entry.entry_id] = entry.entry_id
    cleanup_config_entry_devices(hass, entry.entry_id)
    _register_factory(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_options))

    # During initial startup VT restores its own entities after HA starts.
    # Reloading them here would be redundant and could disturb state restore.
    if hass.state == CoreState.running:
        await _reload_hysteresis_vtherms(hass)
    return True


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload VT thermostats when options are changed so the new parameters apply."""
    await _reload_hysteresis_vtherms(hass, source_entry=entry)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a vtherm_tpi_hysteresis config entry."""
    data = _ensure_domain_data(hass)
    data.pop(entry.entry_id, None)

    if not [key for key in data if key != DATA_FACTORY_REGISTERED]:
        _unregister_factory(hass)

    await _reload_hysteresis_vtherms(hass)
    return True
