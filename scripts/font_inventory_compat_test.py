#!/usr/bin/env python3
"""Functional scanner regressions for OEM aliases, malformed fonts and reuse."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

from fontTools.ttLib import TTCollection, TTFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))
import font_inventory as inventory
import font_inventory_scan as scanner
from stock_metric_contract_test import make_font


class InventoryCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luoshu-inventory-compat-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fonts = self.root / "system/fonts"
        self.etc = self.root / "system/etc"
        self.product_fonts = self.root / "product/fonts"
        self.product_etc = self.root / "product/etc"
        for path in (self.fonts, self.etc, self.product_fonts, self.product_etc):
            path.mkdir(parents=True)
        self.args = scanner.build_parser().parse_args([
            "--scan", "--build-key", "compat-stock", "--output", str(self.root / "inventory.json"),
        ])
        for specs in (scanner.PRIMARY_FONT_SPECS, scanner.AUX_FONT_SPECS,
                      scanner.PRIMARY_ETC_SPECS, scanner.AUX_ETC_SPECS):
            for spec in specs:
                setattr(self.args, spec[2], self.root / "missing" / spec[2])
        self.args.system_fonts, self.args.system_etc = self.fonts, self.etc
        self.args.product_fonts, self.args.product_etc = self.product_fonts, self.product_etc
        env = patch.dict(os.environ, {
            "LUOSHU_DYNAMIC_PARTITION_SCAN_ROOTS": str(self.root / "missing"),
            "LUOSHU_FRESH_STOCK_SCAN": "", "LUOSHU_STOCK_VIEW_VERIFIED": "1",
        })
        env.start()
        self.addCleanup(env.stop)

    def scan(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(scanner.scan(self.args), 0)
        return json.loads(self.args.output.read_text()), json.loads(out.getvalue())

    def seed_ui(self):
        make_font(self.fonts / "UnknownUi.ttf", ascent=980, descent=-240)
        (self.etc / "fonts.xml").write_text(
            '<familyset><family name="sans-serif"><font>UnknownUi.ttf</font></family></familyset>')

    def test_cross_partition_alias_chain_keeps_vendor_face_and_root(self):
        # The basename exists in both partitions. Product XML must resolve its
        # own file, including face 1, even when system XML declares the alias.
        make_font(self.fonts / "VendorCollection.ttf", ascent=700, descent=-100)
        face1 = self.root / "face1.ttf"
        make_font(face1, ascent=1300, descent=-350)
        with TTFont(self.fonts / "VendorCollection.ttf") as first, TTFont(face1) as second:
            collection = TTCollection()
            collection.fonts = [first, second]
            collection.save(self.product_fonts / "VendorCollection.ttf")
        (self.etc / "fonts.xml").write_text(
            '<familyset><alias name="system-ui" to="vendor-default" />'
            '<alias name="vendor-default" to="acme-interface" /></familyset>')
        (self.product_etc / "fonts_customization.xml").write_text(
            '<fonts-modification><family name="acme-interface">'
            '<font weight="450" index="1">VendorCollection.ttf</font>'
            '</family></fonts-modification>')
        data, _ = self.scan()
        key = "/product/fonts/VendorCollection.ttf"
        self.assertEqual(list(data["slots"]), [key])
        self.assertEqual(data["families"]["system-ui"], [key])
        slot = data["slots"][key]
        self.assertEqual((slot["faceIndex"], slot["weight"]), (1, 450))
        self.assertEqual(slot["metrics"]["ascent"], 1300)
        self.assertEqual(slot["sourceXmls"], ["/product/etc/fonts_customization.xml"])

    def test_ui_alias_does_not_promote_language_or_symbol_families(self):
        self.seed_ui()
        for name in ("LanguageFace.ttf", "Pictograms.ttf"):
            path = self.fonts / name
            make_font(path)
            with TTFont(path) as font:
                for table in font["cmap"].tables:
                    if table.isUnicode():
                        table.cmap = {codepoint: "zero" for codepoint in range(32, 129)}
                font.save(path)
        (self.product_etc / "fonts_customization.xml").write_text(
            '<familyset><family name="acme-local" lang="ar"><font>LanguageFace.ttf</font></family>'
            '<family name="acme-symbol"><font>Pictograms.ttf</font></family>'
            '<alias name="system-ui" to="acme-local" />'
            '<alias name="google-sans" to="acme-symbol" /></familyset>')
        data, _ = self.scan()
        self.assertEqual(list(data["slots"]), ["/system/fonts/UnknownUi.ttf"])
        self.assertEqual(set(data["preservedXmlPaths"]), {
            "/system/fonts/LanguageFace.ttf", "/system/fonts/Pictograms.ttf"})
        # A policy refresh must also retire an older generic false positive,
        # instead of resurrecting it through the known-slot preservation pass.
        key = "/system/fonts/LanguageFace.ttf"
        data["slots"][key] = {
            **data["mainSlot"], "path": key, "slotName": "LanguageFace.ttf",
            "source": "verified-scan", "families": [],
        }
        data["slotCount"] = len(data["slots"])
        data["scannerRevision"] = 6
        self.args.output.write_text(json.dumps(data))
        refreshed, _ = self.scan()
        self.assertNotIn(key, refreshed["slots"])

    def test_malformed_lazy_table_cannot_abort_other_valid_slots(self):
        self.seed_ui()
        broken = self.fonts / "CorruptUi.ttf"
        make_font(broken)
        raw = bytearray(broken.read_bytes())
        for offset in range(12, 12 + struct.unpack_from(">H", raw, 4)[0] * 16, 16):
            if raw[offset:offset + 4] == b"hhea":
                struct.pack_into(">I", raw, offset + 12, 2)
        broken.write_bytes(raw)
        with self.assertRaises(inventory.InventoryError):
            inventory._read_metrics(broken)
        (self.etc / "fonts.xml").write_text(
            '<familyset><family name="sans-serif"><font>CorruptUi.ttf</font>'
            '<font>UnknownUi.ttf</font></family></familyset>')
        data, _ = self.scan()
        self.assertEqual(list(data["slots"]), ["/system/fonts/UnknownUi.ttf"])

    def test_many_hardlink_aliases_decode_one_stock_face_and_cache_hit_never_walks(self):
        self.seed_ui()
        names = ["UnknownUi.ttf"]
        for index in range(32):
            name = f"Alias{index}.ttf"
            os.link(self.fonts / names[0], self.fonts / name)
            names.append(name)
        (self.etc / "fonts.xml").write_text(
            '<familyset><family name="sans-serif">'
            + ''.join(f'<font>{name}</font>' for name in names)
            + '</family></familyset>')
        with patch.object(inventory, "_read_metrics_uncached", wraps=inventory._read_metrics_uncached) as reader:
            data, _ = self.scan()
        self.assertEqual(len(data["slots"]), 33)
        self.assertEqual(reader.call_count, 1)
        with patch.object(scanner, "_partition_font_census", side_effect=AssertionError("unexpected walk")), \
             patch.object(inventory, "_read_metrics_uncached", side_effect=AssertionError("unexpected parse")):
            reused, status = self.scan()
        self.assertEqual(reused, data)
        self.assertEqual(status["status"], "reused")
        self.assertEqual(status["fontPathCount"], 33)

    def test_metric_cache_separates_faces_and_never_leaks_into_next_scan(self):
        self.seed_ui()
        font = self.fonts / "UnknownUi.ttf"
        with inventory._scan_metrics_cache():
            first = inventory._read_metrics(font)[1]
            first["hhea"]["ascent"] = 42
            self.assertEqual(inventory._read_metrics(font)[1]["hhea"]["ascent"], 980)
        make_font(font, ascent=1500, descent=-400)
        with inventory._scan_metrics_cache():
            self.assertEqual(inventory._read_metrics(font)[1]["ascent"], 1500)
        other = self.root / "other.ttf"
        make_font(other, ascent=1200, descent=-250)
        collection_path = self.root / "Collection.ttc"
        with TTFont(font) as first, TTFont(other) as second:
            collection = TTCollection()
            collection.fonts = [first, second]
            collection.save(collection_path)
        with inventory._scan_metrics_cache():
            self.assertEqual(inventory._read_metrics(collection_path, 0)[1]["ascent"], 1500)
            self.assertEqual(inventory._read_metrics(collection_path, 1)[1]["ascent"], 1200)

    def test_generic_unknown_italic_and_fixed_pitch_faces_remain_stock(self):
        self.seed_ui()
        for name, trait in (("UnnamedSlant.ttf", "italic"), ("UnnamedFixed.ttf", "mono"),
                            ("UnnamedText.ttf", "normal")):
            path = self.fonts / name
            make_font(path)
            with TTFont(path) as font:
                for table in font["cmap"].tables:
                    if table.isUnicode():
                        table.cmap = {codepoint: "zero" for codepoint in range(32, 129)}
                if trait == "italic":
                    font["head"].macStyle |= 2
                    font["OS/2"].fsSelection |= 1
                    font["OS/2"].fsSelection &= ~64
                if trait == "mono":
                    font["post"].isFixedPitch = 1
                font.save(path)
        data, _ = self.scan()
        self.assertEqual(set(data["slots"]), {"/system/fonts/UnknownUi.ttf", "/system/fonts/UnnamedText.ttf"})

    def test_no_xml_unknown_rom_chooses_real_regular_weight(self):
        for name, weight in (("A-face.ttf", 800), ("Z-face.ttf", 400)):
            path = self.fonts / name
            make_font(path)
            with TTFont(path) as font:
                for table in font["cmap"].tables:
                    if table.isUnicode():
                        table.cmap = {codepoint: "zero" for codepoint in range(32, 129)}
                font["OS/2"].usWeightClass = weight
                font.save(path)
        data, _ = self.scan()
        self.assertEqual(data["mainSlotPath"], "/system/fonts/Z-face.ttf")
        self.assertEqual(data["slots"]["/system/fonts/A-face.ttf"]["weight"], 800)

    def test_unknown_stock_absolute_alias_uses_selected_partition_view(self):
        path = self.product_fonts / "UnnamedText.ttf"
        make_font(path)
        with TTFont(path) as font:
            for table in font["cmap"].tables:
                if table.isUnicode():
                    table.cmap = {codepoint: "zero" for codepoint in range(32, 129)}
            font.save(path)
        (self.fonts / "UnknownAlias.ttf").symlink_to("/product/fonts/UnnamedText.ttf")
        data, _ = self.scan()
        self.assertEqual(set(data["slots"]), {
            "/system/fonts/UnknownAlias.ttf", "/product/fonts/UnnamedText.ttf"})

    def test_unnamed_chinese_fallback_is_still_detected_on_generic_rom(self):
        self.seed_ui()
        path = self.fonts / "LocalGlyphs.ttf"
        make_font(path)
        with TTFont(path) as font:
            for table in font["cmap"].tables:
                if table.isUnicode():
                    table.cmap = {codepoint: "zero" for codepoint in range(0x4e00, 0x5000)}
            font.save(path)
        (self.etc / "font_fallback.xml").write_text(
            '<familyset><family lang="zh-Hans zh-Hant"><font>LocalGlyphs.ttf</font></family></familyset>')
        data, _ = self.scan()
        self.assertIn("/system/fonts/LocalGlyphs.ttf", data["slots"])
        self.assertNotIn("/system/fonts/LocalGlyphs.ttf", data["preservedXmlPaths"])


if __name__ == "__main__":
    unittest.main()
