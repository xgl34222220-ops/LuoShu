#!/usr/bin/env python3
"""Protected /data/fonts replacement: fs-verity, fontRevision, PostScript name.

Covers common/font_verity.py (ioctl protocol, mocked and real filesystem),
the --protected patch mode, and the provider bridge wiring: verity enabled
before bind, verified after bind with rollback, skip when the kernel lacks
fs-verity, schema bump, and unchanged handling of non-protected targets.
A fake verity interpreter stands in for the kernel so CI file systems that
lack fs-verity still exercise every branch.
"""
from __future__ import annotations

import errno
import importlib.util
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
DEJAVU = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
DEJAVU_BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VERITY = load("luoshu_font_verity", ROOT / "common/font_verity.py")
PATCHER = load("luoshu_provider_patch", ROOT / "common/google_font_provider_patch.py")

FAKE_VERITY = textwrap.dedent("""\
    #!/bin/sh
    # Fake interpreter: $1 is font_verity.py, then the command.
    shift
    cmd="$1"; shift
    printf '%s %s\\n' "$cmd" "$*" >> "$FAKE_VERITY_LOG"
    case "$cmd" in
        enable)
            [ "${FAKE_VERITY_MODE:-supported}" = supported ] || { echo unsupported:ENOTTY; exit 3; }
            [ -e "$1.verity" ] && { echo already; exit 0; }
            printf 'sha256:%s\\n' "$(sha256sum "$1" | cut -d' ' -f1)" > "$1.verity"
            echo enabled ;;
        measure)
            [ "${FAKE_VERITY_MODE:-supported}" = supported ] || { echo unsupported:ENOTTY; exit 3; }
            [ -e "$1.verity" ] || { echo none; exit 4; }
            cat "$1.verity" ;;
        *) echo error:usage; exit 1 ;;
    esac
""")


def google_sans(path: Path, source: Path, revision: float, postscript: str) -> Path:
    with TTFont(source) as font:
        for record in font["name"].names:
            if record.nameID in (1, 16):
                record.string = "Google Sans".encode(record.getEncoding())
            if record.nameID == 6:
                record.string = postscript.encode(record.getEncoding())
        font["head"].fontRevision = revision
        font.save(path)
    return path


def identity(path: Path) -> tuple[float, str]:
    with TTFont(path, lazy=True) as font:
        return float(font["head"].fontRevision), PATCHER.postscript_name(font)


class VerityHelperTest(unittest.TestCase):
    def test_ioctl_numbers_match_uapi(self):
        self.assertEqual(VERITY._ENABLE_SIZE, 128)
        self.assertEqual(VERITY.FS_IOC_ENABLE_VERITY, 0x40806685)
        self.assertEqual(VERITY.FS_IOC_MEASURE_VERITY, 0xC0046686)

    def _run(self, argv, side_effect):
        with tempfile.NamedTemporaryFile() as handle, \
                mock.patch.object(VERITY.fcntl, "ioctl", side_effect=side_effect), \
                mock.patch("builtins.print") as printed:
            args = [a if a != "@" else handle.name for a in argv]
            code = VERITY.main(args)
        return code, printed.call_args[0][0]

    def test_enable_states(self):
        def ok(fd, request, buffer, mutate):
            version, algorithm, block = struct.unpack_from("=III", buffer)
            self.assertEqual((request, version, algorithm), (VERITY.FS_IOC_ENABLE_VERITY, 1, 1))
            self.assertIn(block, (4096, 16384, 65536))
            return 0
        self.assertEqual(self._run(["enable", "@"], ok), (0, "enabled"))
        self.assertEqual(self._run(["enable", "@"], OSError(errno.EEXIST, "x")), (0, "already"))
        self.assertEqual(self._run(["enable", "@"], OSError(errno.ENOTTY, "x")), (3, "unsupported:ENOTTY"))
        self.assertEqual(self._run(["enable", "@"], OSError(errno.EOPNOTSUPP, "x"))[0], 3)
        self.assertEqual(self._run(["enable", "@"], OSError(errno.ETXTBSY, "x")), (1, "error:ETXTBSY"))

    def test_measure_states(self):
        digest = bytes(range(32))

        def ok(fd, request, buffer, mutate):
            self.assertEqual(request, VERITY.FS_IOC_MEASURE_VERITY)
            struct.pack_into("=HH", buffer, 0, 1, 32)
            buffer[4:36] = digest
            return 0
        self.assertEqual(self._run(["measure", "@"], ok), (0, "sha256:" + digest.hex()))
        self.assertEqual(self._run(["measure", "@"], OSError(errno.ENODATA, "x")), (4, "none"))
        self.assertEqual(self._run(["measure", "@"], OSError(errno.ENOTTY, "x"))[0], 3)
        self.assertEqual(self._run(["compare", "@", "@"], ok), (0, "match"))
        self.assertEqual(self._run(["compare", "@", "@"], OSError(errno.ENODATA, "x")), (4, "none"))

    def test_real_filesystem_reports_a_known_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "font.ttf"
            path.write_bytes(DEJAVU.read_bytes())
            result = subprocess.run([sys.executable, str(ROOT / "common/font_verity.py"), "enable", str(path)],
                                    capture_output=True, text=True)
            line = result.stdout.strip()
            self.assertTrue(line in ("enabled", "already") or line.startswith(("unsupported:", "error:")), line)
            if result.returncode == 0:
                measured = subprocess.run([sys.executable, str(ROOT / "common/font_verity.py"), "measure", str(path)],
                                          capture_output=True, text=True)
                self.assertTrue(measured.stdout.startswith("sha256:"), measured.stdout)


class ProtectedPatchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.source = google_sans(self.tmp / "source.ttf", DEJAVU, 1.5, "Donor-Regular")
        self.target = google_sans(self.tmp / "GoogleSans-Regular.ttf", DEJAVU_BOLD, 7.25, "GoogleSans-Regular")

    def test_protected_copies_revision_and_postscript(self):
        output = self.tmp / "out.ttf"
        result = PATCHER.patch(self.source, self.target, output, 400, protected=True)
        self.assertEqual(identity(output), (7.25, "GoogleSans-Regular"))
        self.assertEqual(result["protected"], {"fontRevision": 7.25, "postScriptName": "GoogleSans-Regular"})

    def test_default_mode_is_unchanged(self):
        output = self.tmp / "out.ttf"
        result = PATCHER.patch(self.source, self.target, output, 400)
        self.assertNotIn("protected", result)
        self.assertEqual(identity(output)[0], 1.5)

    def test_cli_flag(self):
        output = self.tmp / "cli.ttf"
        subprocess.run([sys.executable, str(ROOT / "common/google_font_provider_patch.py"), "--source", str(self.source),
                        "--target", str(self.target), "--output", str(output), "--weight", "400", "--protected"],
                       check=True, capture_output=True)
        self.assertEqual(identity(output), (7.25, "GoogleSans-Regular"))


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.mod = self.tmp / "module"
        (self.mod / "common").mkdir(parents=True)
        (self.mod / "config/device-font-sources").mkdir(parents=True)
        (self.mod / "logs").mkdir()
        for name in ("google_font_provider_bridge.sh", "google_font_provider_patch.py", "font_verity.sh",
                     "font_verity.py", "task_scope.sh", "task_scope.py", "runtime_paths.sh", "runtime_paths_lock.py"):
            shutil.copy(ROOT / "common" / name, self.mod / "common" / name)
        (self.mod / "config/active_font.conf").write_text("fixture\n")
        google_sans(self.mod / "config/device-font-sources/LuoShu-700.ttf", DEJAVU, 1.0, "Donor-Bold")
        self.protected_root = self.tmp / "data-fonts"
        (self.protected_root / "files/~~abc==").mkdir(parents=True)
        self.fake = self.tmp / "fake-verity"
        self.fake.write_text(FAKE_VERITY)
        self.fake.chmod(0o755)
        self.calls = self.tmp / "verity-calls.log"
        self.calls.touch()

    def env(self, **extra):
        env = dict(os.environ)
        env.update({
            "MODDIR": str(self.mod),
            "LUOSHU_TASK_SCOPE_PYTHON": sys.executable,
            "LUOSHU_RUNTIME_PATHS_PYTHON": sys.executable,
            "LUOSHU_GOOGLE_FONT_PYTHON": sys.executable,
            "LUOSHU_FONT_VERITY_PYTHON": str(self.fake),
            "LUOSHU_PROTECTED_FONT_ROOT": str(self.protected_root),
            "FAKE_VERITY_LOG": str(self.calls),
        })
        env.update(extra)
        return env

    def apply(self, target: Path, **extra) -> int:
        result = subprocess.run(["sh", str(self.mod / "common/google_font_provider_bridge.sh"), "apply"],
                                env=self.env(LUOSHU_GOOGLE_FONT_TARGETS=str(target), LUOSHU_GOOGLE_FONT_DRY_RUN="1", **extra),
                                capture_output=True, text=True, timeout=300)
        return result.returncode

    def state(self) -> list[list[str]]:
        path = self.mod / "config/google-font-provider-mounts.conf"
        return [line.split("|") for line in path.read_text().splitlines()] if path.exists() else []

    def log(self) -> str:
        path = self.mod / "logs/google-font-provider.log"
        return path.read_text() if path.exists() else ""

    def protected_target(self) -> Path:
        return google_sans(self.protected_root / "files/~~abc==/GoogleSans-700.ttf", DEJAVU_BOLD, 9.5, "GoogleSans-Bold")

    def test_protected_target_gets_verity_and_identity(self):
        target = self.protected_target()
        self.assertEqual(self.apply(target), 0, self.log())
        rows = self.state()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][6], "provider-v4")
        clone = Path(rows[0][1])
        self.assertTrue(Path(str(clone) + ".verity").exists(), "verity not enabled on clone before bind")
        self.assertEqual(identity(clone), (9.5, "GoogleSans-Bold"))
        calls = self.calls.read_text()
        self.assertIn(f"enable {clone}", calls)
        self.assertIn(f"measure {clone}", calls)

    def test_unsupported_kernel_skips_protected_target(self):
        target = self.protected_target()
        self.assertEqual(self.apply(target, FAKE_VERITY_MODE="unsupported"), 2, self.log())
        self.assertEqual(self.state(), [])
        self.assertIn("跳过受保护字体目标（fs-verity 不可用）", self.log())
        self.assertIn("受保护跳过=1", self.log())

    def test_non_protected_target_never_touches_verity(self):
        target = google_sans(self.tmp / "Google_Sans-700-100_0-0_0.ttf", DEJAVU_BOLD, 9.5, "GoogleSans-Bold")
        self.assertEqual(self.apply(target), 0, self.log())
        rows = self.state()
        self.assertEqual(rows[0][6], "provider-v4")
        clone = Path(rows[0][1])
        self.assertEqual(self.calls.read_text(), "")
        self.assertFalse(Path(str(clone) + ".verity").exists())
        self.assertEqual(identity(clone)[0], 1.0, "fontRevision must stay the donor's outside /data/fonts")

    def test_old_schema_cache_is_not_reused(self):
        target = self.protected_target()
        stale = self.mod / ".luoshu-state/cache/google-font-provider/stale.ttf"
        stale.parent.mkdir(parents=True)
        shutil.copy(target, stale)
        sha = lambda p: subprocess.run(["sha256sum", str(p)], capture_output=True, text=True).stdout.split()[0]
        source = self.mod / "config/device-font-sources/LuoShu-700.ttf"
        (self.mod / "config/google-font-provider-mounts.conf").write_text(
            f"{target}|{stale}|{sha(target)}|{sha(stale)}|{sha(source)}|700|provider-v3|1:2\n")
        self.assertEqual(self.apply(target), 0, self.log())
        rows = self.state()
        self.assertNotEqual(rows[0][1], str(stale))
        self.assertEqual(rows[0][6], "provider-v4")

    def run_mount(self, protected: bool, copy_verity: bool) -> tuple[int, str, str]:
        proc = self.tmp / "proc"
        target = "/data/fonts/files/x/GoogleSans-700.ttf"
        rootfile = Path(str(proc / "100/root") + target)
        rootfile.parent.mkdir(parents=True)
        rootfile.write_bytes(b"original" * 200)
        (proc / "100/ns").mkdir(parents=True)
        os.symlink("mnt:[4026531840]", proc / "100/ns/mnt")
        clone = self.tmp / "clone.ttf"
        clone.write_bytes(b"clone" * 300)
        subprocess.run([str(self.fake), "x", "enable", str(clone)], env=self.env(), check=True, capture_output=True)
        digest = (Path(str(clone) + ".verity")).read_text().strip() if protected else ""
        script = textwrap.dedent(f"""\
            . "$MODDIR/common/google_font_provider_bridge.sh"
            _gfp_mount_in_pid() {{
                cp "$2" "$LUOSHU_PROC_ROOT/$1/root$3.new" && mv -f "$LUOSHU_PROC_ROOT/$1/root$3.new" "$LUOSHU_PROC_ROOT/$1/root$3"
                [ "$COPY_VERITY" = 1 ] && cp "$2.verity" "$LUOSHU_PROC_ROOT/$1/root$3.verity"
                _gfp_mount_mode=plain; return 0
            }}
            _gfp_unmount_in_pid() {{ echo unmounted >> "$FAKE_VERITY_LOG"; printf 'original' > "$LUOSHU_PROC_ROOT/$1/root$2"; }}
            _gfp_queue_all_consumers() {{ :; }}
            _gfp_mt_verity='{digest}'
            _gfp_mount_target 100 "$CLONE" "$TARGET"
            rc=$?
            printf '%s|%s' "$rc" "$_gfp_mount_detail"
            """)
        result = subprocess.run(["sh", "-c", script], env=self.env(
            LUOSHU_PROC_ROOT=str(proc), CLONE=str(clone), TARGET=target, COPY_VERITY="1" if copy_verity else "0"),
            capture_output=True, text=True, timeout=60)
        rc, _, detail = result.stdout.strip().rpartition("\n")[2].partition("|")
        journal = self.mod / "config/google-font-provider-namespaces.conf"
        return int(rc), detail, journal.read_text() if journal.exists() else ""

    def test_bind_verified_and_journaled(self):
        rc, detail, journal = self.run_mount(protected=True, copy_verity=True)
        self.assertEqual(rc, 0, detail)
        self.assertIn("/data/fonts/files/x/GoogleSans-700.ttf", journal)
        self.assertNotIn("unmounted", self.calls.read_text())

    def test_bind_without_verity_rolls_back(self):
        rc, detail, journal = self.run_mount(protected=True, copy_verity=False)
        self.assertEqual(rc, 1)
        self.assertTrue(detail.startswith("verity-mismatch:none"), detail)
        self.assertIn("unmounted", self.calls.read_text())
        self.assertEqual(journal, "")

    def test_unprotected_bind_skips_verification(self):
        rc, detail, journal = self.run_mount(protected=False, copy_verity=False)
        self.assertEqual(rc, 0, detail)
        self.assertNotIn("measure", self.calls.read_text().replace(f"enable {self.tmp}/clone.ttf", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
