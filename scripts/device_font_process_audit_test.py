#!/usr/bin/env python3
"""Fixture tests for the read-only per-process font audit and inode-aware xmlParity."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "common"))
import device_font_process_audit as audit  # noqa: E402
import device_font_xml_parity as parity  # noqa: E402


def maps_line(path: str, ident: tuple[int, int] | None, start: int = 0x7000) -> str:
    dev, ino = ident or (0, 0)
    return (f"{start:x}-{start + 0x1000:x} r--p 00000000 "
            f"{os.major(dev):02x}:{os.minor(dev):02x} {ino}                  {path}\n")


def fake_stat(table: dict[str, tuple[int, int, int]]):
    def stat(path: str):
        if path not in table:
            raise FileNotFoundError(path)
        dev, ino, size = table[path]
        return SimpleNamespace(st_dev=dev, st_ino=ino, st_size=size)
    return stat


class MapsParsingTest(unittest.TestCase):
    def test_only_font_files_deduplicated_and_memfd_counted(self):
        dev = os.makedev(253, 5)
        text = (maps_line("/system/fonts/MiSansVF.ttf", (dev, 11))
                + maps_line("/system/fonts/MiSansVF.ttf", (dev, 11), 0x9000)
                + maps_line("/system/lib64/libc.so", (dev, 12))
                + maps_line("/data/app/x/base.apk", (dev, 13))
                + maps_line("/memfd:fontmap (deleted)", None)
                + maps_line("/product/fonts/MiSansRoundedSC.ttf (deleted)", (dev, 14))
                + "garbage line\n")
        entries, memfd = audit.parse_maps(text)
        self.assertEqual(1, memfd)
        self.assertEqual(["/system/fonts/MiSansVF.ttf", "/product/fonts/MiSansRoundedSC.ttf"],
                         [e["path"] for e in entries])
        self.assertEqual((dev, 11), entries[0]["identity"])
        self.assertTrue(entries[1]["deleted"])

    def test_location_classes(self):
        self.assertEqual("stock", audit.location_class("/system/fonts/Roboto-Regular.ttf"))
        self.assertEqual("stock", audit.location_class("/system/product/fonts/MiSansTCVF.ttf"))
        self.assertEqual("stock", audit.location_class("/product/fonts/MiClock.otf"))
        self.assertEqual("theme", audit.location_class("/data/system/theme/fonts/Roboto-Regular.ttf"))
        self.assertEqual("updatable", audit.location_class("/data/fonts/files/~~a/b/Emoji.ttf"))
        self.assertEqual("other", audit.location_class("/data/user/0/com.x/files/a.ttf"))


class ClassifyTest(unittest.TestCase):
    """Fixture stat data: payload inode 100 is mounted over /system/fonts/MiSansVF.ttf."""

    def setUp(self):
        self.dev = os.makedev(253, 5)
        self.payload_dev = os.makedev(254, 40)
        self.module = Path("/m")
        self.table = {
            "/m/.luoshu-payload/system/fonts/MiSansVF.ttf": (self.payload_dev, 100, 10),
            "/m/.luoshu-payload/product/fonts/MiSansRoundedSC.ttf": (self.payload_dev, 101, 10),
            "/system/fonts/MiSansVF.ttf": (self.payload_dev, 100, 10),
            "/product/fonts/MiSansRoundedSC.ttf": (self.payload_dev, 101, 10),
            "/system/fonts/NotoColorEmoji.ttf": (self.dev, 7, 10),
        }

    def payload(self) -> audit.PayloadIndex:
        index = audit.PayloadIndex(None)
        stat = fake_stat(self.table)
        for full in self.table:
            if full.startswith("/m/.luoshu-payload/"):
                st = stat(full)
                rel = full[len("/m/.luoshu-payload/"):]
                index.ids.add((st.st_dev, st.st_ino))
                index.by_rel[rel] = {"path": Path(full), "identity": (st.st_dev, st.st_ino), "size": st.st_size}
        return index

    def run_one(self, name: str, maps: str) -> dict[str, str]:
        entries, memfd = audit.parse_maps(maps)
        items = audit.classify(entries, self.payload(), "/", fake_stat(self.table))
        return audit.summarize(name, items, memfd)

    def test_luoshu_inode_is_a_hit(self):
        report = self.run_one("systemui", maps_line("/system/fonts/MiSansVF.ttf", (self.payload_dev, 100)))
        self.assertEqual("1", report["systemui.luoshuHits"])
        self.assertEqual("0", report["systemui.stockHits"])
        self.assertIn("/system/fonts/MiSansVF.ttf@254.40:100", report["systemui.luoshuPaths"])

    def test_same_name_but_stock_inode_is_gap(self):
        # SystemUI mapped the original MiSansRoundedSC (inode 55) before / around the mount.
        maps = (maps_line("/product/fonts/MiSansRoundedSC.ttf", (self.dev, 55))
                + maps_line("/system/fonts/NotoColorEmoji.ttf", (self.dev, 7)))
        report = self.run_one("systemui", maps)
        self.assertEqual("2", report["systemui.loadedFonts"])
        self.assertEqual("0", report["systemui.luoshuHits"])
        self.assertEqual("2", report["systemui.stockHits"])
        self.assertEqual("1", report["systemui.stockOnReplacedSlot"])
        self.assertIn("MiSansRoundedSC.ttf@253.5:55:loaded-before-mount", report["systemui.replacedSlotStockPaths"])

    def test_verdict_rules(self):
        report = {"systemServer.stockHits": "30", "systemServer.stockOnReplacedSlot": "0",
                  "systemui.stockHits": "2", "systemui.stockOnReplacedSlot": "1",
                  "launcher.stockHits": "0", "launcher.stockOnReplacedSlot": "0"}
        self.assertEqual("gap:systemui=2/1", audit.verdict(report, ["systemServer", "systemui", "launcher"], 5))
        report["systemServer.stockOnReplacedSlot"] = "1"
        self.assertEqual("gap:systemServer=30/1,systemui=2/1",
                         audit.verdict(report, ["systemServer", "systemui", "launcher"], 5))
        self.assertEqual("ok", audit.verdict({"launcher.stockHits": "0"}, ["launcher"], 5))
        self.assertEqual("inactive:no-payload", audit.verdict(report, ["systemui"], 0))
        self.assertEqual("unknown:no-process-readable", audit.verdict({}, [], 3))


class CliFixtureTest(unittest.TestCase):
    """Real files in a temp tree: the visible root plays /, payload files are real inodes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="luoshu-audit-")
        self.base = Path(self.tmp.name)
        self.module = self.base / "module"
        self.visible = self.base / "visible"
        self.proc = self.base / "proc"
        payload = self.module / ".luoshu-payload/system/fonts"
        payload.mkdir(parents=True)
        (self.module / "config").mkdir()
        (payload / "MiSansVF.ttf").write_bytes(b"luoshu-payload")
        (self.visible / "system/fonts").mkdir(parents=True)
        # A "bind mount": the visible slot is a hard link to the payload inode.
        os.link(payload / "MiSansVF.ttf", self.visible / "system/fonts/MiSansVF.ttf")
        (self.visible / "system/fonts/Roboto-Regular.ttf").write_bytes(b"stock")
        self.stock_old = self.base / "stock-MiSansVF.ttf"
        self.stock_old.write_bytes(b"stock-misans")

    def tearDown(self):
        self.tmp.cleanup()

    def ident(self, path: Path) -> tuple[int, int]:
        st = os.stat(path)
        return (st.st_dev, st.st_ino)

    def write_maps(self, pid: str, body: str) -> None:
        (self.proc / pid).mkdir(parents=True, exist_ok=True)
        (self.proc / pid / "maps").write_text(body)

    def run_cli(self, *targets: str) -> dict[str, str]:
        out = self.module / "config/device-font-process-audit.conf"
        result = subprocess.run([
            sys.executable, str(ROOT / "common/device_font_process_audit.py"),
            *[arg for t in targets for arg in ("--target", t)],
            "--proc-root", str(self.proc), "--module", str(self.module),
            "--visible-root", str(self.visible), "--output", str(out),
        ], capture_output=True, text=True, timeout=60)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(result.stdout, out.read_text())
        return dict(line.split("=", 1) for line in out.read_text().splitlines() if "=" in line)

    def test_systemui_still_loading_stock_is_reported(self):
        vf = self.ident(self.visible / "system/fonts/MiSansVF.ttf")
        roboto = self.ident(self.visible / "system/fonts/Roboto-Regular.ttf")
        old = self.ident(self.stock_old)
        self.write_maps("100", maps_line("/system/fonts/MiSansVF.ttf", vf)
                        + maps_line("/system/fonts/Roboto-Regular.ttf", roboto))
        self.write_maps("200", maps_line("/system/fonts/MiSansVF.ttf", old)
                        + maps_line("/data/user/0/com.secret.app/files/brand.ttf", roboto))
        self.write_maps("300", maps_line("/system/fonts/MiSansVF.ttf", vf))
        report = self.run_cli("systemServer=100", "systemui=200", "launcher=300@com.miui.home", "webview=")
        self.assertEqual("1", report["payloadFiles"])
        self.assertEqual("systemServer,systemui,launcher", report["audited"])
        self.assertEqual("gap:systemui=1/1", report["fontAudit"])
        self.assertEqual("1", report["systemServer.luoshuHits"])
        self.assertEqual("1", report["systemServer.stockHits"])
        self.assertEqual("0", report["systemServer.stockOnReplacedSlot"])
        self.assertEqual("1", report["systemui.stockOnReplacedSlot"])
        self.assertIn("loaded-before-mount", report["systemui.replacedSlotStockPaths"])
        self.assertEqual("brand.ttf", report["systemui.otherFiles"])
        self.assertNotIn("com.secret.app", "\n".join(report.values()))
        self.assertEqual("com.miui.home", report["launcher.package"])
        self.assertEqual("1", report["launcher.luoshuHits"])
        self.assertEqual("not-running", report["webview.state"])

    def test_unreadable_maps_and_no_payload(self):
        shutil.rmtree(self.module / ".luoshu-payload")
        report = self.run_cli("systemui=999")
        self.assertEqual("exited", report["systemui.state"])  # /proc/999 does not exist
        self.assertEqual("inactive:no-payload", report["fontAudit"])

    def _report(self, *targets: str) -> dict[str, str]:
        args = SimpleNamespace(target=list(targets), proc_root=str(self.proc), module=self.module,
                               visible_root=str(self.visible))
        return audit.build_report(args)

    def test_exited_process_is_not_unreadable(self):
        # Gone from /proc (ENOENT), pid reused by another program, zombie with empty maps.
        (self.proc / "501").mkdir(parents=True)
        (self.proc / "501" / "cmdline").write_bytes(b"com.other.app\0")
        (self.proc / "501" / "maps").mkdir()  # EISDIR: not an exit errno, but cmdline changed
        (self.proc / "502").mkdir(parents=True)
        (self.proc / "502" / "cmdline").write_bytes(b"")
        (self.proc / "502" / "maps").write_text("")
        report = self._report("a=999@com.example.a", "b=501@com.example.b", "c=502@com.example.c")
        self.assertEqual(["exited"] * 3, [report["a.state"], report["b.state"], report["c.state"]])
        self.assertNotIn("a.mapsError", report)
        self.assertEqual("unknown:no-process-readable", report["fontAudit"])

    def test_esrch_means_exited_and_eacces_stays_unreadable(self):
        import errno
        from unittest import mock
        (self.proc / "601").mkdir(parents=True)
        (self.proc / "601" / "cmdline").write_bytes(b"com.example.d:remote\0")
        (self.proc / "601" / "maps").write_text("")
        real = Path.read_text

        def denied(code):
            def read_text(path, *a, **k):
                if path.name == "maps":
                    raise OSError(code, os.strerror(code), str(path))
                return real(path, *a, **k)
            return read_text
        with mock.patch.object(Path, "read_text", denied(errno.EACCES)):
            report = self._report("d=601@com.example.d:remote")
        self.assertEqual(("maps-unreadable", "EACCES"), (report["d.state"], report["d.mapsError"]))
        with mock.patch.object(Path, "read_text", denied(errno.ESRCH)):
            report = self._report("d=601@com.example.d:remote")
        self.assertEqual("exited", report["d.state"])
        # Live process, same program, maps is a directory: genuinely unreadable.
        (self.proc / "601" / "maps").unlink()
        (self.proc / "601" / "maps").mkdir()
        report = self._report("d=601@com.example.d")
        self.assertEqual(("maps-unreadable", "EISDIR"), (report["d.state"], report["d.mapsError"]))

    def test_cli_is_read_only(self):
        self.write_maps("100", maps_line("/system/fonts/MiSansVF.ttf", self.ident(self.stock_old)))
        before = {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file() and "config" not in p.parts}
        self.run_cli("systemui=100")
        after = {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file() and "config" not in p.parts}
        self.assertEqual(before, after)


class XmlParityIdentityTest(unittest.TestCase):
    """xmlParity must not say ok when the same-named file is still the stock inode."""

    FONTS = """<familyset><family name="sans-serif"><font weight="400">Roboto-Regular.ttf</font></family>
<family lang="zh-Hans"><font weight="400">MiSansVF.ttf</font></family></familyset>"""
    DUMP = ("Named Family List\n  Named Family (sans-serif)\n    Family\n"
            "      Font {path = /system/fonts/Roboto-Regular.ttf, index = 0, weight = 400, slant = 0}\n"
            "Dump Fallback Families\n  Fallback Family [0]: lang=\"zh-Hans\"\n"
            "      Font {path = /system/fonts/MiSansVF.ttf, index = 0, weight = 400, slant = 0}\n")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="luoshu-parity-ino-")
        self.base = Path(self.tmp.name)
        self.module = self.base / "module"
        payload = self.module / ".luoshu-payload/system/fonts"
        payload.mkdir(parents=True)
        (payload / "MiSansVF.ttf").write_bytes(b"luoshu")
        self.visible = self.base / "visible"
        (self.visible / "system/fonts").mkdir(parents=True)
        (self.visible / "system/fonts/Roboto-Regular.ttf").write_bytes(b"stock roboto")

    def tearDown(self):
        self.tmp.cleanup()

    def compare(self) -> str:
        identity = parity.IdentityCheck(audit.PayloadIndex(self.module), str(self.visible))
        fm = parity.parse_font_dump(self.DUMP)
        fx = parity.parse_font_xml(parity.ET.fromstring(self.FONTS))
        self.assertEqual("MiSansVF.ttf", fm["zh-Hans"])
        self.assertEqual(fm["zh-Hans"], fx["zh-Hans"])
        return parity.compare(fm, fx, parity.parse_font_xml(None), identity)

    def test_same_name_stock_file_is_mismatch(self):
        (self.visible / "system/fonts/MiSansVF.ttf").write_bytes(b"stock misans")
        result = self.compare()
        self.assertTrue(result.startswith("mismatch:zh-Hans(stock-inode:fm=MiSansVF.ttf@"), result)
        self.assertNotIn("sans-serif", result)  # Roboto was never replaced: name parity suffices

    def test_luoshu_inode_is_ok(self):
        os.link(self.module / ".luoshu-payload/system/fonts/MiSansVF.ttf",
                self.visible / "system/fonts/MiSansVF.ttf")
        self.assertEqual("ok", self.compare())

    def test_overlay_copy_with_same_content_is_ok(self):
        (self.visible / "system/fonts/MiSansVF.ttf").write_bytes(b"luoshu")
        self.assertEqual("ok", self.compare())

    def test_without_identity_name_parity_unchanged(self):
        (self.visible / "system/fonts/MiSansVF.ttf").write_bytes(b"stock misans")
        fm = parity.parse_font_dump(self.DUMP)
        fx = parity.parse_font_xml(parity.ET.fromstring(self.FONTS))
        self.assertEqual("ok", parity.compare(fm, fx, parity.parse_font_xml(None)))


class ShellEntryTest(unittest.TestCase):
    def test_audit_subcommand_resolves_launcher_and_writes_conf(self):
        with tempfile.TemporaryDirectory(prefix="luoshu-audit-sh-") as td:
            base = Path(td)
            module = base / "module"
            (module / "common").mkdir(parents=True)
            (module / "config").mkdir()
            for name in ("device_font_load_verify.sh", "device_font_process_audit.py"):
                (module / "common" / name).write_bytes((ROOT / "common" / name).read_bytes())
            payload = module / ".luoshu-payload/system/fonts"
            payload.mkdir(parents=True)
            (payload / "MiSansVF.ttf").write_bytes(b"luoshu")
            visible = base / "visible"
            (visible / "system/fonts").mkdir(parents=True)
            (visible / "system/fonts/MiSansVF.ttf").write_bytes(b"stock")
            st = os.stat(visible / "system/fonts/MiSansVF.ttf")
            proc = base / "proc"
            (proc / "4242").mkdir(parents=True)
            (proc / "4242/maps").write_text(maps_line("/system/fonts/MiSansVF.ttf", (st.st_dev, st.st_ino)))
            bindir = base / "bin"
            bindir.mkdir()
            (bindir / "cmd").write_text(
                "#!/bin/sh\n"
                "[ \"$1 $2\" = 'package resolve-activity' ] && { echo 'priority=0'; echo 'com.example.home/.Home'; exit 0; }\n"
                "echo FORBIDDEN >&2; exit 99\n")
            (bindir / "pidof").write_text(
                "#!/bin/sh\ncase \"$1\" in com.android.systemui) echo 4242 ;; com.example.home) echo '77 78' ;; *) exit 1 ;; esac\n")
            (bindir / "ps").write_text("#!/bin/sh\nexit 0\n")
            for tool in ("cmd", "pidof", "ps"):
                (bindir / tool).chmod(0o755)
            env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", MODDIR=str(module),
                       MODULE_DIR=str(module), LUOSHU_VISIBLE_ROOT=str(visible), LUOSHU_PROC_ROOT=str(proc))
            result = subprocess.run(["sh", str(module / "common/device_font_load_verify.sh"), "audit"],
                                    env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertNotIn("FORBIDDEN", result.stderr)
            self.assertIn("fontAudit=gap:systemui=1/1", result.stdout)
            conf = (module / "config/device-font-process-audit.conf").read_text()
            self.assertIn("launcher.package=com.example.home", conf)
            self.assertIn("launcher.state=exited", conf)  # pid 77 has no /proc entry: exited
            self.assertIn("systemServer.state=not-running", conf)
            self.assertNotIn("webview.", conf)


if __name__ == "__main__":
    unittest.main()
