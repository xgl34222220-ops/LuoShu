#!/usr/bin/env python3
"""Exercise real font role parsing and error propagation before mix workers launch."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import newTable

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "common/python/lib/python3.14/site-packages"
# Keep the independent fixture explicit: omitting ASCII from the CJK base is unsafe because
# the current composite engine replaces existing cmap entries rather than adding new slots.
PROBES = set(map(ord, "中文字体系统默认洛书汉字ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"))


def make_font(path: Path, missing: int | None = None) -> None:
    cmap = {point: f"uni{point:04X}" for point in sorted(PROBES - {missing})}
    names = [".notdef", *cmap.values()]
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap(cmap)
    glyphs = {}
    for name in names:
        pen = TTGlyphPen(None)
        if name != ".notdef":
            pen.moveTo((50, 0))
            pen.lineTo((550, 0))
            pen.lineTo((550, 700))
            pen.lineTo((50, 700))
            pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (600, 50) for name in names})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    builder.setupNameTable({"familyName": "Role Error Fixture", "styleName": "Regular"})
    builder.setupPost()
    builder.setupMaxp()
    # The production gate intentionally rejects tiny files. Use a legal private table to keep
    # this compact fixture above that guard, without depending on an installed system font.
    padding = newTable("TEST")
    padding.data = b"\0" * 4096
    builder.font["TEST"] = padding
    builder.save(path)
    assert path.stat().st_size > 4096


class FontRoleErrorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.public = self.base / "public"
        self.fonts = self.public / "fonts"
        self.fonts.mkdir(parents=True)
        self.valid = self.fonts / "花轮丸-Regular.ttf"
        self.missing = self.fonts / "缺A-Regular.ttf"
        self.malformed = self.fonts / "损坏-Regular.ttf"
        make_font(self.valid)
        make_font(self.missing, ord("A"))
        self.malformed.write_bytes(b"invalid font" * 600)
        self.modules = {}
        for variant in ("modern", "legacy"):
            module = self.base / variant
            common = module / "common"
            common.mkdir(parents=True)
            (module / "module.prop").write_text("id=LuoShu\n")
            source = ROOT / "common" / ("legacy_v14_4" if variant == "legacy" else "")
            for name in ("font_role_check.py", "font_role_check.sh"):
                shutil.copy2(source / name, common / name)
            for name in ("util_functions.sh", "util_functions_core.sh"):
                shutil.copy2(ROOT / "common" / name, common / name)
            for name in ("v14_mix.sh", "v143_auto_multiweight_mix.sh"):
                shutil.copy2(ROOT / "common/legacy_v14_4" / name, common / name)
            (common / "v142_weighted_mix.sh").write_text(
                '#!/bin/sh\nprintf launched > "$MODDIR/worker-launched"\n'
                'printf \'{"status":"ok","data":{"task":"fixture"}}\\n\'\n'
            )
            launcher = common / "python/bin/luoshu-python"
            launcher.parent.mkdir(parents=True)
            launcher.write_text(
                "#!/bin/sh\nunset PYTHONHOME\n"
                'PYTHONPATH="$FONT_ROLE_TEST_PYTHONPATH"\nexport PYTHONPATH\n'
                f"exec {shlex.quote(sys.executable)} -S \"$@\"\n"
            )
            launcher.chmod(0o755)
            self.modules[variant] = module
        self.env = {
            **os.environ,
            "LUOSHU_PUBLIC_DIR": str(self.public),
            "FONT_ROLE_TEST_PYTHONPATH": str(SITE),
            "PYTHONPATH": str(SITE),
            "PYTHONPYCACHEPREFIX": str(self.base / "bytecode"),
        }
        self.env.pop("PYTHONHOME", None)

    def run_command(self, argv: list[str], *, variant: str = "modern", env: dict | None = None):
        return subprocess.run(argv, env={**self.env, "MODDIR": str(self.modules[variant]), **(env or {})},
                              capture_output=True, text=True, timeout=15, check=False)

    def cli(self, font: Path, *, variant: str = "modern", message: bool = False, env: dict | None = None):
        return self.run_command([sys.executable, "-S", str(self.modules[variant] / "common/font_role_check.py"),
                                 str(font), "cjk", *( ["--message"] if message else [])], variant=variant, env=env)

    def shell(self, family: str, *, variant: str = "modern", message: bool = False, env: dict | None = None):
        return self.run_command(["sh", str(self.modules[variant] / "common/font_role_check.sh"),
                                 family, "cjk", *( ["--message"] if message else [])], variant=variant, env=env)

    def import_failure_env(self) -> dict[str, str]:
        shadow = self.base / "blocked"
        package = shadow / "fontTools"
        package.mkdir(parents=True, exist_ok=True)
        (package / "__init__.py").write_text("raise ModuleNotFoundError('fontTools unavailable fixture')\n")
        path = f"{shadow}{os.pathsep}{SITE}"
        return {"PYTHONPATH": path, "FONT_ROLE_TEST_PYTHONPATH": path}

    def test_valid_real_cjk_ascii_font_passes_both_role_check_copies(self):
        for variant in self.modules:
            with self.subTest(variant=variant):
                for result in (self.cli(self.valid, variant=variant), self.shell("花轮丸", variant=variant)):
                    self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
                    data = json.loads(result.stdout)
                    self.assertTrue(data["valid"])
                    self.assertEqual(data["reason"], "covered")
                    self.assertEqual(data["present"], data["required"])

    def test_only_actual_missing_cmap_entry_returns_exit_two(self):
        for variant in self.modules:
            with self.subTest(variant=variant):
                for result in (self.cli(self.missing, variant=variant), self.shell("缺A", variant=variant)):
                    self.assertEqual(result.returncode, 2, result.stderr or result.stdout)
                    data = json.loads(result.stdout)
                    self.assertEqual(data["reason"], "missing_glyphs")
                    self.assertEqual(data["missing"], ["U+0041"])
                    self.assertIn("U+0041", data["message"])

    def test_malformed_font_is_a_read_error_not_missing_glyphs(self):
        for variant in self.modules:
            with self.subTest(variant=variant):
                for result in (self.cli(self.malformed, variant=variant), self.shell("损坏", variant=variant)):
                    self.assertEqual(result.returncode, 1)
                    data = json.loads(result.stdout)
                    self.assertEqual(data["reason"], "read_failed")
                    self.assertIn("字体读取失败", data["message"])
                    self.assertNotIn("missing", data)

    def test_fonttools_import_failure_remains_structured(self):
        env = self.import_failure_env()
        for variant in self.modules:
            with self.subTest(variant=variant):
                for result in (self.cli(self.valid, variant=variant, env=env),
                               self.shell("花轮丸", variant=variant, env=env)):
                    self.assertEqual(result.returncode, 1)
                    data = json.loads(result.stdout)
                    self.assertEqual(data["reason"], "read_failed")
                    self.assertIn("fontTools unavailable fixture", data["message"])

    def test_missing_source_is_distinguished_from_missing_glyphs(self):
        for variant in self.modules:
            with self.subTest(variant=variant):
                result = self.shell("不存在", variant=variant)
                self.assertEqual(result.returncode, 1)
                data = json.loads(result.stdout)
                self.assertEqual(data["reason"], "source_not_found")
                self.assertIn("不存在", data["message"])
                result = self.cli(self.fonts / "不存在.ttf", variant=variant)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(json.loads(result.stdout)["reason"], "read_failed")

    def test_loader_exit_126_becomes_runtime_error_in_json_and_message_modes(self):
        for variant, module in self.modules.items():
            with self.subTest(variant=variant):
                launcher = module / "common/python/bin/luoshu-python"
                launcher.write_text('#!/bin/sh\nprintf \'CANNOT LINK EXECUTABLE: libpython fixture\\n\' >&2\nexit 126\n')
                result = self.shell("花轮丸", variant=variant)
                self.assertEqual(result.returncode, 1)
                data = json.loads(result.stdout)
                self.assertEqual(data["reason"], "runtime_failed")
                self.assertIn("libpython fixture", data["message"])
                result = self.shell("花轮丸", variant=variant, message=True)
                self.assertEqual(result.returncode, 1)
                self.assertIn("字体检查器运行失败", result.stdout)
                self.assertIn("libpython fixture", result.stdout)

    def test_message_mode_keeps_unicode_missing_codepoint_and_import_error(self):
        for variant in self.modules:
            with self.subTest(variant=variant):
                result = self.shell("缺A", variant=variant, message=True)
                self.assertEqual(result.returncode, 2)
                self.assertIn("中文基底缺少必要字形：U+0041", result.stdout)
                result = self.shell("花轮丸", variant=variant, message=True, env=self.import_failure_env())
                self.assertEqual(result.returncode, 1)
                self.assertIn("字体读取失败：fontTools unavailable fixture", result.stdout)

    def test_legacy_entrypoints_preserve_role_failure_before_launching_workers(self):
        module = self.modules["legacy"]
        for entry in ("v14_mix.sh", "v143_auto_multiweight_mix.sh"):
            for failed_role in range(3):
                with self.subTest(entry=entry, failed_role=failed_role):
                    families = ["花轮丸"] * 3
                    families[failed_role] = "损坏"
                    result = self.run_command(["sh", str(module / "common" / entry), "start", *families,
                                               "wght=400", "wght=400", "wght=400", "fixed", "fixed", "fixed"],
                                              variant="legacy")
                    data = json.loads(result.stdout)
                    self.assertEqual(data["status"], "error")
                    self.assertIn("字体读取失败", data["message"])
                    self.assertNotIn("缺少必要", data["message"])
                    self.assertFalse((module / "worker-launched").exists())

    def test_legacy_entrypoints_preserve_import_and_actual_missing_glyph_errors(self):
        module = self.modules["legacy"]
        for entry in ("v14_mix.sh", "v143_auto_multiweight_mix.sh"):
            for family, env, expected in (("花轮丸", self.import_failure_env(), "fontTools unavailable fixture"),
                                          ("缺A", {}, "U+0041"), ("不存在", {}, "找不到指定字体族")):
                with self.subTest(entry=entry, family=family):
                    result = self.run_command(["sh", str(module / "common" / entry), "start", family,
                                               "花轮丸", "花轮丸"], variant="legacy", env=env)
                    data = json.loads(result.stdout)
                    self.assertEqual(data["status"], "error")
                    self.assertIn(expected, data["message"])
                    self.assertFalse((module / "worker-launched").exists())

    def test_valid_legacy_start_still_reaches_the_worker(self):
        module = self.modules["legacy"]
        for entry in ("v14_mix.sh", "v143_auto_multiweight_mix.sh"):
            with self.subTest(entry=entry):
                result = self.run_command(["sh", str(module / "common" / entry), "start",
                                           "花轮丸", "花轮丸", "花轮丸"], variant="legacy")
                self.assertEqual(json.loads(result.stdout)["status"], "ok")
                self.assertEqual((module / "worker-launched").read_text(), "launched")
                (module / "worker-launched").unlink()


if __name__ == "__main__":
    unittest.main()
