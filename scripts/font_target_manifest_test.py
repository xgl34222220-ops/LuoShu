#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))

import font_target_manifest as target  # noqa: E402


def main() -> int:
    inventory = {
        "schema": "device-font-inventory-v1",
        "state": "ready",
        "buildKey": "fixture-build",
        "romKind": "hyperos",
        "scannerRevision": 3,
        "metricsRevision": 3,
        "preservedDynamicAliases": {
            "/system/fonts/MiSansVF_Overlay.ttf": {
                "source": "hyperos-framework-symlink",
                "target": "/data/system/fonts/theme_webview/Roboto-Regular.ttf",
            }
        },
        "slots": {
            "/system/fonts/Roboto-Regular.ttf": {
                "validatedFormat": "TTF",
                "faceIndex": 0,
                "weight": 400,
                "style": "normal",
                "source": "hyperos-physical",
                "families": ["sans-serif"],
            },
            "/my_region/fonts/XiaomiSansRegion-Regular.ttf": {
                "validatedFormat": "TTF",
                "faceIndex": 0,
                "weight": 400,
                "style": "normal",
                "source": "hyperos-physical",
                "families": [],
            },
            "/product/fonts/NotoSansCJK-Regular.ttc": {
                "validatedFormat": "TTC",
                "faceIndex": 1,
                "weight": 400,
                "style": "normal",
                "source": "xml",
                "families": ["sans-serif"],
            },
            "/system/fonts/MiSansVF_Overlay.ttf": {
                "validatedFormat": "TTF",
                "faceIndex": 0,
                "weight": 400,
                "style": "normal",
                "source": "hyperos-rom-reference",
                "metricsReferencePath": "/system/fonts/Roboto-Regular.ttf",
                "families": [],
            },
        },
    }

    manifest = target.compile_manifest(inventory)
    assert manifest["replaceableCount"] == 3, manifest
    assert manifest["physicalCount"] == 2, manifest
    physical = {item["path"] for item in manifest["targets"] if item["mode"] == "physical"}
    assert physical == {
        "/system/fonts/Roboto-Regular.ttf",
        "/my_region/fonts/XiaomiSansRegion-Regular.ttf",
    }, physical
    modes = {item["path"]: item["mode"] for item in manifest["targets"]}
    assert modes["/product/fonts/NotoSansCJK-Regular.ttc"] == "inventory"
    assert "/system/fonts/MiSansVF_Overlay.ttf" not in modes
    assert manifest["partitionCounts"]["my_region"] == 1

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        inventory_path = root / "device_font_inventory.json"
        output = root / "replaceable_font_targets.json"
        list_output = root / "replaceable_font_targets.list"
        inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
        old_argv = sys.argv
        try:
            sys.argv = [
                "font_target_manifest.py",
                "--inventory", str(inventory_path),
                "--output", str(output),
                "--list-output", str(list_output),
            ]
            assert target.main() == 0
        finally:
            sys.argv = old_argv
        saved = json.loads(output.read_text(encoding="utf-8"))
        assert saved["schema"] == target.SCHEMA
        lines = list_output.read_text(encoding="utf-8").splitlines()
        assert any("|my_region|XiaomiSansRegion-Regular.ttf|physical" in line for line in lines)
        assert all("MiSansVF_Overlay.ttf" not in line for line in lines)

    print("Device-specific replaceable font target manifest tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
