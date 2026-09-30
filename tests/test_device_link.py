"""Tests for Hysteresis device registry cleanup."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, call

from vtherm_tpi_hysteresis import device_link


def test_cleanup_config_entry_devices_uses_modern_sweep(monkeypatch) -> None:
    """Modern cleanup should remove every Hysteresis-owned device."""
    hass = MagicMock()
    remove_helper_devices = MagicMock()
    monkeypatch.setattr(
        device_link.helper_integration,
        "async_remove_helper_devices",
        remove_helper_devices,
        raising=False,
    )

    device_link.cleanup_config_entry_devices(hass, "hysteresis-entry-id")

    remove_helper_devices.assert_called_once_with(
        hass,
        helper_config_entry_id="hysteresis-entry-id",
        source_device_id=None,
        remove_all_devices=True,
    )


def test_cleanup_config_entry_devices_uses_legacy_helper(monkeypatch) -> None:
    """Legacy cleanup should unlink every shared device deterministically."""
    hass = MagicMock()
    device_registry = MagicMock()
    legacy_cleanup = MagicMock()
    monkeypatch.setattr(device_link.dr, "async_get", lambda _hass: device_registry)
    monkeypatch.setattr(
        device_link.dr,
        "async_entries_for_config_entry",
        lambda _registry, _entry_id: [
            SimpleNamespace(id="device-living-room"),
            SimpleNamespace(id="device-bedroom"),
        ],
    )
    monkeypatch.delattr(
        device_link.helper_integration,
        "async_remove_helper_devices",
        raising=False,
    )
    monkeypatch.setattr(
        device_link.helper_integration,
        "async_remove_helper_config_entry_from_source_device",
        legacy_cleanup,
    )

    device_link.cleanup_config_entry_devices(hass, "hysteresis-entry-id")

    assert legacy_cleanup.call_args_list == [
        call(
            hass,
            helper_config_entry_id="hysteresis-entry-id",
            source_device_id="device-bedroom",
        ),
        call(
            hass,
            helper_config_entry_id="hysteresis-entry-id",
            source_device_id="device-living-room",
        ),
    ]


def test_cleanup_config_entry_devices_legacy_path_accepts_no_devices(
    monkeypatch,
) -> None:
    """Legacy cleanup should be a no-op when the entry owns no devices."""
    hass = MagicMock()
    device_registry = MagicMock()
    legacy_cleanup = MagicMock()
    monkeypatch.setattr(device_link.dr, "async_get", lambda _hass: device_registry)
    monkeypatch.setattr(
        device_link.dr,
        "async_entries_for_config_entry",
        lambda _registry, _entry_id: [],
    )
    monkeypatch.delattr(
        device_link.helper_integration,
        "async_remove_helper_devices",
        raising=False,
    )
    monkeypatch.setattr(
        device_link.helper_integration,
        "async_remove_helper_config_entry_from_source_device",
        legacy_cleanup,
    )

    device_link.cleanup_config_entry_devices(hass, "hysteresis-entry-id")

    legacy_cleanup.assert_not_called()
