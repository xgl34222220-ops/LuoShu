#!/usr/bin/env python3
"""Fixture tests for common/umount_visibility.{py,sh} (coverage export umountVisibility).

A fake /proc carries cmdline/status/mountinfo/ns links; the facts script runs
against stub ksud/magisk/dmesg binaries on PATH and a fake modules directory.
No device, no root, nothing mounted.
"""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "common"))
import font_coverage_locator as locator  # noqa: E402
import umount_visibility as uv  # noqa: E402

LUOSHU_OVERLAY = ("101 30 0:88 / /system/fonts ro,relatime shared:5 - overlay KSU "
                  "ro,lowerdir=/data/adb/modules/LuoShu/.luoshu-payload/system/fonts:/data/adb/luoshu/self-mount/lower/system_fonts\n")
LUOSHU_BIND = ("102 30 254:40 /adb/modules/LuoShu/.luoshu-payload/product/fonts/MiSansVF.ttf "
               "/product/fonts/MiSansVF.ttf ro,relatime - f2fs /dev/block/dm-40 rw\n")
STOCK = ("20 1 253:0 / / ro,relatime - ext4 /dev/root ro\n"
         "30 20 253:1 / /system ro - ext4 /dev/block/dm-1 ro\n")
OTHER_MODULE = "110 20 0:90 / /product ro - overlay KSU ro,lowerdir=/data/adb/modules/other/product\n"

FACTS_KSU_NEO = """schema=luoshu-umount-facts-v1
manager=KernelSU
ksudVersion=ksud 3.3.0
ksuKernelVersion=33000
kernelUmount=1
webviewZygoteUmount=0
zygiskModule=zygisksu|NeoZygisk|v2.3 (310)|enabled
kernelUmountManagedBy=zygisksu
preloadModule=absent
dmesgReadable=1
dmesgUmountUid=17
dmesgUmountFonts=3
"""


class ProcFixture:
    def __init__(self, base: Path):
        self.root = base / "proc"
        self.root.mkdir()

    def add(self, pid: int, name: str, *, uid: int = 0, ppid: int = 1, mountinfo: str | None = STOCK,
            ns: str = "mnt:[4026531840]") -> None:
        d = self.root / str(pid)
        d.mkdir()
        (d / "cmdline").write_bytes(name.encode() + b"\0--flag\0")
        (d / "status").write_text(f"Name:\t{name[:15]}\nPPid:\t{ppid}\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n")
        if mountinfo is not None:
            (d / "mountinfo").write_text(mountinfo)
        (d / "ns").mkdir()
        os.symlink(ns, d / "ns" / "mnt")


class UmountVisibilityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.module = self.base / "modules" / "LuoShu"
        (self.module / "common").mkdir(parents=True)
        self.proc = ProcFixture(self.base)
        host = STOCK + LUOSHU_OVERLAY + LUOSHU_BIND
        self.proc.add(1, "/system/bin/init", mountinfo=host)
        self.proc.add(900, "system_server", uid=1000, ns="mnt:[1]", mountinfo=host)
        self.proc.add(700, "zygote64", ns="mnt:[1]", mountinfo=host)

    def build(self, facts=FACTS_KSU_NEO, probe=None):
        return uv.build(module=self.module, proc_root=self.proc.root, facts_text=facts, probe=probe)

    # ------------------------------------------------------------ parsing
    def test_mountinfo_counts_luoshu_overlay_and_bind_with_source_names(self):
        rows = uv.parse_mountinfo(STOCK + LUOSHU_OVERLAY + LUOSHU_BIND + OTHER_MODULE)
        summary = uv.mount_summary(rows, uv.module_markers(self.module))
        self.assertEqual(2, summary["fontMounts"])
        self.assertEqual(2, summary["luoshuMounts"])
        self.assertEqual(2, summary["moduleFontMounts"])  # overlay source KSU; bind root /adb/modules
        self.assertEqual(["/dev/block/dm-40", "KSU"], summary["luoshuSources"])

    def test_real_coloros_bind_mode_mountinfo(self):
        # Shape of a ColorOS 17 / KernelSU export (2026-10-22): per-file binds of
        # fonts and font XML from .luoshu-payload, the captured stock lower and the
        # payload-to-module-dir binds that are not font targets.
        text = STOCK + "".join(
            f"{200 + i} 30 254:40 {root} {target} rw,nosuid,nodev,noatime - f2fs /dev/block/dm-40 rw\n"
            for i, (root, target) in enumerate([
                ("/adb/modules/LuoShu/.luoshu-payload/system_ext/etc/fonts_base.xml", "/system_ext/etc/fonts_base.xml"),
                ("/adb/modules/LuoShu/.luoshu-payload/system", "/data/adb/modules/LuoShu/system"),
                ("/adb/modules/LuoShu/.luoshu-payload/system/fonts/SysSans-Hans-Regular.ttf",
                 "/system/fonts/SysSans-Hans-Regular.ttf"),
                ("/adb/modules/LuoShu/.luoshu-payload/system/etc/fonts.xml", "/system/etc/fonts.xml"),
                ("/adb/modules/LuoShu/.luoshu-payload/system/etc/font_fallback.xml", "/system/etc/font_fallback.xml"),
            ])) + "260 30 253:5 /system/fonts /data/adb/luoshu/self-mount/lower/system-fonts ro - erofs /dev/block/dm-5 ro\n"
        summary = uv.mount_summary(uv.parse_mountinfo(text), uv.module_markers(self.module))
        self.assertEqual((4, 4, 4), (summary["fontMounts"], summary["luoshuMounts"], summary["moduleFontMounts"]))

    def test_bind_root_counts_as_root_trace(self):
        rows = uv.parse_mountinfo(LUOSHU_BIND)
        self.assertTrue(uv._is_root_trace(rows[0]))

    def test_facts_parse_sanitizes_and_lists_modules(self):
        facts = uv.parse_facts(FACTS_KSU_NEO + "bad key=x\nmanager2=a;rm -rf /\n")
        self.assertEqual("1", facts["kernelUmount"])
        self.assertEqual("NeoZygisk", facts["zygiskModule"][0]["name"])
        self.assertNotIn("bad key", facts)
        self.assertNotIn(";", facts["manager2"])
        self.assertEqual("NeoZygisk", uv.zygisk_impl(facts)["impl"])

    def test_zygisk_impl_name_decides_shared_id_and_magisk_builtin(self):
        next_ = uv.parse_facts("zygiskModule=zygisksu|Zygisk Next|1.2|enabled\n")
        self.assertEqual("ZygiskNext", uv.zygisk_impl(next_)["impl"])
        rez = uv.parse_facts("zygiskModule=rezygisk|ReZygisk|1.0|disabled\nmagiskZygisk=1\n")
        self.assertEqual("MagiskBuiltin", uv.zygisk_impl(rez)["impl"])
        self.assertEqual("none", uv.zygisk_impl(uv.parse_facts(""))["impl"])

    # ------------------------------------------------------------ verdicts
    def test_kernel_umount_per_app_partial_and_webview_visible(self):
        self.proc.add(1200, "com.android.systemui", uid=10120, ppid=700, ns="mnt:[1]",
                      mountinfo=STOCK + LUOSHU_OVERLAY + LUOSHU_BIND)
        self.proc.add(1300, "com.bank.app", uid=10300, ppid=700, ns="mnt:[2]", mountinfo=STOCK)
        self.proc.add(1301, "com.bank.app:push", uid=1010300, ppid=700, ns="mnt:[3]", mountinfo=STOCK)
        self.proc.add(800, "webview_zygote", uid=1053, ppid=700, ns="mnt:[1]",
                      mountinfo=STOCK + LUOSHU_OVERLAY)
        self.proc.add(1400, "com.google.android.webview:sandboxed_process0:org.chromium.X0:0",
                      uid=99001, ppid=800, ns="mnt:[1]", mountinfo=STOCK + LUOSHU_OVERLAY)
        data = self.build(facts=FACTS_KSU_NEO.replace("NeoZygisk", "Zygisk Next"))
        procs = data["processes"]
        self.assertEqual("visible", procs["init"]["verdict"])
        self.assertEqual("visible", procs["system_server"]["verdict"])
        self.assertEqual(3, procs["apps"]["checked"])
        self.assertEqual(2, procs["apps"]["unmounted"])
        self.assertEqual("webview_zygote", procs["webviewRenderers"][0]["parent"])
        self.assertIn("KSU", data["overlaySources"])
        c = data["conclusion"]
        self.assertEqual(("partial", "visible"), (c["app"], c["webview"]))
        self.assertIn("kernel_umount-per-app", c["causes"])
        self.assertIn("2/3", c["summary"])
        self.assertIn("WebView：可见", c["summary"])
        self.assertEqual(17, data["dmesg"]["umountForUid"])
        self.assertTrue(data["readOnly"])

    def test_webview_zygote_umount_switch_is_named(self):
        self.proc.add(800, "webview_zygote", uid=1053, ns="mnt:[9]", mountinfo=STOCK)
        facts = FACTS_KSU_NEO.replace("webviewZygoteUmount=0", "webviewZygoteUmount=1") \
            .replace("zygiskModule=zygisksu|NeoZygisk|v2.3 (310)|enabled\n", "")
        c = self.build(facts=facts)["conclusion"]
        self.assertEqual("unmounted", c["webview"])
        self.assertIn("webview_zygote_umount", c["causes"])
        self.assertIn("webview_zygote_umount 卸载", c["summary"])

    def test_neozygisk_forces_webview_and_flags_ksu_source(self):
        self.proc.add(800, "webview_zygote", uid=1053, ns="mnt:[9]", mountinfo=STOCK)
        self.proc.add(1300, "com.bank.app", uid=10300, ns="mnt:[2]", mountinfo=STOCK)
        data = self.build()
        c = data["conclusion"]
        self.assertEqual("NeoZygisk", data["zygisk"]["impl"])
        self.assertIn("neozygisk-webview-denylist", c["causes"])
        self.assertIn("neozygisk-source-match", c["causes"])
        self.assertEqual(2, data["neoZygisk"]["luoshuMountsTargeted"])
        self.assertFalse(data["neoZygisk"]["productOverlayBlocksZygoteUnmount"])
        self.assertIn("NeoZygisk", c["summary"])

    def test_zygote_level_unmount(self):
        (self.proc.root / "700" / "mountinfo").write_text(STOCK)
        os.remove(self.proc.root / "700" / "ns" / "mnt")
        os.symlink("mnt:[5]", self.proc.root / "700" / "ns" / "mnt")
        self.proc.add(800, "webview_zygote", uid=1053, ns="mnt:[5]", mountinfo=STOCK)
        self.proc.add(1300, "com.a.b", uid=10300, ns="mnt:[5]", mountinfo=STOCK)
        c = self.build(facts=FACTS_KSU_NEO.replace("NeoZygisk", "Other"))["conclusion"]
        self.assertIn("zygote-level-unmount", c["causes"])
        self.assertIn("zygote 级卸载", c["summary"])

    def test_host_without_luoshu_mounts_and_no_probe_is_unknown_not_unmounted(self):
        (self.proc.root / "1" / "mountinfo").write_text(STOCK)
        c = self.build()["conclusion"]
        self.assertEqual("unknown", c["host"])
        self.assertIn("未能确认", c["summary"])

    def test_probe_decides_for_metamodule_mounts_without_luoshu_paths(self):
        for pid in ("1", "900", "700"):
            (self.proc.root / pid / "mountinfo").write_text(STOCK + OTHER_MODULE)
        self.proc.add(1300, "com.a.b", uid=10300, ns="mnt:[2]", mountinfo=STOCK)
        probe = {"1": "visible", "900": "visible", "700": "visible", "1300": "hidden"}.get
        c = self.build(probe=lambda pid: probe(pid))["conclusion"]
        self.assertEqual(("visible", "unmounted"), (c["host"], c["app"]))
        self.assertTrue(self.build()["neoZygisk"]["productOverlayBlocksZygoteUnmount"])

    def test_payload_probe_hashes_each_namespace_once(self):
        payload_dir = self.module / ".luoshu-payload/system/fonts"
        payload_dir.mkdir(parents=True)
        (payload_dir / "Roboto-Regular.ttf").write_bytes(b"luoshu" * 100)
        host = self.base / "host/system/fonts"
        host.mkdir(parents=True)
        (host / "Roboto-Regular.ttf").write_bytes(b"luoshu" * 100)  # overlay copy: other dev:ino
        for pid, content in (("1300", b"stock" * 10), ("1301", None)):
            root = self.proc.root / pid / "root/system/fonts"
            root.mkdir(parents=True)
            if content:
                (root / "Roboto-Regular.ttf").write_bytes(content)
        payload = locator.audit.PayloadIndex(self.module)
        calls = []
        original = payload.same_content
        payload.same_content = lambda *a: calls.append(a) or original(*a)
        probe = uv.payload_probe(payload, self.proc.root, self.base / "host", ["/system/fonts/Roboto-Regular.ttf"])
        self.assertEqual("hidden", probe("1300"))
        self.assertEqual("hidden", probe("1300"))
        self.assertEqual("unknown", probe("1301"))
        self.assertEqual(2, len(calls))  # host once + app namespace once
        self.assertIsNone(uv.payload_probe(payload, self.proc.root, self.base, []))

    # ------------------------------------------------------------ export wiring
    def test_export_carries_the_section_and_the_one_line_summary(self):
        (self.module / "module.prop").write_text("id=LuoShu\nversion=v3\n")
        self.proc.add(1300, "com.bank.app", uid=10300, ns="mnt:[2]", mountinfo=STOCK)
        reports = self.base / "reports"
        data = locator.export(module=self.module, out_dir=reports, rom="other", proc_root=self.proc.root,
                              host_root=self.base / "host", theme_dir=self.base / "theme",
                              package_apks=locator.PackageApks(lambda args: ""), now="x",
                              umount_facts=FACTS_KSU_NEO)
        report = json.loads(Path(data["path"]).read_text())
        self.assertEqual({}, report["sectionErrors"])
        self.assertEqual(uv.SCHEMA, report["umountVisibility"]["schema"])
        self.assertEqual("unmounted", data["umount"]["app"])
        self.assertTrue(data["umount"]["summary"].startswith("App 侧："))

    def test_export_survives_missing_facts_script(self):
        reports = self.base / "reports2"
        out = io.StringIO()
        with redirect_stdout(out):
            locator.main(["--export", str(reports), "--module", str(self.module), "--proc-root", str(self.proc.root),
                          "--host-root", str(self.base / "host"), "--theme-dir", str(self.base / "t"), "--rom", "other"])
        status = json.loads(out.getvalue())
        self.assertEqual("ok", status["status"], status)
        report = json.loads(Path(status["data"]["path"]).read_text())
        self.assertEqual("script-missing", report["umountVisibility"]["factsUnavailable"])
        self.assertNotIn("umountVisibility", report["sectionErrors"])

    # ------------------------------------------------------------ shell facts
    def run_facts(self, extra_modules=None, dmesg="ok"):
        bindir = self.base / "bin"
        bindir.mkdir(exist_ok=True)
        log = self.base / "calls.log"
        stubs = {
            "ksud": '''case "$*" in
  "-V") echo "ksud 3.3.0" ;;
  "debug version") echo "Kernel Version: 33000" ;;
  "feature get kernel_umount") printf 'Feature: kernel_umount (1)\\nDescription: x\\nValue: 1\\nStatus: enabled\\n' ;;
  "feature get webview_zygote_umount") echo "Feature 'webview_zygote_umount' is not supported by kernel" ;;
esac''',
            "dmesg": ('printf "[1] KernelSU: handle umount for uid: 10300, pid: 1\\n'
                      '[2] KernelSU: try_umount: unmounting: /system/fonts flags: 0x2\\n'
                      '[3] KernelSU: handle umount for uid: 10301, pid: 2\\n"' if dmesg == "ok" else "exit 1"),
        }
        for name, body in stubs.items():
            path = bindir / name
            path.write_text(f'#!/bin/sh\necho "{name} $*" >> "{log}"\n{body}\n')
            path.chmod(0o755)
        modules = self.base / "modules"
        neo = modules / "zygisksu"
        neo.mkdir(exist_ok=True)
        (neo / "module.prop").write_text("id=zygisksu\nname=NeoZygisk\nversion=v2.3\nmanagedFeatures=kernel_umount\n")
        sham = modules / "zygisk_shamiko"
        sham.mkdir(exist_ok=True)
        (sham / "module.prop").write_text("id=zygisk_shamiko\nname=Shamiko\nversion=1.2\n")
        (sham / "disable").write_text("")
        env = {**os.environ, "PATH": f"{bindir}:/usr/bin:/bin", "LUOSHU_UMOUNT_MODULES_DIR": str(modules)}
        done = subprocess.run(["sh", str(ROOT / "common/umount_visibility.sh"), "facts"], capture_output=True,
                              text=True, env=env, check=True)
        return uv.parse_facts(done.stdout), done.stdout, (log.read_text() if log.exists() else "")

    def test_facts_script_reads_ksu_features_modules_and_dmesg(self):
        facts, raw, calls = self.run_facts()
        self.assertIn("schema=luoshu-umount-facts-v1", raw)
        self.assertEqual("KernelSU", facts["manager"])
        self.assertEqual("1", facts["kernelUmount"])
        self.assertEqual("unsupported", facts["webviewZygoteUmount"])
        self.assertEqual("33000", facts["ksuKernelVersion"])
        self.assertEqual("NeoZygisk", uv.zygisk_impl(facts)["impl"])
        self.assertEqual("zygisksu", facts["kernelUmountManagedBy"])
        self.assertEqual("disabled", facts["hiderModule"][0]["state"])
        self.assertEqual(("2", "1"), (facts["dmesgUmountUid"], facts["dmesgUmountFonts"]))
        self.assertEqual("absent", facts["preloadModule"])
        # Read-only: only get/version queries reach ksud.
        for line in calls.splitlines():
            if line.startswith("ksud "):
                self.assertRegex(line, r"^ksud (-V|debug version|feature get \w+)$")

    def test_facts_script_without_dmesg(self):
        facts, _raw, _calls = self.run_facts(dmesg="fail")
        self.assertEqual("0", facts["dmesgReadable"])

    def test_scripts_contain_no_mutating_commands(self):
        text = (ROOT / "common/umount_visibility.sh").read_text()
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        code = re.sub(r"'[^'\n]*'", "''", code)  # grep/sed patterns are data, not commands
        for pattern in (r"feature set", r"\bumount\s+(add|del|wipe)", r"(^|[\s;|])(u?mount|rm|mv|chmod|chcon|setprop|resetprop)\s",
                        r"--sqlite\s+\"(UPDATE|INSERT|DELETE|REPLACE)", r"--denylist\s+(add|rm|enable|disable)", r">\s*/(?!dev/null)"):
            self.assertIsNone(re.search(pattern, code), pattern)
        py = (ROOT / "common/umount_visibility.py").read_text()
        for pattern in (r"\.write_text\(", r"\.unlink\(", r"os\.remove", r"shutil", r"open\([^)]*['\"]w"):
            self.assertIsNone(re.search(pattern, py), pattern)


if __name__ == "__main__":
    unittest.main()
