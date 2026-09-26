#!/usr/bin/env python3
"""Exercise coverage against real pending trees and batch metric contracts.

All files and commands stay in temporary directories; no Android or mount access.
"""
from __future__ import annotations

import contextlib
import io
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
from unittest import mock

ROOT = Path(os.environ.get("LUOSHU_TEST_SOURCE_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / "common"))
import font_metrics_normalize as metrics
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont


class CoverageBridgeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luoshu-coverage-switch-")
        self.addCleanup(self.temp.cleanup)
        self.module = Path(self.temp.name)
        self.config = self.module / "config"
        self.config.mkdir()
        (self.module / "logs").mkdir()
        launcher = self.module / "common/python/bin/luoshu-python"
        launcher.parent.mkdir(parents=True)
        launcher.write_text("#!/bin/sh\nunset PYTHONHOME PYTHONPATH\nexec " +
                            shlex.quote(sys.executable) + ' "$@"\n')
        launcher.chmod(0o755)
        shutil.copyfile(ROOT / "common/device_font_slot_trace.py",
                        self.module / "common/device_font_slot_trace.py")
        self.live = self.module / ".luoshu-payload"
        self.nxt = self.module / ".luoshu-payload-next"
        for tree in (self.live, self.nxt):
            (tree / "system/fonts").mkdir(parents=True)
            (tree / "system/fonts/A.ttf").write_text("font-A")
        (self.nxt / "system/fonts/B.ttf").write_text("font-B")
        slots = {f"/system/fonts/{name}.ttf": {
            "slotName": f"{name}.ttf", "partition": "system", "format": "TTF",
            "weight": 400, "style": "normal", "families": ["sans-serif"],
        } for name in ("A", "B")}
        (self.config / "device_font_inventory.json").write_text(json.dumps({
            "schema": "device-font-inventory-v1", "slots": slots,
        }))
        (self.config / "active_font.conf").write_text("Selected\n")
        (self.config / "font-payload-next.conf").write_text("state=prepared\nfont=Selected\n")
        (self.config / "device-font-load-verification.conf").write_text("state=verified\n")
        (self.config / "self-mount.conf").write_text(
            "state=failed\nbackend=self-overlay-bind\nfailed=system/fonts-bind-incomplete\n")
        # Reading coverage must never enter this obsolete cache path when a
        # physical tree already exists, even with a stale engine cacheId.
        (self.module / "common/device_font_cache.sh").write_text(
            '#!/bin/sh\ntouch "$MODDIR/unexpected-cache-lookup"\nexit 1\n')
        (self.config / "device-font-engine.conf").write_text("cacheId=obsolete\n")

    def bridge(self, command):
        result = subprocess.run(["sh", str(ROOT / "common/app_bridge.sh"), command],
                                env={**os.environ, "MODDIR": str(self.module)},
                                text=True, capture_output=True, timeout=10)
        self.assertTrue(result.stdout.strip(), result.stderr)
        return json.loads(result.stdout.strip().splitlines()[-1])

    def test_pending_tree_ignores_old_missing_files_and_mount_failure(self):
        result = self.bridge("coverage")
        self.assertEqual(result["traceSource"], "physical-prepared")
        self.assertEqual(result["verificationState"], "pending-reboot")
        self.assertEqual(result["summary"]["pending"], 2)
        self.assertEqual(result["summary"]["issues"], 0)
        self.assertEqual(result["summary"]["remediable"], 0)
        self.assertFalse((self.module / "unexpected-cache-lookup").exists())

    def test_first_apply_can_show_prepared_tree_without_live_payload(self):
        shutil.rmtree(self.live)
        self.assertEqual(self.bridge("coverage")["summary"]["pending"], 2)

    def test_pending_apply_cannot_enqueue_duplicate_repair(self):
        result = self.bridge("coverage_reapply")
        self.assertEqual(result["status"], "error")
        self.assertIn("先完整重启", result["message"])
        self.assertFalse((self.config / "font-payload-rebuild-pending.conf").exists())
        self.assertFalse((self.config / "font-coverage-remediation-paths.txt").exists())
        self.assertEqual((self.nxt / "system/fonts/B.ttf").read_text(), "font-B")

    def test_foreign_pending_font_is_never_shown_as_selected_font(self):
        (self.config / "font-payload-next.conf").write_text("state=prepared\nfont=Other\n")
        result = self.bridge("coverage")
        self.assertEqual(result["traceSource"], "physical-safe")
        self.assertEqual(result["summary"]["mappingMissing"], 1)

    def test_after_boot_live_tree_is_verified_instead_of_pending(self):
        shutil.rmtree(self.live)
        self.nxt.rename(self.live)
        (self.config / "font-payload-next.conf").unlink()
        (self.config / "self-mount.conf").write_text(
            "state=mounted\nbackend=self-overlay-bind\nmounted=system/fonts:overlay\n")
        result = self.bridge("coverage")
        self.assertEqual(result["traceSource"], "physical-safe")
        self.assertEqual(result["summary"]["replaced"], 2)
        self.assertEqual(result["summary"]["remediable"], 0)


class NestedMountManifestTest(unittest.TestCase):
    def test_scanner_paths_are_accepted_and_unsafe_paths_rejected(self):
        text = (ROOT / "common/mount_compat_base.sh").read_text()
        functions = "\n".join(re.findall(
            r"^[A-Za-z_][A-Za-z_0-9]*\(\) [({]\n.*?^[})]$", text, flags=re.M | re.S))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            good = "product|vivo/fonts|product-nested-0123456789abcdef"
            (root / "config/device_font_roots.conf").write_text("\n".join([
                good, "product|../outside|product-nested-0123456789abcdef",
                "data|vivo/fonts|data-nested-0123456789abcdef",
                "product|vivo/fonts|system-nested-0123456789abcdef",
                "product|vivo/fonts|product-nested-not-a-digest", "",
            ]))
            result = subprocess.run(["sh", "-c", functions + "\nluoshu_nested_font_roots"],
                                    env={**os.environ, "LUOSHU_MOUNT_MODDIR": str(root)},
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), [good])


class MetricsBatchSnapshotTest(unittest.TestCase):
    def test_many_slots_read_stock_contract_once_and_reuse_equivalent_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.ttf"
            builder = FontBuilder(1000, isTTF=True)
            names = [".notdef", "H", "x", "zero"]
            builder.setupGlyphOrder(names)
            builder.setupCharacterMap({ord("H"): "H", ord("x"): "x", ord("0"): "zero"})
            glyphs = {}
            for name in names:
                pen = TTGlyphPen(None)
                pen.moveTo((30, 0)); pen.lineTo((600, 0))
                pen.lineTo((600, 700)); pen.lineTo((30, 700)); pen.closePath()
                glyphs[name] = pen.glyph()
            builder.setupGlyf(glyphs)
            builder.setupHorizontalMetrics({name: (700, 30) for name in names})
            builder.setupHorizontalHeader(ascent=900, descent=-200)
            builder.setupOS2(sTypoAscender=900, sTypoDescender=-200,
                             usWinAscent=900, usWinDescent=200)
            builder.setupNameTable({"familyName": "Batch fixture", "styleName": "Regular",
                                    "fullName": "Batch fixture Regular",
                                    "psName": "BatchFixture-Regular",
                                    "copyright": "Generated regression fixture. " * 100})
            builder.setupPost(); builder.setupMaxp(); builder.save(source)
            original = source.read_bytes()
            slots, rows = {}, []
            for index in range(60):
                logical = f"/system/fonts/A{index}.ttf"
                slots[logical] = {"slotName": f"A{index}.ttf", "path": logical, "metrics": {
                    "upem": 1000, "hhea": {"ascent": 850 + 50 * (index % 2), "descent": -200},
                }}
                rows.append(f"{source}\t{root / f'out{index}.ttf'}\t-\t{logical}\n")
            inventory = root / "inventory.json"
            inventory.write_text(json.dumps({"schema": "device-font-inventory-v1",
                "state": "ready", "inventoryRevision": 1, "buildKey": "fixture", "slots": slots}))
            manifest = root / "batch.tsv"
            manifest.write_text("".join(rows))
            with mock.patch.object(metrics, "_device_build_key", return_value="fixture") as identity:
                with mock.patch.object(metrics, "normalize_path", wraps=metrics.normalize_path) as normalize:
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(metrics.run_batch(manifest, inventory), 0)
                    self.assertEqual(normalize.call_count, 2)
                self.assertEqual(identity.call_count, 1)
            self.assertEqual(source.read_bytes(), original)
            for index in range(60):
                with TTFont(root / f"out{index}.ttf") as font:
                    self.assertEqual(font["hhea"].ascent, 850 + 50 * (index % 2))
                    self.assertEqual(font["hhea"].descent, -200)
                    self.assertEqual(font["OS/2"].sTypoAscender, font["hhea"].ascent)
            self.assertEqual((root / "out0.ttf").stat().st_ino, (root / "out2.ttf").stat().st_ino)


if __name__ == "__main__":
    unittest.main(verbosity=2)
