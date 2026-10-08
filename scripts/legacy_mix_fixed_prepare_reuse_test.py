#!/usr/bin/env python3
"""Run the active legacy multiweight worker with real variable-font inputs."""
from __future__ import annotations

import hashlib
import json
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
ENGINE = Path(os.environ.get("LUOSHU_REUSE_TEST_ENGINE", ROOT / "common/legacy_v14_4/v143_auto_multiweight_mix.sh"))
# check.sh supplies pure FontTools via PYTHONPATH when the host interpreter has
# no installed copy. Resolve that already imported package for every real child
# rather than inheriting the Android runtime path set by production run_instance.
HOST_FONTTOOLS_SITE = str(Path(fontTools.__file__).resolve().parent.parent)


def variable_font(path: Path, top: int = 700) -> None:
    points = sorted(set(range(32, 256)) | set(map(ord, "中文字体系统默认洛书汉字国一的。")))
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
    builder.setupOS2(sTypoAscender=900, sTypoDescender=-200,
                     usWinAscent=900, usWinDescent=200)
    builder.setupNameTable({"familyName": "ReuseFixture", "styleName": "Regular"})
    builder.setupPost(); builder.setupMaxp()
    builder.setupFvar([("wght", 100, 400, 900, "Weight")], [])
    builder.setupGvar({name: [] for name in order})
    builder.font["head"].created = builder.font["head"].modified = 3_400_000_000
    builder.save(path)


class LegacyMixPrepareReuse(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luoshu-active-multiweight-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / "module"
        self.public = self.root / "public"
        self.taskroot = self.module / "cache/task-one"
        self.captured = self.root / "captured"
        for directory in (self.module / "common/python/bin", self.module / "config",
                          self.module / "logs", self.public / "fonts", self.taskroot):
            directory.mkdir(parents=True)
        self.script = self.module / "common/v143_auto_multiweight_mix.sh"
        shutil.copyfile(ENGINE, self.script)
        for name in ("font_check.sh", "font_instance.py", "composite_font.py", "composite_layout.py"):
            shutil.copyfile(ROOT / "common/legacy_v14_4" / name, self.module / "common" / name)
        (self.module / "common/util_functions.sh").write_text(
            "detect_font_family() { printf '%s\\n' \"${1%%-*}\"; }\n"
            "detect_font_weight() { printf 'regular\\n'; }\n"
            "is_variable_font() { font_has_table \"$1\" fvar; }\n")
        (self.module / "common/background_task.sh").write_text(
            "luoshu_clear_task_pid() { return 0; }\n")
        self.calls = self.root / "instance-calls.jsonl"
        self.composite_calls = self.root / "composite-calls.txt"
        self.child_errors = self.root / "instance-errors.jsonl"
        wrapper = self.module / "common/python/bin/luoshu-python"
        wrapper.write_text('#!/bin/sh\nunset PYTHONHOME LD_LIBRARY_PATH\n'
                           'PYTHONPATH="$REUSE_HOST_FONTTOOLS_SITE"\nexport PYTHONPATH\n'
                           'exec "$HOST_PYTHON" "$MODDIR/common/host-instance.py" "$@"\n')
        (self.module / "common/host-instance.py").write_text('''import json, os, subprocess, sys, time
from pathlib import Path
if sys.argv[1].endswith('font_instance.py'):
    args = sys.argv[2:]
    values = dict(zip(args[::2], args[1::2]))
    with Path(os.environ['REUSE_CALLS']).open('a') as stream:
        stream.write(json.dumps(values) + '\\n')
    if os.environ.get('REUSE_FAIL') == '1':
        sys.exit(7)
    if os.environ.get('REUSE_HOLD') == '1':
        Path(os.environ['REUSE_HOLD_READY']).write_text(str(os.getpid()))
        time.sleep(30)
    if os.environ.get('REUSE_CHANGE_GENERATOR') == '1':
        with Path(sys.argv[1]).open('a') as stream:
            stream.write('\\n# generator changed during invocation\\n')
for name in ('PYTHONHOME', 'LD_LIBRARY_PATH'):
    os.environ.pop(name, None)
os.environ['PYTHONPATH'] = os.environ['REUSE_HOST_FONTTOOLS_SITE']
# The production shell removes its temporary .err on failure. Retain the real
# Python diagnostic in this isolated fixture before forwarding it unchanged.
result = subprocess.run([sys.executable, *sys.argv[1:]], stderr=subprocess.PIPE, text=True)
if result.returncode:
    with Path(os.environ['REUSE_ERRORS']).open('a') as stream:
        stream.write(json.dumps({'code': result.returncode, 'stderr': result.stderr}, ensure_ascii=False) + '\\n')
sys.stderr.write(result.stderr)
sys.exit(result.returncode)
''')
        wrapper.chmod(0o755)
        (self.module / "common/luoshu_composite.sh").write_text(
            '#!/bin/sh\nprintf "run\\n" >> "$REUSE_COMPOSITE_CALLS"\n'
            '"$HOST_PYTHON" "$MODDIR/common/composite_font.py" "$@" || exit $?\n'
            '[ -z "${REUSE_COMPOSITE_CHANGE:-}" ] || printf "\\n# changed during generation\\n" >> "$REUSE_COMPOSITE_CHANGE"\n'
            'if [ "${REUSE_HOLD_COMPOSITE:-0}" = 1 ]; then\n'
            '    printf "%s\\n" "$$" > "$REUSE_HOLD_READY"\n    exec sleep 30\nfi\n')
        (self.module / "common/font_manager.sh").write_text('''#!/bin/sh
mkdir -p "$REUSE_CAPTURED"
cp "$LUOSHU_PUBLIC_DIR"/fonts/* "$REUSE_CAPTURED"/ || exit 1
printf '%s\\n' '{"status":"ok"}'
''')
        for family in ("CJK", "Latin", "Digit"):
            variable_font(self.public / "fonts" / f"{family}-Variable.ttf")
        self.env = {**os.environ, "MODDIR": str(self.module), "LUOSHU_PUBLIC_DIR": str(self.public),
                    "LUOSHU_TASK_SCOPE_PIDFILE": str(self.module / ".luoshu-state/tasks/auto_multiweight_worker.pid"),
                    "REUSE_CALLS": str(self.calls), "REUSE_CAPTURED": str(self.captured),
                    "REUSE_ERRORS": str(self.child_errors), "REUSE_HOST_FONTTOOLS_SITE": HOST_FONTTOOLS_SITE,
                    "REUSE_COMPOSITE_CALLS": str(self.composite_calls),
                    "HOST_PYTHON": sys.executable}
        definitions = self.script.read_text().split('case "${1:-config}" in', 1)[0]
        self.definitions = self.module / "common/definitions.sh"
        self.definitions.write_text(definitions)

    def instance_calls(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def child_diagnostics(self):
        if not self.child_errors.exists():
            return ""
        records = [json.loads(line) for line in self.child_errors.read_text().splitlines()]
        return "".join(f"font_instance exited {record['code']}:\n{record['stderr']}" for record in records)

    def prepare(self, requests, *, root=None, extra_env=None):
        root = root or self.taskroot
        root.mkdir(parents=True, exist_ok=True)
        driver = self.module / "prepare.sh"
        driver.write_text('. "$MODDIR/common/definitions.sh"\n_root="$REUSE_ROOT"\n' + requests)
        result = subprocess.run(["sh", str(driver)], env={**self.env, "REUSE_ROOT": str(root), **(extra_env or {})},
                                capture_output=True, text=True, timeout=20)
        if result.returncode:
            result.stderr += self.child_diagnostics()
        return result

    def assert_prepared(self, requests, *, root=None):
        result = self.prepare(requests, root=root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def prepare_composite_inputs(self):
        self.assert_prepared('''prepare_source cjk CJK wght=400 fixed 400 "$REUSE_ROOT/in/cjk.ttf" || exit $?
prepare_source latin Latin wght=400 fixed 400 "$REUSE_ROOT/in/latin.ttf" || exit $?
prepare_source digit Digit wght=400 fixed 400 "$REUSE_ROOT/in/digit.ttf" || exit $?
''')

    def composite(self, name="result", *, extra_env=None, prefix=""):
        return self.prepare(prefix + f'''build_composite_cached "$REUSE_ROOT/in/cjk.ttf" "$REUSE_ROOT/in/latin.ttf" "$REUSE_ROOT/in/digit.ttf" "$REUSE_ROOT/{name}.ttf" "$REUSE_ROOT/{name}.progress.json"
''', extra_env=extra_env)

    def composite_count(self):
        return len(self.composite_calls.read_text().splitlines()) if self.composite_calls.exists() else 0

    def composite_cache(self):
        return self.module / "cache/auto-multiweight-mix/composites-v3"

    def test_persistent_cache_tracks_real_engine_layout_and_runner_identity(self):
        self.prepare_composite_inputs()
        result = self.composite()
        self.assertEqual(result.returncode, 0, result.stderr)
        original = (self.taskroot / "result.ttf").read_bytes()
        for index, name in enumerate(("composite_font.py", "composite_layout.py", "luoshu_composite.sh"), 2):
            with self.subTest(dependency=name):
                with (self.module / "common" / name).open("a") as stream:
                    stream.write("\n# identity changed without changing glyphs\n")
                result = self.composite(name="changed-" + str(index))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.composite_count(), index)
                self.assertEqual((self.taskroot / f"changed-{index}.ttf").read_bytes(), original)

    def test_persistent_cache_layout_change_uses_new_real_glyphs(self):
        self.prepare_composite_inputs()
        result = self.composite()
        self.assertEqual(result.returncode, 0, result.stderr)
        with TTFont(self.taskroot / "result.ttf") as font:
            original_bottom = font["glyf"][font.getBestCmap()[ord("A")]].yMin
        layout = self.module / "common/composite_layout.py"
        old = "return scale, max(-limit, min(limit, shift))"
        self.assertIn(old, layout.read_text())
        layout.write_text(layout.read_text().replace(old, old + " + 37.0"))
        shutil.rmtree(self.module / "common/__pycache__", ignore_errors=True)
        result = self.composite(name="new-layout")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.composite_count(), 2)
        with TTFont(self.taskroot / "new-layout.ttf") as font:
            self.assertEqual(font["glyf"][font.getBestCmap()[ord("A")]].yMin, original_bottom + 37)
            self.assertTrue(set(map(ord, "Aa09中文")) <= set(font.getBestCmap()))

    def test_corrupt_persistent_composite_is_rebuilt_with_same_font_bytes(self):
        self.prepare_composite_inputs()
        self.assertEqual(self.composite().returncode, 0)
        original = (self.taskroot / "result.ttf").read_bytes()
        cached, = self.composite_cache().glob("*.font")
        cached.write_bytes(b"damaged nonempty composite cache")
        result = self.composite(name="recovered")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.composite_count(), 2)
        self.assertEqual((self.taskroot / "recovered.ttf").read_bytes(), original)
        with TTFont(self.taskroot / "recovered.ttf") as font:
            self.assertTrue(set(map(ord, "Aa09中文")) <= set(font.getBestCmap()))

    def test_valid_but_changed_persistent_payload_is_rebuilt(self):
        self.prepare_composite_inputs()
        self.assertEqual(self.composite().returncode, 0)
        original = (self.taskroot / "result.ttf").read_bytes()
        cached, = self.composite_cache().glob("*.font")
        with TTFont(cached, recalcTimestamp=False) as font:
            font["head"].fontRevision += 1
            font.save(cached)
        result = self.composite(name="recovered")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.composite_count(), 2)
        self.assertEqual((self.taskroot / "recovered.ttf").read_bytes(), original)

    def test_atomic_receipt_avoids_revalidation_but_missing_or_invalid_proof_does_not(self):
        self.prepare_composite_inputs()
        # Count real shell font validation only for the composite stage. Keep its
        # complete implementation and original font/coverage assertions.
        validation_calls = self.root / "validation-calls.txt"
        check = self.module / "common/font_check.sh"
        check.write_text(check.read_text().replace("font_validate() {", "real_font_validate() {") +
                         '\nfont_validate() { printf "validate\\n" >> "$REUSE_VALIDATE_CALLS"; real_font_validate "$@"; }\n')
        env = {"REUSE_VALIDATE_CALLS": str(validation_calls)}
        self.assertEqual(self.composite(extra_env=env).returncode, 0)
        original = (self.taskroot / "result.ttf").read_bytes()
        cached, = self.composite_cache().glob("*.font")
        receipt = Path(str(cached) + ".receipt")
        self.assertTrue(receipt.is_file())
        self.assertEqual(len(validation_calls.read_text().splitlines()), 1)
        self.assertEqual(self.composite(name="warm", extra_env=env).returncode, 0)
        self.assertEqual(len(validation_calls.read_text().splitlines()), 1)
        self.assertEqual(self.composite_count(), 1)
        self.assertEqual((self.taskroot / "warm.ttf").read_bytes(), original)
        receipt.unlink()
        self.assertEqual(self.composite(name="no-proof", extra_env=env).returncode, 0)
        self.assertEqual(len(validation_calls.read_text().splitlines()), 2)
        self.assertEqual(self.composite_count(), 1)
        receipt.write_text("schema=invalid\npayloadDigest=unproven\n")
        self.assertEqual(self.composite(name="bad-proof", extra_env=env).returncode, 0)
        self.assertEqual(self.composite_count(), 2)
        self.assertEqual((self.taskroot / "bad-proof.ttf").read_bytes(), original)

    def test_composite_dependency_changing_during_generation_is_never_published(self):
        self.prepare_composite_inputs()
        for name in ("composite_font.py", "composite_layout.py", "luoshu_composite.sh"):
            with self.subTest(dependency=name):
                result = self.composite(extra_env={"REUSE_COMPOSITE_CHANGE": str(self.module / "common" / name)})
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.taskroot / "result.ttf").exists())
                self.assertFalse(list(self.composite_cache().glob("*.font")))
                self.assertFalse(list(self.composite_cache().glob("*.receipt")))

    def test_missing_composite_dependency_cannot_reuse_verified_cache(self):
        self.prepare_composite_inputs()
        self.assertEqual(self.composite().returncode, 0)
        (self.module / "common/composite_layout.py").unlink()
        result = self.composite(name="missing-dependency")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.taskroot / "missing-dependency.ttf").exists())

    def test_composite_identity_change_during_atomic_publication_is_rejected(self):
        self.prepare_composite_inputs()
        real_mv = shutil.which("mv")
        directory = self.root / "publication-bin"
        directory.mkdir()
        move = directory / "mv"
        move.write_text(f'''#!/bin/sh
"{real_mv}" "$@" || exit $?
case "$*" in *composites-v3/*.font*) printf '\\n# replaced during payload publication\\n' >> "$MODDIR/common/composite_font.py" ;; esac
''')
        move.chmod(0o755)
        result = self.composite(extra_env={"PATH": str(directory) + ":" + self.env["PATH"]})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.taskroot / "result.ttf").exists())
        self.assertFalse(list(self.composite_cache().glob("*.font")))
        self.assertFalse(list(self.composite_cache().glob("*.receipt")))

    def test_composite_stage_timeout_and_cancel_retire_only_owned_artifacts(self):
        for action in ("timeout", "cancel"):
            with self.subTest(action=action):
                for name in ("task_scope.sh", "task_scope.py"):
                    shutil.copyfile(ROOT / "common" / name, self.module / "common" / name)
                task_id = "composite-owned-" + action
                task = self.module / "config/axes_task.conf"
                task.write_text(f"task={task_id}\nstate=queued\ncjk=CJK\nlatin=Latin\ndigit=Digit\n"
                                "cjkAxes=wght=400\nlatinAxes=wght=400\ndigitAxes=wght=400\n"
                                "cjkMode=auto\nlatinMode=fixed\ndigitMode=fixed\n"
                                f"root={self.taskroot}\nstarted=1\nfinished=\npercent=1\n")
                marker = self.root / (task_id + ".ready")
                cache = self.composite_cache()
                cache.mkdir(parents=True, exist_ok=True)
                sentinel_file = cache / "unrelated.keep"
                sentinel_file.write_bytes(b"unrelated reusable fixture cache")
                # A task record does not authorize recursive deletion of an
                # external root; the worker must place all scratch in its scope.
                external_file = self.taskroot / "external.keep"
                external_file.write_bytes(b"outside owned scope")
                sentinel = subprocess.Popen(["sleep", "30"])
                environment = {**self.env, "LUOSHU_TASK_SCOPE_PYTHON": sys.executable,
                               "REUSE_HOLD_COMPOSITE": "1", "REUSE_HOLD_READY": str(marker)}
                pidfile = self.module / ".luoshu-state/tasks/auto_multiweight_worker.pid"
                process = subprocess.Popen(["sh", str(self.module / "common/task_scope.sh"), "run",
                                            "--pid-file", str(pidfile), "--task", task_id,
                                            "--timeout", "5" if action == "timeout" else "30", "--",
                                            "sh", str(self.script), "worker", task_id], env=environment,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    deadline = time.monotonic() + 4
                    while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                        time.sleep(.02)
                    self.assertTrue(marker.exists(), "real composite never completed: " + self.child_diagnostics())
                    temporary, = (pidfile.parent / "tmp").glob("task-" + task_id + "-*")
                    self.assertTrue(list(temporary.rglob("*.font")))
                    if action == "cancel":
                        cancelled = subprocess.run(["sh", str(self.module / "common/task_scope.sh"),
                                                    "cancel", str(pidfile), task_id], env=environment,
                                                   capture_output=True, text=True, timeout=8)
                        self.assertEqual(cancelled.returncode, 0, cancelled.stderr + cancelled.stdout)
                        self.assertTrue(json.loads(cancelled.stdout)["data"]["cleaned"])
                    _, stderr = process.communicate(timeout=10)
                    self.assertEqual(process.returncode, 124 if action == "timeout" else 143, stderr)
                    proof = json.loads(Path(str(pidfile) + ".cleanup.json").read_text())
                    self.assertTrue(proof["cleaned"], proof)
                    self.assertEqual(proof["leftoverPids"], [])
                    self.assertFalse(temporary.exists())
                    self.assertFalse(Path("/proc", marker.read_text().strip()).exists())
                    self.assertIsNone(sentinel.poll())
                    self.assertEqual(sentinel_file.read_bytes(), b"unrelated reusable fixture cache")
                    self.assertEqual(external_file.read_bytes(), b"outside owned scope")
                    self.assertEqual(list(cache.iterdir()), [sentinel_file])
                    self.assertFalse((self.taskroot / "prepared").exists())
                finally:
                    if process.poll() is None:
                        process.terminate()
                    process.communicate(timeout=10)
                    sentinel.terminate()
                    sentinel.wait(timeout=3)

    def test_fixed_slot_reuses_exact_instance_and_bytes(self):
        started = time.monotonic()
        result = self.prepare('''for target in 100 200 300 400 500 600 700 800 900; do
    prepare_source latin Latin wght=400 fixed "$target" "$REUSE_ROOT/out/$target.ttf" || exit $?
done
''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        outputs = [self.taskroot / "out" / f"{weight}.ttf" for weight in range(100, 1000, 100)]
        first = outputs[0].read_bytes()
        self.assertTrue(all(path.read_bytes() == first for path in outputs))
        with TTFont(outputs[0]) as font:
            self.assertNotIn("fvar", font)
            self.assertEqual(font["OS/2"].usWeightClass, 400)
        count = len(self.instance_calls())
        print(json.dumps({"scope": "host-fixed-slot-preparation", "instanceCalls": count,
                          "outputBytes": len(first), "sha256": hashlib.sha256(first).hexdigest(),
                          "elapsedSeconds": round(time.monotonic() - started, 4)}), flush=True)
        self.assertEqual(count, 1)

    def test_mixed_preparation_driver_preserves_all_output_bytes(self):
        # Independent successful driver for comparable before/after call counts.
        # The historical full worker fails at weight 200, so it is not a valid
        # whole-task performance baseline.
        started = time.monotonic()
        result = self.prepare('''for target in 100 200 300 400 500 600 700 800 900; do
    prepare_source cjk CJK wght=400 auto "$target" "$REUSE_ROOT/out/$target/cjk.ttf" || exit $?
    prepare_source latin Latin wght=400 fixed "$target" "$REUSE_ROOT/out/$target/latin.ttf" || exit $?
    prepare_source digit Digit wght=400 fixed "$target" "$REUSE_ROOT/out/$target/digit.ttf" || exit $?
done
''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        outputs = sorted((self.taskroot / "out").glob("*/*.ttf"))
        self.assertEqual(len(outputs), 27)
        for path in outputs:
            with TTFont(path) as font:
                self.assertNotIn("fvar", font)
                self.assertEqual(font["OS/2"].usWeightClass,
                                 int(path.parent.name) if path.stem == "cjk" else 400)
        count = len(self.instance_calls())
        print(json.dumps({"scope": "host-mixed-slot-preparation", "instanceCalls": count,
                          "outputBytes": sum(path.stat().st_size for path in outputs),
                          "sha256": hashlib.sha256(b"".join(path.read_bytes() for path in outputs)).hexdigest(),
                          "elapsedSeconds": round(time.monotonic() - started, 4)}), flush=True)
        self.assertEqual(count, 11)

    def test_active_worker_completes_all_nine_weights_and_preserves_config(self):
        config = {"task": "active-fixture", "state": "queued", "cjk": "CJK", "latin": "Latin", "digit": "Digit",
                  "cjkAxes": "wght=400", "latinAxes": "wght=400", "digitAxes": "wght=400",
                  "cjkMode": "auto", "latinMode": "fixed", "digitMode": "fixed", "root": str(self.taskroot),
                  "started": "1", "finished": "", "percent": "1"}
        task = self.module / "config/axes_task.conf"
        task.write_text("".join(f"{key}={value}\n" for key, value in config.items()))
        started = time.monotonic()
        result = subprocess.run(["sh", str(self.script), "worker", "active-fixture"], env=self.env,
                                capture_output=True, text=True, timeout=30)
        state = dict(line.split("=", 1) for line in task.read_text().splitlines())
        print(json.dumps({"scope": "host-active-worker", "code": result.returncode,
                          "state": state["state"], "message": state["message"],
                          "instanceCalls": len(self.instance_calls()),
                          "elapsedSeconds": round(time.monotonic() - started, 4)}, ensure_ascii=False), flush=True)
        self.assertEqual(result.returncode, 0, task.read_text() + result.stderr + self.child_diagnostics())
        self.assertEqual(state["state"], "success")
        roles = {100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular", 500: "Medium",
                 600: "SemiBold", 700: "Bold", 800: "ExtraBold", 900: "Black"}
        expected = {f"LuoShuAutoMix-{role}.{'ttf' if weight == 400 else 'otf'}": weight
                    for weight, role in roles.items()}
        self.assertEqual({path.name for path in self.captured.iterdir()}, set(expected))
        for name, weight in expected.items():
            with TTFont(self.captured / name) as font:
                self.assertNotIn("fvar", font)
                self.assertEqual(font["OS/2"].usWeightClass, weight)
                self.assertTrue(set(map(ord, "Aa09中文")) <= set(font.getBestCmap()))
        saved = dict(line.split("=", 1) for line in (self.module / "config/font_mix.conf").read_text().splitlines())
        self.assertEqual([saved[role] for role in ("cjk", "latin", "digit")], ["CJK", "Latin", "Digit"])
        self.assertEqual(len(self.instance_calls()), 11)
        self.assertFalse(self.taskroot.exists())

    def test_weight_role_axes_and_generator_changes_do_not_reuse(self):
        result = self.prepare('''prepare_source latin Latin wght=400 auto 100 "$REUSE_ROOT/100.ttf" || exit $?
prepare_source latin Latin wght=400 auto 900 "$REUSE_ROOT/900.ttf" || exit $?
prepare_source digit Latin wght=900 fixed 100 "$REUSE_ROOT/digit.ttf" || exit $?
prepare_source latin Latin wght=500 fixed 100 "$REUSE_ROOT/500.ttf" || exit $?
prepare_source latin Latin wght=500,wdth=100 fixed 100 "$REUSE_ROOT/500-width.ttf" || exit $?
printf '\\n# changed generator identity\\n' >> "$INSTANCE_PY"
prepare_source latin Latin wght=500 fixed 100 "$REUSE_ROOT/500-new-generator.ttf" || exit $?
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.instance_calls()), 6)
        for name, weight in (("100.ttf", 100), ("900.ttf", 900), ("500.ttf", 500)):
            with TTFont(self.taskroot / name) as font:
                self.assertEqual(font["OS/2"].usWeightClass, weight)

    def test_failed_instance_is_never_reused(self):
        requests = 'prepare_source latin Latin wght=400 fixed 100 "$REUSE_ROOT/result.ttf"\n'
        failed = self.prepare(requests, extra_env={"REUSE_FAIL": "1"})
        self.assertNotEqual(failed.returncode, 0)
        self.assertFalse((self.taskroot / "result.ttf").exists())
        success = self.prepare(requests)
        self.assertEqual(success.returncode, 0, success.stderr)
        self.assertEqual(len(self.instance_calls()), 2)

    def test_generator_changing_during_instance_is_not_published(self):
        requests = 'prepare_source latin Latin wght=400 fixed 100 "$REUSE_ROOT/result.ttf"\n'
        failed = self.prepare(requests, extra_env={"REUSE_CHANGE_GENERATOR": "1"})
        self.assertNotEqual(failed.returncode, 0)
        self.assertFalse((self.taskroot / "result.ttf").exists())
        self.assertFalse(list((self.taskroot / "prepared-cache").glob("*.font")))
        success = self.prepare(requests)
        self.assertEqual(success.returncode, 0, success.stderr)
        self.assertEqual(len(self.instance_calls()), 2)

    def test_public_replacement_uses_stable_task_snapshot_and_new_task_reloads(self):
        requests = 'prepare_source latin Latin wght=400 fixed 100 "$REUSE_ROOT/result.ttf"\n'
        self.assert_prepared(requests)
        first = (self.taskroot / "result.ttf").read_bytes()
        variable_font(self.public / "fonts/Latin-Variable.ttf", top=820)
        self.assert_prepared(requests)
        self.assertEqual((self.taskroot / "result.ttf").read_bytes(), first)
        another = self.module / "cache/task-two"
        self.assert_prepared(requests, root=another)
        self.assertNotEqual((another / "result.ttf").read_bytes(), first)
        self.assertEqual(len(self.instance_calls()), 2)

    def test_selected_public_source_can_be_removed_without_changing_task(self):
        requests = 'prepare_source latin Latin wght=400 fixed 100 "$REUSE_ROOT/result.ttf"\n'
        self.assert_prepared(requests)
        first = (self.taskroot / "result.ttf").read_bytes()
        (self.public / "fonts/Latin-Variable.ttf").unlink()
        self.assert_prepared(requests)
        self.assertEqual((self.taskroot / "result.ttf").read_bytes(), first)
        self.assertEqual(len(self.instance_calls()), 1)

    def test_source_changing_during_snapshot_is_not_published(self):
        variable_font(self.public / "replacement.ttf", top=820)
        # Mutate the public source immediately after the real copy finishes.
        # Both inputs pass the actual font gate, so only content proof catches it.
        real_cp = shutil.which("cp")
        bin_dir = self.root / "race-bin"
        bin_dir.mkdir()
        cp = bin_dir / "cp"
        cp.write_text(f'''#!/bin/sh
"{real_cp}" "$@" || exit $?
case "$*" in *source-snapshots*) "{real_cp}" "$REUSE_REPLACEMENT" "$REUSE_PUBLIC_SOURCE" ;; esac
''')
        cp.chmod(0o755)
        requests = 'prepare_source latin Latin wght=400 fixed 100 "$REUSE_ROOT/result.ttf"\n'
        result = self.prepare(requests, extra_env={"PATH": str(bin_dir) + ":" + self.env["PATH"],
                              "REUSE_REPLACEMENT": str(self.public / "replacement.ttf"),
                              "REUSE_PUBLIC_SOURCE": str(self.public / "fonts/Latin-Variable.ttf")})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.taskroot / "result.ttf").exists())
        self.assertEqual(self.instance_calls(), [])
        self.assertFalse(list((self.taskroot / "source-snapshots").glob("*.font")))
        self.assert_prepared(requests)
        self.assertEqual(len(self.instance_calls()), 1)

    def test_corrupt_prepared_output_is_validated_and_rebuilt(self):
        requests = 'prepare_source latin Latin wght=400 fixed 100 "$REUSE_ROOT/result.ttf"\n'
        self.assert_prepared(requests)
        original = (self.taskroot / "result.ttf").read_bytes()
        # Outputs may be hardlinks; corruption must not turn the next hit into
        # a success merely because a nonempty prepared entry exists.
        (self.taskroot / "result.ttf").write_bytes(b"damaged")
        self.assert_prepared(requests)
        self.assertEqual((self.taskroot / "result.ttf").read_bytes(), original)
        self.assertEqual(len(self.instance_calls()), 2)

    def test_timeout_and_cancel_retire_owned_preparation_cache(self):
        for action in ("timeout", "cancel"):
            with self.subTest(action=action):
                for name in ("task_scope.sh", "task_scope.py"):
                    shutil.copyfile(ROOT / "common" / name, self.module / "common" / name)
                task_id = "owned-" + action
                task = self.module / "config/axes_task.conf"
                task.write_text(f"task={task_id}\nstate=queued\ncjk=CJK\nlatin=Latin\ndigit=Digit\n"
                                "cjkAxes=wght=400\nlatinAxes=wght=400\ndigitAxes=wght=400\n"
                                "cjkMode=auto\nlatinMode=fixed\ndigitMode=fixed\n"
                                f"root={self.taskroot}\nstarted=1\nfinished=\npercent=1\n")
                self.taskroot.mkdir(parents=True, exist_ok=True)
                marker = self.root / (task_id + ".ready")
                environment = {**self.env, "LUOSHU_TASK_SCOPE_PYTHON": sys.executable,
                               "REUSE_HOLD": "1", "REUSE_HOLD_READY": str(marker)}
                # Use the worker's real registered slot so it runs inside this
                # supervisor rather than creating another 900-second scope.
                actual_pidfile = self.module / ".luoshu-state/tasks/auto_multiweight_worker.pid"
                process = subprocess.Popen(["sh", str(self.module / "common/task_scope.sh"), "run",
                                            "--pid-file", str(actual_pidfile), "--task", task_id,
                                            "--timeout", "1" if action == "timeout" else "10", "--",
                                            "sh", str(self.script), "worker", task_id], env=environment,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    deadline = time.monotonic() + 3
                    while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                        time.sleep(.02)
                    self.assertTrue(marker.exists(), "owned instance never began")
                    temporary = list((actual_pidfile.parent / "tmp").glob("task-" + task_id + "-*"))
                    self.assertEqual(len(temporary), 1)
                    self.assertTrue((temporary[0] / "source-snapshots").is_dir())
                    if action == "cancel":
                        cancelled = subprocess.run(["sh", str(self.module / "common/task_scope.sh"),
                                                    "cancel", str(actual_pidfile), task_id], env=environment,
                                                   capture_output=True, text=True, timeout=8)
                        self.assertEqual(cancelled.returncode, 0, cancelled.stderr + cancelled.stdout)
                        self.assertTrue(json.loads(cancelled.stdout)["data"]["cleaned"])
                    _, stderr = process.communicate(timeout=8)
                    self.assertEqual(process.returncode, 124 if action == "timeout" else 143, stderr)
                    proof = json.loads(Path(str(actual_pidfile) + ".cleanup.json").read_text())
                    self.assertTrue(proof["cleaned"], proof)
                    self.assertEqual(proof["leftoverPids"], [])
                    self.assertFalse(temporary[0].exists())
                    held_pid = marker.read_text()
                    self.assertFalse(Path("/proc").joinpath(held_pid).exists())
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.communicate(timeout=8)


if __name__ == "__main__":
    unittest.main()
