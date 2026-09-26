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
        for logical in (REGULAR, BOLD, COLLECTION, DIGITS, NESTED, UNKNOWN):
            self.assertTrue(f.path(logical).is_file(), logical)
        for logical in (HEAVY, SCRIPT, PARTIAL):
            self.assertFalse(f.path(logical).exists(), logical)
        report = f.report()
        protected = report.get("preservedFonts", report.get("preserved", {}))
        self.assertEqual(protected[HEAVY], "source-weight-missing")
        self.assertEqual(protected[SCRIPT], "source-script-coverage-missing")
        self.assertIn("source-weight-missing", protected[PARTIAL])
        with TTFont(f.path(BOLD)) as font:
            self.assertEqual(font["OS/2"].usWeightClass, 700)
            self.assertEqual(font["hmtx"].metrics["zero"][0], 920)
            self.assertEqual(font["hhea"].ascent, 980)
        with TTCollection(f.path(COLLECTION)) as collection:
            self.assertEqual([font["OS/2"].usWeightClass for font in collection.fonts], [400, 700])
            self.assertEqual([font["hhea"].ascent for font in collection.fonts], [1000, 1050])

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

    def test_plan_rebuilds_requested_slot_and_fills_clean_stage(self):
        self.f.path(REGULAR).parent.mkdir(parents=True, exist_ok=True)
        self.f.path(REGULAR).write_bytes(b"stale staged data")
        summary = self.assert_success(self.f.invoke(plan=[REGULAR, NESTED]))
        self.assertEqual((summary["requested"], summary["matched"]), (2, 2))
        self.assertEqual((summary["planned"], summary["rewritten"], summary["added"]), (6, 1, 5))
        self.assertEqual((summary["preserved"], summary["fallback"], summary["failed"]), (3, 0, 0))
        self.assert_mapping()

    def test_plan_reuses_other_completed_files_without_regenerating_them(self):
        self.assert_success(self.f.invoke())
        other = self.f.path(NESTED)
        before = (other.stat().st_ino, other.stat().st_mtime_ns, other.read_bytes())
        summary = self.assert_success(self.f.invoke(plan=[REGULAR, SCRIPT], source=False))
        self.assertEqual((summary["requested"], summary["matched"]), (2, 2))
        self.assertEqual((summary["planned"], summary["rewritten"], summary["existing"]), (1, 1, 5))
        self.assertEqual((other.stat().st_ino, other.stat().st_mtime_ns, other.read_bytes()), before)
        self.assert_mapping()

    def test_plan_cannot_report_corrupt_unrequested_output_as_covered(self):
        self.assert_success(self.f.invoke())
        corrupt = self.f.path(NESTED)
        corrupt.unlink()
        corrupt.write_bytes(b"interrupted or damaged font output")
        result = self.f.invoke(plan=[REGULAR], source=False)
        self.assertEqual(self.f.snapshot_live(), self.before_live)
        if result.returncode == 0:
            # Either rebuild the untrusted output or abort the isolated stage.
            # Merely finding its pathname is not proof that coverage exists.
            try:
                with TTFont(corrupt) as font:
                    self.assertEqual(font["OS/2"].usWeightClass, 400)
                    self.assertEqual(font["hhea"].ascent, 980)
            except Exception as error:
                self.fail(f"plan reported success with a corrupt unrequested font: {error}")

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
        self.assertEqual((summary["planned"], summary["existing"], summary["rewritten"]), (1, 5, 1))
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

    def test_multiscript_slot_stays_detected_until_source_supports_all_scripts(self):
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
        self.assertEqual((before["mapped"], before["preserved"]), (5, 4))
        self.assertFalse(self.f.path(REGULAR).exists())
        self.assertEqual(self.f.report()["preservedFonts"][REGULAR],
                         "source-script-coverage-missing")
        status = trace.build_physical_trace(self.f.inventory, self.f.stage, prepared=True)
        slot = next(item for item in status["slots"] if item["path"] == REGULAR)
        self.assertEqual(slot["category"], "protected")
        self.assertFalse(slot["safeToRetry"])
        # No scanner change is needed when the same family gains a real face
        # with the required scripts. Its glyphs must actually be present.
        text_font(self.f.library / "multilingual-regular.ttf",
                  points=LATIN | greek | cyrillic | han, advance=880)
        after = self.assert_success(self.f.invoke())
        self.assertEqual(after["inventorySlots"], before["inventorySlots"])
        self.assertEqual((after["mapped"], after["preserved"]), (6, 3))
        self.assertNotIn(REGULAR, self.f.report()["preservedFonts"])
        with TTFont(self.f.path(REGULAR)) as font:
            self.assertTrue((LATIN | greek | cyrillic).issubset(font.getBestCmap()))
            self.assertEqual(font["hmtx"].metrics["zero"][0], 880)
        with TTFont(self.f.path(NESTED)) as font:
            self.assertEqual(font["hmtx"].metrics["zero"][0], 660)

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
        result = trace.build_physical_trace(self.f.inventory, self.f.stage, prepared=False)
        slots = {item["path"]: item for item in result["slots"]}
        for logical in (HEAVY, SCRIPT, PARTIAL):
            self.assertEqual(slots[logical]["category"], "protected", slots[logical])
            self.assertFalse(slots[logical]["safeToRetry"])
        self.assertEqual(result["summary"]["issues"], 0)
        self.assertEqual(result["summary"]["inventorySlots"], 9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
