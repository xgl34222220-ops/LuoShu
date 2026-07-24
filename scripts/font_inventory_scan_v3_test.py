#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
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
    common = root / "common"
    sys.path.insert(0, str(common))
    embedded_fonttools = common / "python/lib/python3.14/site-packages"
    if embedded_fonttools.is_dir():
        previous = os.environ.get("PYTHONPATH", "")
        os.environ["PYTHONPATH"] = str(embedded_fonttools) + (os.pathsep + previous if previous else "")
    script = common / "font_inventory_scan_v3.py"

    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        primary = ("system", "system_ext", "product", "my_product", "vendor")
        auxiliary = ("odm", "oem", "my_region", "hw_product")
        font_dirs = {name: temp / name / "fonts" for name in (*primary, *auxiliary)}
        etc_dirs = {name: temp / name / "etc" for name in (*primary, *auxiliary)}
        for path in (*font_dirs.values(), *etc_dirs.values()):
            path.mkdir(parents=True)

        shutil.copy2(args.font, font_dirs["system"] / "Roboto-Regular.ttf")
        shutil.copy2(args.font, font_dirs["product"] / "ProductUi-Regular.ttf")
        shutil.copy2(args.font, font_dirs["my_product"] / "SysFont-Hans-Regular.ttf")
        os.link(font_dirs["product"] / "ProductUi-Regular.ttf", font_dirs["odm"] / "DuplicateProduct.ttf")
        shutil.copy2(args.font, font_dirs["oem"] / "OPlusSans3.0.ttf")

        (etc_dirs["system"] / "fonts.xml").write_text(
            '<familyset><family name="sans-serif"><font weight="400">Roboto-Regular.ttf</font></family></familyset>\n',
            encoding="utf-8",
        )
        (etc_dirs["product"] / "fonts_customization.xml").write_text(
            '<fonts-modification><family name="system-ui"><font weight="400">ProductUi-Regular.ttf</font></family></fonts-modification>\n',
            encoding="utf-8",
        )
        (etc_dirs["my_product"] / "fonts.xml").write_text(
            '<familyset><family name="sysfont"><font weight="400">SysFont-Hans-Regular.ttf</font></family></familyset>\n',
            encoding="utf-8",
        )
        (etc_dirs["oem"] / "fonts.xml").write_text(
            '<familyset><family name="system-ui"><font weight="400">ProductUi-Regular.ttf</font></family></familyset>\n',
            encoding="utf-8",
        )

        font_check = temp / "font_check.sh"
        font_check.write_text(
            '#!/bin/sh\nprintf \'%s\\n\' \'{"valid":true,"format":"TTF","bytes":4096,"variable":false,"color":false}\'\n',
            encoding="utf-8",
        )
        font_check.chmod(0o755)
        output = temp / "device_font_inventory.json"
        command = [
            sys.executable,
            str(script),
            "--scan",
            "--output", str(output),
            "--font-check", str(font_check),
            "--build-key", "inventory-v3-rom",
        ]
        for name in primary:
            command.extend(["--" + name.replace("_", "-") + "-fonts", str(font_dirs[name])])
            command.extend(["--" + name.replace("_", "-") + "-etc", str(etc_dirs[name])])
        for name in auxiliary:
            command.extend(["--" + name.replace("_", "-") + "-fonts", str(font_dirs[name])])
            command.extend(["--" + name.replace("_", "-") + "-etc", str(etc_dirs[name])])

        first = run(command)
        assert first.returncode == 0, first.stderr
        result = json.loads(first.stdout)
        payload = json.loads(output.read_text(encoding="utf-8"))
        summary = payload["scanSummary"]

        assert payload["scannerRevision"] == 3
        assert payload["romKind"] == "coloros"
        assert result["stockFontFileCount"] == 5
        assert result["stockFontUniqueFileCount"] == 4
        assert summary["stockFontFileCount"] == 5
        assert summary["stockFontUniqueFileCount"] == 4
        assert summary["partitionFontFileCounts"]["odm"] == 1
        assert summary["partitionUniqueFontFileCounts"]["odm"] == 0
        assert summary["xmlSourceCount"] == 4
        assert payload["slotCount"] == 3
        assert "/system/fonts/Roboto-Regular.ttf" in payload["slots"]
        assert "/product/fonts/ProductUi-Regular.ttf" in payload["slots"]
        assert "/my_product/fonts/SysFont-Hans-Regular.ttf" in payload["slots"]
        assert summary["fontSignatures"]["coloros"] == ["SysFont-Hans-Regular.ttf", "OPlusSans3.0.ttf"]
        assert "Roboto-Regular.ttf" in summary["fontSignatures"]["aosp"]
        assert all(not path.startswith("/data/") for path in payload["slots"])

        reused = run(command)
        assert reused.returncode == 0, reused.stderr
        reused_result = json.loads(reused.stdout)
        assert reused_result["status"] == "reused"
        assert reused_result["stockFontUniqueFileCount"] == 4

        scanner = importlib.import_module("font_inventory_scan_v3")
        theme = temp / "theme/fonts"
        theme.mkdir(parents=True)
        shutil.copy2(args.font, theme / "Theme.ttf")
        scanner.THEME_FONT_ROOTS = (theme,)
        assert scanner._theme_override_roots() == [str(theme)]

    print("font_inventory_scan_v3_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
