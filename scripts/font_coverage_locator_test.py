#!/usr/bin/env python3
"""Fixture tests for the App's 未覆盖界面定位 helper (common/font_coverage_locator.py).

A fake /proc tree carries maps lines whose dev:ino are the real fixture files'
identities, and /proc/<pid>/root is a directory standing in for the app's
mount namespace. No device, no root.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "common"))
import font_coverage_locator as locator  # noqa: E402
import hyperos_physical_policy as policy  # noqa: E402

PID = "4242"


def maps_line(path: str, real: Path, start: int) -> str:
    st = os.stat(real)
    return (f"{start:x}-{start + 0x1000:x} r--p 00000000 "
            f"{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x} {st.st_ino}          {path}\n")


class LocatorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.module = base / "module"
        self.payload = self.module / ".luoshu-payload/system/fonts"
        self.payload.mkdir(parents=True)
        (self.payload / "MiSansVF.ttf").write_bytes(b"luoshu-font" * 200)
        self.host = base / "host"
        (self.host / "system/fonts").mkdir(parents=True)
        os.link(self.payload / "MiSansVF.ttf", self.host / "system/fonts/MiSansVF.ttf")
        self.proc = base / "proc"
        self.app_root = self.proc / PID / "root"
        (self.app_root / "system/fonts").mkdir(parents=True)
        (self.app_root / "data/system/theme/fonts").mkdir(parents=True)
        self.theme = base / "theme"
        self.theme.mkdir()
        self.stock = base / "stock"
        self.stock.mkdir()
        self.maps: list[str] = []

    def app_sees_payload(self):
        os.link(self.payload / "MiSansVF.ttf", self.app_root / "system/fonts/MiSansVF.ttf")

    def map(self, device_path: str, real: Path):
        self.maps.append(maps_line(device_path, real, 0x7000 + 0x2000 * len(self.maps)))

    def stock_file(self, name: str, size: int = 4096) -> Path:
        path = self.stock / name
        path.write_bytes(b"s" * size)
        visible = self.app_root / "system/fonts" / name
        if not visible.exists():
            os.link(path, visible)
        return path

    def run_locate(self, package="com.android.systemui", pid=PID, groups=None, weight=False):
        (self.proc / PID / "maps").write_text("".join(self.maps))
        return locator.locate(package, pid, module=self.module, proc_root=self.proc,
                              host_root=self.host, theme_dir=self.theme,
                              groups=policy.parse_groups("") if groups is None else groups,
                              weight_probe=lambda _path: weight, rom="hyperos")

    def categories(self, result):
        return [item["category"] for item in result["findings"]]

    def test_fully_covered_process(self):
        self.app_sees_payload()
        self.map("/system/fonts/MiSansVF.ttf", self.payload / "MiSansVF.ttf")
        result = self.run_locate()
        self.assertEqual(result["verdict"], "covered")
        self.assertEqual(self.categories(result), ["covered"])

    def test_theme_store_font_is_reported_first_with_action(self):
        self.app_sees_payload()
        (self.theme / "Roboto-Regular.ttf").write_bytes(b"t" * 300000)
        themed = self.app_root / "data/system/theme/fonts/Roboto-Regular.ttf"
        themed.write_bytes(b"t" * 300000)
        self.map("/data/system/theme/fonts/Roboto-Regular.ttf", themed)
        result = self.run_locate()
        self.assertEqual(result["verdict"], "theme-takeover")
        self.assertIn("主题商店", result["findings"][0]["action"])
        self.assertEqual(result["theme"]["state"], "user-theme")

    def test_placeholder_theme_is_not_a_takeover(self):
        self.app_sees_payload()
        (self.theme / "Roboto-Regular.ttf").write_bytes(b"t" * 9000)
        self.map("/system/fonts/MiSansVF.ttf", self.payload / "MiSansVF.ttf")
        result = self.run_locate()
        self.assertEqual(result["theme"]["state"], "placeholder")
        self.assertEqual(result["verdict"], "covered")

    def test_module_invisible_in_app_namespace(self):
        stock = self.stock_file("MiSansVF.ttf", 9999)
        self.map("/system/fonts/MiSansVF.ttf", stock)
        result = self.run_locate()
        self.assertIn("namespace-hidden", self.categories(result))
        hidden = next(f for f in result["findings"] if f["category"] == "namespace-hidden")
        self.assertEqual(hidden["files"], ["/system/fonts/MiSansVF.ttf"])
        self.assertIn("卸载模块", hidden["action"])
        self.assertIn("DenyList", hidden["action"])

    def test_outside_whitelist_disabled_group_and_kept_by_design(self):
        self.app_sees_payload()
        self.map("/system/fonts/MiSansVF.ttf", self.payload / "MiSansVF.ttf")
        self.map("/system/fonts/C800.ttf", self.stock_file("C800.ttf"))
        self.map("/system/fonts/MiSansL3.otf", self.stock_file("MiSansL3.otf"))
        self.map("/system/fonts/VendorClockX.ttf", self.stock_file("VendorClockX.ttf"))
        result = self.run_locate()
        outside = next(f for f in result["findings"] if f["category"] == "outside-whitelist")
        self.assertIn("/system/fonts/C800.ttf（lockscreen_styles 组未开启）", outside["files"])
        # Clock faces are policy targets now: a stock clock is not "outside".
        self.assertNotIn("/system/fonts/VendorClockX.ttf", outside["files"])
        self.assertTrue(any("MiSansL3" in item for item in result["keptByDesign"]))
        # With the lock screen group on, C800 is no longer "outside".
        result = self.run_locate(groups=policy.ALL_GROUPS)
        outside = next((f for f in result["findings"] if f["category"] == "outside-whitelist"),
                       {"files": []})
        self.assertNotIn("/system/fonts/C800.ttf（lockscreen_styles 组未开启）", outside["files"])

    def test_embedded_font_apps_and_private_font_files(self):
        self.app_sees_payload()
        private = self.stock / "wechat.ttf"
        private.write_bytes(b"w" * 100)
        self.map("/data/data/com.tencent.mm/files/xweb/fonts/wechat.ttf", private)
        result = self.run_locate(package="com.tencent.mm")
        self.assertEqual(result["verdict"], "app-embedded")
        self.assertIn("微信", result["findings"][0]["detail"])
        result = self.run_locate(package="com.example.reader")
        embedded = next(f for f in result["findings"] if f["category"] == "app-embedded")
        self.assertEqual(embedded["files"], ["wechat.ttf"])

    def test_weight_loss_on_static_font(self):
        self.app_sees_payload()
        self.map("/system/fonts/MiSansVF.ttf", self.payload / "MiSansVF.ttf")
        result = self.run_locate(weight=True)
        self.assertIn("weight-loss", self.categories(result))

    def test_not_running_and_no_payload(self):
        result = self.run_locate(pid="")
        self.assertEqual(result["verdict"], "not-running")
        for path in self.payload.iterdir():
            path.unlink()
        result = self.run_locate()
        self.assertEqual(result["verdict"], "no-payload")

    def test_cli_rejects_bad_package_and_emits_json(self):
        out = io.StringIO()
        with redirect_stdout(out):
            locator.main(["--package", "bad;rm -rf /", "--pid", PID])
        self.assertEqual(json.loads(out.getvalue())["status"], "error")
        out = io.StringIO()
        with redirect_stdout(out):
            locator.main(["--package", "com.android.settings", "--pid", "",
                          "--module", str(self.module), "--theme-dir", str(self.theme)])
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["verdict"], "not-running")

    def test_luoshu_route_clone_in_theme_dir_is_not_a_theme_font(self):
        # Real device: theme store on DEFAULT, LuoShu's early route bind serves
        # its Roboto on /data/system/theme/fonts/Roboto-Regular.ttf.
        self.app_sees_payload()
        clone = self.module / "config/hyperos-webview-route/route.ttf"
        clone.parent.mkdir(parents=True)
        clone.write_bytes(b"r" * 300000)
        os.link(clone, self.theme / "Roboto-Regular.ttf")
        self.map("/system/fonts/MiSansVF.ttf", self.payload / "MiSansVF.ttf")
        result = self.run_locate()
        self.assertEqual(result["theme"]["state"], "placeholder")
        self.assertEqual(result["theme"]["luoshuFiles"], ["Roboto-Regular.ttf"])
        self.assertEqual(result["verdict"], "covered")

    def test_theme_engine_roboto_and_payload_copies_are_not_theme_fonts(self):
        stock_dir = self.stock / "sysfonts"
        stock_dir.mkdir()
        (stock_dir / "Roboto-Regular.ttf").write_bytes(b"s" * 300000)
        (self.theme / "Roboto-Regular.ttf").write_bytes(b"s" * 300000)
        self.assertEqual(locator.theme_state(self.theme, self.module, stock_dir)["state"], "placeholder")
        (self.theme / "Roboto-Regular.ttf").write_bytes(b"\0\1\0\0" + "Roboto".encode("utf-16-be") + b"\0" * 300000)
        self.assertEqual(locator.theme_state(self.theme, self.module, stock_dir)["state"], "placeholder")
        big = self.payload / "Roboto-Regular.ttf"
        big.write_bytes(b"p" * 300000)
        (self.theme / "Roboto-Regular.ttf").write_bytes(big.read_bytes())
        self.assertEqual(locator.theme_state(self.theme, self.module, stock_dir)["state"], "placeholder")
        (self.theme / "Roboto-Regular.ttf").write_bytes(b"t" * 300000)
        self.assertEqual(locator.theme_state(self.theme, self.module, stock_dir)["userFiles"], ["Roboto-Regular.ttf"])

    def test_takeover_owned_file_stays_user_theme(self):
        clone = self.module / "config/hyperos-theme-takeover/Roboto-Regular.ttf"
        clone.parent.mkdir(parents=True)
        clone.write_bytes((self.payload / "MiSansVF.ttf").read_bytes() * 200)
        os.link(clone, self.theme / "Roboto-Regular.ttf")
        st = os.stat(clone)
        (self.module / "config/hyperos-theme-takeover.journal").write_text(
            f"boot|{self.theme / 'Roboto-Regular.ttf'}|{clone}|{st.st_dev}:{st.st_ino}\n")
        self.assertEqual(locator.theme_state(self.theme, self.module)["state"], "user-theme")

    def scan_fixture(self):
        """Three running apps: covered, lock-screen group off, module hidden; plus noise."""
        self.app_sees_payload()
        procs = {"100": ("com.android.systemui", [("/system/fonts/MiSansVF.ttf", self.payload / "MiSansVF.ttf")]),
                 "101": ("com.miui.aod", [("/system/fonts/MiSansVF.ttf", self.payload / "MiSansVF.ttf"),
                                         ("/system/fonts/C800.ttf", self.stock_file("C800.ttf"))]),
                 "102": ("com.example.hidden", [("/system/fonts/MiSansVF.ttf", self.stock / "hidden.ttf")])}
        (self.stock / "hidden.ttf").write_bytes(b"h" * 9999)
        for pid, (name, maps) in procs.items():
            root = self.proc / pid / "root"
            (root / "system/fonts").mkdir(parents=True, exist_ok=True)
            if pid != "102":
                target = root / "system/fonts/MiSansVF.ttf"
                if not target.exists():
                    os.link(self.payload / "MiSansVF.ttf", target)
            else:
                os.link(self.stock / "hidden.ttf", root / "system/fonts/MiSansVF.ttf")
            if pid == "101":
                os.link(self.stock / "C800.ttf", root / "system/fonts/C800.ttf")
            (self.proc / pid / "cmdline").write_bytes(name.encode() + b"\0")
            (self.proc / pid / "maps").write_text("".join(
                maps_line(path, real, 0x7000 + 0x2000 * i) for i, (path, real) in enumerate(maps)))
        for pid, cmdline in (("200", b"/system/bin/surfaceflinger\0"), ("201", b"zygote64\0"),
                             ("202", b"com.android.systemui\0")):
            (self.proc / pid).mkdir(parents=True)
            (self.proc / pid / "cmdline").write_bytes(cmdline)

    def test_scan_lists_uncovered_processes_with_fixes_and_reasons(self):
        self.scan_fixture()
        result = locator.scan(module=self.module, proc_root=self.proc, host_root=self.host,
                              theme_dir=self.theme, groups=policy.parse_groups(""),
                              weight_probe=lambda _p: False, rom="hyperos")
        self.assertEqual(result["verdict"], "ok")
        self.assertEqual((result["scanned"], result["covered"]), (3, 1))
        by_package = {item["package"]: item for item in result["items"]}
        self.assertEqual(set(by_package), {"com.miui.aod", "com.example.hidden"})
        self.assertEqual(by_package["com.miui.aod"]["fixes"], ["group:lockscreen_styles"])
        self.assertEqual(by_package["com.example.hidden"]["fixes"], [])
        self.assertTrue(any("卸载模块" in reason for reason in by_package["com.example.hidden"]["reasons"]))
        self.assertEqual(result["fixes"], ["group:lockscreen_styles"])
        self.assertFalse(result["truncated"])

    def test_scan_weight_loss_is_global_and_budget_truncates(self):
        self.scan_fixture()
        result = locator.scan(module=self.module, proc_root=self.proc, host_root=self.host,
                              theme_dir=self.theme, groups=policy.ALL_GROUPS, weight_probe=lambda _p: True,
                              rom="hyperos")
        self.assertTrue(result["weightLoss"])
        self.assertEqual([item["package"] for item in result["items"]], ["com.example.hidden"])
        ticks = iter([0.0, 0.0, 100.0, 100.0, 100.0])
        result = locator.scan(module=self.module, proc_root=self.proc, host_root=self.host,
                              theme_dir=self.theme, weight_probe=lambda _p: False, budget_s=1.0,
                              clock=lambda: next(ticks), rom="hyperos")
        self.assertTrue(result["truncated"])

    def test_scan_cli_emits_json(self):
        self.scan_fixture()
        out = io.StringIO()
        with redirect_stdout(out):
            locator.main(["--scan", "--module", str(self.module), "--proc-root", str(self.proc),
                          "--theme-dir", str(self.theme), "--rom", "hyperos"])
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["schema"], locator.SCAN_SCHEMA)


    def test_scan_items_carry_files_and_ignore_files_kept_by_design(self):
        # Real device: zygote preloads every system font, so script fallbacks,
        # emoji and the AOSP decorative families sit in every app process. They
        # are kept by design, never "outside-whitelist" (93 processes before).
        self.scan_fixture()
        for name in ("NotoSansArmenian-Regular.ttf", "NotoColorEmoji.ttf", "CarroisGothicSC-Regular.ttf",
                     "NotoSansSymbols-Regular-Subsetted.ttf", "MiSansL3.otf"):
            self.stock_file(name)
            root = self.proc / "100" / "root/system/fonts" / name
            if not root.exists():
                os.link(self.stock / name, root)
            with (self.proc / "100" / "maps").open("a") as stream:
                stream.write(maps_line(f"/system/fonts/{name}", self.stock / name, 0x90000 + len(name) * 0x2000))
        result = locator.scan(module=self.module, proc_root=self.proc, host_root=self.host,
                              theme_dir=self.theme, groups=policy.parse_groups(""),
                              weight_probe=lambda _p: False, rom="hyperos")
        by_package = {item["package"]: item for item in result["items"]}
        self.assertNotIn("com.android.systemui", by_package)
        aod = by_package["com.miui.aod"]
        self.assertEqual(["/system/fonts/C800.ttf（lockscreen_styles 组未开启）"], aod["files"])
        self.assertEqual("outside-whitelist", aod["findings"][0]["category"])
        self.assertEqual(aod["files"], aod["findings"][0]["files"])
        result = locator.locate("com.android.systemui", "100", module=self.module, proc_root=self.proc,
                                host_root=self.host, theme_dir=self.theme, groups=policy.parse_groups(""),
                                weight_probe=lambda _p: False, rom="hyperos")
        self.assertEqual("covered", result["verdict"])
        self.assertEqual(5, len(result["keptByDesign"]))

    def test_preserved_collection_reason_comes_from_metrics_report(self):
        self.app_sees_payload()
        self.map("/system/fonts/MiSansVF.ttf", self.payload / "MiSansVF.ttf")
        self.map("/system/fonts/NotoSansCJK-Regular.ttc", self.stock_file("NotoSansCJK-Regular.ttc"))
        reason = "ValueError: 来源字形 uni302A 超出本机原厂字体面边界"
        (self.module / ".luoshu-payload/.luoshu-metrics-report.json").write_text(json.dumps(
            {"collections": [], "preservedCollections": {"/system/fonts/NotoSansCJK-Regular.ttc": reason}},
            ensure_ascii=False))
        result = self.run_locate()
        self.assertEqual("collection-kept", result["verdict"])
        self.assertIn(reason, result["findings"][0]["detail"])
        self.assertNotIn("outside-whitelist", self.categories(result))
        fixes, reasons = locator.suggested_fixes(result)
        self.assertEqual([], fixes)
        self.assertTrue(any(reason in item for item in reasons))
        # Built this time: the collection is LuoShu's and nothing is reported.
        (self.module / ".luoshu-payload/.luoshu-metrics-report.json").write_text('{"collections": []}')
        result = self.run_locate()
        self.assertNotIn("collection-kept", self.categories(result))

    def test_other_rom_uses_actual_payload_and_lists_unknown_files(self):
        self.app_sees_payload()
        self.map("/system/fonts/MiSansVF.ttf", self.payload / "MiSansVF.ttf")
        self.map("/system/fonts/VendorUI-Regular.ttf", self.stock_file("VendorUI-Regular.ttf"))
        self.map("/system/fonts/NotoSansThai-Regular.ttf", self.stock_file("NotoSansThai-Regular.ttf"))
        (self.proc / PID / "maps").write_text("".join(self.maps))
        result = locator.locate("com.android.settings", PID, module=self.module, proc_root=self.proc,
                                host_root=self.host, theme_dir=self.theme, weight_probe=lambda _p: False,
                                rom="other")
        outside = next(f for f in result["findings"] if f["category"] == "outside-whitelist")
        self.assertEqual(["/system/fonts/VendorUI-Regular.ttf"], outside["files"])
        self.assertIn("实际替换的清单", outside["action"])
        self.assertNotIn("HyperOS", outside["action"])
        self.assertEqual(1, len(result["keptByDesign"]))
        self.assertEqual("none", result["theme"]["state"])

    def test_every_category_has_a_guide(self):
        for category in ("theme-takeover", "outside-whitelist", "namespace-hidden", "app-embedded",
                         "link-switched", "weight-loss", "covered", "not-running", "collection-kept",
                         "flip-font"):
            title, action = locator.GUIDE[category]
            self.assertTrue(title and action, category)


class ColorOSLocatorTest(unittest.TestCase):
    """ColorOS / OxygenOS: targets from coloros_global.sh, keep rules from
    coloros_latin_policy, the OPlus flip font, and no HyperOS-only settings."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.module = base / "module"
        self.payload = self.module / ".luoshu-payload/system/fonts"
        self.payload.mkdir(parents=True)
        (self.payload / "SysSans-En-Regular.ttf").write_bytes(b"luoshu-font" * 200)
        self.host = base / "host"
        (self.host / "system/fonts").mkdir(parents=True)
        os.link(self.payload / "SysSans-En-Regular.ttf", self.host / "system/fonts/SysSans-En-Regular.ttf")
        self.proc = base / "proc"
        self.root = self.proc / PID / "root/system/fonts"
        self.root.mkdir(parents=True)
        os.link(self.payload / "SysSans-En-Regular.ttf", self.root / "SysSans-En-Regular.ttf")
        self.stock = base / "stock"
        self.stock.mkdir()
        groups = base / "coloros_slot_groups.conf"
        groups.write_text("osans_digits=0\n")
        env = {"LUOSHU_COLOROS_SLOT_GROUPS_CONF": str(groups)}
        old = {key: os.environ.get(key) for key in env}
        os.environ.update(env)
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
                                 for k, v in old.items()])
        maps = [("/system/fonts/SysSans-En-Regular.ttf", self.payload / "SysSans-En-Regular.ttf")]
        for name in ("OSans-RC-Regular.ttf", "OplusSans-Regular.ttf", "VendorDisplay-Regular.ttf",
                     "OSans-Solid-Digits-VF.ttf", "NotoSansKhmer-Regular.ttf", "NotoColorEmoji.ttf"):
            (self.stock / name).write_bytes(b"s" * 4096)
            os.link(self.stock / name, self.root / name)
            maps.append((f"/system/fonts/{name}", self.stock / name))
        flip = self.stock / "OplusOSUI-Regular.ttf"
        flip.write_bytes(b"f" * 200000)
        maps.append(("/data/format_unclear/font/OplusOSUI-Regular.ttf", flip))
        (self.proc / PID / "cmdline").write_bytes(b"com.android.launcher\0")
        (self.proc / PID / "maps").write_text("".join(
            maps_line(path, real, 0x7000 + 0x2000 * i) for i, (path, real) in enumerate(maps)))

    def locate(self):
        return locator.locate("com.android.launcher", PID, module=self.module, proc_root=self.proc,
                              host_root=self.host, theme_dir=self.stock / "no-theme",
                              weight_probe=lambda _p: False, rom="coloros")

    def test_coloros_policy_classifies_targets_keep_rules_and_unknown_files(self):
        result = self.locate()
        self.assertEqual("coloros", result["rom"])
        categories = [item["category"] for item in result["findings"]]
        self.assertEqual("flip-font", categories[0])
        self.assertNotIn("app-embedded", categories)
        outside = next(f for f in result["findings"] if f["category"] == "outside-whitelist")
        self.assertIn("/system/fonts/VendorDisplay-Regular.ttf", outside["files"])
        self.assertIn("/system/fonts/OSans-Solid-Digits-VF.ttf（osans_digits 组未开启）", outside["files"])
        self.assertFalse(any("OplusSans" in f or "OSans-RC" in f or "Noto" in f for f in outside["files"]))
        self.assertIn("SysSans", outside["action"])
        self.assertNotIn("HyperOS", outside["action"] + outside["title"])
        # A ColorOS target the payload lacks is listed apart, not as outside.
        self.assertTrue(any("OplusSans-Regular.ttf" in f for f in result["targetsNotInPayload"]))
        kept = " ".join(result["keptByDesign"])
        for name in ("OSans-RC-Regular.ttf", "NotoSansKhmer-Regular.ttf", "NotoColorEmoji.ttf"):
            self.assertIn(name, kept)

    def test_coloros_cjk_collection_follows_the_collections_switch(self):
        judge = locator.StockPolicy("coloros", self.module, metrics={}, coloros_names=frozenset())
        verdict = judge.judge("/system/fonts/NotoSansCJK-Regular.ttc")
        self.assertEqual("outside", verdict[0])
        (self.module / "config").mkdir(exist_ok=True)
        (self.module / "config/coloros_cjk_collections.conf").write_text("enabled=0\n")
        self.assertEqual(("kept", "多语言字体集合"),
                         locator.StockPolicy("coloros", self.module, metrics={}, coloros_names=frozenset())
                         .judge("/system/fonts/NotoSansCJK-Regular.ttc"))
        kept = {"preservedCollections": {"/system/fonts/NotoSansCJK-Regular.ttc": "ValueError: x"}}
        self.assertEqual("collection", locator.StockPolicy("coloros", self.module, metrics=kept,
                                                           coloros_names=frozenset())
                         .judge("/system/fonts/NotoSansCJK-Regular.ttc")[0])

    def test_coloros_scan_offers_no_hyperos_switches(self):
        result = locator.scan(module=self.module, proc_root=self.proc, host_root=self.host,
                              theme_dir=self.stock / "no-theme", weight_probe=lambda _p: False, rom="coloros")
        self.assertEqual("coloros", result["rom"])
        self.assertEqual([], result["fixes"])
        item = result["items"][0]
        self.assertIn("/system/fonts/VendorDisplay-Regular.ttf", item["files"])
        self.assertTrue(any("VendorDisplay-Regular.ttf" in reason for reason in item["reasons"]))

    def test_rom_detection_props(self):
        props = {"ro.build.version.oplusrom": "V16.0.0"}
        old = os.environ.pop("LUOSHU_COVERAGE_ROM", None)
        try:
            self.assertEqual("coloros", locator.detect_rom(lambda key: props.get(key, "")))
            self.assertEqual("hyperos", locator.detect_rom(lambda key: "OS2.0" if key == "ro.mi.os.version.name" else ""))
        finally:
            if old is not None:
                os.environ["LUOSHU_COVERAGE_ROM"] = old


class CoverageExportTest(LocatorTest):
    """One file with everything: deduped issues, metrics, slots, WebView, log."""

    def test_export_writes_one_sanitized_deduplicated_report(self):
        self.scan_fixture()
        # Two processes with the identical miss collapse into one issue.
        (self.proc / "103").mkdir()
        (self.proc / "103" / "root").symlink_to(self.proc / "101" / "root")
        (self.proc / "103" / "cmdline").write_bytes(b"com.miui.aod:remote\0")
        (self.proc / "103" / "maps").write_text((self.proc / "101" / "maps").read_text())
        (self.proc / "300").mkdir()
        (self.proc / "300" / "root").symlink_to(self.proc / "102" / "root")
        (self.proc / "300" / "cmdline").write_bytes(b"webview_zygote\0")
        (self.module / "module.prop").write_text("id=LuoShu\nversion=v3.0.0\nversionCode=300\n")
        (self.module / ".luoshu-payload/.luoshu-metrics-report.json").write_text(json.dumps({
            "collections": [], "preservedCollections": {"/system/fonts/NotoSerifCJK-Regular.ttc": "ValueError: x"}}))
        (self.module / "logs").mkdir()
        (self.module / "logs/fontswitch.log").write_text(
            "[MIX] 应用字体 我的私人字体.ttf 来自 /sdcard/Download/a.ttf\n"
            "[MIX] CJK 集合生成失败：MiSansVF.ttf\nunrelated line\n")
        reports = self.tmp.name + "/reports"
        Path(reports).mkdir()
        (Path(reports) / "LuoShu-diagnostic-summary.txt").write_text("report=luoshu-sanitized-diagnostic-v1\n")
        out = io.StringIO()
        with redirect_stdout(out):
            locator.main(["--export", reports, "--module", str(self.module), "--proc-root", str(self.proc),
                          "--host-root", str(self.host), "--theme-dir", str(self.theme), "--rom", "hyperos",
                          "--device", "rootManager=KernelSU", "--device", "androidSdk=35",
                          "--device", "bad key=x"])
        status = json.loads(out.getvalue())
        self.assertEqual("ok", status["status"], status)
        path = Path(status["data"]["path"])
        self.assertTrue(path.name.startswith("LuoShu-coverage-full-") and path.suffix == ".json")
        data = json.loads(path.read_text())
        self.assertEqual(locator.EXPORT_SCHEMA, data["schema"])
        self.assertEqual("v3.0.0", data["module"]["version"])
        self.assertEqual({"rom": "hyperos", "romLabel": "HyperOS", "rootManager": "KernelSU", "androidSdk": "35"},
                         data["device"])
        aod = [group for group in data["issues"] if "com.miui.aod" in group["processes"]]
        self.assertEqual(1, len(aod))
        self.assertEqual(["com.miui.aod", "com.miui.aod:remote"], sorted(aod[0]["processes"]))
        self.assertEqual(["/system/fonts/C800.ttf（lockscreen_styles 组未开启）"], aod[0]["findings"][0]["files"])
        self.assertEqual({"/system/fonts/NotoSerifCJK-Regular.ttc": "ValueError: x"},
                         data["metrics"]["preservedCollections"])
        self.assertEqual("luoshu", next(row for row in data["slots"]
                                        if row["slot"] == "/system/fonts/MiSansVF.ttf")["state"])
        self.assertEqual("hidden", data["webview"][0]["state"])
        log = "\n".join(data["fontswitchLog"])
        self.assertNotIn("私人字体", log)
        self.assertNotIn("/sdcard", log)
        self.assertIn("MiSansVF.ttf", log)
        self.assertNotIn("unrelated", log)
        self.assertIn("luoshu-sanitized-diagnostic-v1", data["sanitizedDiagnostic"])
        self.assertIn("theme", data)
        self.assertEqual({}, data["sectionErrors"])

    def _export(self, metrics):
        self.scan_fixture()
        (self.module / ".luoshu-payload/.luoshu-metrics-report.json").write_text(json.dumps(metrics))
        reports = Path(self.tmp.name) / "reports-real"
        out = io.StringIO()
        with redirect_stdout(out):
            locator.main(["--export", str(reports), "--module", str(self.module), "--proc-root", str(self.proc),
                          "--host-root", str(self.host), "--theme-dir", str(self.theme), "--rom", "hyperos"])
        status = json.loads(out.getvalue())
        self.assertEqual("ok", status["status"], status)
        return json.loads(Path(status["data"]["path"]).read_text())

    def test_export_reads_real_metrics_report_with_slot_list(self):
        # hyperos_metrics_batch writes `slots` as a list of {"slot": ...} rows;
        # treating it as a dict raised TypeError on device (导出失败：TypeError).
        data = self._export({"schema": "luoshu-slot-metrics-v1",
                             "slots": [{"slot": "/system/fonts/MiSansVF.ttf", "variableSlotSource": "x"},
                                       {"slot": "/system/fonts/Roboto-Regular.ttf"}, "junk"],
                             "collections": [], "preservedCollections": {}})
        self.assertEqual({}, data["sectionErrors"])
        self.assertTrue(data["metrics"]["available"])
        self.assertEqual(["/system/fonts/MiSansVF.ttf"],
                         sorted(locator.metric_slots({"slots": [{"slot": "/system/fonts/MiSansVF.ttf"}]})))

    def test_export_survives_a_broken_section(self):
        original = locator.webview_visibility
        locator.webview_visibility = lambda *a, **k: (_ for _ in ()).throw(TypeError("boom /sdcard/x"))
        try:
            data = self._export({"slots": {"/system/fonts/MiSansVF.ttf": {}}})
        finally:
            locator.webview_visibility = original
        self.assertEqual([], data["webview"])
        self.assertTrue(data["sectionErrors"]["webview"].startswith("TypeError@"))
        self.assertNotIn("sdcard", json.dumps(data["sectionErrors"]))
        self.assertTrue(data["issues"])

    def test_missing_report_names_the_inherited_payload_instead_of_no_reason(self):
        # Device export 2026-10-18: no .luoshu-metrics-report.json at all after a
        # module update kept the old composite payload; the note said "未记录原因".
        judge = locator.StockPolicy("hyperos", self.module, metrics={})
        kind, note = judge.judge("/system/fonts/NotoSansCJK-Regular.ttc")
        self.assertEqual("outside", kind)
        self.assertIn("缺少度量/集合报告", note)
        (self.module / "config").mkdir(exist_ok=True)
        (self.module / "config/font-payload-rebuild-pending.conf").write_text(
            "state=awaiting-explicit-apply\nreason=font-builder-changed\ndetail=metrics-report-missing\n")
        kind, note = locator.StockPolicy("hyperos", self.module, metrics={}).judge(
            "/system/fonts/NotoSerifCJK-Regular.ttc")
        self.assertIn("模块更新后沿用了旧版本生成的字体负载", note)
        self.assertNotIn("未记录原因", note)

    def test_export_carries_the_last_apply_with_phase_timings(self):
        (self.module / "logs").mkdir(exist_ok=True)
        (self.module / "logs/fontswitch.log").write_text("\n".join([
            "[SAFE-TIMING] task=old event=begin phase=map_rom uptime=1.0",
            "[SAFE-TIMING] task=old event=end phase=map_rom status=completed uptime=2.0 elapsedMs=1000",
            "[SAFE-TIMING] task=new event=begin phase=source_lookup_validation uptime=5.0",
            "stage output for /sdcard/LuoShu/fonts/私人字体.ttf",
            '{"mapped": 40, "generated": 12, "collections": ["/system/fonts/NotoSansCJK-Regular.ttc"]}',
            "[SAFE-TIMING] task=new event=end phase=source_lookup_validation status=completed uptime=5.4 elapsedMs=400",
            "[SAFE-TIMING] task=new event=begin phase=complete_hyperos uptime=5.4",
            "[SAFE-TIMING] task=new event=end phase=complete_hyperos status=completed uptime=75.4 elapsedMs=70000",
            "[2026-10-18 09:18:13] [WEBVIEW-ROUTE] already bound",
        ]) + "\n")
        data = self._export({"collections": []})
        last = data["lastApply"]
        self.assertTrue(last["found"])
        self.assertEqual(7, last["lineCount"])
        self.assertEqual([("source_lookup_validation", 400), ("complete_hyperos", 70000)],
                         [(row["phase"], row["elapsedMs"]) for row in last["phases"]])
        self.assertEqual(70400, last["totalPhaseMs"])
        joined = "\n".join(last["lines"])
        self.assertIn('"mapped": 40', joined)          # unfiltered stage output stays
        self.assertNotIn("task=old", joined)
        self.assertNotIn("/sdcard", joined)
        self.assertNotIn("私人字体", joined)
        self.assertEqual({}, data["sectionErrors"])
        (self.module / "logs/fontswitch.log").write_text("[WEBVIEW-ROUTE] only\n")
        self.assertFalse(locator.last_apply_log(self.module, str)["found"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
