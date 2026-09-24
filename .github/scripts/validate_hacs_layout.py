#!/usr/bin/env python3
"""Validate the HACS integration layout and manifest.

Catches the regression where the integration package is moved out of the
``custom_components/<domain>/`` directory HACS expects.  The download error
``No manifest.json file found 'custom_components/None/manifest.json'`` occurs
when HACS cannot resolve the integration domain from the repo layout.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_MANIFEST_KEYS = ("domain", "name", "version")
CUSTOM_COMPONENTS = Path("custom_components")
HACS_JSON = Path("hacs.json")


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"ERROR: {path} not found")
    except json.JSONDecodeError as exc:
        sys.exit(f"ERROR: {path} is not valid JSON: {exc}")


def main() -> None:
    errors: list[str] = []

    if not HACS_JSON.exists():
        errors.append("hacs.json not found at repository root")
        hacs = {}
    else:
        hacs = _load_json(HACS_JSON)

    # When content_in_root is true the manifest lives at the repo root.
    # Otherwise it must live under custom_components/<domain>/manifest.json.
    content_in_root = bool(hacs.get("content_in_root", False))

    if content_in_root:
        manifest_dir = Path(".")
    else:
        if not CUSTOM_COMPONENTS.is_dir():
            errors.append("custom_components/ directory not found")
            manifest_dir = None
        else:
            subdirs = [
                d for d in CUSTOM_COMPONENTS.iterdir() if d.is_dir() and not d.name.startswith(".")
            ]
            if len(subdirs) == 0:
                errors.append("custom_components/ contains no integration directory")
                manifest_dir = None
            else:
                manifest_dir = subdirs[0]
                if len(subdirs) > 1:
                    errors.append(
                        "custom_components/ contains multiple integration directories: "
                        + ", ".join(d.name for d in subdirs)
                    )

    if manifest_dir is not None:
        manifest_path = manifest_dir / "manifest.json"
        if not manifest_path.exists():
            errors.append(f"manifest.json not found at {manifest_path}")
        else:
            manifest = _load_json(manifest_path)
            for key in REQUIRED_MANIFEST_KEYS:
                if not manifest.get(key):
                    errors.append(f"manifest.json is missing required key: {key}")
            if manifest_dir.name != manifest.get("domain"):
                errors.append(
                    f"integration directory name {manifest_dir.name!r} does not "
                    f"match manifest domain {manifest.get('domain')!r}"
                )

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        sys.exit(1)

    print("HACS layout OK")


if __name__ == "__main__":
    main()
