#!/usr/bin/env python3
"""Exercise the real flash wrapper with controlled Android/scan/deploy results."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class InstallerFlowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luoshu-install-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.new = self.base / "new"
        self.old = self.base / "old"
        for path in (self.new / "common/python/bin", self.new / "config",
                     self.new / "bundled", self.old / "config",
                     self.old / ".luoshu-payload/system/fonts"):
            path.mkdir(parents=True)
        self.write("module.prop", "id=LuoShu\nversion=v2.0.0\n")
        (self.old / "module.prop").write_text("id=LuoShu\nversion=v2.0.0\n")
        self.write("bundled/LuoShu-App.apk", "fixture")
        self.write("common/luoshu_cli.sh", "#!/system/bin/sh\n")
        self.write("common/util_functions.sh", "ensure_public_storage() { :; }\n")
        self.write("common/private_payload.sh", """
luoshu_private_partitions() { printf 'system\n'; }
luoshu_private_mount_module_view() { return 1; }
luoshu_private_unmount_module_view() { : > "$MOCK_CLEANED"; }
luoshu_private_install_migrate() {
    ui_print 'MOCK_DEPLOY_REACHED'
    [ "${MOCK_DEPLOY_FAIL:-0}" = 0 ]
}
""")
        self.write("common/stock_inventory_scan.py", "# scanner fixture\n")
        self.write("common/python/bin/luoshu-python", """#!/bin/sh
if [ "${MOCK_SCAN_FAIL:-0}" = 1 ]; then
    printf '{"message":"fixture stock view unavailable"}\n'
    exit 1
fi
printf '{"stockFontFileCount":45,"slotCount":12,"xmlSlotCount":8,"genericSlotCount":2,"heuristicSlotCount":2,"physicalSlotCount":0}\n'
""", executable=True)
        self.write("common/app_installer.sh", """#!/bin/sh
printf '%s\n' "${MOCK_APP_RESULT:-already-current}"
exit "${MOCK_APP_CODE:-0}"
""")

    def write(self, name, content, executable=False):
        target = self.new / name
        target.write_text(content, encoding="utf-8")
        if executable:
            target.chmod(0o755)

    def run_install(self, **overrides):
        env = {**os.environ, "MODPATH": str(self.new), "LUOSHU_OLD_MOD": str(self.old),
               "MOCK_CLEANED": str(self.base / "cleaned"), **overrides}
        return subprocess.run(["sh", str(ROOT / "customize.sh")], env=env,
                              capture_output=True, text=True, timeout=10)

    def assert_cleaned(self):
        self.assertTrue((self.base / "cleaned").exists())
        self.assertFalse(list(self.new.glob(".luoshu-old-view.*")))
        self.assertFalse(list(self.new.glob(".customize-v227.*")))

    def test_success_is_reported_only_after_final_deployment(self):
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr)
        positions = [result.stdout.index(f"[{number}/4]") for number in range(1, 5)]
        self.assertEqual(positions, sorted(positions))
        self.assertGreater(result.stdout.index("安装完成"), result.stdout.index("MOCK_DEPLOY_REACHED"))
        self.assertIn("检测：45 个原厂字体 / 12 个已识别文字槽位", result.stdout)
        self.assertIn("App：已是当前版本", result.stdout)
        self.assertNotIn("\x1b", result.stdout)
        self.assert_cleaned()

    def test_deploy_failure_never_claims_completion(self):
        result = self.run_install(MOCK_DEPLOY_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("洛书私有挂载树部署失败", result.stdout)
        self.assertNotIn("安装完成", result.stdout)
        self.assert_cleaned()

    def test_entry_preparation_failure_cleans_temporary_old_view(self):
        # Fail the wrapper's entry conversion after its old-payload view exists.
        # Earlier reads of module.prop/schema still use the host sed normally.
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        sed = bin_dir / "sed"
        sed.write_text("#!/bin/sh\n[ \"$1\" != -e ] || exit 1\nexec " +
                       shlex.quote(shutil.which("sed")) + ' "$@"\n')
        sed.chmod(0o755)
        result = self.run_install(PATH=f"{bin_dir}:{os.environ['PATH']}")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("安装入口准备失败", result.stdout)
        self.assertNotIn("安装完成", result.stdout)
        self.assert_cleaned()

    def test_untrusted_scan_remains_pending_without_fake_success(self):
        result = self.run_install(MOCK_SCAN_FAIL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.new / "config/stock_inventory_scan_pending").exists())
        self.assertIn("检测：待首次启动补扫", result.stdout)
        self.assertIn("fixture stock view unavailable", result.stdout)
        self.assertNotIn("✓ 原厂字体", result.stdout)
        self.assert_cleaned()

    def test_app_errors_are_not_misreported_as_automatic_recovery(self):
        for status, code, summary in (
            ("permanent-failure", "12", "App：安装受阻，请查看安装日志"),
            ("invalid-apk", "22", "App：校验失败，请重新下载完整模块包"),
            ("unexpected", "99", "App：安装状态未知，请查看安装日志"),
            ("installed", "99", "App：安装状态未知，请查看安装日志"),
        ):
            with self.subTest(status=status):
                result = self.run_install(MOCK_APP_RESULT=status, MOCK_APP_CODE=code)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(summary, result.stdout)
                self.assertNotIn("待首次启动自动补装", result.stdout)
                self.assert_cleaned()

    def test_deferred_app_is_visible_in_final_summary(self):
        result = self.run_install(MOCK_APP_RESULT="deferred", MOCK_APP_CODE="10")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("App：待首次启动自动补装", result.stdout)


if __name__ == "__main__":
    unittest.main()
