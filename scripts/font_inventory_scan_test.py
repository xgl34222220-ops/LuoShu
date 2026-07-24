#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", type=Path, required=True)
    args = parser.parse_args()
    if not args.font.is_file():
        raise SystemExit("test font missing")

    root = Path(__file__).resolve().parents[1]
    embedded_fonttools = root / "common/python/lib/python3.14/site-packages"
    if embedded_fonttools.is_dir():
        previous = os.environ.get("PYTHONPATH", "")
        os.environ["PYTHONPATH"] = str(embedded_fonttools) + (os.pathsep + previous if previous else "")
    script = root / "common/font_inventory_scan.py"

    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        partitions = ("system", "system_ext", "product", "my_product", "vendor")
        font_dirs = {name: temp / name / "fonts" for name in partitions}
        etc_dirs = {name: temp / name / "etc" for name in partitions}
        for path in (*font_dirs.values(), *etc_dirs.values()):
            path.mkdir(parents=True)

        stock_files = (
            font_dirs["system"] / "Roboto-Regular.ttf",
            font_dirs["system"] / "Roboto-Italic.ttf",
            font_dirs["system"] / "NotoSerif-Regular.ttf",
            font_dirs["system_ext"] / "GoogleSansText-Regular.ttf",
            font_dirs["product"] / "ProductUi-Regular.ttf",
            font_dirs["my_product"] / "SysFont-Hans-Regular.ttf",
            font_dirs["vendor"] / "VendorSymbol.ttf",
        )
        for destination in stock_files:
            shutil.copy2(args.font, destination)

        (etc_dirs["system"] / "fonts.xml").write_text(
            """<?xml version="1.0" encoding="utf-8"?>
<familyset>
  <family name="sans-serif">
    <font weight="400" style="normal">Roboto-Regular.ttf</font>
    <font weight="400" style="italic">Roboto-Italic.ttf</font>
  </family>
  <family name="serif">
    <font weight="400">NotoSerif-Regular.ttf</font>
  </family>
</familyset>
""",
            encoding="utf-8",
        )
        (etc_dirs["system_ext"] / "fonts_overlay.xml").write_text(
            """<familyset>
  <family name="google-sans-text">
    <font weight="400">GoogleSansText-Regular.ttf</font>
  </family>
</familyset>
""",
            encoding="utf-8",
        )
        (etc_dirs["product"] / "fonts_customization.xml").write_text(
            """<fonts-modification version="1">
  <family customizationType="new-named-family" name="system-ui">
    <font weight="400">ProductUi-Regular.ttf</font>
  </family>
</fonts-modification>
""",
            encoding="utf-8",
        )
        (etc_dirs["my_product"] / "fonts.xml").write_text(
            """<familyset>
  <family name="sysfont">
    <font weight="400">SysFont-Hans-Regular.ttf</font>
  </family>
</familyset>
""",
            encoding="utf-8",
        )

        font_check = temp / "font_check.sh"
        font_check.write_text(
            """#!/bin/sh
printf '%s\n' '{"valid":true,"format":"TTF","bytes":4096,"variable":false,"color":false}'
""",
            encoding="utf-8",
        )
        font_check.chmod(0o755)
        output = temp / "device_font_inventory.json"
        base = [
            sys.executable,
            str(script),
            "--scan",
            "--output",
            str(output),
            "--font-check",
            str(font_check),
            "--system-fonts",
            str(font_dirs["system"]),
            "--system-ext-fonts",
            str(font_dirs["system_ext"]),
            "--product-fonts",
            str(font_dirs["product"]),
            "--my-product-fonts",
            str(font_dirs["my_product"]),
            "--vendor-fonts",
            str(font_dirs["vendor"]),
            "--system-etc",
            str(etc_dirs["system"]),
            "--system-ext-etc",
            str(etc_dirs["system_ext"]),
            "--product-etc",
            str(etc_dirs["product"]),
            "--my-product-etc",
            str(etc_dirs["my_product"]),
            "--vendor-etc",
            str(etc_dirs["vendor"]),
        ]

        first = run([*base, "--build-key", "partition-rom-a"])
        assert first.returncode == 0, first.stderr
        result = json.loads(first.stdout)
        payload = json.loads(output.read_text(encoding="utf-8"))
        slots = payload["slots"]
        summary = payload["scanSummary"]

        assert payload["scannerRevision"] == 2
        assert payload["romKind"] == "coloros"
        assert result["stockFontFileCount"] == len(stock_files)
        assert summary["stockFontFileCount"] == len(stock_files)
        assert summary["partitionFontFileCounts"] == {
            "system": 3,
            "system_ext": 1,
            "product": 1,
            "my_product": 1,
            "vendor": 1,
        }
        assert summary["xmlSourceCount"] == 4
        assert summary["uiFileCount"] == 5
        assert summary["xmlUiFileCount"] == 5
        assert summary["heuristicUiFileCount"] == 0
        assert summary["uiXmlFaceCount"] == 5

        # The v1 substring classifier incorrectly rejected the exact family name sans-serif.
        assert slots["/system/fonts/Roboto-Regular.ttf"]["source"] == "xml"
        assert "sans-serif" in slots["/system/fonts/Roboto-Regular.ttf"]["families"]
        assert slots["/system/fonts/Roboto-Italic.ttf"]["source"] == "xml"

        # Product and OEM XML must resolve files in their own partitions before same-name files elsewhere.
        assert slots["/product/fonts/ProductUi-Regular.ttf"]["source"] == "xml"
        assert slots["/my_product/fonts/SysFont-Hans-Regular.ttf"]["source"] == "xml"
        assert "/system/fonts/NotoSerif-Regular.ttf" not in slots
        assert "/vendor/fonts/VendorSymbol.ttf" not in slots

        reused = run([*base, "--build-key", "partition-rom-a"])
        assert reused.returncode == 0, reused.stderr
        reused_result = json.loads(reused.stdout)
        assert reused_result["status"] == "reused"
        assert reused_result["stockFontFileCount"] == len(stock_files)
        assert reused_result["slotCount"] == 5

        # The count is derived from the ROM tree, not a fixed 18-slot template.
        extra = font_dirs["product"] / "ProductUi-Medium.ttf"
        shutil.copy2(args.font, extra)
        (etc_dirs["product"] / "fonts_customization.xml").write_text(
            """<fonts-modification version="1">
  <family customizationType="new-named-family" name="system-ui">
    <font weight="400">ProductUi-Regular.ttf</font>
    <font weight="500">ProductUi-Medium.ttf</font>
  </family>
</fonts-modification>
""",
            encoding="utf-8",
        )
        refreshed = run([*base, "--build-key", "partition-rom-b"])
        assert refreshed.returncode == 0, refreshed.stderr
        refreshed_payload = json.loads(output.read_text(encoding="utf-8"))
        assert refreshed_payload["scanSummary"]["stockFontFileCount"] == len(stock_files) + 1
        assert refreshed_payload["slotCount"] == 6
        assert "/product/fonts/ProductUi-Medium.ttf" in refreshed_payload["slots"]

    print("font_inventory_scan_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
