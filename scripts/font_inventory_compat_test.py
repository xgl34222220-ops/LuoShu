#!/usr/bin/env python3
"""Functional scanner regressions for OEM aliases, malformed fonts and reuse."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

from fontTools.ttLib import TTCollection, TTFont, newTable
from fontTools.ttLib.tables._f_v_a_r import Axis, NamedInstance

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

    def make_text_face(self, path, codepoints, *, ascent=980):
        make_font(path, ascent=ascent, descent=-240)
        with TTFont(path) as font:
            for table in font["cmap"].tables:
                if table.isUnicode():
                    table.cmap = {point: "zero" for point in codepoints}
            font.save(path)

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
        self.assertEqual(set(data["slots"]), {key, "/system/fonts/VendorCollection.ttf"})
        self.assertEqual(data["families"]["system-ui"], [key])
        slot = data["slots"][key]
        self.assertEqual((slot["faceIndex"], slot["weight"]), (1, 450))
        self.assertEqual(slot["metrics"]["ascent"], 1300)
        self.assertEqual(slot["sourceXmls"], ["/product/etc/fonts_customization.xml"])

    def test_script_fonts_are_measured_and_symbol_families_are_protected(self):
        self.seed_ui()
        for name in ("LanguageFace.ttf", "Pictograms.ttf"):
            path = self.fonts / name
            points = set(range(32, 129))
            if name == "LanguageFace.ttf":
                # Real script fallbacks can carry ASCII too; a language label
                # attached to a purely Latin fixture cannot prove that risk.
                points.update(range(0x621, 0x64b))
            self.make_text_face(path, points)
        (self.product_etc / "fonts_customization.xml").write_text(
            '<familyset><family name="acme-local" lang="ar"><font>LanguageFace.ttf</font></family>'
            '<family name="acme-symbol"><font>Pictograms.ttf</font></family>'
            '<alias name="system-ui" to="acme-local" />'
            '<alias name="google-sans" to="acme-symbol" /></familyset>')
        data, _ = self.scan()
        self.assertEqual(set(data["slots"]), {"/system/fonts/UnknownUi.ttf", "/system/fonts/LanguageFace.ttf"})
        self.assertIn("Arab", data["slots"]["/system/fonts/LanguageFace.ttf"]["requiresScripts"])
        self.assertEqual(set(data["preservedXmlPaths"]), {"/system/fonts/Pictograms.ttf"})
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
        self.assertIn(key, refreshed["slots"])

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

    def test_generic_unknown_styles_record_capabilities_for_source_matching(self):
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
        self.assertEqual(set(data["slots"]), {"/system/fonts/UnknownUi.ttf", "/system/fonts/UnnamedText.ttf",
            "/system/fonts/UnnamedSlant.ttf", "/system/fonts/UnnamedFixed.ttf"})
        self.assertTrue(data["slots"]["/system/fonts/UnnamedSlant.ttf"]["metrics"]["fontTraits"]["italic"])
        self.assertTrue(data["slots"]["/system/fonts/UnnamedFixed.ttf"]["metrics"]["fontTraits"]["monospaced"])

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

    def test_language_qualified_latin_ui_and_unknown_latin_languages_are_detected(self):
        self.seed_ui()
        cases = [("en", "sans-serif"), ("en-Latn", "system-ui"),
                 ("de", ""), ("vi-Latn", "acme-local"), ("und", "")]
        families = []
        expected = {"/system/fonts/UnknownUi.ttf"}
        for index, (language, family) in enumerate(cases):
            name = f"LocalLatin{index}.ttf"
            # Greek/Cyrillic coverage in a normal UI face is not evidence that
            # the file is a dedicated script fallback.
            points = set(range(32, 129)) | set(range(0x391, 0x3ca)) | set(range(0x410, 0x450))
            self.make_text_face(self.fonts / name, points)
            families.append(f'<family name="{family}" lang="{language}"><font>{name}</font></family>')
            expected.add(f"/system/fonts/{name}")
        (self.etc / "font_fallback.xml").write_text('<familyset>' + ''.join(families) + '</familyset>')
        data, _ = self.scan()
        self.assertEqual(set(data["slots"]), expected)
        self.assertFalse(data["preservedXmlPaths"])

    def test_named_ui_and_aliases_record_script_faces_with_ascii(self):
        self.seed_ui()
        families = []
        expected = set()
        for index, (language, points) in enumerate([
                ("ar", range(0x621, 0x64b)), ("he", range(0x5d0, 0x5eb)),
                ("th", range(0xe01, 0xe3b))]):
            name = f"LanguageFace{index}.ttf"
            self.make_text_face(self.fonts / name, set(range(32, 129)) | set(points))
            families.append(f'<family name="sans-serif" lang="{language}"><font>{name}</font></family>')
            expected.add(f"/system/fonts/{name}")
        # The same family name also has a real Latin face. Alias promotion must
        # retain per-file eligibility instead of promoting every family member.
        self.make_text_face(self.fonts / "LocalLatin.ttf", range(32, 129))
        families.append('<family name="sans-serif" lang="en"><font>LocalLatin.ttf</font></family>')
        families.append('<alias name="google-sans" to="sans-serif" />')
        (self.etc / "font_fallback.xml").write_text('<familyset>' + ''.join(families) + '</familyset>')
        data, _ = self.scan()
        self.assertEqual(set(data["slots"]), expected | {
            "/system/fonts/UnknownUi.ttf", "/system/fonts/LocalLatin.ttf"})
        self.assertFalse(data["preservedXmlPaths"])

    def test_shared_cjk_collection_keeps_proven_chinese_face_in_either_xml_order(self):
        self.seed_ui()
        collection_path = self.fonts / "LocalCollection.ttc"
        face_paths = [self.root / "first.ttf", self.root / "second.ttf"]
        for index, path in enumerate(face_paths):
            self.make_text_face(path, range(0x4e00, 0x5100), ascent=900 + index * 400)
        with TTFont(face_paths[0]) as first, TTFont(face_paths[1]) as second:
            collection = TTCollection()
            collection.fonts = [first, second]
            collection.save(collection_path)
        families = [
            '<family lang="ja"><font index="0">LocalCollection.ttc</font></family>',
            '<family lang="ko"><font index="0">LocalCollection.ttc</font></family>',
            '<family lang="zh-Hans"><font index="1">LocalCollection.ttc</font></family>',
        ]
        key = "/system/fonts/LocalCollection.ttc"
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                ordered = list(reversed(families)) if reverse else families
                (self.etc / "font_fallback.xml").write_text('<familyset>' + ''.join(ordered) + '</familyset>')
                self.args.force = True
                data, _ = self.scan()
                self.assertEqual(data["slots"][key]["faceIndex"], 1)
                self.assertEqual(data["slots"][key]["metrics"]["ascent"], 1300)
                self.assertNotIn(key, data["preservedXmlPaths"])

    def test_mixed_language_han_and_old_v7_exclusion_are_recovered(self):
        self.seed_ui()
        self.make_text_face(self.fonts / "SharedHan.ttf", range(0x4e00, 0x5100))
        (self.etc / "font_fallback.xml").write_text(
            '<familyset><family lang="zh-Hans ja ko"><font>SharedHan.ttf</font></family></familyset>')
        key = "/system/fonts/SharedHan.ttf"
        data, _ = self.scan()
        self.assertIn(key, data["slots"])
        self.assertNotIn(key, data["preservedXmlPaths"])
        # Test3 persisted the omission as a protected path. A scanner revision
        # upgrade must rebuild eligibility rather than perpetuating that list.
        data["scannerRevision"] = 7
        data["slots"].pop(key)
        data["slotCount"] = len(data["slots"])
        data["preservedXmlPaths"] = [key]
        self.args.output.write_text(json.dumps(data))
        refreshed, status = self.scan()
        self.assertNotEqual(status["status"], "reused")
        self.assertIn(key, refreshed["slots"])
        self.assertNotIn(key, refreshed["preservedXmlPaths"])

    def test_ui_alias_keeps_accepted_collection_face_when_other_language_is_rejected(self):
        self.seed_ui()
        chinese = self.root / "chinese.ttf"
        arabic = self.root / "arabic.ttf"
        self.make_text_face(chinese, range(0x4e00, 0x5100), ascent=1300)
        self.make_text_face(arabic, set(range(32, 129)) | set(range(0x621, 0x64b)), ascent=700)
        with TTFont(chinese) as first, TTFont(arabic) as second:
            collection = TTCollection()
            collection.fonts = [first, second]
            collection.save(self.fonts / "Shared.ttc")
        families = [
            '<family name="acme-local" lang="zh-Hans"><font index="0">Shared.ttc</font></family>',
            '<family name="acme-local" lang="ar"><font index="1">Shared.ttc</font></family>',
        ]
        key = "/system/fonts/Shared.ttc"
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                ordered = list(reversed(families)) if reverse else families
                (self.etc / "font_fallback.xml").write_text(
                    '<familyset>' + ''.join(ordered)
                    + '<alias name="system-ui" to="acme-local" /></familyset>')
                self.args.force = True
                data, _ = self.scan()
                self.assertEqual(data["slots"][key]["faceIndex"], 0)
                self.assertEqual(data["slots"][key]["metrics"]["ascent"], 1300)
                self.assertNotIn("Arab", data["slots"][key]["metrics"]["fontTraits"]["letterScripts"])
                self.assertNotIn(key, data["preservedXmlPaths"])

    def test_language_text_coverage_does_not_override_protected_family_roles(self):
        self.seed_ui()
        families = []
        protected = set()
        for index, role in enumerate(("serif", "monospace", "symbol", "emoji", "icon")):
            name = f"RoleFace{index}.ttf"
            self.make_text_face(self.fonts / name, set(range(32, 129)) | set(range(0x4e00, 0x5100)))
            families.append(f'<family name="vendor-{role}" lang="zh-Hans en"><font>{name}</font></family>')
            if role not in {"serif", "monospace"}:
                protected.add(f"/system/fonts/{name}")
        (self.etc / "font_fallback.xml").write_text('<familyset>' + ''.join(families) + '</familyset>')
        data, _ = self.scan()
        self.assertEqual(set(data["slots"]), {"/system/fonts/UnknownUi.ttf",
            "/system/fonts/RoleFace0.ttf", "/system/fonts/RoleFace1.ttf"})
        self.assertEqual(set(data["preservedXmlPaths"]), protected)

    def test_language_scan_measures_every_script_and_reuses_shared_face_metrics(self):
        self.seed_ui()
        self.make_text_face(self.fonts / "SharedLatin.ttf", range(32, 129))
        self.make_text_face(self.fonts / "NotoSansArabic.ttf", range(0x621, 0x64b))
        (self.etc / "font_fallback.xml").write_text(
            '<familyset><family lang="en"><font>SharedLatin.ttf</font></family>'
            '<family lang="de"><font>SharedLatin.ttf</font></family>'
            '<family lang="ar"><font>NotoSansArabic.ttf</font></family></familyset>')
        with patch.object(inventory, "_read_metrics_uncached", wraps=inventory._read_metrics_uncached) as reader:
            data, _ = self.scan()
        parsed = [Path(call.args[0]).name for call in reader.call_args_list]
        self.assertEqual(parsed.count("SharedLatin.ttf"), 1)
        self.assertEqual(parsed.count("UnknownUi.ttf"), 1)
        self.assertEqual(parsed.count("NotoSansArabic.ttf"), 1)
        self.assertEqual(set(data["slots"]), {
            "/system/fonts/UnknownUi.ttf", "/system/fonts/SharedLatin.ttf", "/system/fonts/NotoSansArabic.ttf"})

    def test_unknown_clock_and_misleading_filenames_use_measured_capabilities(self):
        self.seed_ui()
        self.make_text_face(self.fonts / "FutureBrandClock.ttf", range(48, 58))
        self.make_text_face(self.fonts / "IconicSerifMusicArabic.ttf", range(32, 127))
        self.make_text_face(self.fonts / "TotallyNormal.ttf", range(0xe000, 0xe100))
        data, _ = self.scan()
        self.assertEqual(data["slots"]["/system/fonts/FutureBrandClock.ttf"]["replacementRole"], "digits")
        self.assertIn("/system/fonts/IconicSerifMusicArabic.ttf", data["slots"])
        self.assertEqual(data["preservedFonts"]["/system/fonts/TotallyNormal.ttf"]["reason"], "private-use-symbol-font")

    def test_unlisted_partial_and_fullwidth_digits_are_scanned_and_actually_replaced(self):
        import inventory_font_stage as engine
        self.seed_ui()
        for name, points in (("PartialDigits.ttf", {0x30, 0x31}),
                             ("FullwidthDigits.ttf", {0xFF10, 0xFF11})):
            self.make_text_face(self.fonts / name, points)
        self.make_text_face(self.fonts / "SymbolDigits.ttf", {0x30})
        with TTFont(self.fonts / "SymbolDigits.ttf") as font:
            font["OS/2"].sFamilyClass = 12 << 8
            font.save(self.fonts / "SymbolDigits.ttf")
        data, _ = self.scan()
        for name in ("PartialDigits.ttf", "FullwidthDigits.ttf"):
            slot = data["slots"]["/system/fonts/" + name]
            self.assertEqual(slot["replacementRole"], "digits")
            self.assertEqual(slot["metrics"]["fontTraits"]["digitCount"], 2)
        self.assertEqual(data["preservedFonts"]["/system/fonts/SymbolDigits.ttf"]["reason"],
                         "symbol-font-metadata")
        source = self.root / "source.ttf"
        self.make_text_face(source, {0x30, 0xFF10})
        with TTFont(source) as font:
            glyph = font["glyf"]["zero"]
            glyph.coordinates = type(glyph.coordinates)((x - 200 if x == 640 else x, y)
                                                         for x, y in glyph.coordinates)
            font.save(source)
        module = self.root / "module"
        (module / "config").mkdir(parents=True)
        (module / "config/device_font_inventory.json").write_text(json.dumps(data))
        stage = module / ".luoshu-payload-stage"
        with patch.dict(os.environ, {"LUOSHU_BUILD_KEY": "compat-stock"}):
            summary = engine.run(module, stage, "direct", source)
        self.assertEqual(summary["mapped"], 3)
        report = json.loads((stage / ".luoshu-metrics-report.json").read_text())
        for name, replaced, retained in (("PartialDigits.ttf", 0x30, 0x31),
                                         ("FullwidthDigits.ttf", 0xFF10, 0xFF11)):
            row = next(row for row in report["slots"] if row["slot"].endswith(name))
            self.assertEqual(row["replacedRoleCounts"]["digit"], 1)
            self.assertEqual(row["retainedTargetRoleCounts"]["digit"], 1)
            with TTFont(stage / "system/fonts" / name) as output:
                glyphs, cmap = output["glyf"], output.getBestCmap()
                self.assertEqual(max(x for x, _ in glyphs[cmap[replaced]].getCoordinates(glyphs)[0]), 440)
                self.assertEqual(max(x for x, _ in glyphs[cmap[retained]].getCoordinates(glyphs)[0]), 640)
        self.assertFalse((stage / "system/fonts/SymbolDigits.ttf").exists())

    def test_previous_digit_scan_revision_cannot_reuse_incomplete_inventory(self):
        self.seed_ui()
        data, _ = self.scan()
        self.make_text_face(self.fonts / "NewDigits.ttf", {0x31})
        data["scannerRevision"], data["metricsRevision"] = 9, 4
        self.args.output.write_text(json.dumps(data))
        self.assertFalse(scanner._can_reuse(data, "compat-stock"))
        refreshed, _ = self.scan()
        self.assertIn("/system/fonts/NewDigits.ttf", refreshed["slots"])
        self.assertEqual((refreshed["scannerRevision"], refreshed["metricsRevision"]), (11, 5))

    def test_legacy_xml_and_modern_axis_references_survive(self):
        self.make_text_face(self.fonts / "LegacyFace.ttf", range(32, 127))
        self.make_text_face(self.fonts / "VariableFace.ttf", range(32, 127))
        (self.etc / "system_fonts.xml").write_text(
            '<familyset><family><nameset><name>sans-serif</name><name>system-ui</name></nameset>'
            '<fileset><file>LegacyFace.ttf</file></fileset></family></familyset>')
        (self.etc / "fonts.xml").write_text(
            '<familyset><family name="future-ui" lang="en,fr">'
            '<font weight="300" supportedAxes="wght,ital">VariableFace.ttf<axis tag="wght" stylevalue="300" /></font>'
            '<font weight="700" style="italic" supportedAxes="wght,ital">VariableFace.ttf<axis tag="wght" stylevalue="700" /></font>'
            '</family></familyset>')
        data, _ = self.scan()
        self.assertEqual(data["families"]["system-ui"], ["/system/fonts/LegacyFace.ttf"])
        entry = data["slots"]["/system/fonts/VariableFace.ttf"]
        self.assertEqual(entry["supportedAxes"], ["wght", "ital"])
        self.assertEqual(entry["familyLanguages"], ["en", "fr"])
        self.assertEqual([ref["axes"]["wght"] for ref in entry["faces"][0]["xmlReferences"]], [300, 700])
        self.assertEqual([ref["weight"] for ref in entry["faces"][0]["xmlReferences"]], [300, 700])

    def test_dynamic_aliases_are_generic_and_never_read_mutable_targets(self):
        self.seed_ui()
        (self.fonts / "FutureOverlay.ttf").symlink_to("/data/vendor/future-theme/font.ttf")
        (self.fonts / "Chained.ttf").symlink_to("FutureOverlay.ttf")
        (self.product_fonts / "Another.ttf").symlink_to("/system/fonts/Chained.ttf")
        with patch.object(inventory, "_read_metrics", wraps=inventory._read_metrics) as reader:
            data, _ = self.scan()
        expected = {"/system/fonts/FutureOverlay.ttf", "/system/fonts/Chained.ttf", "/product/fonts/Another.ttf"}
        self.assertEqual(set(data["preservedDynamicAliases"]), expected)
        self.assertEqual({entry["alias"] for entry in data["dynamicFontRoutes"]}, expected)
        self.assertTrue(all(entry["target"] == "/data/vendor/future-theme/font.ttf" for entry in data["dynamicFontRoutes"]))
        self.assertTrue(all(not str(call.args[0]).startswith("/data/") for call in reader.call_args_list))

    def test_arbitrary_nested_assets_in_unknown_partition_are_discovered(self):
        self.seed_ui()
        partition = self.root / "partitions/future_os/assets/glyphs"
        partition.mkdir(parents=True)
        self.make_text_face(partition / "OpaqueName.otf", range(32, 127))
        with patch.dict(os.environ, {"LUOSHU_DYNAMIC_PARTITION_SCAN_ROOTS": str(self.root / "partitions")}):
            data, _ = self.scan()
        self.assertIn("/future_os/assets/glyphs/OpaqueName.otf", data["slots"])
        self.assertIn("future_os", data["discoveredPartitions"])
        self.assertTrue(any(root["logical"] == "/future_os/assets/glyphs" for root in data["discoveredFontRoots"]))

    def test_fallback_targets_require_real_xml_route(self):
        self.make_text_face(self.fonts / "Latin.ttf", range(32, 127))
        self.make_text_face(self.fonts / "Han.ttf", range(0x4e00, 0x5000))
        self.make_text_face(self.fonts / "Unreferenced.ttf", range(32, 127))
        (self.etc / "fonts.xml").write_text('<familyset>'
            '<family name="future-ui"><font>Latin.ttf</font></family>'
            '<family lang="zh-Hans"><font fallbackFor="future-ui">Han.ttf</font></family>'
            '</familyset>')
        data, _ = self.scan()
        latin = data["slots"]["/system/fonts/Latin.ttf"]
        self.assertTrue(latin["fallbackReachable"])
        self.assertEqual(latin["fallbackTargets"], ["/system/fonts/Han.ttf"])
        self.assertFalse(data["slots"]["/system/fonts/Unreferenced.ttf"]["fallbackReachable"])

    def test_rom_properties_and_renaming_cannot_change_detected_capabilities(self):
        self.seed_ui()
        self.make_text_face(self.fonts / "MiSansVF.ttf", range(32, 127))
        self.make_text_face(self.fonts / "SysSans-Hans-Regular.ttf", range(32, 127))
        snapshots = []
        for property_values in ({"ro.mi.os.version.name": "3"}, {"ro.build.version.oplusrom": "16"}, {}):
            self.args.force = True
            with patch.object(inventory, "_getprop", side_effect=lambda key: property_values.get(key, "")):
                data, _ = self.scan()
            self.assertEqual(data["romKind"], "generic")
            snapshots.append((set(data["slots"]), data["mainSlotPath"]))
        self.assertEqual(snapshots[0], snapshots[1])
        self.assertEqual(snapshots[1], snapshots[2])

    def test_symbol_metadata_and_collection_all_faces_are_retained(self):
        self.seed_ui()
        self.make_text_face(self.fonts / "Ordinary.ttf", range(32, 127))
        with TTFont(self.fonts / "Ordinary.ttf") as font:
            font["OS/2"].sFamilyClass = 12 << 8
            font.save(self.fonts / "Ordinary.ttf")
        first = self.root / "first.ttf"
        self.make_text_face(first, range(32, 127))
        with TTFont(first) as text_face, TTFont(self.fonts / "Ordinary.ttf") as icon_face:
            collection = TTCollection()
            collection.fonts = [text_face, icon_face]
            collection.save(self.fonts / "SharedFaces.ttc")
        data, _ = self.scan()
        self.assertEqual(data["preservedFonts"]["/system/fonts/Ordinary.ttf"]["reason"], "symbol-font-metadata")
        faces = data["slots"]["/system/fonts/SharedFaces.ttc"]["faces"]
        self.assertEqual([face["faceIndex"] for face in faces], [0, 1])
        self.assertEqual(faces[1]["preservedReason"], "symbol-font-metadata")
        self.assertNotIn("preservedReason", faces[0])

    def test_xml_can_reference_an_extensionless_sfnt_and_path_validation_rejects_escape(self):
        self.seed_ui()
        self.make_text_face(self.fonts / "opaque", range(32, 127))
        (self.etc / "font_fallback.xml").write_text(
            '<familyset><family name="future-ui"><font>opaque</font></family></familyset>')
        data, _ = self.scan()
        key = "/system/fonts/opaque"
        self.assertIn(key, data["slots"])
        escaped = "/system/fonts/../../data/external.ttf"
        data["slots"][escaped] = {**data["slots"][key], "path": escaped}
        data["slotCount"] = len(data["slots"])
        with self.assertRaises(inventory.InventoryError):
            inventory.validate_inventory(data)

    def test_xml_absolute_binary_reference_discovers_a_new_trusted_root(self):
        self.seed_ui()
        assets = self.root / "product/assets/typefaces"
        assets.mkdir(parents=True)
        self.make_text_face(assets / "blob.bin", range(32, 127))
        (self.etc / "fonts.xml").write_text('<familyset><family name="sans-serif">'
            '<font>/product/assets/typefaces/blob.bin</font></family></familyset>')
        data, _ = self.scan()
        key = "/product/assets/typefaces/blob.bin"
        self.assertIn(key, data["slots"])
        self.assertEqual(data["slots"][key]["format"], "TTF")
        self.assertTrue(data["slots"][key]["faces"])
        self.assertTrue(any(root["logical"] == "/product/assets/typefaces" for root in data["discoveredFontRoots"]))
        self.assertIn("product|assets/typefaces|", (self.root / "device_font_roots.conf").read_text())
        candidates = json.loads((self.root / "device_font_candidates.json").read_text())
        self.assertTrue(any(entry["path"] == key and entry["candidate"] for entry in candidates["paths"]))
        self.assertEqual(data["scanSummary"]["stockFontFileCount"], 2)
        reused, status = self.scan()
        self.assertEqual(status["status"], "reused")
        self.assertEqual(data, reused)

    def test_xml_binary_reference_does_not_allow_data_or_unverified_links(self):
        self.seed_ui()
        assets = self.root / "product/assets/typefaces"
        assets.mkdir(parents=True)
        (assets / "blob.bin").symlink_to("/data/user/theme/font.ttf")
        (self.etc / "font_fallback.xml").write_text('<familyset><family name="other-ui">'
            '<font>/product/assets/typefaces/blob.bin</font><font>/data/user/theme/font.ttf</font>'
            '</family></familyset>')
        with patch.object(inventory, "_read_metrics", wraps=inventory._read_metrics) as reader:
            data, _ = self.scan()
        self.assertEqual(set(data["slots"]), {"/system/fonts/UnknownUi.ttf"})
        self.assertTrue(all(not str(call.args[0]).startswith("/data/") for call in reader.call_args_list))

    def test_unreferenced_sfnt_bytes_are_discovered_inside_any_trusted_directory(self):
        self.seed_ui()
        expected = {"/system/fonts/UnknownUi.ttf"}
        for relative in ("product/framework/cache/opaque.bin", "product/app/Clock/assets/Face",
                         "product/media/nested/opaque.fontdata", "system/fonts/no_suffix"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            self.make_text_face(path, {0x41, 0x31, 0x4e00})
            expected.add("/" + relative)
        # A SFNT-looking suffix cannot promote malformed content; an unrelated
        # executable or a FIFO cannot be opened by the magic-byte census.
        (self.product_fonts / "wrong.ttf").write_bytes(b"not a font" * 2)
        (self.product_fonts / "binary").write_bytes(b"\x7fELF" + b"0" * 64)
        os.mkfifo(self.product_fonts / "pipe")
        data, _ = self.scan()
        self.assertEqual(set(data["slots"]), expected)
        self.assertEqual(data["preservedFonts"]["/product/fonts/wrong.ttf"]["reason"], "unreadable-stock-font")
        candidates = json.loads((self.root / "device_font_candidates.json").read_text())
        self.assertEqual({item["path"] for item in candidates["paths"]}, expected | {"/product/fonts/wrong.ttf"})
        for logical in expected - {"/system/fonts/UnknownUi.ttf"}:
            self.assertEqual(set(data["slots"][logical]["replacementRoles"]), {"cjk", "latin", "digit"})

    def test_digit_replacement_is_not_limited_by_other_retained_character_count(self):
        self.seed_ui()
        points = {0x30} | set(range(0x2500, 0x2600))
        self.make_text_face(self.fonts / "SparseDigits.ttf", points)
        self.make_text_face(self.fonts / "LinesOnly.ttf", points - {0x30})
        data, _ = self.scan()
        slot = data["slots"]["/system/fonts/SparseDigits.ttf"]
        self.assertEqual(slot["replacementRoles"], ["digit"])
        self.assertGreater(slot["metrics"]["coverage"]["unicodeCount"], 128)
        self.assertEqual(data["preservedFonts"]["/system/fonts/LinesOnly.ttf"]["reason"], "non-text-cmap")

    def test_archive_keeps_complete_face_coverage_axes_and_weight_instances(self):
        self.seed_ui()
        source = self.fonts / "Variable.ttf"
        points = {0x30, 0x31, 0x33, 0x41, 0x4e00, 0x4e01}
        self.make_text_face(source, points)
        with TTFont(source) as font:
            font["fvar"] = newTable("fvar")
            axis = Axis()
            axis.axisTag, axis.minValue, axis.defaultValue, axis.maxValue = "wght", 100, 400, 900
            axis.flags, axis.axisNameID = 0, font["name"].addName("Weight")
            instance = NamedInstance()
            instance.subfamilyNameID = font["name"].addName("Bold")
            instance.coordinates, instance.flags = {"wght": 700}, 0
            font["fvar"].axes, font["fvar"].instances = [axis], [instance]
            font.save(source)
        data, _ = self.scan()
        slot = data["slots"]["/system/fonts/Variable.ttf"]
        face = slot["faces"][0]
        archived = face["stockSource"]
        restored = {cp for start, end in archived["codepointRanges"] for cp in range(start, end + 1)}
        self.assertEqual(restored, points)
        self.assertEqual(archived["codepointRanges"], [[48, 49], [51, 51], [65, 65], [19968, 19969]])
        digest = hashlib.sha256(b"".join(struct.pack(">I", cp) for cp in sorted(points))).hexdigest()
        self.assertEqual(archived["codepointSha256"], digest)
        self.assertEqual(archived["sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual(face["metrics"]["stockCodepointSha256"], digest)
        self.assertEqual(face["metrics"]["variationAxes"]["wght"], {"min": 100, "default": 400, "max": 900})
        self.assertEqual(face["metrics"]["variationInstances"][0]["coordinates"], {"wght": 700})
        self.assertTrue(slot["variable"])
        self.assertEqual(slot["faceCount"], 1)

    def test_mutable_theme_files_are_observations_not_stock_replacement_contracts(self):
        self.seed_ui()
        theme = self.root / "mutable/theme/fonts"
        theme.mkdir(parents=True)
        self.make_text_face(theme / "opaque", {0x30, 0x41})
        (theme / "broken.ttf").write_bytes(b"invalid")
        (theme / "alias.ttf").symlink_to("/data/vendor/new-theme/font.ttf")
        with patch.object(scanner, "THEME_FONT_ROOTS", (theme.parent, theme)):
            data, _ = self.scan()
        entries = {entry["path"]: entry for entry in data["dynamicFontFiles"]}
        self.assertEqual(len(entries), 3)
        self.assertEqual(set(data["slots"]), {"/system/fonts/UnknownUi.ttf"})
        opaque = entries[str(theme / "opaque")]
        self.assertEqual(opaque["reason"], "mutable-theme-font")
        self.assertFalse(opaque["candidate"])
        self.assertEqual(opaque["faces"][0]["replacementRoles"], ["latin", "digit"])
        self.assertEqual(entries[str(theme / "broken.ttf")]["reason"], "unreadable-dynamic-font")
        self.assertEqual(entries[str(theme / "alias.ttf")]["reason"], "dynamic-font-alias")
        self.assertEqual(data["scanSummary"]["dynamicFontFileCount"], 3)

    def test_protected_xml_collection_face_does_not_hide_other_text_faces(self):
        self.seed_ui()
        text, icons = self.root / "text.ttf", self.root / "icons.ttf"
        self.make_text_face(text, {0x41, 0x31})
        self.make_text_face(icons, {0x41, 0x4e00})
        with TTFont(text) as first, TTFont(icons) as second:
            collection = TTCollection()
            collection.fonts = [first, second]
            collection.save(self.fonts / "Shared.ttc")
        (self.etc / "font_fallback.xml").write_text(
            '<familyset><family name="vendor-text"><font index="0">Shared.ttc</font></family>'
            '<family name="vendor-icons"><font index="1">Shared.ttc</font></family></familyset>')
        data, _ = self.scan()
        slot = data["slots"]["/system/fonts/Shared.ttc"]
        self.assertEqual(slot["faceCount"], 2)
        self.assertEqual(slot["replacementRoles"], ["digit", "latin"])
        self.assertNotIn("preservedReason", slot["faces"][0])
        self.assertEqual(slot["faces"][1]["preservedReason"], "xml-symbol-family")
        self.assertEqual(slot["faces"][1]["replacementRoles"], ["cjk", "latin"])

    def test_runtime_apex_fonts_are_discovered_but_not_promoted_to_static_slots(self):
        self.seed_ui()
        apex = self.root / "apex"
        fonts = apex / "com.example.fonts@42/assets"
        fonts.mkdir(parents=True)
        self.make_text_face(fonts / "opaque", {0x31, 0x41, 0x4e00})
        (fonts / "broken.ttf").write_bytes(b"not font")
        (apex / "com.example.fonts").symlink_to("com.example.fonts@42")
        with patch.object(scanner, "RUNTIME_FONT_ROOTS", (apex,)):
            data, _ = self.scan()
        entries = {entry["path"]: entry for entry in data["runtimeFontFiles"]}
        self.assertEqual(set(data["slots"]), {"/system/fonts/UnknownUi.ttf"})
        self.assertEqual(len(entries), 4)
        canonical = entries[str(apex / "com.example.fonts/assets/opaque")]
        self.assertEqual(canonical["scope"], "runtime-container")
        self.assertEqual(canonical["reason"], "runtime-font-container")
        self.assertEqual(canonical["faces"][0]["replacementRoles"], ["cjk", "latin", "digit"])
        self.assertFalse(canonical["candidate"])
        self.assertEqual(entries[str(fonts / "broken.ttf")]["reason"], "unreadable-runtime-font")

    def test_valid_spaced_directory_is_reported_with_mount_transport_limitation(self):
        self.seed_ui()
        path = self.root / "product/app/My Clock/assets/opaque"
        path.parent.mkdir(parents=True)
        self.make_text_face(path, {0x30, 0x31})
        data, _ = self.scan()
        logical = "/product/app/My Clock/assets/opaque"
        self.assertNotIn(logical, data["slots"])
        entry = data["preservedFonts"][logical]
        self.assertEqual(entry["reason"], "unsupported-mount-root-path")
        self.assertEqual(entry["faces"][0]["replacementRoles"], ["digit"])
        candidates = json.loads((self.root / "device_font_candidates.json").read_text())
        candidate = next(item for item in candidates["paths"] if item["path"] == logical)
        self.assertEqual(candidate["reason"], "unsupported-mount-root-path")
        self.assertFalse(candidate["candidate"])


if __name__ == "__main__":
    unittest.main()
