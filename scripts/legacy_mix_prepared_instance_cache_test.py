#!/usr/bin/env python3
"""Fixed-weight legacy mix (v142) prepare/wait regressions.

A device report showed one composite switch spending ~86 s re-instancing the
same variable sources before every composite build, and the outer worker
polling a Python identity probe at 10 Hz while the commit monitor ran. These
tests run the real shell functions with real variable fonts and the real
font_instance.py generator (through a counting wrapper).
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

import fontTools
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "common/legacy_v14_4"
ENGINE = LEGACY / "v142_weighted_mix.sh"
HOST_SITE = str(Path(fontTools.__file__).resolve().parent.parent)


def variable_font(path: Path, top: int = 700, points=None) -> None:
    points = sorted(points or (set(range(32, 127)) | set(map(ord, "中文字体系统默认洛书汉字国一的。"))))
    cmap = {cp: f"u{cp:X}" for cp in points}
    order = [".notdef", *cmap.values()]
    glyphs = {}
    for name in order:
        pen = TTGlyphPen(None)
        pen.moveTo((0, 0)); pen.lineTo((500, 0))
        pen.lineTo((500, top)); pen.lineTo((0, top)); pen.closePath()
        glyphs[name] = pen.glyph()
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(order); builder.setupCharacterMap(cmap)
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (600, 0) for name in order})
    builder.setupHorizontalHeader(ascent=900, descent=-200)
    builder.setupOS2(sTypoAscender=900, sTypoDescender=-200, usWinAscent=900, usWinDescent=200)
    builder.setupNameTable({"familyName": path.stem, "styleName": "Regular"})
    builder.setupPost(); builder.setupMaxp()
    builder.setupFvar([("wght", 100, 400, 900, "Weight")], [])
    builder.setupGvar({name: [] for name in order})
    builder.font["head"].created = builder.font["head"].modified = 3_400_000_000
    builder.save(path)


def extract(names: list[str]) -> str:
    """Copy exact top-level shell function bodies from the production engine."""
    lines = ENGINE.read_text(encoding="utf-8").splitlines()
    out = []
    for name in names:
        start = next(i for i, line in enumerate(lines) if line.startswith(f"{name}() "))
        end = next(i for i in range(start, len(lines)) if lines[i] == "}")
        out.extend(lines[start:end + 1])
    return "\n".join(out) + "\n"


class PreparedInstanceCache(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luoshu-v142-prepare-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / "module"
        self.public = self.root / "public/fonts"
        self.public.mkdir(parents=True)
        (self.module / "common").mkdir(parents=True)
        (self.module / "logs").mkdir()
        shutil.copy(LEGACY / "font_instance.py", self.module / "common/font_instance.py")
        self.calls = self.root / "instance-calls"
        self.calls.write_text("")
        wrapper = self.root / "luoshu-python"
        wrapper.write_text(
            "#!/bin/sh\n"
            f"printf 'x\\n' >> '{self.calls}'\n"
            "unset PYTHONHOME LD_LIBRARY_PATH\n"
            f"PYTHONPATH='{HOST_SITE}' exec '{sys.executable}' \"$@\"\n")
        wrapper.chmod(0o755)
        self.wrapper = wrapper
        variable_font(self.public / "CJKFixture-VF.ttf", 700)
        variable_font(self.public / "LatinFixture-VF.ttf", 650, set(range(32, 127)) | set(range(0xA0, 0x250)))
        self.harness = self.root / "harness.sh"
        self.harness.write_text(
            "set +e\n"
            f"MODULE_DIR='{self.module}'\n"
            f"LUOSHU_PUBLIC_DIR='{self.public.parent}'\n"
            f". '{LEGACY / 'util_functions.sh'}'\n"
            f". '{LEGACY / 'font_check.sh'}'\n"
            f"MODDIR='{self.module}'\n"
            f"USER_FONTS_DIR='{self.public}'\n"
            f"CACHE_ROOT='{self.module}/cache/axes-mix'\n"
            "PREPARED_CACHE=\"$CACHE_ROOT/prepared-v1\"\n"
            f"INSTANCE_PY='{self.module}/common/font_instance.py'\n"
            f"PYROOT='{self.root}/pyroot'\n"
            f"PYBIN='{wrapper}'\n"
            f"LOG_FILE='{self.module}/logs/fontswitch.log'\n"
            + extract(["axis_value", "safe_weight", "role_weight", "find_best_source", "run_instance",
                       "prepared_hash_file", "prepared_hash_text", "prune_prepared_cache",
                       "prepare_instance_cached", "prepare_slot"]))

    def request(self, name: str) -> Path:
        out = self.root / name
        script = (f". '{self.harness}'\n"
                  f"prepare_slot cjk CJKFixture-VF wght=400 '{out}' LuoShuMixCJK || exit 11\n"
                  f"prepare_slot latin LatinFixture-VF wght=400 '{out}' LuoShuMixLatin || exit 12\n"
                  f"prepare_slot digit LatinFixture-VF wght=400 '{out}' LuoShuMixDigit || exit 13\n")
        result = subprocess.run(["sh", "-c", script], capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return out / "fonts"

    def instance_calls(self) -> int:
        return len(self.calls.read_text().splitlines())

    @staticmethod
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_same_request_shares_identical_role_instances_and_next_request_reuses_all(self):
        first = self.request("request-1")
        # Latin and digit select the same family and axes: one generator run.
        self.assertEqual(self.instance_calls(), 2)
        for name in ("LuoShuMixCJK", "LuoShuMixLatin", "LuoShuMixDigit"):
            with TTFont(first / f"{name}-Regular.ttf") as font:
                self.assertNotIn("fvar", font)
                self.assertEqual(font["OS/2"].usWeightClass, 400)
        self.assertEqual(self.digest(first / "LuoShuMixLatin-Regular.ttf"),
                         self.digest(first / "LuoShuMixDigit-Regular.ttf"))
        second = self.request("request-2")
        self.assertEqual(self.instance_calls(), 2, "a repeated switch must not re-instance")
        for name in ("LuoShuMixCJK", "LuoShuMixLatin", "LuoShuMixDigit"):
            # Byte-identical inputs keep the downstream composite cache key stable.
            self.assertEqual(self.digest(first / f"{name}-Regular.ttf"),
                             self.digest(second / f"{name}-Regular.ttf"))
        self.assertIn("[MIX-PREPARE] reused instance",
                      (self.module / "logs/fontswitch.log").read_text())

    def test_axes_source_and_generator_changes_are_new_identities(self):
        self.request("request-1")
        script = (f". '{self.harness}'\n"
                  f"prepare_slot cjk CJKFixture-VF wght=700 '{self.root}/r2' LuoShuMixCJK || exit 11\n")
        subprocess.run(["sh", "-c", script], check=True, timeout=120)
        self.assertEqual(self.instance_calls(), 3)
        variable_font(self.public / "CJKFixture-VF.ttf", 720)
        self.request("request-3")
        self.assertEqual(self.instance_calls(), 4)
        with (self.module / "common/font_instance.py").open("a") as stream:
            stream.write("\n# generator revision\n")
        self.request("request-4")
        self.assertEqual(self.instance_calls(), 6)

    def test_damaged_cache_entry_is_rebuilt_not_trusted(self):
        self.request("request-1")
        entries = sorted((self.module / "cache/axes-mix/prepared-v1").glob("*.font"))
        self.assertEqual(len(entries), 2)
        for entry in entries:
            # Break the inode shared with nothing else: replace content in place.
            data = bytearray(entry.read_bytes()); data[-8:] = b"\0" * 8
            entry.unlink(); entry.write_bytes(bytes(data))
        out = self.request("request-2")
        self.assertEqual(self.instance_calls(), 4)
        for entry in entries:
            self.assertEqual(self.digest(entry), entry.with_name(entry.name + ".sha256").read_text().strip())
        with TTFont(out / "LuoShuMixCJK-Regular.ttf") as font:
            self.assertNotIn("fvar", font)

    def test_cache_is_bounded(self):
        for weight in range(100, 1000, 100):
            script = (f". '{self.harness}'\n"
                      f"prepare_slot cjk CJKFixture-VF wght={weight} '{self.root}/w{weight}' LuoShuMixCJK || exit 11\n")
            subprocess.run(["sh", "-c", script], check=True, timeout=120)
        self.assertLessEqual(len(list((self.module / "cache/axes-mix/prepared-v1").glob("*.font"))), 6)
        self.assertEqual(list((self.module / "cache/axes-mix/prepared-v1").glob("*.tmp.*")), [])


class WaitChildCleanup(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luoshu-v142-wait-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tasks = self.root / "tasks"
        self.tasks.mkdir()
        self.probes = self.root / "probes"
        self.probes.write_text("")
        runner = self.root / "scope.sh"
        runner.write_text("#!/bin/sh\nexit 0\n")
        self.harness = self.root / "harness.sh"
        # The stubbed supervisor probe counts calls; liveness follows the pid file.
        self.harness.write_text(
            "set +e\n"
            f"LUOSHU_TASKS_DIR='{self.tasks}'\n"
            f"luoshu_scope_runner() {{ printf '%s\\n' '{runner}'; }}\n"
            "luoshu_pid_value() { sed -n '1{s/[^0-9].*$//;p;}' \"$1\" 2>/dev/null; }\n"
            "luoshu_task_pid_alive() {\n"
            f"    printf 'x\\n' >> '{self.probes}'\n"
            "    _p=$(luoshu_pid_value \"$1\"); [ -n \"$_p\" ] && kill -0 \"$_p\" 2>/dev/null\n"
            "}\n" + extract(["_wcc_pid_running", "wait_child_cleanup"]))

    def run_wait(self, monitor_seconds: float, timeout: str | None = None) -> tuple[int, float]:
        monitor = subprocess.Popen(["sleep", str(monitor_seconds)])
        self.addCleanup(monitor.kill)
        (self.tasks / "mix-monitor-child.pid").write_text(f"{monitor.pid}\n")
        env = dict(os.environ)
        if timeout is not None:
            env["LUOSHU_MIX_CHILD_CLEANUP_TIMEOUT"] = timeout
        started = time.monotonic()
        # Reap the sleeper as soon as it exits so kill -0 reports it gone.
        script = f". '{self.harness}'\nwait_child_cleanup child\n"
        proc = subprocess.Popen(["sh", "-c", script], env=env)
        while proc.poll() is None:
            monitor.poll()
            time.sleep(0.05)
        return proc.returncode, time.monotonic() - started

    def test_waits_for_monitor_without_ten_hertz_identity_probes(self):
        code, elapsed = self.run_wait(3.0)
        self.assertEqual(code, 0)
        self.assertGreaterEqual(elapsed, 2.9)
        self.assertLess(elapsed, 6.0)
        # Old loop: two supervisor probes every 0.1 s (~60 for 3 s).
        probes = len(self.probes.read_text().splitlines())
        self.assertLessEqual(probes, 12, probes)

    def test_wall_clock_bound_still_reports_unconfirmed_cleanup(self):
        code, elapsed = self.run_wait(30.0, timeout="2")
        self.assertEqual(code, 124)
        self.assertLess(elapsed, 6.0)


if __name__ == "__main__":
    unittest.main()
