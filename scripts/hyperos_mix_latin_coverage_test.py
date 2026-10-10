#!/usr/bin/env python3
"""HyperOS composite (组合模式) must reach the Latin UI slots, not only MiSansVF.

Runs the real legacy composite generator, then the real HyperOS stage
completion batch that mix_router.sh finalize uses, on a dali-shaped stock
layout (MiSansVF with Han, MiSansLatinVF Latin-only plus U+3007, Roboto,
DroidSans, product/fonts copies). Fixture glyphs encode their origin in the
contour count, so scaling by the composite layout cannot hide a stock/CJK leak.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import fontTools
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))
from font_inventory import _read_metrics  # noqa: E402
import hyperos_metrics_batch as batch  # noqa: E402

HOST_SITE = str(Path(fontTools.__file__).resolve().parent.parent)
HAN = [ord(c) for c in "中文字体系统默认洛书汉字国一的。"] + list(range(0x4E00, 0x4E00 + 600))
LATIN = list(range(0x20, 0x7F)) + list(range(0xA0, 0x180))


def font(path: Path, points, contours: int, top: int, upem: int = 1000, ascent=900, descent=-200):
    """Each glyph has `contours` boxes: 1 = CJK base, 2 = Latin donor, 3 = stock."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cmap = {cp: f"u{cp:X}" for cp in sorted(set(points))}
    order = [".notdef", *cmap.values()]
    glyphs = {".notdef": TTGlyphPen(None).glyph()}
    for name in order[1:]:
        pen = TTGlyphPen(None)
        for index in range(contours):
            left = 40 + index * 150
            pen.moveTo((left, 0)); pen.lineTo((left + 100, 0))
            pen.lineTo((left + 100, top)); pen.lineTo((left, top)); pen.closePath()
        glyphs[name] = pen.glyph()
    builder = FontBuilder(upem, isTTF=True)
    builder.setupGlyphOrder(order); builder.setupCharacterMap(cmap); builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (600, 40) for name in order})
    builder.setupHorizontalHeader(ascent=ascent, descent=descent)
    builder.setupOS2(sTypoAscender=ascent, sTypoDescender=descent, usWinAscent=ascent, usWinDescent=-descent)
    builder.setupNameTable({"familyName": path.stem, "styleName": "Regular"})
    builder.setupPost(); builder.setupMaxp(); builder.save(path)


def contours(path: Path, char: str) -> int | None:
    with TTFont(path) as face:
        name = (face.getBestCmap() or {}).get(ord(char))
        if name is None:
            return None
        glyph = face["glyf"][name]
        glyph.expand(face["glyf"])
        return glyph.numberOfContours


class HyperOSMixLatinCoverage(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luoshu-hyperos-mix-latin-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / "module"
        (self.module / "config").mkdir(parents=True)
        self.stage = self.root / "module/.luoshu-state/tmp/mix-stage"
        self.env = dict(os.environ, LUOSHU_BUILD_KEY="fixture",
                        PYTHONPATH=os.pathsep.join([str(ROOT / "common"), HOST_SITE]))
        for part in batch.PARTS:
            (self.root / "stock" / part).mkdir(parents=True)
            self.env[f"LUOSHU_{part.upper()}_FONTS_ROOT"] = str(self.root / "stock" / part)
        stock = {
            ("system", "MiSansVF.ttf"): (HAN + LATIN, ["mipro"]),
            ("product", "MiSansVF.ttf"): (HAN + LATIN, ["mipro"]),
            ("system", "MiSansLatinVF.ttf"): (LATIN + [0x3007], ["mipro-latin"]),
            ("product", "MiSansLatinVF.ttf"): (LATIN + [0x3007], ["mipro-latin"]),
            ("system", "Roboto-Regular.ttf"): (LATIN, ["sans-serif"]),
            ("system", "RobotoStatic-Regular.ttf"): (LATIN, []),
            ("system", "DroidSans.ttf"): (LATIN, []),
        }
        slots = {}
        for (part, name), (points, families) in stock.items():
            path = self.root / "stock" / part / name
            upem = 2048 if name.startswith("Roboto") else 1000
            font(path, points, 3, 700, upem=upem, ascent=1044 if upem == 1000 else 1900,
                 descent=-282 if upem == 1000 else -500)
            fmt, metrics = _read_metrics(path)
            slots[f"/{part}/fonts/{name}"] = {
                "path": f"/{part}/fonts/{name}", "source": "xml", "weight": 400, "style": "normal",
                "faceIndex": 0, "families": families, "format": fmt, "metrics": metrics}
        (self.module / "config/device_font_inventory.json").write_text(json.dumps({
            "schema": "device-font-inventory-v1", "inventoryRevision": 1, "state": "ready",
            "buildKey": "fixture", "mainSlotPath": "/system/fonts/MiSansVF.ttf", "slots": slots}))
        self.names = sorted({name for _part, name in stock})
        self.cjk = self.root / "public/CJK.ttf"
        self.latin = self.root / "public/Latin.ttf"
        font(self.cjk, HAN + LATIN, 1, 760)
        font(self.latin, LATIN, 2, 680)

    def composite(self) -> Path:
        output = self.root / "composite.otf"
        result = subprocess.run(
            [sys.executable, str(ROOT / "common/legacy_v14_4/composite_font.py"), "--cjk", str(self.cjk),
             "--latin", str(self.latin), "--digit", str(self.latin), "--output", str(output)],
            env={**self.env, "PYTHONPATH": os.pathsep.join([str(ROOT / "common/legacy_v14_4"), HOST_SITE])},
            capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        return output

    def populate(self, composite: Path) -> None:
        """Same file set as font_mix_engine.sh populate_hyperos_payload."""
        engine = (ROOT / "common/legacy_v14_4/font_mix_engine.sh").read_text(encoding="utf-8")
        body = engine[engine.index("populate_hyperos_payload() ("):]
        body = body[:body.index("\n)\n")]
        names = re.findall(r"[A-Za-z0-9_-]+\.(?:ttf|otf)", body.split("verify_core_files")[0])
        fonts = self.stage / "system/fonts"
        store = fonts / ".luoshu-font-store"
        store.mkdir(parents=True)
        anchor = store / "mix-composite.font"
        anchor.write_bytes(composite.read_bytes())
        self.assertIn("MiSansLatinVF.ttf", names)
        for name in dict.fromkeys(names):
            os.link(anchor, fonts / name)

    def test_composite_latin_and_digits_reach_hyperos_latin_slots(self):
        self.populate(self.composite())
        result = subprocess.run([sys.executable, str(ROOT / "common/hyperos_metrics_batch.py"),
                                 str(self.module), str(self.stage)], input="\n".join(self.names),
                                env=self.env, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["fallbackSlots"], 0)
        report = {row["slot"]: row for row in json.loads(
            (self.stage / ".luoshu-metrics-report.json").read_text())["slots"]}
        for logical in ("/system/fonts/MiSansLatinVF.ttf", "/product/fonts/MiSansLatinVF.ttf",
                        "/system/fonts/Roboto-Regular.ttf", "/system/fonts/RobotoStatic-Regular.ttf",
                        "/system/fonts/DroidSans.ttf", "/system/fonts/MiSansVF.ttf",
                        "/product/fonts/MiSansVF.ttf"):
            path = self.stage / logical.lstrip("/")
            with self.subTest(slot=logical):
                self.assertEqual(report[logical]["metricsSource"], "stock")
                # Latin letters and digits come from the chosen Latin/digit font,
                # never the CJK base (1 contour) or the stock slot (3 contours).
                for char in "AHx0179":
                    self.assertEqual(contours(path, char), 2, char)
                if "Latin" in logical or "Roboto" in logical or "Droid" in logical:
                    self.assertIsNone(contours(path, "中"))
                    self.assertEqual(report[logical]["cjkRoutingSource"], "stock-fallback")
                else:
                    self.assertEqual(contours(path, "中"), 1)

    def test_mix_router_finalize_runs_the_same_hyperos_completion(self):
        router = (ROOT / "common/legacy_v14_4/mix_router.sh").read_text(encoding="utf-8")
        helper = router[router.index("complete_hyperos_stage() {"):]
        helper = helper[:helper.index("\n}\n")]
        self.assertIn('"$REALMOD/common/hyperos_stage_complete.sh"', helper)
        commit = router[router.index("commit_mix_stage_if_needed() {"):]
        self.assertIn("complete_hyperos_stage || return 1", commit[:commit.index("\n}\n")])
        stage = (ROOT / "common/hyperos_stage_complete.sh").read_text(encoding="utf-8")
        self.assertIn("hyperos_metrics_batch.py", stage)
        self.assertIn("hyperos_full_coverage.sh", stage)


if __name__ == "__main__":
    unittest.main()
