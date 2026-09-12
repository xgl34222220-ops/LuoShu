#!/usr/bin/env python3
"""Provider cache identity and static/variable compatibility regressions."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from fontTools.fontBuilder import FontBuilder
from fontTools.ttLib import TTCollection, TTFont

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("google_provider_patch", ROOT / "common/google_font_provider_patch.py")
PATCHER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCHER)
FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


class ProviderPatchTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def font(self, filename, family="Google Sans", weight=400, variable=False):
        path = self.root / filename
        with TTFont(FONT) as font:
            for record in font["name"].names:
                if record.nameID in (1, 16):
                    record.string = family.encode(record.getEncoding())
            font["OS/2"].usWeightClass = weight
            if variable:
                builder = FontBuilder(font=font)
                builder.setupFvar([
                    ("wght", 100, 400, 900, "Weight"),
                    ("wdth", 75, 100, 125, "Width"),
                ], [])
                builder.setupGvar({glyph: [] for glyph in font.getGlyphOrder()})
            font.save(path)
        return path

    def test_opaque_filename_uses_family_and_weight_tables(self):
        opaque = self.font("a871063982044", family="Google Sans Text", weight=700)
        self.assertEqual(PATCHER.inspect_target(opaque), 700)

    def test_named_instance_weight_overrides_variable_default(self):
        font = self.font("Google_Sans-700-100_0-0_0.ttf", variable=True)
        self.assertEqual(PATCHER.inspect_target(font), 700)

    def test_filename_cannot_enable_unrelated_or_code_font(self):
        for family in ("DejaVu Sans", "Google Sans Code", "Noto Color Emoji"):
            with self.subTest(family=family):
                self.assertIsNone(PATCHER.inspect_target(self.font("GoogleSans.ttf", family=family)))

    def test_collections_are_not_replaced_with_a_single_face(self):
        first = self.font("one.ttf")
        second = self.font("two.ttf", family="Unrelated")
        collection = TTCollection()
        collection.fonts = [TTFont(first), TTFont(second)]
        target = self.root / "GoogleSans.ttc"
        collection.save(target)
        collection.close()
        self.assertIsNone(PATCHER.inspect_target(target))

    def test_static_source_replaces_variable_target_without_fake_axes(self):
        source = self.font("source.ttf", family="User Font", weight=700)
        target = self.font("target.ttf", variable=True)
        output = self.root / "output.ttf"
        result = PATCHER.patch(source, target, output, 700)
        self.assertTrue(result["targetVariable"])
        self.assertFalse(result["outputVariable"])
        with TTFont(output) as font, TTFont(source) as donor:
            self.assertNotIn("fvar", font)
            self.assertNotIn("gvar", font)
            self.assertEqual(font["OS/2"].usWeightClass, 700)
            self.assertEqual(font.getBestCmap(), donor.getBestCmap())
            self.assertEqual(font.getTableData("glyf"), donor.getTableData("glyf"))
            self.assertEqual(font["name"].getBestFamilyName(), "Google Sans")

    def test_variable_source_is_fully_instantiated_for_static_target(self):
        source = self.font("source.ttf", family="User Font", variable=True)
        target = self.font("target.ttf", weight=700)
        output = self.root / "output.ttf"
        PATCHER.patch(source, target, output, 700)
        with TTFont(output) as font:
            self.assertNotIn("fvar", font)
            self.assertNotIn("gvar", font)
            self.assertEqual(font["OS/2"].usWeightClass, 700)

    def test_provider_clone_does_not_carry_unrelated_cjk_donor_glyphs(self):
        from hyperos_cjk_routing_test import make_font
        source = self.root / 'large-cjk.ttf'
        make_font(source, points=(*range(32, 127), *range(0x4E00, 0x5E00)), variable=True)
        target = self.font('target.ttf', variable=True)
        output = self.root / 'provider.ttf'
        before = source.read_bytes()
        PATCHER.patch(source, target, output, 400)
        with TTFont(output) as font:
            self.assertTrue(all(cp in font.getBestCmap() for cp in range(32, 127)))
            self.assertNotIn(0x4E00, font.getBestCmap())
            self.assertLess(len(font.getGlyphOrder()), 150)
            self.assertIn('fvar', font)
        self.assertLess(output.stat().st_size, len(before) // 10)
        self.assertEqual(source.read_bytes(), before)

    def test_scan_ignores_nonfonts_and_preserves_spaces(self):
        valid = self.font("opaque with spaces", weight=600)
        invalid = self.root / "metadata.json"
        invalid.write_text('{"family":"Google Sans"}')
        candidates = self.root / "candidates"
        candidates.write_text(f"{invalid}\n{valid}\n{valid}\n")
        result = subprocess.run([sys.executable, str(ROOT / "common/google_font_provider_patch.py"),
                                 "--inspect-targets", str(candidates)], text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout, f"{valid}\t600\n")

    def test_service_keeps_discovering_after_first_success(self):
        module = self.root / "module"
        (module / "common").mkdir(parents=True)
        (module / "config").mkdir()
        (module / "config/active_font.conf").write_text("fixture\n")
        marker = self.root / "passes"
        (module / "common/google_font_provider_bridge.sh").write_text(
            'case "$1" in fingerprint) echo unchanged;; '
            'apply) printf "pass\\n" >> "$PROVIDER_TEST_MARKER";; esac\nexit 0\n')
        shutil.copyfile(ROOT / "common/font_switch_lock.sh", module / "common/font_switch_lock.sh")
        commands = self.root / "bin"
        commands.mkdir()
        for name, content in {"getprop": "echo 1", "sleep": ":"}.items():
            path = commands / name
            path.write_text(f"#!/bin/sh\n{content}\n")
            path.chmod(0o755)
        env = dict(os.environ, MODDIR=str(module), LUOSHU_GOOGLE_FONT_RETRIES="3",
                   LUOSHU_GOOGLE_FONT_WATCH_CYCLES="0",
                   PROVIDER_TEST_MARKER=str(marker), PATH=f"{commands}:{os.environ['PATH']}")
        subprocess.run(["sh", str(ROOT / "common/google_font_provider_service.sh")], env=env, check=True)
        self.assertEqual(marker.read_text().splitlines(), ["pass"])

    def test_equal_clone_skips_remount_in_target_namespace(self):
        source = self.font("source.ttf")
        target = self.root / "target.ttf"
        shutil.copyfile(source, target)
        commands = self.root / "bin"
        commands.mkdir()
        nsenter = commands / "nsenter"
        nsenter.write_text('#!/bin/sh\nwhile [ "$1" != -- ]; do shift; done\nshift\nexec "$@"\n')
        nsenter.chmod(0o755)
        mount = commands / "mount"
        mount.write_text('#!/bin/sh\necho unexpected-mount >&2\nexit 90\n')
        mount.chmod(0o755)
        env = dict(os.environ, PATH=f"{commands}:{os.environ['PATH']}", LUOSHU_GOOGLE_FONT_NS_SHELL="/bin/sh")
        result = subprocess.run(["sh", "-c", '. "$1"; _gfp_mount_in_pid 1 "$2" "$3"; '
                                 'code=$?; printf "%s:%s" "$code" "$_gfp_mount_mode"; '
                                 'printf "%s" "$_gfp_mount_detail" >&2', "sh",
                                 str(ROOT / "common/google_font_provider_bridge.sh"), str(source), str(target)],
                                env=env, text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout, "0:already", result.stderr)

    def test_partial_namespace_mount_is_not_reported_as_complete(self):
        module = self.root / "module"
        (module / "common").mkdir(parents=True)
        (module / "config/device-font-sources").mkdir(parents=True)
        (module / "config/active_font.conf").write_text("fixture\n")
        target = self.font("opaque")
        source = self.font("source.ttf", family="Custom")
        cache = module / "config/google-font-provider"
        cache.mkdir()
        old_clone = cache / "previous-selection.ttf"
        shutil.copyfile(source, old_clone)
        shutil.copyfile(source, module / "config/device-font-sources/LuoShu-400.ttf")
        shutil.copyfile(ROOT / "common/google_font_provider_patch.py", module / "common/google_font_provider_patch.py")
        script = '''. "$1"
_gfp_unique_namespace_pids() { printf '10\\n20\\n'; }
_gfp_mount_in_pid() {
    if [ "$1" = 10 ]; then _gfp_mount_mode=already; return 0; fi
    _gfp_mount_detail=permission-denied
    return 1
}
_gfp_apply_once
'''
        env = dict(os.environ, MODDIR=str(module), LUOSHU_GOOGLE_FONT_PYTHON=sys.executable,
                   LUOSHU_GOOGLE_FONT_TARGETS=str(target))
        result = subprocess.run(["sh", "-c", script, "sh", str(ROOT / "common/google_font_provider_bridge.sh")],
                                env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("failed:1", (module / "logs/google-font-provider.log").read_text())
        self.assertTrue(old_clone.exists(), "partial repair discarded a potentially needed clone")

    def test_complete_repair_removes_obsolete_clones_but_preserves_current_state(self):
        module = self.root / "module"
        (module / "common").mkdir(parents=True)
        (module / "config/device-font-sources").mkdir(parents=True)
        (module / "config/active_font.conf").write_text("fixture\n")
        target = self.font("opaque")
        source = self.font("source.ttf", family="Custom")
        shutil.copyfile(source, module / "config/device-font-sources/LuoShu-400.ttf")
        shutil.copyfile(ROOT / "common/google_font_provider_patch.py", module / "common/google_font_provider_patch.py")
        cache = module / "config/google-font-provider"
        cache.mkdir()
        old_clone = cache / "previous-selection.ttf"
        shutil.copyfile(source, old_clone)
        script = '''. "$1"
_gfp_unique_namespace_pids() { printf '10\\n'; }
_gfp_mount_in_pid() { _gfp_mount_mode=already; return 0; }
_gfp_apply_once
'''
        env = dict(os.environ, MODDIR=str(module), LUOSHU_GOOGLE_FONT_PYTHON=sys.executable,
                   LUOSHU_GOOGLE_FONT_TARGETS=str(target), LUOSHU_GOOGLE_FONT_ALLOW_RESTART="0")
        subprocess.run(["sh", "-c", script, "sh", str(ROOT / "common/google_font_provider_bridge.sh")],
                       env=env, capture_output=True, check=True)
        current = Path((module / "config/google-font-provider-mounts.conf").read_text().split("|")[1])
        self.assertTrue(current.exists())
        self.assertFalse(old_clone.exists())
        self.assertEqual(list(cache.glob("*.ttf")), [current])

    def test_existing_clone_visible_at_target_reuses_original_cache_entry(self):
        module = self.root / "module"
        (module / "common").mkdir(parents=True)
        (module / "config/device-font-sources").mkdir(parents=True)
        (module / "config/active_font.conf").write_text("fixture\n")
        target = self.font("opaque")
        source = self.font("source.ttf", family="Custom")
        shutil.copyfile(source, module / "config/device-font-sources/LuoShu-400.ttf")
        shutil.copyfile(ROOT / "common/google_font_provider_patch.py", module / "common/google_font_provider_patch.py")
        env = dict(os.environ, MODDIR=str(module), LUOSHU_GOOGLE_FONT_PYTHON=sys.executable,
                   LUOSHU_GOOGLE_FONT_TARGETS=str(target), LUOSHU_GOOGLE_FONT_DRY_RUN="1")
        command = ["sh", str(ROOT / "common/google_font_provider_bridge.sh"), "apply"]
        subprocess.run(command, env=env, check=True, capture_output=True)
        state = module / "config/google-font-provider-mounts.conf"
        first = Path(state.read_text().split("|")[1])
        # A shared mount namespace now exposes our clone at the provider path.
        shutil.copyfile(first, target)
        subprocess.run(command, env=env, check=True, capture_output=True)
        self.assertEqual(Path(state.read_text().split("|")[1]), first)
        self.assertEqual(list((module / "config/google-font-provider").glob("*.ttf")), [first])

    def test_warm_target_inspection_and_new_namespace_do_not_restart_python(self):
        module = self.root / "module"
        (module / "common").mkdir(parents=True)
        (module / "config/device-font-sources").mkdir(parents=True)
        (module / "config/active_font.conf").write_text("fixture\n")
        target = self.font("opaque")
        source = self.font("source.ttf", family="Custom")
        shutil.copyfile(source, module / "config/device-font-sources/LuoShu-400.ttf")
        shutil.copyfile(ROOT / "common/google_font_provider_patch.py", module / "common/google_font_provider_patch.py")
        script = '''. "$1"
_gfp_unique_namespace_pids() { :; }
_gfp_apply_once || exit 10
_gfp_python() { echo unexpected-python >&2; return 99; }
_gfp_apply_once || exit 11
'''
        env = dict(os.environ, MODDIR=str(module), LUOSHU_GOOGLE_FONT_PYTHON=sys.executable,
                   LUOSHU_GOOGLE_FONT_TARGETS=str(target), LUOSHU_GOOGLE_FONT_DRY_RUN="1")
        result = subprocess.run(["sh", "-c", script, "sh", str(ROOT / "common/google_font_provider_bridge.sh")],
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("unexpected-python", result.stderr)

    def test_inspection_cache_invalidates_same_size_timestamp_inode_replacement(self):
        module = self.root / "module"
        (module / "config/google-font-provider").mkdir(parents=True)
        (module / "logs").mkdir()
        target = self.root / "opaque-font"
        target.write_bytes(b"font-fixture")
        candidates = self.root / "targets"
        candidates.write_text(str(target) + "\n")
        script = '''. "$1"
_gfp_python() {
    echo inspected >> "$TEST_ROOT/inspections"
    while IFS= read -r target; do printf '%s\t400\n' "$target"; done < "$2"
}
_gfp_inspect_targets "$TEST_ROOT/targets" "$TEST_ROOT/out" || exit 10
_gfp_inspect_targets "$TEST_ROOT/targets" "$TEST_ROOT/out" || exit 11
cp -p "$TEST_ROOT/opaque-font" "$TEST_ROOT/replacement"
mv "$TEST_ROOT/replacement" "$TEST_ROOT/opaque-font"
_gfp_inspect_targets "$TEST_ROOT/targets" "$TEST_ROOT/out" || exit 12
'''
        result = subprocess.run(["sh", "-c", script, "sh", str(ROOT / "common/google_font_provider_bridge.sh")],
                                env={**os.environ, "MODDIR": str(module), "TEST_ROOT": str(self.root)},
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "inspections").read_text().splitlines(), ["inspected"] * 2)
        self.assertEqual((self.root / "out").read_text(), str(target) + "\t400\n")

    def test_temporary_inspection_error_does_not_commit_negative_cache(self):
        module = self.root / "module"
        (module / "config/google-font-provider").mkdir(parents=True)
        (module / "logs").mkdir()
        target = self.root / "opaque-font"
        target.write_bytes(b"font-fixture")
        (self.root / "targets").write_text(str(target) + "\n")
        script = '''. "$1"
_gfp_python() { echo temporary-runtime-error >&2; return 1; }
_gfp_inspect_targets "$TEST_ROOT/targets" "$TEST_ROOT/out"
[ "$?" = 1 ] && [ ! -e "$INSPECT_CACHE" ] || exit 10
_gfp_python() { while IFS= read -r target; do printf '%s\t400\n' "$target"; done < "$2"; }
_gfp_inspect_targets "$TEST_ROOT/targets" "$TEST_ROOT/out" || exit 11
'''
        result = subprocess.run(["sh", "-c", script, "sh", str(ROOT / "common/google_font_provider_bridge.sh")],
                                env={**os.environ, "MODDIR": str(module), "TEST_ROOT": str(self.root)},
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "out").read_text(), str(target) + "\t400\n")

    def test_unreadable_font_is_a_retryable_batch_failure(self):
        missing = self.root / "removed-during-scan.ttf"
        candidates = self.root / "candidates"
        candidates.write_text(str(missing) + "\n")
        result = subprocess.run([sys.executable, str(ROOT / "common/google_font_provider_patch.py"),
                                 "--inspect-targets", str(candidates)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("provider-target-inspection-failed:", result.stderr)
        self.assertIn("FileNotFoundError", result.stderr)

    def test_one_apply_hashes_shared_full_source_only_once(self):
        module = self.root / "module"
        (module / "common").mkdir(parents=True)
        (module / "config/device-font-sources").mkdir(parents=True)
        (module / "config/active_font.conf").write_text("fixture\n")
        targets = [self.font("regular", weight=400), self.font("bold", weight=700)]
        source = self.font("source.ttf", family="Custom")
        donor = module / "config/device-font-sources/LuoShu-400.ttf"
        shutil.copyfile(source, donor)
        shutil.copyfile(ROOT / "common/google_font_provider_patch.py", module / "common/google_font_provider_patch.py")
        script = '''. "$1"
_gfp_hash_raw() { printf '%s\n' "$1" >> "$TEST_ROOT/hashed"; sha256sum "$1" | awk '{print $1}'; }
_gfp_apply_once
'''
        env = dict(os.environ, MODDIR=str(module), TEST_ROOT=str(self.root),
                   LUOSHU_GOOGLE_FONT_PYTHON=sys.executable,
                   LUOSHU_GOOGLE_FONT_TARGETS="\n".join(map(str, targets)), LUOSHU_GOOGLE_FONT_DRY_RUN="1")
        subprocess.run(["sh", "-c", script, "sh", str(ROOT / "common/google_font_provider_bridge.sh")],
                       env=env, capture_output=True, text=True, check=True)
        self.assertEqual((self.root / "hashed").read_text().splitlines().count(str(donor)), 1)

    def test_background_mount_repair_does_not_force_stop_play(self):
        module = self.root / "module"
        (module / "common").mkdir(parents=True)
        (module / "config/device-font-sources").mkdir(parents=True)
        (module / "config/active_font.conf").write_text("fixture\n")
        target = self.font("opaque")
        source = self.font("source.ttf", family="Custom")
        shutil.copyfile(source, module / "config/device-font-sources/LuoShu-400.ttf")
        shutil.copyfile(ROOT / "common/google_font_provider_patch.py", module / "common/google_font_provider_patch.py")
        marker = self.root / "force-stopped"
        script = '''. "$1"
_gfp_unique_namespace_pids() { printf '10\\n'; }
_gfp_mount_in_pid() { _gfp_mount_mode=plain; return 0; }
am() { printf '%s\\n' "$*" >> "$TEST_RESTARTS"; }
_gfp_apply_once
'''
        env = dict(os.environ, MODDIR=str(module), LUOSHU_GOOGLE_FONT_PYTHON=sys.executable,
                   LUOSHU_GOOGLE_FONT_TARGETS=str(target), TEST_RESTARTS=str(marker),
                   LUOSHU_GOOGLE_FONT_ALLOW_RESTART="0")
        subprocess.run(["sh", "-c", script, "sh", str(ROOT / "common/google_font_provider_bridge.sh")],
                       env=env, capture_output=True, check=True)
        self.assertFalse(marker.exists(), "background repair interrupted the foreground Play app")


if __name__ == "__main__":
    unittest.main()
