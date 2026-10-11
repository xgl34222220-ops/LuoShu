#!/usr/bin/env python3
"""Fixture tests for the read-only three-way XML parity / updatable-font diagnostic."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "common"))
import device_font_xml_parity as parity  # noqa: E402

FONTS_XML = """<?xml version="1.0" encoding="utf-8"?>
<familyset version="23">
    <family name="sans-serif">
        <font weight="100" style="normal">Roboto-Regular.ttf
            <axis tag="wght" stylevalue="100" />
        </font>
        <font weight="400" style="normal">{sans}</font>
        <font weight="400" style="italic">Roboto-Italic.ttf</font>
    </family>
    <alias name="sans-serif-medium" to="sans-serif" weight="500" />
    <family name="serif"><font weight="400" style="normal">NotoSerif-Regular.ttf</font></family>
    <family lang="und-Zsye"><font weight="400" style="normal">NotoColorEmoji.ttf</font></family>
    <family lang="zh-Hans">
        <font weight="400" style="normal" index="2">{cjk}</font>
    </family>
    <family lang="zh-Hant zh-Bopo">
        <font weight="400" style="normal" index="3">NotoSansCJK-Regular.ttc</font>
    </family>
</familyset>
"""

FALLBACK_XML = """<?xml version="1.0" encoding="utf-8"?>
<familyset>
    <family-list name="sans-serif">
        <family>
            <font weight="400" style="normal">{sans}</font>
        </family>
        <family><font weight="400" style="normal">Other.ttf</font></family>
    </family-list>
    <family lang="zh-Hans">
        <font weight="400" style="normal" index="2">{cjk}</font>
    </family>
</familyset>
"""

CUSTOMIZATION_XML = """<?xml version="1.0" encoding="utf-8"?>
<fonts-modification version="1">
    <family customizationType="new-locale-family" lang="zh-Hans" operation="prepend">
        <font weight="400" style="normal">OemCjk.ttf</font>
    </family>
</fonts-modification>
"""

# Android 14+ FontManagerShellCommand format.
DUMP_14 = """Named Family List
  Named Family (sans-serif)
    Family
      style = FontStyle { weight=100, slant=0}, path = /system/fonts/Roboto-Regular.ttf, axes = 'wght' 100
      style = FontStyle { weight=400, slant=0}, path = {sans_path}
    Family
      style = FontStyle { weight=400, slant=0}, path = /system/fonts/Other.ttf
  Named Family (serif)
    Family
      style = FontStyle { weight=400, slant=0}, path = /system/fonts/NotoSerif-Regular.ttf
Dump Fallback Families
  Fallback Family [0]: lang="und-Zsye"
    style = FontStyle { weight=400, slant=0}, path = /data/fonts/files/~~abc==/def==/NotoColorEmoji.ttf
      Font is updated from /system/fonts/NotoColorEmoji.ttf
  Fallback Family [1]: lang="zh-Hans"
    style = FontStyle { weight=400, slant=0}, path = {cjk_path}, index = 2
  Fallback Family [2]: lang="zh-Hant,zh-Bopo"
    style = FontStyle { weight=400, slant=0}, path = /system/fonts/NotoSansCJK-Regular.ttc, index = 3
Dump Family Aliases
  alias = sans-serif-medium, reference = sans-serif, width = 500
"""

# Android 12/13 format (no "Family" sub-blocks).
DUMP_13 = """Named Font Families
  Named Family (sans-serif)
    style = FontStyle { weight=400, slant=0}, path = /system/fonts/LuoShuSlot-sans-400.ttf
Dump Fallback Families
  Fallback Family [0]: lang="zh-Hans"
    style = FontStyle { weight=400, slant=0}, path = /system/fonts/LuoShuSlot-cjk-400.ttf
"""


def dump14(sans: str = "/system/fonts/LuoShuSlot-sans-400.ttf",
           cjk: str = "/system/fonts/NotoSansCJK-Regular.ttc") -> str:
    return DUMP_14.replace("{sans_path}", sans).replace("{cjk_path}", cjk)


def make_font(path: Path, ps_name: str, revision: float) -> bool:
    try:
        from fontTools.fontBuilder import FontBuilder
    except Exception:
        return False
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([".notdef"])
    builder.setupCharacterMap({})
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    builder.setupGlyf({".notdef": TTGlyphPen(None).glyph()})
    builder.setupHorizontalMetrics({".notdef": (500, 0)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": ps_name, "styleName": "Regular", "psName": ps_name})
    builder.setupOS2()
    builder.setupPost()
    builder.setupHead(unitsPerEm=1000, fontRevision=revision)
    builder.save(str(path))
    return True


class ParityParsingTest(unittest.TestCase):
    def test_dump_android14(self):
        parsed = parity.parse_font_dump(dump14())
        self.assertEqual("LuoShuSlot-sans-400.ttf", parsed["sans-serif"])
        self.assertEqual("NotoSansCJK-Regular.ttc#2", parsed["zh-Hans"])
        self.assertEqual(["/system/fonts/NotoColorEmoji.ttf"], parsed["updatedFrom"])
        self.assertTrue(parsed["available"])

    def test_dump_android13(self):
        parsed = parity.parse_font_dump(DUMP_13)
        self.assertEqual("LuoShuSlot-sans-400.ttf", parsed["sans-serif"])
        self.assertEqual("LuoShuSlot-cjk-400.ttf", parsed["zh-Hans"])

    def test_empty_dump_is_unknown_not_ok(self):
        fonts = parity.parse_font_xml(parity.ET.fromstring(FONTS_XML.format(sans="A.ttf", cjk="B.ttc")))
        self.assertEqual("unknown:font-manager-dump-unavailable",
                         parity.compare(parity.parse_font_dump(""), fonts, {"available": False}))

    def test_fonts_xml_and_fallback_xml(self):
        fonts = parity.parse_font_xml(parity.ET.fromstring(
            FONTS_XML.format(sans="LuoShuSlot-sans-400.ttf", cjk="NotoSansCJK-Regular.ttc")))
        self.assertEqual("LuoShuSlot-sans-400.ttf", fonts["sans-serif"])
        self.assertEqual("NotoSansCJK-Regular.ttc#2", fonts["zh-Hans"])
        fallback = parity.parse_font_xml(parity.ET.fromstring(
            FALLBACK_XML.format(sans="LuoShuSlot-sans-400.ttf", cjk="NotoSansCJK-Regular.ttc")))
        self.assertEqual("LuoShuSlot-sans-400.ttf", fallback["sans-serif"])
        self.assertEqual("ok", parity.compare(parity.parse_font_dump(dump14()), fonts, fallback))

    def test_chromium_view_mismatch(self):
        dump = parity.parse_font_dump(dump14())
        fonts = parity.parse_font_xml(parity.ET.fromstring(
            FONTS_XML.format(sans="Roboto-Regular.ttf", cjk="NotoSansCJK-Regular.ttc")))
        fallback = parity.parse_font_xml(parity.ET.fromstring(
            FALLBACK_XML.format(sans="LuoShuSlot-sans-400.ttf", cjk="NotoSansCJK-Regular.ttc")))
        result = parity.compare(dump, fonts, fallback)
        self.assertTrue(result.startswith("mismatch:sans-serif("), result)
        self.assertIn("fontsXml=Roboto-Regular.ttf", result)
        self.assertNotIn("zh-Hans", result)

    def test_customization_prepend_changes_fallback_view(self):
        fallback = parity.parse_font_xml(parity.ET.fromstring(
            FALLBACK_XML.format(sans="LuoShuSlot-sans-400.ttf", cjk="NotoSansCJK-Regular.ttc")))
        custom = parity.apply_customization(fallback, parity.ET.fromstring(CUSTOMIZATION_XML))
        self.assertEqual("OemCjk.ttf", custom["zh-Hans"])
        fonts = parity.parse_font_xml(parity.ET.fromstring(
            FONTS_XML.format(sans="LuoShuSlot-sans-400.ttf", cjk="NotoSansCJK-Regular.ttc")))
        result = parity.compare(parity.parse_font_dump(dump14()), fonts, custom)
        self.assertIn("zh-Hans(", result)
        self.assertIn("fallbackXml=OemCjk.ttf", result)

    def test_missing_fallback_xml_compares_two_views(self):
        fonts = parity.parse_font_xml(parity.ET.fromstring(
            FONTS_XML.format(sans="LuoShuSlot-sans-400.ttf", cjk="NotoSansCJK-Regular.ttc")))
        self.assertEqual("ok", parity.compare(parity.parse_font_dump(dump14()), fonts,
                                              parity.parse_font_xml(None)))


class UpdatableFontTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="luoshu-parity-")
        self.base = Path(self.tmp.name)
        self.module = self.base / "module"
        (self.module / "config").mkdir(parents=True)
        (self.module / ".luoshu-payload/system/fonts").mkdir(parents=True)
        self.data = self.base / "data/fonts/files/~~abc==/def=="
        self.data.mkdir(parents=True)
        (self.module / "config/font-payload-manifest.conf").write_text(
            "system/fonts/NotoColorEmoji.ttf|hash|1\nsystem/fonts/Roboto-Regular.ttf|hash|1\n")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *extra: str) -> dict[str, str]:
        system = self.base / "visible"
        (system / "system/etc").mkdir(parents=True, exist_ok=True)
        (system / "system/etc/fonts.xml").write_text(
            FONTS_XML.format(sans="LuoShuSlot-sans-400.ttf", cjk="NotoSansCJK-Regular.ttc"))
        dump = self.base / "dump.txt"
        dump.write_text(dump14())
        status = self.base / "status.txt"
        status.write_text("Current Version: 3\nLast Modified Date: 2026-10-01T00:00:00\nNumber of updated font files: 1\n")
        out = self.module / "config/device-font-xml-parity.conf"
        result = subprocess.run([
            sys.executable, str(ROOT / "common/device_font_xml_parity.py"),
            "--font-dump", str(dump), "--font-status", str(status),
            "--fonts-xml", str(system / "system/etc/fonts.xml"),
            "--fallback-xml", str(system / "system/etc/font_fallback.xml"),
            "--customization-xml", str(system / "product/etc/fonts_customization.xml"),
            "--data-fonts", str(self.base / "data/fonts/files"),
            "--module", str(self.module), "--visible-root", str(system),
            "--output", str(out), *extra,
        ], capture_output=True, text=True, timeout=60)
        self.assertEqual(0, result.returncode, result.stderr)
        report = dict(line.split("=", 1) for line in out.read_text().splitlines() if "=" in line)
        self.assertEqual(result.stdout, out.read_text())
        return report

    def test_filename_fallback_marks_shadowed_slot(self):
        (self.data / "NotoColorEmoji.ttf").write_bytes(b"not a real font")
        report = self.run_cli()
        self.assertEqual("ok", report["xmlParity"])
        self.assertEqual("absent", report["fallbackXml"])
        self.assertEqual("1", report["updatableFonts"])
        self.assertIn("NotoColorEmoji@", report["updatableFontList"])
        self.assertEqual("NotoColorEmoji", report["shadowedByUpdatableFont"])
        self.assertEqual("3", report["fontStatusCurrentVersion"])
        self.assertEqual("2", report["replacedSlots"])

    def test_postscript_name_and_revision_with_fonttools(self):
        if not make_font(self.data / "Emoji-Update.ttf", "NotoColorEmoji", 2.042):
            self.skipTest("fontTools unavailable")
        report = self.run_cli()
        self.assertEqual("fonttools", report["updatableFontNameSource"])
        self.assertEqual("NotoColorEmoji@2.042", report["updatableFontList"])
        self.assertEqual("NotoColorEmoji", report["shadowedByUpdatableFont"])

    def test_unrelated_updatable_font_is_not_shadowing(self):
        if not make_font(self.data / "Other.ttf", "SomeOtherFont", 1.0):
            self.skipTest("fontTools unavailable")
        (self.module / "config/font-payload-manifest.conf").write_text("system/fonts/Roboto-Regular.ttf|hash|1\n")
        dump = dump14().replace("      Font is updated from /system/fonts/NotoColorEmoji.ttf\n", "")
        parsed = parity.parse_font_dump(dump)
        names = parity.slot_postscript_names(self.module, ["system/fonts/Roboto-Regular.ttf"],
                                             parity._fonttools(), str(self.base))
        entries = parity.scan_updatable_fonts(self.base / "data/fonts/files", parity._fonttools())
        self.assertEqual([], parity.shadowed(entries, names, ["system/fonts/Roboto-Regular.ttf"],
                                             parsed["updatedFrom"]))

    def test_cli_never_modifies_data_fonts(self):
        target = self.data / "NotoColorEmoji.ttf"
        target.write_bytes(b"payload")
        before = sorted(str(p) for p in (self.base / "data").rglob("*"))
        self.run_cli()
        after = sorted(str(p) for p in (self.base / "data").rglob("*"))
        self.assertEqual(before, after)
        self.assertEqual(b"payload", target.read_bytes())


class ShellEntryTest(unittest.TestCase):
    def test_parity_subcommand_writes_conf_and_prints_conclusion(self):
        with tempfile.TemporaryDirectory(prefix="luoshu-parity-sh-") as td:
            base = Path(td)
            module = base / "module"
            (module / "common").mkdir(parents=True)
            (module / "config").mkdir()
            for name in ("device_font_load_verify.sh", "device_font_xml_parity.py"):
                (module / "common" / name).write_bytes((ROOT / "common" / name).read_bytes())
            visible = base / "visible"
            (visible / "system/etc").mkdir(parents=True)
            (visible / "system/etc/fonts.xml").write_text(
                FONTS_XML.format(sans="Roboto-Regular.ttf", cjk="NotoSansCJK-Regular.ttc"))
            bindir = base / "bin"
            bindir.mkdir()
            dump_file = base / "dump.txt"
            dump_file.write_text(dump14())
            (bindir / "cmd").write_text(
                "#!/bin/sh\n"
                f"[ \"$1 $2\" = 'font dump' ] && exec cat '{dump_file}'\n"
                "[ \"$1 $2\" = 'font status' ] && { echo 'Current Version: 1'; exit 0; }\n"
                "case \"$2\" in clear|update|restart) echo FORBIDDEN >&2; exit 99 ;; esac\n"
                "exit 1\n")
            (bindir / "cmd").chmod(0o755)
            env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", MODDIR=str(module),
                       MODULE_DIR=str(module), LUOSHU_VISIBLE_ROOT=str(visible),
                       LUOSHU_DATA_FONTS_DIR=str(base / "data/fonts/files"))
            result = subprocess.run(["sh", str(module / "common/device_font_load_verify.sh"), "parity"],
                                    env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertNotIn("FORBIDDEN", result.stderr)
            self.assertIn("xmlParity=mismatch:sans-serif(", result.stdout)
            self.assertIn("shadowedByUpdatableFont=none", result.stdout)
            conf = (module / "config/device-font-xml-parity.conf").read_text()
            self.assertIn("xmlParity=mismatch:", conf)
            self.assertIn("fontStatus=available", conf)
            leftovers = [p.name for p in (module / "config").iterdir() if p.name.startswith(".xml-parity")]
            self.assertEqual([], leftovers)


if __name__ == "__main__":
    unittest.main()
