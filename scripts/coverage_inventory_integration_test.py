#!/usr/bin/env python3
"""Real scanner -> shell bridge -> inventory engine coverage integration.

All fonts are generated locally using the stock metric fixture. No ROM fonts,
commercial fonts, fake font bytes or mocked normalizer are used.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import fontTools
from fontTools.ttLib import TTCollection, TTFont

ROOT = Path(os.environ.get("LUOSHU_TEST_SOURCE_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / "common"))
import device_font_slot_trace as trace
import font_inventory_scan as scanner
from stock_metric_contract_test import make_font

LATIN = set(range(32, 127))
ARABIC = set(range(0x621, 0x64b))
REGULAR = "/system/fonts/Unknown-Regular.ttf"
BOLD = "/system/fonts/Unknown-Bold.ttf"
HEAVY = "/system/fonts/Unknown-Heavy.ttf"
SCRIPT = "/system/fonts/LocalScript.ttf"
COLLECTION = "/system/fonts/MultiFace.ttc"
PARTIAL = "/system/fonts/PartialFace.ttc"
DIGITS = "/system/fonts/Digits.ttf"
NESTED = "/product/odd/layout/fonts/Text.ttf"
UNKNOWN = "/nebula/fonts/Unlisted-Regular.ttf"


def text_font(path: Path, *, weight=400, points=None, family="Selected Family", advance=660,
              ascent=950, descent=-250):
    path.parent.mkdir(parents=True, exist_ok=True)
    make_font(path, ascent=ascent, descent=descent)
    with TTFont(path) as font:
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap = {cp: "zero" for cp in (LATIN if points is None else points)}
        font["OS/2"].usWeightClass = weight
        font["hmtx"].metrics["zero"] = (advance, 40)
        style = "Bold" if weight == 700 else "Regular"
        font["name"].setName(family, 1, 3, 1, 0x409)
        font["name"].setName(family, 16, 3, 1, 0x409)
        font["name"].setName(style, 2, 3, 1, 0x409)
        font["name"].setName(style, 17, 3, 1, 0x409)
        font.save(path)


class CoverageFixture:
    """A fabricated system with unknown names, partition and nested font roots."""

    def __init__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luoshu-coverage-inventory-")
        self.root = Path(self.temp.name)
        self.module = self.root / "module"
        self.stock = self.root / "stock"
        self.stage = self.module / ".luoshu-payload-stage.integration"
        self.live = self.module / ".luoshu-payload"
        self.config = self.module / "config"
        self.inventory_path = self.config / "device_font_inventory.json"
        self.library = self.module / "fonts/selected"
        self.source = self.library / "selected.ttf"
        for directory in (self.stage, self.config, self.live, self.module / "logs", self.library):
            directory.mkdir(parents=True)
        (self.live / "keep-live.txt").write_text("live payload must remain untouched\n")
        common = self.module / "common"
        common.mkdir()
        for file in (ROOT / "common").glob("*.py"):
            shutil.copyfile(file, common / file.name)
        for name in ("inventory_font_stage.sh", "coverage_payload_remediate.sh"):
            shutil.copyfile(ROOT / "common" / name, common / name)
        launcher = common / "python/bin/luoshu-python"
        launcher.parent.mkdir(parents=True)
        fonttools_site = str(Path(fontTools.__file__).resolve().parent.parent)
        launcher.write_text("#!/bin/sh\nunset PYTHONHOME\nexport PYTHONPATH=" +
            shlex.quote(str(common) + os.pathsep + fonttools_site) + "\nexec " +
            shlex.quote(sys.executable) + ' "$@"\n')
        launcher.chmod(0o755)
        self.env = {**os.environ, "LUOSHU_REAL_MODDIR": str(self.module),
                    "LUOSHU_PUBLIC_DIR": str(self.root / "public"),
                    "LUOSHU_DYNAMIC_PARTITION_SCAN_ROOTS": str(self.stock),
                    "LUOSHU_STOCK_VIEW_VERIFIED": "1", "LUOSHU_FRESH_STOCK_SCAN": "",
                    "LUOSHU_BUILD_KEY": "unknown"}
        self.env.pop("LUOSHU_COVERAGE_PLAN", None)
        for logical, weight, points in ((REGULAR, 400, LATIN), (BOLD, 700, LATIN),
                (HEAVY, 900, LATIN), (SCRIPT, 400, LATIN | ARABIC),
                (DIGITS, 400, set(range(48, 58))), (NESTED, 400, LATIN), (UNKNOWN, 400, LATIN)):
            text_font(self.stock / logical.lstrip("/"), weight=weight, points=points,
                      family="Stock text", advance=710, ascent=980, descent=-240)
        for logical, weights in ((COLLECTION, (400, 700)), (PARTIAL, (400, 900))):
            faces = []
            for index, weight in enumerate(weights):
                file = self.root / (Path(logical).stem + str(index) + ".ttf")
                text_font(file, weight=weight, family="Stock collection", ascent=1000 + index * 50)
                faces.append(TTFont(file))
            collection = TTCollection()
            collection.fonts = faces
            collection.save(self.stock / logical.lstrip("/"))
            collection.close()
        text_font(self.source)
        text_font(self.library / "real-bold.ttf", weight=700, advance=920)
        # A filename alone never makes an unrelated font an eligible weight.
        text_font(self.library / "black.ttf", weight=900, family="Unrelated Family", advance=1000)
        self.scan()

    def close(self):
        self.temp.cleanup()

    def scan(self):
        cmd = [sys.executable, str(ROOT / "common/font_inventory_scan.py"), "--scan", "--force",
               "--build-key", "unknown", "--output", str(self.inventory_path)]
        for specs in (scanner.PRIMARY_FONT_SPECS, scanner.AUX_FONT_SPECS,
                      scanner.PRIMARY_ETC_SPECS, scanner.AUX_ETC_SPECS):
            for spec in specs:
                logical, argument = spec[1], spec[2]
                cmd.extend(["--" + argument.replace("_", "-"), str(self.stock / str(logical).lstrip("/"))])
        result = subprocess.run(cmd, env=self.env, text=True, capture_output=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        self.inventory = json.loads(self.inventory_path.read_text())
        return self.inventory

    def save_inventory(self):
        self.inventory_path.write_text(json.dumps(self.inventory))

    def seed_mix(self, include_bold=True):
        store = self.stage / "system/fonts/.luoshu-font-store"
        store.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.source, store / "regular.font")
        if include_bold:
            shutil.copyfile(self.library / "real-bold.ttf", store / "bold.font")

    def invoke(self, mode="direct", plan=None, source=True):
        env = dict(self.env)
        if plan is not None:
            file = self.config / "coverage-plan.txt"
            file.write_text("".join(item + "\n" for item in plan))
            env["LUOSHU_COVERAGE_PLAN"] = str(file)
        cmd = ["sh", str(self.module / "common/coverage_payload_remediate.sh"),
               str(self.stage), mode, "Fixture"]
        if mode == "direct" and source:
            cmd.append(str(self.source))
        return subprocess.run(cmd, env=env, text=True, capture_output=True, timeout=30)

    def report(self):
        return json.loads((self.stage / ".luoshu-metrics-report.json").read_text())

    def path(self, logical):
        return self.stage / logical.lstrip("/")

    def snapshot_live(self):
        return {str(path.relative_to(self.live)): path.read_bytes()
                for path in self.live.rglob("*") if path.is_file()}


class CoverageInventoryIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.f = CoverageFixture()
        self.addCleanup(self.f.close)
        self.before_live = self.f.snapshot_live()

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        value = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertNotEqual(value.get("status"), "error", value)
        self.assertEqual(self.f.snapshot_live(), self.before_live)
        return value.get("data", value)

    def assert_mapping(self):
        f = self.f
        for logical in (REGULAR, BOLD, COLLECTION, PARTIAL, DIGITS, NESTED, UNKNOWN, SCRIPT):
            self.assertTrue(f.path(logical).is_file(), logical)
        self.assertFalse(f.path(HEAVY).exists(), HEAVY)
        report = f.report()
        protected = report.get("preservedFonts", report.get("preserved", {}))
        self.assertEqual(protected[HEAVY], "source-weight-missing")
        self.assertNotIn(SCRIPT, protected)
        self.assertNotIn(PARTIAL, protected)
        partial_faces = [row for row in report["slots"] if row["slot"] == PARTIAL]
        self.assertEqual([row["state"] for row in partial_faces], ["replaced", "retained-stock"])
        self.assertEqual(partial_faces[1]["reason"], "source-weight-missing")
        with TTFont(f.path(SCRIPT)) as font:
            self.assertTrue(ARABIC.issubset(font.getBestCmap()))
        with TTFont(f.path(BOLD)) as font:
            self.assertEqual(font["OS/2"].usWeightClass, 700)
            self.assertEqual(font["hmtx"].metrics["zero"][0], 920)
            self.assertEqual(font["hhea"].ascent, 980)
        with TTCollection(f.path(COLLECTION)) as collection:
            self.assertEqual([font["OS/2"].usWeightClass for font in collection.fonts], [400, 700])
            self.assertEqual([font["hhea"].ascent for font in collection.fonts], [1000, 1050])
        with TTCollection(f.path(PARTIAL)) as partial, TTCollection(f.stock / PARTIAL.lstrip("/")) as stock:
            self.assertEqual([font["OS/2"].usWeightClass for font in partial.fonts], [400, 900])
            for tag in ("glyf", "cmap", "name", "hmtx", "OS/2"):
                self.assertEqual(partial.fonts[1].reader[tag], stock.fonts[1].reader[tag], tag)

    def test_direct_measures_unknown_system_nested_roots_and_real_collection_faces(self):
        self.assertEqual(set(self.f.inventory["slots"]), {
            REGULAR, BOLD, HEAVY, SCRIPT, COLLECTION, PARTIAL, DIGITS, NESTED, UNKNOWN})
        self.assertEqual(self.f.inventory["romKind"], "generic")
        self.assert_success(self.f.invoke())
        self.assert_mapping()

    def test_mix_uses_real_weight_anchors_and_same_capability_decisions(self):
        self.f.seed_mix()
        self.assert_success(self.f.invoke("mix"))
        self.assert_mapping()

    def test_mix_composite_does_not_borrow_unselected_bold(self):
        self.f.seed_mix()
        store = self.f.stage / "system/fonts/.luoshu-font-store"
        shutil.copyfile(self.f.source, store / "mix-composite.font")
        self.assert_success(self.f.invoke("mix"))
        self.assertTrue(self.f.path(REGULAR).is_file())
        self.assertFalse(self.f.path(BOLD).exists())
        report = self.f.report()
        self.assertEqual(report.get("preservedFonts", report.get("preserved", {}))[BOLD],
                         "source-weight-missing")

    def test_plan_cannot_turn_unproven_stage_into_full_rebuild(self):
        self.f.path(REGULAR).parent.mkdir(parents=True, exist_ok=True)
        self.f.path(REGULAR).write_bytes(b"stale staged data")
        result = self.f.invoke(plan=[REGULAR, NESTED], source=False)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.f.path(REGULAR).read_bytes(), b"stale staged data")
        self.assertFalse(self.f.path(NESTED).exists())
        self.assertEqual(self.f.snapshot_live(), self.before_live)

    def test_plan_reuses_other_completed_files_without_regenerating_them(self):
        self.assert_success(self.f.invoke())
        other = self.f.path(NESTED)
        before = (other.stat().st_ino, other.stat().st_mtime_ns, other.read_bytes())
        summary = self.assert_success(self.f.invoke(plan=[REGULAR], source=False))
        self.assertEqual((summary["requested"], summary["matched"]), (1, 1))
        self.assertEqual((summary["planned"], summary["rewritten"], summary["existing"]), (1, 1, 7))
        self.assertEqual((other.stat().st_ino, other.stat().st_mtime_ns, other.read_bytes()), before)
        self.assert_mapping()

    def test_plan_cannot_report_corrupt_unrequested_output_as_covered(self):
        self.assert_success(self.f.invoke())
        corrupt = self.f.path(NESTED)
        corrupt.unlink()
        corrupt.write_bytes(b"interrupted or damaged font output")
        result = self.f.invoke(plan=[REGULAR], source=False)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.f.snapshot_live(), self.before_live)
        self.assertEqual(corrupt.read_bytes(), b"interrupted or damaged font output")

    def test_cache_roundtrip_retains_proof_for_incremental_repair(self):
        from font_stage_chain_test import functions
        self.assert_success(self.f.invoke())
        safe = ROOT / "common/legacy_v14_4/font_switch_safe.sh"
        library = self.f.root / "cache-functions.sh"
        library.write_text("\n".join(functions(path.read_text()) for path in (
            ROOT / "common/legacy_v14_4/payload_clone.sh", ROOT / "common/font_provenance.sh", safe)))
        schema = re.search(r'^SWITCH_CACHE_SCHEMA="([^"]+)"', safe.read_text(), re.M).group(1)
        env = {**self.f.env, "MODDIR": str(self.f.module), "MODULE_DIR": str(self.f.module),
               "CONFIG_DIR": str(self.f.config), "LEGACY_DIR": str(self.f.module / "common/legacy_v14_4"),
               "STAGE_PAYLOAD": str(self.f.stage), "SOURCE": str(self.f.source),
               "SWITCH_CACHE_ROOT": str(self.f.config / "safe-switch-cache"),
               "SWITCH_CACHE_SCHEMA": schema, "SWITCH_CACHE_MAX_ENTRIES": "3",
               "SWITCH_CACHE_MAX_KB": "786432", "LIBRARY": str(library),
               "LOG_FILE": str(self.f.module / "logs/fontswitch.log")}
        result = subprocess.run(["sh", "-eu", "-c", '''
            . "$LIBRARY"
            safe_stage_begin "$SOURCE" Fixture
            safe_switch_cache_store "$SOURCE" Fixture
            stage_clear_text_payload
            test ! -e "$STAGE_PAYLOAD/.luoshu-inventory-output-manifest.json"
            safe_switch_cache_restore "$SOURCE" Fixture
        '''], env=env, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.f.stage / ".luoshu-inventory-output-manifest.json").is_file())
        summary = self.assert_success(self.f.invoke(plan=[REGULAR], source=False))
        self.assertEqual((summary["planned"], summary["existing"], summary["rewritten"]), (1, 7, 1))
        self.assert_mapping()

    def test_stale_or_traversing_plan_cannot_invent_targets(self):
        for plan in (["/system/fonts/Absent.ttf"], ["/system/fonts/../../outside.ttf"]):
            with self.subTest(plan=plan):
                result = self.f.invoke(plan=plan)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(self.f.snapshot_live(), self.before_live)
                self.assertFalse(self.f.path(REGULAR).exists())

    def test_corrupt_selected_source_aborts_without_fallback_or_live_mutation(self):
        self.f.source.write_bytes(b"not a font")
        result = self.f.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.f.snapshot_live(), self.before_live)
        self.assertFalse(self.f.path(REGULAR).exists())
        self.assertFalse((self.f.stage / ".luoshu-metrics-report.json").exists())

    def test_sfnt_without_outlines_is_not_accepted_as_a_renderable_source(self):
        with TTFont(self.f.source, recalcBBoxes=False) as font:
            del font["glyf"]
            del font["loca"]
            font.save(self.f.source)
        result = self.f.invoke()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.f.snapshot_live(), self.before_live)
        self.assertFalse(self.f.path(REGULAR).exists())

    def test_source_collection_selects_real_weight_faces(self):
        collection = TTCollection()
        collection.fonts = [TTFont(self.f.source), TTFont(self.f.library / "real-bold.ttf")]
        file = self.f.library / "selected.ttc"
        collection.save(file)
        collection.close()
        self.f.source.unlink()
        (self.f.library / "real-bold.ttf").unlink()
        self.f.source = file
        self.assert_success(self.f.invoke())
        self.assert_mapping()

    def test_selected_face_is_not_replaced_by_same_family_larger_variant(self):
        text_font(self.f.library / "broader-variant.ttf", points=LATIN | set(range(0x410, 0x450)),
                  advance=990)
        self.assert_success(self.f.invoke())
        with TTFont(self.f.path(REGULAR)) as output:
            self.assertEqual(output["hmtx"].metrics["zero"][0], 660,
                             "the selected usable face must take priority over a sibling variant")

    def test_multiscript_slot_changes_latin_while_retaining_other_scripts(self):
        greek = set(range(0x391, 0x3aa)) - {0x3a2}
        cyrillic = set(range(0x410, 0x430))
        han = set(range(0x4e00, 0x5000))
        text_font(self.f.stock / REGULAR.lstrip("/"), points=LATIN | greek | cyrillic,
                  family="Stock multilingual UI", ascent=980, descent=-240)
        text_font(self.f.source, points=LATIN | han)
        self.f.scan()
        scripts = self.f.inventory["slots"][REGULAR]["requiresScripts"]
        self.assertEqual(set(scripts), {"Latn", "Grek", "Cyrl"})
        before = self.assert_success(self.f.invoke())
        self.assertEqual(before["inventorySlots"], 9)
        self.assertEqual((before["mapped"], before["preserved"]), (8, 1))
        self.assertTrue(self.f.path(REGULAR).is_file())
        self.assertNotIn(REGULAR, self.f.report()["preservedFonts"])
        status = trace.build_physical_trace(self.f.inventory, self.f.stage, prepared=True)
        slot = next(item for item in status["slots"] if item["path"] == REGULAR)
        self.assertEqual(slot["category"], "pending")
        self.assertFalse(slot["safeToRetry"])
        # An unrelated-script sibling must not replace the selected Latin face;
        # non-target scripts continue to use their original stock glyphs.
        text_font(self.f.library / "multilingual-regular.ttf",
                  points=LATIN | greek | cyrillic | han, advance=880)
        after = self.assert_success(self.f.invoke())
        self.assertEqual(after["inventorySlots"], before["inventorySlots"])
        self.assertEqual((after["mapped"], after["preserved"]), (8, 1))
        self.assertNotIn(REGULAR, self.f.report()["preservedFonts"])
        with TTFont(self.f.path(REGULAR)) as font:
            self.assertTrue((LATIN | greek | cyrillic).issubset(font.getBestCmap()))
            self.assertEqual(font["hmtx"].metrics[font.getBestCmap()[65]][0], 660)
        with TTFont(self.f.path(NESTED)) as font:
            self.assertEqual(font["hmtx"].metrics["zero"][0], 660)

    def test_real_targeted_replacement_keeps_greek_arabic_hiragana_layout(self):
        from inventory_font_supplement_test import fixture, outline, shape
        stock_path = self.f.stock / REGULAR.lstrip("/")
        fixture(stock_path)
        fixture(self.f.source, source=True)
        han = set(range(0x4e00, 0x5000))
        for path, source in ((stock_path, False), (self.f.source, True)):
            with TTFont(path) as font:
                for table in font["cmap"].tables:
                    if table.isUnicode() and table.format != 14:
                        for cp in LATIN | han:
                            table.cmap.setdefault(cp, "A" if source else "B")
                        if not source:
                            table.cmap[0x3042] = "cyrillic"
                font.save(path)
        self.f.scan()
        originals = {path: path.read_bytes() for path in (stock_path, self.f.source)}
        expected_shapes = {text: shape(stock_path, text) for text in ("ΑΒ", "بَا", "あ")}
        self.assert_success(self.f.invoke())
        output_path = self.f.path(REGULAR)
        with TTFont(stock_path) as stock, TTFont(self.f.source) as donor, TTFont(output_path) as output:
            self.assertTrue(set(stock.getBestCmap()).issubset(output.getBestCmap()))
            for cp in (65, 48, 0x4e00):
                self.assertEqual(outline(output, output.getBestCmap()[cp]),
                                 outline(donor, donor.getBestCmap()[cp]))
                self.assertNotEqual(outline(output, output.getBestCmap()[cp]),
                                    outline(stock, stock.getBestCmap()[cp]))
            for cp in (0x391, 0x392, 0x410, 0x627, 0x628, 0x64e, 0x3042):
                self.assertEqual(outline(output, output.getBestCmap()[cp]),
                                 outline(stock, stock.getBestCmap()[cp]))
        for text, expected in expected_shapes.items():
            self.assertEqual(shape(output_path, text), expected, text)
        row = next(row for row in self.f.report()["slots"] if row["slot"] == REGULAR)
        self.assertEqual(set(row["replacedRoles"]), {"cjk", "latin", "digit"})
        self.assertTrue(row["supplemented"])
        self.assertGreaterEqual(row["retainedStockCodepoints"], 7)
        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), original)

    def test_digit_changes_cannot_report_success_when_main_text_did_not_change(self):
        etc = self.f.stock / "system/etc"
        etc.mkdir(parents=True, exist_ok=True)
        (etc / "fonts.xml").write_text('<familyset><family name="sans-serif">'
            '<font weight="400">Unknown-Regular.ttf</font></family></familyset>')
        self.f.scan()
        self.assertEqual(self.f.inventory["mainSlotPath"], REGULAR)
        text_font(self.f.source, points=set(range(48, 58)))
        result = self.f.invoke()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("主要中文或英文字体尚未替换", result.stderr)
        self.assertFalse(self.f.path(DIGITS).exists())
        self.assertFalse(self.f.path(REGULAR).exists())
        self.assertEqual(self.f.snapshot_live(), self.before_live)

    def test_full_base_character_coverage_keeps_original_unicode_variants(self):
        from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
        from inventory_font_supplement_test import fixture, outline, shape
        stock_path = self.f.stock / REGULAR.lstrip("/")
        fixture(stock_path)
        fixture(self.f.source, source=True)
        for path in (stock_path, self.f.source):
            with TTFont(path) as font:
                for table in font["cmap"].tables:
                    if table.isUnicode() and table.format != 14:
                        table.cmap = {cp: table.cmap.get(cp, "A") for cp in LATIN}
                if path == stock_path:
                    uvs = CmapSubtable.newSubtable(14)
                    uvs.platformID, uvs.platEncID, uvs.language = 0, 5, 0
                    uvs.cmap = {}
                    uvs.uvsDict = {0xFE00: [(65, None)], 0xFE01: [(66, "B")]}
                    font["cmap"].tables.append(uvs)
                font.save(path)
        self.f.scan()
        expected = {text: shape(stock_path, text) for text in ("A\ufe00", "B\ufe01")}
        self.assert_success(self.f.invoke())
        output_path = self.f.path(REGULAR)
        with TTFont(stock_path) as stock, TTFont(self.f.source) as donor, TTFont(output_path) as output:
            self.assertEqual(set(stock.getBestCmap()), set(donor.getBestCmap()))
            self.assertEqual(outline(output, output.getBestCmap()[65]), outline(donor, "A"))
            self.assertNotEqual(outline(output, output.getBestCmap()[65]), outline(stock, "A"))
            variants = next(table for table in output["cmap"].tables if table.format == 14).uvsDict
            for selector, cp, name in ((0xFE00, 65, "A"), (0xFE01, 66, "B")):
                variant = dict(variants[selector])[cp]
                self.assertIsNotNone(variant)
                self.assertEqual(outline(output, variant), outline(stock, name))
        for text, original in expected.items():
            self.assertEqual(shape(output_path, text), original, text)
        row = next(row for row in self.f.report()["slots"] if row["slot"] == REGULAR)
        self.assertTrue(row["supplemented"])
        self.assertEqual(row["retainedStockCodepoints"], 0)

    def test_cff2_source_keeps_outline_bytes_and_stock_layout(self):
        from fontTools.cffLib.CFFToCFF2 import convertCFFToCFF2
        from font_metrics_batch_raw_test import make_source
        make_source(self.f.source, cff=True)
        with TTFont(self.f.source) as font:
            convertCFFToCFF2(font)
            font.save(self.f.source)
        with TTFont(self.f.source, lazy=True) as source:
            before = source.reader["CFF2"]
        self.assert_success(self.f.invoke())
        with TTFont(self.f.path(REGULAR)) as output:
            self.assertEqual(output.reader["CFF2"], before)
            self.assertEqual(output["hhea"].ascent, 980)
            self.assertEqual(output["hhea"].descent, -240)
            glyph = output.getGlyphSet()[output.getBestCmap()[65]]
            from fontTools.pens.boundsPen import BoundsPen
            pen = BoundsPen(output.getGlyphSet())
            glyph.draw(pen)
            self.assertIsNotNone(pen.bounds)

    def test_freetype_loads_ttf_and_cff_outputs_with_unchanged_glyph_pixels(self):
        from hyperos_layout_freetype_test import FreeType, fixture_font
        freetype = FreeType()
        self.addCleanup(freetype.close)
        stock = self.f.inventory["slots"][REGULAR]["metrics"]
        for cff in (False, True):
            with self.subTest(format="CFF" if cff else "TTF"):
                fixture_font(self.f.source, upem=1000, cff=cff)
                with TTFont(self.f.source) as font:
                    for table in font["cmap"].tables:
                        if table.isUnicode():
                            for cp in LATIN:
                                table.cmap.setdefault(cp, "A")
                    font.save(self.f.source)
                original = self.f.source.read_bytes()
                before = freetype.inspect(self.f.source)
                self.assert_success(self.f.invoke())
                after = freetype.inspect(self.f.path(REGULAR))
                self.assertEqual(before["glyphs"], after["glyphs"])
                self.assertEqual((after["ascender"], after["descender"]),
                                 (stock["hhea"]["ascent"], stock["hhea"]["descent"]))
                self.assertEqual((after["bbox"][1], after["bbox"][3]),
                                 (stock["head"]["yMin"], stock["head"]["yMax"]))
                self.assertNotEqual(before["bbox"], after["bbox"])
                self.assertEqual(self.f.source.read_bytes(), original)

    def test_variable_source_instantiates_real_weight_outline_deltas(self):
        from font_instance_contract_test import make_font as make_variable_font
        make_variable_font(self.f.source, variable=True)
        with TTFont(self.f.source) as font:
            for table in font["cmap"].tables:
                if table.isUnicode():
                    table.cmap.update({cp: "u0041" for cp in LATIN})
            font.save(self.f.source)
        self.assert_success(self.f.invoke())
        for logical, weight, expected_right in ((REGULAR, 400, 150), (BOLD, 700, 270),
                                                 (HEAVY, 900, 350)):
            with self.subTest(weight=weight), TTFont(self.f.path(logical)) as output:
                self.assertNotIn("fvar", output)
                self.assertEqual(output["OS/2"].usWeightClass, weight)
                glyph = output["glyf"][output.getBestCmap()[65]]
                coords = glyph.getCoordinates(output["glyf"])[0]
                self.assertEqual(max(x for x, _ in coords), expected_right)

    def test_invalid_contract_fails_atomically_without_copying_regular(self):
        entry = self.f.inventory["slots"][NESTED]
        entry["metrics"]["hhea"]["ascent"] = -10
        for face in entry.get("faces", []):
            face["metrics"]["hhea"]["ascent"] = -10
        self.f.save_inventory()
        result = self.f.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.f.snapshot_live(), self.before_live)
        self.assertFalse(self.f.path(REGULAR).exists())
        self.assertFalse(self.f.path(NESTED).exists())

    def test_trace_explains_unsupported_fonts_without_offering_futile_repair(self):
        self.assert_success(self.f.invoke())
        import physical_font_load_verify as physical_verify
        with patch.dict(os.environ, {"LUOSHU_VISIBLE_ROOT": str(self.f.stage),
                                     "LUOSHU_TEST_BOOT_ID": "coverage-integration-boot"}):
            proof = physical_verify.verify(self.f.module, self.f.stage, "selected")
            self.assertEqual(proof["state"], "verified", proof)
            physical_verify.save_result(self.f.module, proof, True)
            result = trace.build_physical_trace(self.f.inventory, self.f.stage,
                                                prepared=False, active_font="selected")
        slots = {item["path"]: item for item in result["slots"]}
        for logical in (HEAVY, PARTIAL):
            self.assertEqual(slots[logical]["category"], "issue", slots[logical])
            self.assertFalse(slots[logical]["safeToRetry"])
        self.assertTrue(slots[HEAVY]["sourceUnavailable"])
        self.assertFalse(slots[PARTIAL]["sourceUnavailable"])
        self.assertEqual(slots[PARTIAL]["state"], "partial")
        self.assertEqual(slots[PARTIAL]["retainedFaces"][0]["faceIndex"], 1)
        self.assertIn("第 1 面 · 已替换", slots[PARTIAL]["routes"][0]["family"])
        self.assertIn("第 2 面 · 保留原厂", slots[PARTIAL]["routes"][1]["family"])
        self.assertEqual(result["summary"]["issues"], 2)
        self.assertEqual(result["summary"]["sourceUnavailable"], 1)
        self.assertEqual(result["summary"]["partial"], 1)
        self.assertEqual(result["summary"]["remediable"], 0)
        self.assertEqual(result["summary"]["inventorySlots"], 9)
        self.assertEqual(result["summary"]["replaced"], 7)
        self.assertEqual(result["verificationState"], "partial")


if __name__ == "__main__":
    unittest.main(verbosity=2)
