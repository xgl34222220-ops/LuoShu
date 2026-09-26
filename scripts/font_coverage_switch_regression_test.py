#!/usr/bin/env python3
"""Exercise coverage against real pending trees and batch metric contracts.

All files and commands stay in temporary directories; no Android or mount access.
"""
from __future__ import annotations

import contextlib
import io
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
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
        shutil.copyfile(ROOT / "common/font_switch_lock.sh",
                        self.module / "common/font_switch_lock.sh")
        shutil.copyfile(ROOT / "common/physical_font_load_verify.py",
                        self.module / "common/physical_font_load_verify.py")
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

    def bridge(self, command, *arguments):
        result = subprocess.run(["sh", str(ROOT / "common/app_bridge.sh"), command, *arguments],
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

    def test_duplicate_repair_cannot_remove_starting_workers_plan(self):
        (self.config / "font-payload-next.conf").unlink()
        (self.config / "self-mount.conf").write_text(
            "state=mounted\nbackend=self-overlay-bind\nmounted=system/fonts:overlay\n")
        (self.module / "common/font_switch_task.sh").write_text('''#!/bin/sh
case "$1" in
  reconcile) exit 0 ;;
  start)
    if ! mkdir "$MODDIR/worker-started" 2>/dev/null; then
      printf '{"status":"error","message":"busy"}\\n'; exit 1
    fi
    sleep 1
    test -s "$LUOSHU_COVERAGE_PLAN" || exit 2
    printf 'state=queued\\n' > "$MODDIR/config/switch_task.conf"
    printf '{"status":"ok"}\\n'
    ;;
esac
''')
        first = subprocess.Popen(["sh", str(ROOT / "common/app_bridge.sh"), "coverage_reapply"],
                                 env={**os.environ, "MODDIR": str(self.module)},
                                 text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 5
            while not (self.module / "worker-started").exists():
                self.assertLess(time.monotonic(), deadline)
                time.sleep(.01)
            second = self.bridge("coverage_reapply")
            output, errors = first.communicate(timeout=8)
            self.assertEqual(first.returncode, 0, output + errors)
            self.assertEqual(json.loads(output)["status"], "ok")
            self.assertEqual(second["status"], "error")
            self.assertIn("重复点击", second["message"])
            self.assertEqual((self.config / "font-coverage-remediation-paths.txt").read_text(),
                             "/system/fonts/B.ttf\n")
            self.assertFalse((self.config / "font-payload-rebuild-pending.conf").exists())
            self.assertFalse((self.module / ".font_coverage_start.lock").exists())
        finally:
            if first.poll() is None:
                first.kill()
            first.communicate()

    def test_mix_repair_uses_pinned_payload_even_without_recipe_or_library(self):
        (self.config / "font-payload-next.conf").unlink()
        (self.config / "active_font.conf").write_text("mix\n")
        (self.config / "self-mount.conf").write_text(
            "state=mounted\nbackend=self-overlay-bind\nmounted=system/fonts:overlay\n")
        (self.module / "common/font_mix_controller.sh").write_text('''#!/bin/sh
case "$1" in reconcile) exit 0 ;; esac
touch "$MODDIR/unexpected-mix-rebuild"
printf '{"status":"error","message":"must not recompose"}\\n'
exit 1
''')
        (self.module / "common/font_switch_task.sh").write_text('''#!/bin/sh
case "$1" in
reconcile) exit 0 ;;
start)
    printf '%s\\n' "$2" "$LUOSHU_FORCE_REBUILD" "$LUOSHU_COVERAGE_REMEDIATE" "$LUOSHU_COVERAGE_PLAN" > "$MODDIR/repair-args"
    printf '{"status":"ok","data":{"task":"repair-switch","font":"mix"}}\\n'
    ;;
esac
''')
        result = self.bridge("coverage_reapply")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["task"], "repair-switch")
        arguments = (self.module / "repair-args").read_text().splitlines()
        self.assertEqual(arguments[:3], ["mix", "1", "1"])
        self.assertEqual(Path(arguments[3]).read_text(), "/system/fonts/B.ttf\n")
        self.assertFalse((self.module / "unexpected-mix-rebuild").exists())
        self.assertFalse((self.config / "axes_mix.conf").exists())
        self.assertFalse((self.config / "font_mix.conf").exists())
        self.assertEqual((self.live / "system/fonts/A.ttf").read_text(), "font-A")

    def test_current_font_upgrade_requires_full_apply_without_enqueuing_repair(self):
        (self.config / "font-payload-next.conf").unlink()
        marker = self.config / "font-payload-rebuild-pending.conf"
        saved = "state=awaiting-explicit-apply\nfont=Selected\nreason=font-builder-changed\ntime=12345\n"
        marker.write_text(saved)
        (self.module / "common/font_switch_task.sh").write_text(
            '#!/bin/sh\n[ "$1" = reconcile ] && exit 0\ntouch "$MODDIR/unexpected-repair-start"\n')
        result = self.bridge("coverage_reapply")
        self.assertEqual(result['status'], 'error')
        self.assertIn('完整重新应用', result['message'])
        self.assertFalse((self.module / "unexpected-repair-start").exists())
        self.assertFalse((self.config / "font-coverage-remediation-paths.txt").exists())
        self.assertEqual(marker.read_text(), saved)

    def test_repair_enqueue_preserves_upgrade_marker_for_different_font(self):
        (self.config / "font-payload-next.conf").unlink()
        marker = self.config / "font-payload-rebuild-pending.conf"
        saved = "state=awaiting-explicit-apply\nfont=Other\nreason=font-builder-changed\ntime=12345\n"
        for fails in (False, True):
            marker.write_text(saved)
            response = json.dumps({"status": "error" if fails else "ok", "message": "fixture"})
            script = '#!/bin/sh\n[ "$1" = reconcile ] && exit 0\ntouch "$MODDIR/repair-started"\n'
            script += "printf '%s\\n' " + shlex.quote(response) + "\n"
            script += "exit " + ("1" if fails else "0") + "\n"
            (self.module / "common/font_switch_task.sh").write_text(script)
            result = self.bridge("coverage_reapply")
            self.assertEqual(result['status'], 'error' if fails else 'ok')
            self.assertTrue((self.module / "repair-started").exists())
            (self.module / "repair-started").unlink()
            self.assertEqual(marker.read_text(), saved)

    def test_old_app_mix_status_reads_only_matching_switch_repair(self):
        (self.config / "switch_task.conf").write_text(
            "task=repair-id\nfont=mix\ncoverageRemediate=true\nstate=running\npercent=63\n")
        (self.module / "common/font_mix_controller.sh").write_text('''#!/bin/sh
touch "$MODDIR/mix-status-called"
printf '{"status":"error","message":"composite status"}\\n'
''')
        (self.module / "common/font_switch_task.sh").write_text('''#!/bin/sh
[ "$1" = status ] && [ "$2" = repair-id ] || exit 1
printf '{"status":"ok","data":{"task":"repair-id","state":"running","percent":63,"message":"repair progress"}}\\n'
''')
        result = self.bridge("mix_status", "repair-id")
        self.assertEqual(result["data"]["state"], "running")
        self.assertEqual(result["data"]["percent"], 63)
        self.assertFalse((self.module / "mix-status-called").exists())
        # Similar task prefixes, non-mix fonts and non-repair switches are never
        # adopted by the compatibility route.
        self.assertEqual(self.bridge("mix_status", "repair")['status'], 'error')
        self.assertTrue((self.module / "mix-status-called").exists())
        for font, repair in (("Demo", "true"), ("mix", "false")):
            (self.module / "mix-status-called").unlink()
            (self.config / "switch_task.conf").write_text(
                f"task=repair-id\nfont={font}\ncoverageRemediate={repair}\nstate=running\n")
            self.assertEqual(self.bridge("mix_status", "repair-id")['status'], 'error')
            self.assertTrue((self.module / "mix-status-called").exists())

    def test_explicit_mix_start_keeps_axes_and_modes_through_real_bridge(self):
        runtime = self.module / "runtime/common"
        runtime.mkdir(parents=True)
        (runtime / "font_role_check.sh").write_text("exit 0\n")
        (runtime / "v142_weighted_mix.sh").write_text("exit 99\n")
        (runtime / "mix_weight_mode.sh").write_text("infer_mix_weight_mode() { echo auto; }\n")
        (runtime / "v143_auto_multiweight_mix.sh").write_text('''#!/bin/sh
printf '%s\\n' "$@" > "$MODDIR/request-args"
printf '{"status":"ok","data":{"task":"explicit-mode"}}\\n'
''')
        engine = shlex.quote(str(ROOT / "common/legacy_v14_4/v14_mix.sh"))
        (self.module / "common/font_mix_controller.sh").write_text(
            'MODDIR="$MODDIR/runtime" sh ' + engine + ' "$@"\n')
        arguments = ("CJK", "Latin", "Digit", "wght=400,wdth=90", "wght=550", "wght=400", "fixed", "auto", "fixed")
        result = self.bridge("mix_start", *arguments)
        self.assertEqual(result["status"], "ok")
        self.assertEqual((self.module / "runtime/request-args").read_text().splitlines(),
                         ["start", *arguments])

    def test_after_boot_live_tree_is_verified_instead_of_pending(self):
        shutil.rmtree(self.live)
        self.nxt.rename(self.live)
        (self.config / "font-payload-next.conf").unlink()
        (self.config / "self-mount.conf").write_text(
            "state=mounted\nbackend=self-overlay-bind\nmounted=system/fonts:overlay\n")
        files = {"/" + str(path.relative_to(self.live)): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in self.live.rglob("*.ttf")}
        (self.live / ".luoshu-inventory-output-manifest.json").write_text(json.dumps({
            "schema": "inventory-font-output-v1", "files": files}))
        with mock.patch.dict(os.environ, LUOSHU_VISIBLE_ROOT=str(self.live)):
            checked = subprocess.run([sys.executable, str(self.module / "common/physical_font_load_verify.py"),
                                      "--module", str(self.module), "verify"],
                                     capture_output=True, text=True, timeout=5)
            self.assertEqual(checked.returncode, 0, checked.stderr)
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
