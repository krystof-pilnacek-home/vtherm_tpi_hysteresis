"""Device registry cleanup for Hysteresis config entries."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import helper_integration


def cleanup_config_entry_devices(
    hass: HomeAssistant,
    config_entry_id: str,
) -> None:
    """Remove devices left by config-entry co-ownership."""
    if remove_helper_devices := getattr(
        helper_integration,
        "async_remove_helper_devices",
        None,
    ):
        remove_helper_devices(
            hass,
            helper_config_entry_id=config_entry_id,
            source_device_id=None,
            remove_all_devices=True,
        )
        return

    device_registry = dr.async_get(hass)
    device_ids = {
        device.id
        for device in dr.async_entries_for_config_entry(
            device_registry,
            config_entry_id,
        )
    }
    for device_id in sorted(device_ids):
        helper_integration.async_remove_helper_config_entry_from_source_device(
            hass,
            helper_config_entry_id=config_entry_id,
            source_device_id=device_id,
        )
