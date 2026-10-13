#!/usr/bin/env python3
"""Font capability: weights, variable instances, TTC faces, italic, emoji, fallback."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))
sys.path.insert(0, str(ROOT / "scripts"))

from fontTools.ttLib import TTFont  # noqa: E402

import font_capability as cap  # noqa: E402
from font_capability_fixtures import HAN, HANT, LATIN, build, build_collection, build_variable, stem_width  # noqa: E402


class WeightNameTest(unittest.TestCase):
    def test_compound_weights_before_plain_bold_light(self):
        cases = {
            "Roboto-ExtraBold.ttf": 800, "Roboto-UltraBold.ttf": 800, "Foo-Extra Bold": 800,
            "Roboto-UltraLight.ttf": 200, "Roboto-ExtraLight.ttf": 200, "foo-extralight.otf": 200,
            "Foo-SemiBold": 600, "Foo-DemiBold": 600, "Foo-Black": 900, "Foo-Heavy": 900,
            "Foo-ExtraBlack": 900, "Foo-Bold": 700, "Foo-Medium": 500, "Foo-Light": 300,
            "Foo-Thin": 100, "Foo-Hairline": 100, "OplusOSUI-XThin.ttf": 100,
            "ASCH-W3.ttf": 300, "asch-w8.ttf": 800, "700.ttf": 700, "350.ttf": 350,
            "某字体-特粗": 800, "某字体-中粗": 600, "Foo-Regular": 400,
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(cap.weight_from_name(name), expected)

    def test_words_containing_weight_letters_are_not_weights(self):
        for name in ("AndroidClock_Highlight.ttf", "Nothing.ttf", "MiSansVF.ttf", "Foo-Italic.ttf"):
            with self.subTest(name=name):
                self.assertIsNone(cap.weight_from_name(name))

    def test_metrics_batch_weight_for_name_uses_the_same_parser(self):
        import hyperos_metrics_batch as batch
        self.assertEqual(batch.weight_for_name("Roboto-ExtraBold.ttf"), 800)
        self.assertEqual(batch.weight_for_name("Roboto-UltraLight.ttf"), 200)
        self.assertEqual(batch.weight_for_name("AndroidClock_Highlight.ttf"), 400)

    def test_slot_kinds(self):
        for name in ("MiSansVF.ttf", "MiSansVF_Overlay.ttf", "GoogleSans-VF.ttf", "GoogleSansTextVF.ttf",
                     "RobotoFlex-Regular.ttf", "NotoSansVariable.ttf"):
            self.assertTrue(cap.is_variable_slot_name(name), name)
        for name in ("Roboto-Regular.ttf", "700.ttf", "MitypeClock.otf"):
            self.assertFalse(cap.is_variable_slot_name(name), name)
        self.assertTrue(cap.is_emoji_slot_name("NotoColorEmoji.ttf"))
        self.assertTrue(cap.is_italic_slot_name("Roboto-BoldItalic.ttf"))
        self.assertTrue(cap.is_serif_slot_name("NotoSerif-Bold.ttf"))
        self.assertFalse(cap.is_serif_slot_name("Roboto-Regular.ttf"))
        self.assertEqual(cap.fallback_script_for_slot("MiSansTCVF.ttf"), "hant")
        self.assertEqual(cap.fallback_script_for_slot("NotoSansHK-Regular.otf"), "hant")
        self.assertEqual(cap.fallback_script_for_slot("NotoSansSC-Regular.otf"), "han")
        self.assertEqual(cap.fallback_script_for_slot("DroidSansFallback.ttf"), "han")
        self.assertIsNone(cap.fallback_script_for_slot("MiSansVF.ttf"))
        self.assertIsNone(cap.fallback_script_for_slot("Roboto-Regular.ttf"))


class FontCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)


class StaticFamilyTest(FontCase):
    def test_os2_weights_map_every_slot_and_missing_weights_go_to_nearest(self):
        # Filenames carry no weight; OS/2 decides.
        light = build(self.dir / "Mystery-A.ttf", style="Light", weight=300)
        regular = build(self.dir / "Mystery-B.ttf", style="Regular", weight=400)
        bold = build(self.dir / "Mystery-C.ttf", style="Bold", weight=700)
        plan = cap.plan_slots(cap.collect_faces([light, regular, bold]))
        picked = {weight: Path(choice.path).name for weight, choice in plan.items()}
        self.assertEqual(picked, {
            100: "Mystery-A.ttf", 200: "Mystery-A.ttf", 300: "Mystery-A.ttf",
            400: "Mystery-B.ttf", 500: "Mystery-B.ttf", 600: "Mystery-C.ttf",
            700: "Mystery-C.ttf", 800: "Mystery-C.ttf", 900: "Mystery-C.ttf"})
        self.assertEqual(plan[300].mode, "exact")
        self.assertEqual(plan[900].mode, "nearest")
        # Not everything falls back to Regular.
        self.assertNotEqual(plan[900].path, plan[400].path)
        self.assertNotEqual(plan[100].path, plan[400].path)

    def test_generic_400_contradicted_by_style_name_uses_the_name(self):
        extra = build(self.dir / "Fam-X.ttf", style="ExtraBold", weight=400)
        regular = build(self.dir / "Fam-Y.ttf", style="Regular", weight=400)
        faces = cap.collect_faces([extra, regular])
        weights = {Path(face.path).name: face.weight for face in faces}
        self.assertEqual(weights, {"Fam-X.ttf": 800, "Fam-Y.ttf": 400})
        ultra = build(self.dir / "Fam-Z.ttf", style="UltraLight", weight=400)
        self.assertEqual(cap.inspect_face(ultra, -1).weight, 200)

    def test_explicit_os2_weight_is_authoritative(self):
        semi = build(self.dir / "Fam-Bold.ttf", style="Bold", weight=600)
        self.assertEqual(cap.inspect_face(semi, -1).weight, 600)

    def test_import_probe_reconciles_os2_with_style_name(self):
        extra = build(self.dir / "Pkg-A.ttf", style="ExtraBold", weight=400)
        out = subprocess.run([sys.executable, str(ROOT / "common/font_import_probe.py"), str(extra)],
                             capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(out.split("|")[2], "800")
        italic = build(self.dir / "Pkg-I.ttf", style="Regular", weight=400, italic=True)
        out = subprocess.run([sys.executable, str(ROOT / "common/font_import_probe.py"), str(italic)],
                             capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(out.split("|")[3], "true")


class VariableTest(FontCase):
    def test_missing_static_weights_are_instantiated_on_wght(self):
        vf = build_variable(self.dir / "Demo-Variable.ttf")
        faces = cap.collect_faces([vf])
        plan = cap.plan_slots(faces)
        self.assertEqual({choice.mode for choice in plan.values()}, {"instance"})
        rows = cap.build_anchors([vf], self.dir / "store", variable_anchor="variable.font")
        self.assertEqual(len(rows), 9)
        widths = {}
        for weight, target, _mode in rows:
            with TTFont(str(target)) as font:
                self.assertNotIn("fvar", font)
                self.assertEqual(font["OS/2"].usWeightClass, weight)
            widths[weight] = stem_width(target)
        # Real outlines differ per weight instead of reusing the default 400.
        self.assertLess(widths[100], widths[400])
        self.assertLess(widths[400], widths[700])
        self.assertLess(widths[700], widths[900])
        with TTFont(str(self.dir / "store/variable.font")) as font:
            self.assertIn("fvar", font)

    def test_narrow_axis_uses_nearest_instance(self):
        vf = build_variable(self.dir / "Narrow-Variable.ttf", low=300, high=700, default=400)
        plan = cap.plan_slots(cap.collect_faces([vf]))
        self.assertEqual(plan[900].mode, "nearest-instance")
        self.assertEqual(plan[900].wght, 700.0)
        self.assertEqual(plan[100].wght, 300.0)
        self.assertEqual(plan[500].mode, "instance")

    def test_static_exact_face_beats_instance(self):
        vf = build_variable(self.dir / "Mix-Variable.ttf")
        bold = build(self.dir / "Mix-Bold.ttf", style="Bold", weight=700)
        plan = cap.plan_slots(cap.collect_faces([vf, bold]))
        self.assertEqual(Path(plan[700].path).name, "Mix-Bold.ttf")
        self.assertEqual(plan[500].mode, "instance")


class CollectionTest(FontCase):
    def test_ttc_faces_are_routed_by_index(self):
        regular = build(self.dir / "r.ttf", family="Coll", style="Regular", weight=400)
        bold = build(self.dir / "b.ttf", family="Coll", style="Bold", weight=700)
        ttc = build_collection(self.dir / "Coll.ttc", [regular, bold])
        faces = cap.collect_faces([ttc])
        self.assertEqual([face.index for face in faces], [0, 1])
        plan = cap.plan_slots(faces)
        self.assertEqual(plan[700].index, 1)
        self.assertEqual(plan[400].index, 0)
        rows = cap.build_anchors([ttc], self.dir / "store")
        for weight, target, _mode in rows:
            self.assertNotEqual(target.read_bytes()[:4], b"ttcf", weight)
        self.assertGreater(stem_width(self.dir / "store/wght-700.font"),
                           stem_width(self.dir / "store/wght-400.font"))

    def test_extractor_groups_faces_and_rejects_unsupported(self):
        regular = build(self.dir / "r.ttf", family="Coll", style="Regular", weight=400)
        bold = build(self.dir / "b.ttf", family="Coll", style="Bold", weight=700)
        emoji = build(self.dir / "e.ttf", family="Coll", style="Regular", weight=400, color=True)
        ttc = build_collection(self.dir / "Coll.ttc", [regular, bold, emoji])
        out = self.dir / "out"
        result = subprocess.run([sys.executable, str(ROOT / "common/font_extract_faces.py"),
                                 "--input", str(ttc), "--output-dir", str(out), "--label", "Coll"],
                                capture_output=True, text=True)
        data = json.loads(result.stdout)
        self.assertEqual(data["status"], "ok", data)
        self.assertEqual(data["data"]["imported"], 2)
        self.assertEqual([item["faceIndex"] for item in data["data"]["skipped"]], [2])
        names = sorted(path.name for path in out.iterdir())
        self.assertEqual(len(names), 2)
        self.assertTrue(names[0].endswith("-Bold.ttf") and names[1].endswith("-Regular.ttf"), names)
        # One family stem: detect_font_family strips only the weight suffix.
        self.assertEqual(names[0][: -len("-Bold.ttf")], names[1][: -len("-Regular.ttf")])

        only_emoji = build_collection(self.dir / "Emoji.ttc", [emoji, emoji])
        result = subprocess.run([sys.executable, str(ROOT / "common/font_extract_faces.py"),
                                 "--input", str(only_emoji), "--output-dir", str(self.dir / "out2")],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        message = json.loads(result.stdout)["message"]
        self.assertIn("没有可作为文字字体的字体面", message)
        self.assertIn("Emoji", message)


class ItalicEmojiTest(FontCase):
    def test_italic_never_serves_upright_and_absent_italic_plans_nothing(self):
        regular = build(self.dir / "Demo-Regular.ttf", weight=400)
        italic = build(self.dir / "Demo-Italic.ttf", style="Italic", weight=400, italic=True)
        faces = cap.collect_faces([italic, regular])
        upright = cap.plan_slots(faces)
        self.assertTrue(all(Path(choice.path).name == "Demo-Regular.ttf" for choice in upright.values()))
        slanted = cap.plan_slots(faces, italic=True)
        self.assertTrue(all(Path(choice.path).name == "Demo-Italic.ttf" for choice in slanted.values()))
        self.assertEqual(cap.plan_slots(cap.collect_faces([regular]), italic=True), {})

    def test_color_fonts_are_detected_and_never_planned(self):
        emoji = build(self.dir / "MyEmoji.ttf", family="Emo", color=True)
        self.assertTrue(cap.is_color_font(emoji))
        self.assertFalse(cap.is_color_font(build(self.dir / "Text.ttf")))
        self.assertEqual(cap.plan_slots(cap.collect_faces([emoji])), {})

    def test_single_static_regular_is_shared_by_hard_links(self):
        regular = build(self.dir / "Solo-Regular.ttf", weight=400)
        rows = cap.build_anchors([regular], self.dir / "store")
        inodes = {target.stat().st_ino for _weight, target, _mode in rows}
        self.assertEqual(len(inodes), 1)


class MetricsBatchCapabilityTest(FontCase):
    def test_variable_slot_prefers_fvar_source(self):
        import hyperos_metrics_batch as batch
        fonts = self.dir / "system/fonts"
        store = fonts / ".luoshu-font-store"
        build(store / "wght-400.font", weight=400)
        build(fonts / "400.ttf", weight=400)
        self.assertIsNone(batch.variable_slot_source(fonts, "MiSansVF.ttf"))
        build_variable(store / "variable.font")
        self.assertEqual(batch.variable_slot_source(fonts, "MiSansVF.ttf"), store / "variable.font")
        self.assertIsNone(batch.variable_slot_source(fonts, "Roboto-Bold.ttf"))
        # Static slots still take the per-weight anchor.
        build(store / "wght-800.font", weight=800)
        self.assertEqual(batch.pick_source(fonts, "Roboto-ExtraBold.ttf"), store / "wght-800.font")

    def test_language_fallback_slot_keeps_stock_when_donor_lacks_script(self):
        import hyperos_metrics_batch as batch
        stock = build(self.dir / "stock/MiSansTCVF.ttf", text=LATIN + HANT + HAN)
        latin_only = build(self.dir / "latin.ttf", text=LATIN + HAN)
        complete = build(self.dir / "complete.ttf", text=LATIN + HAN + HANT)
        cache: dict = {}
        keep, script, ratio = batch.keeps_stock_fallback(latin_only, stock, "MiSansTCVF.ttf", cache)
        self.assertEqual((keep, script), (True, "hant"))
        self.assertLess(ratio, cap.SCRIPT_COVERAGE_MIN)
        self.assertFalse(batch.keeps_stock_fallback(complete, stock, "MiSansTCVF.ttf", cache)[0])
        # The main UI slot is never gated, and a stock slot without the script is not either.
        self.assertFalse(batch.keeps_stock_fallback(latin_only, stock, "MiSansVF.ttf", cache)[0])
        latin_stock = build(self.dir / "stock/DroidSansFallback.ttf", text=LATIN)
        self.assertFalse(batch.keeps_stock_fallback(build(self.dir / "l2.ttf", text=LATIN),
                                                    latin_stock, "DroidSansFallback.ttf", cache)[0])


class CliTest(FontCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "common/font_capability.py"), *args],
                              capture_output=True, text=True)

    def test_plan_and_anchor_cli(self):
        vf = build_variable(self.dir / "Cli-Variable.ttf")
        result = self.run_cli("plan", str(vf))
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.strip().splitlines()
        self.assertEqual(len(lines), 9)
        self.assertEqual(lines[6].split("|")[0], "700")
        self.assertEqual(lines[6].split("|")[3], "instance")
        store = self.dir / "store"
        result = self.run_cli("anchors", "--store", str(store), "--weights", "100,350,900",
                              "--variable-anchor", "variable.font", str(vf))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((store / "wght-350.font").is_file())
        self.assertTrue((store / "variable.font").is_file())
        self.assertNotEqual(self.run_cli("anchors", "--store", str(store), "--prefix", "../x", str(vf)).returncode, 0)
        self.assertEqual(self.run_cli("plan", str(build(self.dir / "e.ttf", color=True))).returncode, 3)
        han = build(self.dir / "han.ttf", text=LATIN + HAN)
        self.assertEqual(self.run_cli("covers", "--script", "han", str(han)).returncode, 0)
        self.assertNotEqual(self.run_cli("covers", "--script", "hant", str(han)).returncode, 0)


if __name__ == "__main__":
    unittest.main()
