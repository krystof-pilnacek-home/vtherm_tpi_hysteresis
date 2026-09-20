"""Test configuration for standalone unit tests."""

from __future__ import annotations

import sys
import types
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CUSTOM_COMPONENTS_ROOT = PROJECT_ROOT / "custom_components"
INTEGRATION_ROOT = CUSTOM_COMPONENTS_ROOT / "vtherm_hysteresis"


def _ensure_project_on_path() -> None:
    """Make the repository importable for pytest."""
    project_root_str = str(PROJECT_ROOT)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)


def _ensure_package_stub(name: str, path: Path) -> None:
    """Register a lightweight package stub without importing its __init__."""
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    module.__path__ = [str(path)]


def _ensure_homeassistant_stubs() -> None:
    """Provide the minimal Home Assistant surface used by unit tests."""
    if "homeassistant" in sys.modules:
        return

    homeassistant = types.ModuleType("homeassistant")
    helpers = types.ModuleType("homeassistant.helpers")
    storage = types.ModuleType("homeassistant.helpers.storage")
    util = types.ModuleType("homeassistant.util")

    class Store:
        """Minimal stub used by handler unit tests."""

        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def async_load(self):
            """Return no persisted data."""
            return None

        async def async_save(self, _data) -> None:
            """Accept persisted data."""
            return None

    def slugify(value: object) -> str:
        """Return a simple deterministic slug for tests."""
        return str(value).lower().replace(" ", "_")

    storage.Store = Store
    util.slugify = slugify
    homeassistant.helpers = helpers
    homeassistant.util = util
    helpers.storage = storage

    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.storage"] = storage
    sys.modules["homeassistant.util"] = util


_ensure_project_on_path()
_ensure_package_stub("custom_components", CUSTOM_COMPONENTS_ROOT)
_ensure_package_stub("custom_components.vtherm_hysteresis", INTEGRATION_ROOT)
_ensure_homeassistant_stubs()
