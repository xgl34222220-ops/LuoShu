#!/usr/bin/env python3
"""Exercise same-build stock inventory migrations with real font files."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from fontTools.ttLib import TTCollection, TTFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))
import font_inventory as inventory  # noqa: E402
import font_inventory_scan as scanner  # noqa: E402
from stock_metric_contract_test import make_font  # noqa: E402


class ScannerRefreshTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="luoshu-scan-refresh-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fonts = self.root / "state/lower/system-fonts"
        self.etc = self.root / "state/lower/system-etc"
        self.fonts.mkdir(parents=True)
        self.etc.mkdir(parents=True)
        self.args = scanner.build_parser().parse_args([
            "--scan", "--build-key", "same-build", "--output", str(self.root / "inventory.json"),
        ])
        for specs in (scanner.PRIMARY_FONT_SPECS, scanner.PRIMARY_ETC_SPECS,
                      scanner.AUX_FONT_SPECS, scanner.AUX_ETC_SPECS):
            for spec in specs:
                setattr(self.args, spec[2], self.root / "absent" / spec[2])
        self.args.system_fonts, self.args.system_etc = self.fonts, self.etc
        self.environment = mock.patch.dict(os.environ, {
            "LUOSHU_SELF_MOUNT_STATE_ROOT": str(self.root / "state"),
            "LUOSHU_STOCK_VIEW_VERIFIED": "",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.mirrors = mock.patch.object(inventory, "MIRROR_PREFIXES", ())
        self.mirrors.start()
        self.addCleanup(self.mirrors.stop)

    def scan(self) -> tuple[int, dict, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = scanner.scan(self.args)
        return rc, json.loads(self.args.output.read_text()), stderr.getvalue()

    def seed_coloros(self) -> str:
        make_font(self.fonts / "SysSans-Hans-Regular.ttf", ascent=1100, descent=-300)
        known = "OemReading-Regular.ttf"  # Deliberately outside filename heuristics.
        make_font(self.fonts / known, ascent=900, descent=-200)
        (self.etc / "fonts.xml").write_text(
            '<familyset><family name="sans-serif"><font>SysSans-Hans-Regular.ttf</font></family>'
            f'<family name="oplus-sans"><font>{known}</font></family></familyset>')
        rc, previous, error = self.scan()
        self.assertEqual(rc, 0, error)
        self.assertEqual(previous["romKind"], "generic")
        previous.pop("metricsRevision")
        for entry in (*previous["slots"].values(), previous["mainSlot"]):
            entry["metrics"].pop("head")
        self.args.output.write_text(json.dumps(previous))
        # Discovery loses an OEM family while its known stock file remains.
        (self.etc / "fonts.xml").write_text(
            '<familyset><family name="sans-serif"><font>SysSans-Hans-Regular.ttf</font>'
            '</family></familyset>')
        return known

    def test_refresh_reads_known_coloros_slot_when_xml_discovery_omits_it(self) -> None:
        known = self.seed_coloros()
        make_font(self.fonts / known, ascent=970, descent=-220)
        source = (self.fonts / known).read_bytes()
        rc, refreshed, error = self.scan()
        self.assertEqual(rc, 0, error)
        restored = refreshed["slots"]["/system/fonts/" + known]
        self.assertEqual(restored["metrics"]["hhea"]["ascent"], 970)
        self.assertEqual(restored["metrics"]["hhea"]["descent"], -220)
        self.assertIn("head", restored["metrics"])
        self.assertTrue(scanner._can_reuse(refreshed, "same-build"))
        self.assertIn(restored["path"], refreshed["families"]["oplus-sans"])
        self.assertEqual((self.fonts / known).read_bytes(), source)

    def test_missing_known_slot_still_retains_previous_inventory(self) -> None:
        known = self.seed_coloros()
        (self.fonts / known).unlink()
        original = self.args.output.read_bytes()
        rc, _result, error = self.scan()
        self.assertEqual(rc, 2)
        self.assertIn(known, error)
        self.assertEqual(self.args.output.read_bytes(), original)

    def test_refresh_preserves_collection_face_selection(self) -> None:
        known = self.seed_coloros()
        first, second = self.root / "first.ttf", self.root / "second.ttf"
        make_font(first, ascent=800, descent=-150)
        make_font(second, ascent=1250, descent=-350)
        with TTFont(first) as face0, TTFont(second) as face1:
            collection = TTCollection()
            collection.fonts = [face0, face1]
            collection.save(self.fonts / known)
        previous = json.loads(self.args.output.read_text())
        entry = previous["slots"]["/system/fonts/" + known]
        entry.update(format="TTC", faceIndex=1, weight=650)
        entry.pop("faces", None)  # Legacy inventories did not retain the collection face list.
        self.args.output.write_text(json.dumps(previous))
        rc, refreshed, error = self.scan()
        self.assertEqual(rc, 0, error)
        restored = refreshed["slots"]["/system/fonts/" + known]
        self.assertEqual(restored["metrics"]["hhea"]["ascent"], 1250)
        self.assertEqual(restored["metrics"]["hhea"]["descent"], -350)
        self.assertEqual(restored["faceIndex"], 1)
        self.assertEqual(restored["weight"], 650)

    def test_corrupt_known_slot_still_retains_previous_inventory(self) -> None:
        known = self.seed_coloros()
        (self.fonts / known).write_bytes(b"broken font")
        original = self.args.output.read_bytes()
        rc, _result, error = self.scan()
        self.assertEqual(rc, 2)
        self.assertIn(known, error)
        self.assertEqual(self.args.output.read_bytes(), original)

    def test_known_slot_cannot_refresh_from_a_theme_symlink(self) -> None:
        known = self.seed_coloros()
        theme = self.root / "theme.ttf"
        make_font(theme, ascent=1600, descent=-500)
        (self.fonts / known).unlink()
        (self.fonts / known).symlink_to(theme)
        original = self.args.output.read_bytes()
        with mock.patch.object(inventory, "_read_metrics", wraps=inventory._read_metrics) as reader:
            rc, _result, _error = self.scan()
        self.assertEqual(rc, 2)
        self.assertNotIn(theme, [Path(call.args[0]) for call in reader.call_args_list])
        self.assertEqual(self.args.output.read_bytes(), original)

    def test_policy_upgrade_measures_unknown_script_name_instead_of_brand_filtering(self) -> None:
        self.seed_coloros()
        path = self.fonts / "NotoSansAdlam-Regular.ttf"
        make_font(path)
        with TTFont(path) as font:
            for table in font["cmap"].tables:
                if table.isUnicode():
                    table.cmap = {point: "zero" for point in range(0x621, 0x64b)}
            font.save(path)
        rc, refreshed, error = self.scan()
        self.assertEqual(rc, 0, error)
        key = "/system/fonts/" + path.name
        self.assertIn(key, refreshed["slots"])
        self.assertIn("Arab", refreshed["slots"][key]["requiresScripts"])
        self.assertTrue(scanner._can_reuse(refreshed, "same-build"))


if __name__ == "__main__":
    unittest.main()
