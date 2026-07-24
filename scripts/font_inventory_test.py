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
    script = root / "common/font_inventory.py"
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        system_fonts = temp / "system/fonts"
        system_ext_fonts = temp / "system_ext/fonts"
        product_fonts = temp / "product/fonts"
        my_product_fonts = temp / "my_product/fonts"
        vendor_fonts = temp / "vendor/fonts"
        system_etc = temp / "system/etc"
        for path in (system_fonts, system_ext_fonts, product_fonts, my_product_fonts, vendor_fonts, system_etc):
            path.mkdir(parents=True)

        for destination in (
            system_fonts / "Roboto-Regular.ttf",
            system_fonts / "NotoSerif-Regular.ttf",
            system_fonts / "NotoSansArabic-Regular.ttf",
            system_fonts / "MiSansVF.ttf",
            system_fonts / "400.ttf",
            system_ext_fonts / "GoogleSansText-Regular.ttf",
            product_fonts / "SysFont-Hans-Regular.ttf",
        ):
            shutil.copy2(args.font, destination)
        (system_fonts / "MiSansTCVF.ttf").write_bytes(b"not-a-font" * 1024)

        (system_etc / "fonts.xml").write_text(
            """<?xml version="1.0" encoding="utf-8"?>
<familyset>
  <family name="sans-serif">
    <font weight="400" style="normal">Roboto-Regular.ttf</font>
  </family>
  <family name="serif">
    <font weight="400">NotoSerif-Regular.ttf</font>
  </family>
  <family name="sans-serif-arabic" lang="ar">
    <font weight="400">NotoSansArabic-Regular.ttf</font>
  </family>
  <alias name="system-ui" to="sans-serif" />
</familyset>
""",
            encoding="utf-8",
        )
        (system_etc / "font_fallback.xml").write_text("<familyset><family><font>NotoSerif-Regular.ttf</font></family></familyset>\n", encoding="utf-8")

        font_check = temp / "font_check.sh"
        font_check.write_text(
            """#!/bin/sh
file="$2"
case "${file##*/}" in
  MiSansTCVF.ttf) printf '%s\n' '{"valid":false,"format":"UNKNOWN"}'; exit 1 ;;
  *) printf '%s\n' '{"valid":true,"format":"TTF","bytes":4096,"variable":false,"color":false}' ;;
esac
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
            str(system_fonts),
            "--system-ext-fonts",
            str(system_ext_fonts),
            "--product-fonts",
            str(product_fonts),
            "--my-product-fonts",
            str(my_product_fonts),
            "--vendor-fonts",
            str(vendor_fonts),
            "--system-etc",
            str(system_etc),
        ]

        first = run([*base, "--build-key", "rom-a"])
        assert first.returncode == 0, first.stderr
        payload = json.loads(output.read_text(encoding="utf-8"))
        slots = payload["slots"]
        assert payload["schema"] == "device-font-inventory-v1"
        assert payload["buildKey"] == "rom-a"
        assert payload["mainSlot"]["slotName"] == "MiSansVF.ttf"
        assert payload["romKind"] == "hyperos"
        assert "/system/fonts/Roboto-Regular.ttf" in slots
        assert "/system/fonts/MiSansVF.ttf" in slots
        assert "/system/fonts/400.ttf" in slots
        assert "/system_ext/fonts/GoogleSansText-Regular.ttf" in slots
        assert "/product/fonts/SysFont-Hans-Regular.ttf" in slots
        assert "/system/fonts/NotoSerif-Regular.ttf" not in slots
        assert "/system/fonts/NotoSansArabic-Regular.ttf" not in slots
        assert "/system/fonts/MiSansTCVF.ttf" not in slots
        metrics = payload["mainSlot"]["metrics"]
        assert metrics["upem"] > 0
        assert metrics["hhea"]["ascent"] > 0
        assert metrics["hhea"]["descent"] < 0
        assert payload["families"]["sans-serif"] == ["/system/fonts/Roboto-Regular.ttf"]
        assert payload["families"]["system-ui"] == ["/system/fonts/Roboto-Regular.ttf"]

        listed = run([sys.executable, str(script), "--list", "--output", str(output), "--build-key", "rom-a"])
        assert listed.returncode == 0, listed.stderr
        assert "/system/fonts/MiSansVF.ttf\tMiSansVF.ttf\tsystem\tTTF" in listed.stdout

        # Same fingerprint reuses the frozen stock inventory even if the live directory changes.
        (system_fonts / "MiSansVF.ttf").unlink()
        reused = run([*base, "--build-key", "rom-a"])
        assert reused.returncode == 0, reused.stderr
        assert json.loads(reused.stdout)["status"] == "reused"
        assert json.loads(output.read_text(encoding="utf-8"))["mainSlot"]["slotName"] == "MiSansVF.ttf"

        # A new fingerprint forces a rescan and therefore selects the remaining AOSP main slot.
        refreshed = run([*base, "--build-key", "rom-b"])
        assert refreshed.returncode == 0, refreshed.stderr
        refreshed_payload = json.loads(output.read_text(encoding="utf-8"))
        assert refreshed_payload["buildKey"] == "rom-b"
        assert refreshed_payload["mainSlot"]["slotName"] == "SysFont-Hans-Regular.ttf"
        assert refreshed_payload["romKind"] == "coloros"
        assert "/system/fonts/MiSansVF.ttf" not in refreshed_payload["slots"]

        # When a changed build cannot be rescanned safely, the stale file is removed so both the
        # mapper and normalizer fall back instead of consuming metrics from the previous ROM.
        for root_path in (system_fonts, system_ext_fonts, product_fonts, my_product_fonts, vendor_fonts):
            for font_file in root_path.iterdir():
                if font_file.is_file():
                    font_file.unlink()
        for xml_file in system_etc.iterdir():
            if xml_file.is_file():
                xml_file.unlink()
        failed = run([*base, "--build-key", "rom-c"])
        assert failed.returncode != 0
        assert not output.exists()

    print("font_inventory_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
