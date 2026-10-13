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
                              weight_probe=lambda _path: weight)

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
        self.map("/system/fonts/RobotoMono-Regular.ttf", self.stock_file("RobotoMono-Regular.ttf"))
        self.map("/system/fonts/VendorClockX.ttf", self.stock_file("VendorClockX.ttf"))
        result = self.run_locate()
        outside = next(f for f in result["findings"] if f["category"] == "outside-whitelist")
        self.assertIn("/system/fonts/C800.ttf（lockscreen_styles 组未开启）", outside["files"])
        self.assertIn("/system/fonts/VendorClockX.ttf", outside["files"])
        self.assertTrue(any("RobotoMono" in item for item in result["keptByDesign"]))
        # With the lock screen group on, C800 is no longer "outside".
        result = self.run_locate(groups=policy.ALL_GROUPS)
        outside = next(f for f in result["findings"] if f["category"] == "outside-whitelist")
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

    def test_every_category_has_a_guide(self):
        for category in ("theme-takeover", "outside-whitelist", "namespace-hidden", "app-embedded",
                         "link-switched", "weight-loss", "covered", "not-running"):
            title, action = locator.GUIDE[category]
            self.assertTrue(title and action, category)


if __name__ == "__main__":
    unittest.main(verbosity=2)
