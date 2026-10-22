#!/usr/bin/env python3
"""Protected /data/fonts replacements: fs-verity, fontRevision, PostScript name.

hwui aborts every app that opens a FontManagerService ``hasVerity`` font whose
visible file lost fs-verity, changed head.fontRevision or changed its
PostScript name. These regressions cover:

* font_verity.py seal/measure/ownership and "unsupported" classification
  (ENOTTY/EOPNOTSUPP/ENOSYS/EINVAL) with a mocked ioctl;
* google_font_provider_patch.py copying the original fontRevision, keeping the
  PostScript name, sealing the clone and producing nothing (exit 3) when the
  device has no fs-verity; non-protected targets keep their old bytes;
* the bridge namespace helper sealing before bind, verifying the visible digest
  after bind and rolling back on mismatch, using fake nsenter/mount/verity;
* the bridge apply pass skipping protected targets safely without fs-verity
  and retiring old unsealed protected binds.

Logic ported from 字域 Ziyu v1.4.8 (GPL-3.0-only); see THIRD_PARTY_NOTICES.md.
"""
from __future__ import annotations

import errno
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "common"
FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VERITY = load("font_verity", COMMON / "font_verity.py")
sys.modules["font_verity"] = VERITY
PATCHER = load("google_provider_patch_verity", COMMON / "google_font_provider_patch.py")


def oserror(code: int) -> OSError:
    return OSError(code, os.strerror(code))


class FontVerityTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.file = self.root / "clone.ttf"
        self.file.write_bytes(b"x" * 4096)

    def fake_ioctl(self, script):
        calls = []

        def ioctl(fd, request, argument, mutate=False):
            calls.append((request, argument if isinstance(argument, bytes) else None))
            action = script.pop(0)
            if isinstance(action, int):
                raise oserror(action)
            if request == VERITY.MEASURE:
                argument[:4] = (1).to_bytes(2, "little") + (32).to_bytes(2, "little")
                argument[4:36] = bytes(range(32))
            return 0
        return ioctl, calls

    def test_seal_enables_then_measures(self):
        ioctl, calls = self.fake_ioctl([errno.ENODATA, "enable", "measure"])
        with mock.patch.object(VERITY.fcntl, "ioctl", ioctl):
            digest = VERITY.seal(self.file)
        self.assertEqual(digest, "01002000" + bytes(range(32)).hex())
        self.assertEqual([call[0] for call in calls], [VERITY.MEASURE, VERITY.ENABLE, VERITY.MEASURE])
        # version 1, SHA-256, 4096-byte blocks (AOSP VerityUtils uses 4096).
        self.assertEqual(calls[1][1][:12], (1).to_bytes(4, "little") + (1).to_bytes(4, "little")
                         + (4096).to_bytes(4, "little"))

    def test_already_sealed_is_only_measured(self):
        ioctl, calls = self.fake_ioctl(["measure"])
        with mock.patch.object(VERITY.fcntl, "ioctl", ioctl):
            VERITY.seal(self.file)
        self.assertEqual([call[0] for call in calls], [VERITY.MEASURE])

    def test_unsupported_kernel_or_filesystem_is_classified(self):
        for code in (errno.ENOTTY, errno.EOPNOTSUPP, errno.ENOSYS):
            with self.subTest(errno=code):
                ioctl, _ = self.fake_ioctl([errno.ENODATA, code])
                with mock.patch.object(VERITY.fcntl, "ioctl", ioctl), \
                        self.assertRaises(VERITY.VerityUnsupported):
                    VERITY.seal(self.file)
            with self.subTest(measure_errno=code):
                ioctl, _ = self.fake_ioctl([code])
                with mock.patch.object(VERITY.fcntl, "ioctl", ioctl), \
                        self.assertRaises(VERITY.VerityUnsupported):
                    VERITY.seal(self.file)

    def test_einval_retries_page_size_then_reports_unsupported(self):
        ioctl, calls = self.fake_ioctl([errno.ENODATA, errno.EINVAL, errno.EINVAL])
        with mock.patch.object(VERITY.os, "sysconf", return_value=16384), \
                mock.patch.object(VERITY.fcntl, "ioctl", ioctl), \
                self.assertRaises(VERITY.VerityUnsupported):
            VERITY.seal(self.file)
        sizes = [int.from_bytes(call[1][8:12], "little") for call in calls if call[0] == VERITY.ENABLE]
        self.assertEqual(sizes, [4096, 16384])

    def test_other_errors_are_failures_not_unsupported(self):
        ioctl, _ = self.fake_ioctl([errno.ENODATA, errno.ETXTBSY])
        with mock.patch.object(VERITY.fcntl, "ioctl", ioctl), self.assertRaises(OSError) as raised:
            VERITY.seal(self.file)
        self.assertNotIsInstance(raised.exception, VERITY.VerityUnsupported)

    def test_symlink_is_refused(self):
        link = self.root / "link.ttf"
        link.symlink_to(self.file)
        with self.assertRaises(ValueError):
            VERITY.seal(link)

    def test_only_module_and_stage_files_are_owned(self):
        module = Path("/data/adb/modules/LuoShu")
        self.assertTrue(VERITY.owned(Path("/data/adb/modules/LuoShu/.luoshu-state/cache/x.ttf"), module))
        self.assertTrue(VERITY.owned(Path("/data/adb/modules_update/LuoShu/x.ttf"), module))
        self.assertTrue(VERITY.owned(Path("/proc/1/root/data/adb/modules/LuoShu/x.ttf"), module))
        self.assertTrue(VERITY.owned(Path("/data/local/tmp/.luoshu-provider-1-2.ttf"), module))
        for path in ("/data/fonts/files/~~a/GoogleSans.ttf", "/data/local/tmp/other.ttf",
                     "/data/adb/modules/LuoShuX/x.ttf", "/data/adb/modules/other/x.ttf"):
            with self.subTest(path=path):
                self.assertFalse(VERITY.owned(Path(path), module))

    def test_cli_refuses_original_update_file(self):
        result = subprocess.run([sys.executable, str(COMMON / "font_verity.py"), "seal", str(self.file)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("refusing", result.stderr)

    def test_shell_wrapper_runs_override_python(self):
        result = subprocess.run(["sh", str(COMMON / "font_verity.sh"), "bogus", str(self.file)],
                                env={**os.environ, "LUOSHU_FONT_VERITY_PYTHON": sys.executable},
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown fs-verity action", result.stderr)


class ProtectedPatchTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source.ttf"
        with TTFont(FONT) as font:
            font["head"].fontRevision = 9.25
            for record in font["name"].names:
                if record.nameID in (1, 16):
                    record.string = "User Font".encode(record.getEncoding())
                if record.nameID == 6:
                    record.string = "UserFont-Regular".encode(record.getEncoding())
            font.save(self.source)
        self.target = self.root / "GoogleSans-Regular.ttf"
        with TTFont(BOLD) as font:
            font["head"].fontRevision = 1.5
            for record in font["name"].names:
                if record.nameID in (1, 16):
                    record.string = "Google Sans".encode(record.getEncoding())
                if record.nameID == 6:
                    record.string = "GoogleSans-Regular".encode(record.getEncoding())
            font.save(self.target)

    def identity(self, path):
        with TTFont(path, lazy=True) as font:
            return float(font["head"].fontRevision), PATCHER.postscript_names(font)

    def test_protected_clone_copies_revision_and_postscript_and_seals(self):
        output = self.root / "out.ttf"
        sealed = []
        with mock.patch.object(VERITY, "seal", lambda path: sealed.append(Path(path)) or "digest"):
            result = PATCHER.patch(self.source, self.target, output, 400, protected=True)
        self.assertEqual(self.identity(output), (1.5, {"GoogleSans-Regular"}))
        self.assertEqual(sealed, [output])
        self.assertTrue(result["protected"])
        self.assertEqual(result["fontRevision"], 1.5)
        self.assertEqual(result["verity"], "digest")

    def test_data_fonts_path_is_protected_by_default(self):
        self.assertTrue(PATCHER.is_protected_target(Path("/data/fonts/files/~~x/GoogleSans.ttf")))
        self.assertFalse(PATCHER.is_protected_target(Path("/data/data/com.google.android.gms/files/fonts/a.ttf")))

    def test_unsupported_verity_leaves_no_clone(self):
        output = self.root / "out.ttf"

        def unsupported(path):
            raise VERITY.VerityUnsupported(errno.ENOTTY, "no verity")
        with mock.patch.object(VERITY, "seal", unsupported), \
                self.assertRaises(PATCHER.ProtectedVerityUnsupported):
            PATCHER.patch(self.source, self.target, output, 400, protected=True)
        self.assertFalse(output.exists())

    def test_seal_failure_leaves_no_clone(self):
        output = self.root / "out.ttf"

        def failure(path):
            raise oserror(errno.ETXTBSY)
        with mock.patch.object(VERITY, "seal", failure), self.assertRaises(OSError):
            PATCHER.patch(self.source, self.target, output, 400, protected=True)
        self.assertFalse(output.exists())

    def test_missing_postscript_name_is_refused_for_protected(self):
        with TTFont(self.target) as font:
            font["name"].names = [r for r in font["name"].names if r.nameID != 6]
            font.save(self.target)
        output = self.root / "out.ttf"
        with mock.patch.object(VERITY, "seal", lambda path: "digest"), \
                self.assertRaises(PATCHER.ProviderPatchError):
            PATCHER.patch(self.source, self.target, output, 400, protected=True)
        self.assertFalse(output.exists())

    def test_non_protected_target_keeps_previous_behaviour(self):
        output = self.root / "out.ttf"
        with mock.patch.object(VERITY, "seal", side_effect=AssertionError("must not seal")):
            result = PATCHER.patch(self.source, self.target, output, 400)
        self.assertNotIn("protected", result)
        revision, names = self.identity(output)
        self.assertEqual(revision, 9.25)  # donor revision, as before this PR
        self.assertEqual(names, {"GoogleSans-Regular"})

    def test_cli_exit_code_three_when_unsupported(self):
        # A tmpfs/overlay test directory has no fs-verity: the CLI must report
        # "unsupported" (3) and produce nothing. Kernels with verity on this
        # filesystem would refuse for ownership-free reasons too; accept 0 only
        # if the output is actually sealed.
        output = self.root / "cli.ttf"
        result = subprocess.run([sys.executable, str(COMMON / "google_font_provider_patch.py"),
                                 "--source", str(self.source), "--target", str(self.target),
                                 "--output", str(output), "--weight", "400", "--protected"],
                                capture_output=True, text=True)
        if result.returncode == 0:
            self.assertTrue(json.loads(result.stdout)["verity"])
        else:
            self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
            self.assertIn("fs-verity-unsupported", result.stdout)
            self.assertFalse(output.exists())


FAKE_NSENTER = """#!/bin/sh
while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do shift; done
shift
exec "$@"
"""

# Bind is simulated by copying the source over the destination and keeping the
# original beside it; verity state is tracked per content digest.
FAKE_MOUNT = """#!/bin/sh
echo "mount $*" >> "$FAKE_EVENTS"
case "$*" in *remount*) exit 0 ;; esac
eval "dst=\\${$#}"
eval "src=\\${$(($# - 1))}"
[ -f "$dst.orig" ] || cp "$dst" "$dst.orig"
cp "$src" "$dst"
"""
FAKE_UMOUNT = """#!/bin/sh
echo "umount $*" >> "$FAKE_EVENTS"
[ "${FAKE_UMOUNT_FAIL:-0}" != 1 ] || exit 1
[ -f "$1.orig" ] && mv -f "$1.orig" "$1"
"""
FAKE_VERITY = """#!/bin/sh
digest=$(sha256sum "$2" | cut -c1-16)
case "$1" in
  seal)
    echo "seal $2" >> "$FAKE_EVENTS"
    [ "${FAKE_VERITY:-ok}" != unsupported ] || { echo unsupported >&2; exit 3; }
    echo "$digest" >> "$FAKE_SEALED"; echo "v:$digest" ;;
  check)
    grep -qx "$digest" "$FAKE_SEALED" 2>/dev/null || exit 1
    [ "${FAKE_VERITY:-ok}" != mismatch ] || { echo v:other; exit 0; }
    echo "v:$digest" ;;
  *) exit 1 ;;
esac
"""


class BridgeProtectedTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name, body in (("nsenter", FAKE_NSENTER), ("mount", FAKE_MOUNT),
                           ("umount", FAKE_UMOUNT), ("verity", FAKE_VERITY)):
            path = self.bin / name
            path.write_text(body)
            path.chmod(0o755)
        self.module = self.root / "module"
        (self.module / "config").mkdir(parents=True)
        (self.module / "logs").mkdir()
        self.protected = self.root / "data/fonts"
        (self.protected / "files").mkdir(parents=True)
        self.target = self.protected / "files/GoogleSans.ttf"
        self.target.write_bytes(b"ORIGINAL" * 256)
        self.clone = self.module / "clone.ttf"
        self.clone.write_bytes(b"REPLACED" * 256)
        self.proc = self.root / "proc"
        (self.proc / "101/ns").mkdir(parents=True)
        (self.proc / "101/ns/mnt").symlink_to("mnt:[101]")
        # The fake namespace shares this filesystem view.
        (self.proc / "101/root").symlink_to("/")
        self.events = self.root / "events"
        self.env = {**os.environ,
                    "PATH": f"{self.bin}:{os.environ['PATH']}",
                    "MODDIR": str(self.module),
                    "LUOSHU_PROC_ROOT": str(self.proc),
                    "LUOSHU_GOOGLE_FONT_NS_SHELL": "sh",
                    "LUOSHU_GOOGLE_FONT_STAGE_DIR": str(self.root / "stage"),
                    "LUOSHU_GOOGLE_FONT_PROTECTED_PREFIX": str(self.protected) + "/",
                    "LUOSHU_FONT_VERITY_TOOL": str(self.bin / "verity"),
                    "LUOSHU_FONT_VERITY_NS_TOOL": str(self.bin / "verity"),
                    "FAKE_EVENTS": str(self.events),
                    "FAKE_SEALED": str(self.root / "sealed"),
                    "LUOSHU_TASK_SCOPE_PID": "1"}

    def run_shell(self, body, **env):
        script = '. "$1"\n' + body
        return subprocess.run(["sh", "-c", script, "verity-test", str(COMMON / "google_font_provider_bridge.sh")],
                              env={**self.env, **env}, capture_output=True, text=True, timeout=30)

    def mount_once(self, **env):
        result = self.run_shell(
            '_gfp_mount_in_pid 101 "$2" "$3"; rc=$?\n'
            'printf "rc=%s mode=%s detail=%s\\n" "$rc" "$_gfp_mount_mode" "$_gfp_mount_detail"\n'
            .replace('"$2" "$3"', f'"{self.clone}" "{self.target}"'), **env)
        self.assertEqual(result.stderr, "")
        return result.stdout.strip()

    def events_list(self):
        return self.events.read_text().splitlines() if self.events.exists() else []

    def test_protected_bind_is_sealed_then_verified(self):
        out = self.mount_once()
        self.assertEqual(out, "rc=0 mode=plain detail=")
        self.assertEqual(self.target.read_bytes(), self.clone.read_bytes())
        events = self.events_list()
        self.assertEqual(events[0], f"seal {self.clone}")
        self.assertTrue(events[1].startswith("mount --bind"))

    def test_unsupported_verity_never_binds(self):
        out = self.mount_once(FAKE_VERITY="unsupported")
        self.assertTrue(out.startswith("rc=1"), out)
        self.assertIn("replacement-not-sealed", out)
        self.assertEqual(self.target.read_bytes(), b"ORIGINAL" * 256)
        self.assertFalse(any(e.startswith("mount --bind") or e.startswith("mount -o bind ")
                             for e in self.events_list()))

    def test_visible_digest_mismatch_rolls_back(self):
        out = self.mount_once(FAKE_VERITY="mismatch")
        self.assertTrue(out.startswith("rc=1"), out)
        self.assertIn("visible-verity-verification-failed", out)
        self.assertEqual(self.target.read_bytes(), b"ORIGINAL" * 256)
        self.assertIn(f"umount {self.target}", self.events_list())

    def test_failed_rollback_is_reported_and_journaled(self):
        result = self.run_shell(
            f'_gfp_mount_target 101 "{self.clone}" "{self.target}"; echo "rc=$? detail=$_gfp_mount_detail"; '
            'cat "$MOUNTS"', FAKE_VERITY="mismatch", FAKE_UMOUNT_FAIL="1")
        self.assertIn("rc=1 detail=verity-verification-and-rollback-failed", result.stdout)
        self.assertIn(f"|{self.target}|", result.stdout)

    def test_non_protected_target_is_not_sealed(self):
        other = self.root / "gms/fonts/GoogleSans.ttf"
        other.parent.mkdir(parents=True)
        other.write_bytes(b"ORIGINAL" * 256)
        result = self.run_shell(f'_gfp_mount_in_pid 101 "{self.clone}" "{other}"; echo "rc=$?"')
        self.assertEqual(result.stdout.strip(), "rc=0")
        self.assertFalse(any(e.startswith("seal") for e in self.events_list()))

    def test_already_visible_but_unsealed_is_rebound(self):
        # Same bytes visible (e.g. an old unsealed bind) are not "already ok".
        self.target.write_bytes(self.clone.read_bytes())
        out = self.mount_once()
        self.assertEqual(out, "rc=0 mode=plain detail=")
        self.assertIn(f"seal {self.clone}", self.events_list())

    def test_retire_old_unsealed_protected_bind(self):
        journal = self.module / "config/google-font-provider-namespaces.conf"
        result = self.run_shell(
            f'''_gfp_unmount_in_pid() {{ echo "unmount:$1:$2" >> "$FAKE_EVENTS"; rm -f "$LUOSHU_PROC_ROOT/$1/root$2"; }}
rm -f "{self.target}"
ln "{self.clone}" "{self.target}"
id=$(_gfp_identity "{self.clone}")
printf 'mnt:[101]|{self.target}|%s|{self.clone}\\n' "$id" > "$MOUNTS"
printf '{self.target}|{self.clone}|a|b|c|400|provider-v3|x\\n' > "$STATE"
_gfp_namespace_pid_list=101
_gfp_retire_unsealed_protected; echo "rc=$?"''')
        self.assertIn("rc=0", result.stdout, result.stderr)
        self.assertIn(f"unmount:101:{self.target}", self.events_list())
        self.assertTrue(journal.exists())

    def test_sealed_v4_bind_is_not_retired(self):
        result = self.run_shell(
            f'''_gfp_unmount_in_pid() {{ echo "unmount:$1:$2" >> "$FAKE_EVENTS"; }}
printf 'mnt:[101]|{self.target}|1:2:3|{self.clone}\\n' > "$MOUNTS"
printf '{self.target}|{self.clone}|a|b|c|400|provider-v4-verity|x\\n' > "$STATE"
_gfp_namespace_pid_list=101
_gfp_retire_unsealed_protected; echo "rc=$?"''')
        self.assertIn("rc=0", result.stdout, result.stderr)
        self.assertEqual(self.events_list(), [])


class BridgeApplyFallbackTest(unittest.TestCase):
    """End to end: a protected target without fs-verity is skipped, not bound."""

    def test_apply_skips_protected_target_without_verity(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            module = root / "module"
            (module / "common").mkdir(parents=True)
            (module / "config/device-font-sources").mkdir(parents=True)
            for name in ("google_font_provider_bridge.sh", "google_font_provider_patch.py", "font_verity.py",
                         "font_verity.sh", "task_scope.sh", "task_scope.py", "runtime_paths.sh",
                         "runtime_paths_lock.py"):
                shutil.copy(COMMON / name, module / "common" / name)
            (module / "config/active_font.conf").write_text("fixture\n")
            shutil.copy(FONT, module / "config/device-font-sources/LuoShu-400.ttf")
            protected = root / "data/fonts"
            target = protected / "files/GoogleSans-400.ttf"
            target.parent.mkdir(parents=True)
            with TTFont(BOLD) as font:
                for record in font["name"].names:
                    if record.nameID in (1, 16):
                        record.string = "Google Sans".encode(record.getEncoding())
                font.save(target)
            original = target.read_bytes()
            bin_dir = root / "bin"
            bin_dir.mkdir()
            env = {**os.environ,
                   "MODDIR": str(module),
                   "LUOSHU_GOOGLE_FONT_PYTHON": sys.executable,
                   "LUOSHU_TASK_SCOPE_PYTHON": sys.executable,
                   "LUOSHU_RUNTIME_PATHS_PYTHON": sys.executable,
                   "LUOSHU_GOOGLE_FONT_TARGETS": str(target),
                   "LUOSHU_GOOGLE_FONT_PROTECTED_PREFIX": str(protected) + "/",
                   "LUOSHU_GOOGLE_FONT_DRY_RUN": "1",
                   "LUOSHU_GOOGLE_FONT_RETRIES": "1"}
            # Force the patcher's protected branch on this (non-/data) path and
            # make the real seal report "unsupported" via a sitecustomize shim.
            shim = root / "shim"
            shim.mkdir()
            (shim / "sitecustomize.py").write_text(
                "import errno, sys\n"
                "sys.path.insert(0, %r)\n"
                "import font_verity\n"
                "def _seal(path):\n"
                "    raise font_verity.VerityUnsupported(errno.ENOTTY, 'no fs-verity')\n"
                "font_verity.seal = _seal\n" % str(module / "common"))
            env["PYTHONPATH"] = str(shim)
            result = subprocess.run(["sh", str(module / "common/google_font_provider_bridge.sh"), "apply"],
                                    env=env, capture_output=True, text=True, timeout=110)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertEqual(target.read_bytes(), original)
            log = next(module.rglob("google-font-provider.log")).read_text()
            self.assertIn("设备不支持 fs-verity", log)
            self.assertIn("受保护跳过(无fs-verity)=1", log)
            self.assertFalse((module / "config/google-font-provider-mounts.conf").exists())
            self.assertFalse(list(module.rglob("google-font-provider/*.ttf")))
            marker = list(module.rglob("verity-unsupported.boot"))
            self.assertEqual(len(marker), 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
