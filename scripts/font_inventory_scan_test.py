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


def run(command: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)


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
    script = common / "font_inventory_scan.py"

    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        primary = ("system", "system_ext", "product", "my_product", "vendor")
        auxiliary = ("odm", "oem", "my_region", "hw_product")
        font_dirs = {name: temp / name / "fonts" for name in (*primary, *auxiliary)}
        etc_dirs = {name: temp / name / "etc" for name in (*primary, *auxiliary)}
        for path in (*font_dirs.values(), *etc_dirs.values()):
            path.mkdir(parents=True)

        shutil.copy2(args.font, font_dirs["system"] / "Roboto-Regular.ttf")
        # Absent from XML and every OEM filename heuristic: revision 5 must
        # discover this slot from real font structure/coverage alone.
        shutil.copy2(args.font, font_dirs["system_ext"] / "MysteryUiFace-Regular.ttf")
        shutil.copy2(args.font, font_dirs["product"] / "ProductUi-Regular.ttf")
        shutil.copy2(args.font, font_dirs["my_product"] / "SysFont-Hans-Regular.ttf")
        os.link(font_dirs["product"] / "ProductUi-Regular.ttf", font_dirs["odm"] / "DuplicateProduct.ttf")
        shutil.copy2(args.font, font_dirs["oem"] / "OPlusSans3.0.ttf")
        shutil.copy2(args.font, font_dirs["hw_product"] / "HwUi-Regular.ttf")

        # Nested OEM font roots must be discovered generically, without a Vivo
        # directory/name hard-code. A standalone font elsewhere in the partition
        # is still recorded by the broad census but is not promoted automatically.
        vivo_fonts = temp / "product/vivo/fonts"
        vivo_fonts.mkdir(parents=True)
        shutil.copy2(args.font, vivo_fonts / "VivoFont.ttf")
        vivo_subdir = vivo_fonts / "subdir"
        vivo_subdir.mkdir()
        os.link(vivo_fonts / "VivoFont.ttf", vivo_subdir / "VivoNested.ttf")
        hidden_assets = temp / "product/assets"
        hidden_assets.mkdir(parents=True)
        shutil.copy2(args.font, hidden_assets / "HiddenStandalone.ttf")

        dynamic_root = temp / "dynamic-root"
        future_fonts = dynamic_root / "future_oem/fonts"
        future_etc = dynamic_root / "future_oem/etc"
        future_fonts.mkdir(parents=True)
        future_etc.mkdir(parents=True)
        shutil.copy2(args.font, future_fonts / "FutureUi-Regular.ttf")

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
        (etc_dirs["hw_product"] / "fonts.xml").write_text(
            '<familyset><family name="system-ui"><font weight="400">HwUi-Regular.ttf</font></family></familyset>\n',
            encoding="utf-8",
        )

        (future_etc / "fonts.xml").write_text(
            '<familyset><family name="system-ui"><font weight="400">FutureUi-Regular.ttf</font></family></familyset>\n',
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
            "--build-key", "inventory-v6-rom",
        ]
        for name in primary:
            command.extend(["--" + name.replace("_", "-") + "-fonts", str(font_dirs[name])])
            command.extend(["--" + name.replace("_", "-") + "-etc", str(etc_dirs[name])])
        for name in auxiliary:
            command.extend(["--" + name.replace("_", "-") + "-fonts", str(font_dirs[name])])
            command.extend(["--" + name.replace("_", "-") + "-etc", str(etc_dirs[name])])

        scan_env = {**os.environ, "LUOSHU_DYNAMIC_PARTITION_SCAN_ROOTS": str(dynamic_root)}
        first = run(command, scan_env)
        assert first.returncode == 0, first.stderr
        result = json.loads(first.stdout)
        payload = json.loads(output.read_text(encoding="utf-8"))
        candidates = json.loads((temp / "device_font_candidates.json").read_text(encoding="utf-8"))
        summary = payload["scanSummary"]

        assert payload["scannerRevision"] == 11
        assert payload["romKind"] == "generic"
        assert result["stockFontFileCount"] == 11
        assert result["stockFontUniqueFileCount"] == 9
        assert result["genericSlotCount"] >= 2
        assert result["candidatePathCount"] == 11
        assert result["fontPathCount"] == 11
        assert result["nestedFontRootCount"] == 2
        assert candidates["schema"] == "device-font-candidates-v1"
        assert candidates["fontFileCount"] == 11
        assert candidates["candidateCount"] == 11
        assert candidates["nestedFontFileCount"] == 3
        assert summary["installCandidatePathCount"] == 11
        assert summary["installFontPathCount"] == 11
        assert summary["installNestedFontPathCount"] == 3
        assert summary["nestedReplaceableRootCount"] == 2
        assert summary["stockFontFileCount"] == 11
        assert summary["stockFontUniqueFileCount"] == 9
        assert summary["verifiedScanUiFileCount"] >= 2
        assert summary["partitionFontFileCounts"]["odm"] == 1
        assert summary["partitionUniqueFontFileCounts"]["odm"] == 0
        assert summary["xmlSourceCount"] == 6
        assert payload["slotCount"] == 11
        assert "/system/fonts/Roboto-Regular.ttf" in payload["slots"]
        mystery = payload["slots"]["/system_ext/fonts/MysteryUiFace-Regular.ttf"]
        assert mystery["source"] == "verified-scan"
        assert mystery["validatedBy"] == "fontTools-universal-stock-scan"
        assert "/product/fonts/ProductUi-Regular.ttf" in payload["slots"]
        assert "/my_product/fonts/SysFont-Hans-Regular.ttf" in payload["slots"]
        assert "/oem/fonts/OPlusSans3.0.ttf" in payload["slots"]
        assert "/hw_product/fonts/HwUi-Regular.ttf" in payload["slots"]
        assert "/future_oem/fonts/FutureUi-Regular.ttf" in payload["slots"]
        assert "/product/vivo/fonts/VivoFont.ttf" in payload["slots"]
        assert "/product/vivo/fonts/subdir/VivoNested.ttf" in payload["slots"]
        assert "/product/assets/HiddenStandalone.ttf" in payload["slots"]
        assert any(
            item["path"] == "/product/assets/HiddenStandalone.ttf"
            for item in candidates["paths"]
        )
        assert payload["discoveredPartitions"] == ["future_oem"]
        assert len(payload["discoveredFontRoots"]) == 2, payload["discoveredFontRoots"]
        nested = next(item for item in payload["discoveredFontRoots"] if item["relative"] == "vivo/fonts")
        assert nested["partition"] == "product"
        assert nested["relative"] == "vivo/fonts"
        assert nested["logical"] == "/product/vivo/fonts"
        root_manifest = (temp / "device_font_roots.conf").read_text(encoding="utf-8").strip()
        assert any(line.startswith("product|vivo/fonts|product-nested-") for line in root_manifest.splitlines()), root_manifest
        assert summary["partitionFontFileCounts"]["future_oem"] == 1
        assert (temp / "device_font_partitions.conf").read_text(encoding="utf-8") == "future_oem\n"
        assert "fontSignatures" not in summary
        assert all(not path.startswith("/data/") for path in payload["slots"])

        reused = run(command, scan_env)
        assert reused.returncode == 0, reused.stderr
        reused_result = json.loads(reused.stdout)
        assert reused_result["status"] == "reused"
        assert reused_result["stockFontUniqueFileCount"] == 9
        assert reused_result["genericSlotCount"] >= 2
        assert reused_result["candidatePathCount"] == 11
        assert reused_result["fontPathCount"] == 11
        assert reused_result["nestedFontPathCount"] == 3
        assert reused_result["nestedFontRootCount"] == 2

        scanner = importlib.import_module("font_inventory_scan")
        theme = temp / "theme/fonts"
        theme.mkdir(parents=True)
        shutil.copy2(args.font, theme / "Theme.ttf")
        scanner.THEME_FONT_ROOTS = (theme,)
        assert scanner._theme_override_roots() == [str(theme)]

    print("font_inventory_scan_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
