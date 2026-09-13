from pathlib import Path
import subprocess

# Exact, reviewed transformations of the large existing route/build files.
def replace(path, old, new):
    p=Path(path); s=p.read_text()
    assert s.count(old)==1, (path, old[:80], s.count(old))
    p.write_text(s.replace(old,new,1))

hub='android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/settings/SettingsHubScreen.kt'
replace(hub, '    BACKUP("备份与恢复"', '    GOOGLE("Google 字体兼容", "谷歌英数回退处理、状态与中文说明", Icons.Rounded.Build, .96f),\n    BACKUP("备份与恢复"')
replace(hub, '                        SettingsSection.BACKUP ->', '                        SettingsSection.GOOGLE -> GoogleFontCompatibilityPage()\n                        SettingsSection.BACKUP ->')
replace(hub, '                SettingsNavigationRow(\n                    section = SettingsSection.BACKUP,', '                SettingsNavigationRow(\n                    section = SettingsSection.GOOGLE,\n                    onClick = { onOpenSection(SettingsSection.GOOGLE) },\n                )\n                SettingsDivider()\n                SettingsNavigationRow(\n                    section = SettingsSection.BACKUP,')
replace('scripts/module_payload_manifest.txt', 'common/google_font_provider_bridge.sh', 'common/google_font_fallback_core.py\ncommon/google_font_fallback.py\ncommon/google_font_fallback.sh\ncommon/google_font_provider_bridge.sh')
replace('scripts/check.sh', 'python3 "$ROOT/scripts/google_font_provider_lifecycle_test.py"', 'python3 "$ROOT/scripts/google_font_fallback_test.py"\npython3 "$ROOT/scripts/google_font_fallback_integration_test.py"\npython3 "$ROOT/scripts/google_font_provider_lifecycle_test.py"')
replace('uninstall.sh', '. "$MODDIR/.luoshu-runtime/uninstall-v227.sh"', '''# Restore recorded component overrides before removing the runtime.
if [ -f "$MODDIR/common/google_font_fallback.sh" ]; then
    sh "$MODDIR/common/google_font_fallback.sh" restore-owned --json || \\
        echo '洛书：Google 字体兼容恢复未全部完成，恢复记录仍保留。' >&2
fi
. "$MODDIR/.luoshu-runtime/uninstall-v227.sh"''')
p=Path('scripts/google_font_fallback_test.py')
s=p.read_text(); assert s.count("ROOT / 'tools/google_font_fallback.py'")==2
p.write_text(s.replace("ROOT / 'tools/google_font_fallback.py'", "ROOT / 'common/google_font_fallback.py'"))
assert subprocess.check_output(['git','hash-object','tools/google_font_fallback.py'],text=True).strip()=='991c2c19479b2a82b6ed9428263ec691960d4862'
Path('tools/google_font_fallback.py').write_text('''#!/usr/bin/env python3
"""Source-tree CLI wrapper; the bundled implementation is authoritative."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'common'))
from google_font_fallback import main
if __name__ == '__main__':
    raise SystemExit(main())
''')
replace('module.prop','version=v4.4.4','version=v5.0.0-Beta1')
replace('module.prop','versionCode=40404','versionCode=50000')
Path('config/version_notes.conf').write_text('version=v5.0.0-Beta1\nsummary=内置中文 Google 字体兼容入口\nnotes=设置首页新增 Google 字体兼容：状态检测、确认开启、恢复原设置和中文使用说明。兼容独立脚本恢复记录，仅显式操作字体提供组件，不清数据、不停用整个 GMS。签名集成测试包，正式渠道不变。\n')
p=Path('.github/workflows/google-font-fallback-regression.yml')
s=p.read_text().replace('      - tools/google_font_fallback.py','      - common/google_font_fallback*.py\n      - common/google_font_fallback.sh\n      - tools/google_font_fallback.py').replace('      - scripts/google_font_fallback_test.py','      - scripts/google_font_fallback_test.py\n      - scripts/google_font_fallback_integration_test.py')
s=s.replace('          python3 scripts/google_font_fallback_test.py','          sh -n common/google_font_fallback.sh\n          python3 scripts/google_font_fallback_test.py\n          python3 scripts/google_font_fallback_integration_test.py')
p.write_text(s)
# Reuse actual fixed-certificate signing + lint/unit tests + package gates.
# This workflow has read-only contents permission and NEVER creates a Release.
s=Path('.github/workflows/release.yml').read_text()
steps=s[s.index('      - uses: actions/checkout@v4'):s.index('      - name: Publish immutable GitHub release')]
a=steps.index('      - name: Read and verify release version'); b=steps.index('      - name: Require signing secrets')
steps=steps[:a]+'''      - name: Read integration version
        id: version
        run: |
          . ./scripts/version.sh
          test "$LUOSHU_VERSION" = 'v5.0.0-Beta1'
          echo "version=$LUOSHU_VERSION" >> "$GITHUB_OUTPUT"
          echo "artifact_version=$LUOSHU_ARTIFACT_VERSION" >> "$GITHUB_OUTPUT"
          echo "prerelease=true" >> "$GITHUB_OUTPUT"
          git rev-parse HEAD > SOURCE_COMMIT.txt
      - name: Verify component integration
        run: |
          python3 scripts/google_font_fallback_test.py
          python3 scripts/google_font_fallback_integration_test.py
'''+steps[b:]
steps=steps.replace('-verified-release','-signed-integration').replace('            dist/pre-release-readiness/','            dist/pre-release-readiness/\n            SOURCE_COMMIT.txt\n            docs/GOOGLE_FONT_COMPATIBILITY_ZH.md\n            android-app/app/build/test-results/testDebugUnitTest/\n            android-app/app/build/reports/lint-results-release.html')
Path('.github/workflows/google-compat-signed.yml').write_text('''name: Signed Google compatibility integration
on:
  push:
    branches: [fix/google-provider-fallback-20260913]
permissions:
  contents: read
concurrency:
  group: luoshu-google-compat-signed
  cancel-in-progress: true
jobs:
  integration:
    runs-on: ubuntu-24.04
    timeout-minutes: 60
    steps:
'''+steps)
# Remove one-time transport files from the resulting source tree.
Path('.github/workflows/apply-google-integration.yml').unlink()
Path('.github/apply-google-integration.py').unlink()
