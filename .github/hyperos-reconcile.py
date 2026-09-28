"""One-use reviewed merge; only listed test-branch files may be replaced."""
from pathlib import Path
import sys, subprocess, shutil
p=Path(sys.argv[1])
expected={
'common/font_config_overlay.py':'4ebb3e133a644e1678b0db90f6c627bdacf02f0c',
'common/font_role_policy.py':'0fb1ab79743e70ca13e90d53b515bd3dcebee716',
'common/google_font_provider_service.sh':'79df57c44e1f5dd768d850420bfe126104d595aa',
'common/hyperos_metrics_batch.py':'0655c9cd23b2a0c61c1b6bc171bc4c57c826793d',
'common/hyperos_theme_font_bridge.sh':'1c2ea9d0627e332a046dc5a1316b2acf6a2614ef',
'common/legacy_v14_4/font_switch_safe.sh':'1ddf2552d1686673a120bbed645573595d9e0623',
'common/legacy_v14_4/hyperos_clock_compat.sh':'60465f6d5778c910b1091f51bf016f6875e743e4',
'common/legacy_v14_4/hyperos_full_coverage.sh':'027e3635bb4cc09d32ff7196d8d57b449e67a3ca',
'common/task_scope.py':'ef91d9909f42ad5fede141963ce48bfebcb80756',
'scripts/google_font_provider_lifecycle_test.py':'6fd583fe0a0cbfc72bc0ec5f0015e54092f73fa0',
'scripts/hyperos_cjk_routing_test.py':'0cf3e4d274df1a24403a6fa10fe4e14b80059406',
'scripts/hyperos_coverage_regression_test.py':'cf12d8898d597c24f2ca4d7245814d9a48469468',
'scripts/stable111_round2_test.py':'bc4d43e60f2ae21ccf1741bcb50a29b07571d3d7'}
for name,sha in expected.items():
    actual=subprocess.check_output(['git','hash-object',name],text=True).strip()
    if actual!=sha: raise SystemExit('Concurrent source drift: '+name)
def replace(name, old, new):
    f=p/name; s=f.read_text()
    if s.count(old)!=1: raise SystemExit('Unexpected reconstruction: '+name)
    f.write_text(s.replace(old,new))
replace('scripts/stable111_round2_test.py',"self.stock('VendorFixedFace.ttf')", "# A genuinely unclassified fixed-pitch face must remain stock.\n        self.stock('VendorFixedFace.ttf', family='')")
replace('scripts/hyperos_cjk_routing_test.py',"    def test_no_staged_fallback_keeps_primary_han(self):\n        self.default_pair()\n        self.build(['Roboto-Regular.ttf'])", "    def test_no_staged_fallback_keeps_primary_han(self):\n        self.default_pair()\n        # Inventory discovery now fills omitted known UI slots. Model an actual\n        # missing stock target, not merely omission from the caller's name list.\n        (self.root / 'stock/system/MiSansVF.ttf').unlink()\n        self.build(['Roboto-Regular.ttf'])\n        self.assertNotIn('/system/fonts/MiSansVF.ttf', self.reports)")
replace('common/hyperos_metrics_batch.py','memo[identity] = preferred_unicode_codepoints(font)', '# Retain only the 62 core code points, not a CJK cmap per alias.\n            memo[identity] = frozenset(cp for cp in preferred_unicode_codepoints(font)\n                                       if 48 <= cp <= 57 or 65 <= cp <= 90 or 97 <= cp <= 122)')
replace('common/font_role_policy.py',"    # Split CamelCase before lowercasing: DroidSansMono is code, Monotype is not.\n", "    # Keep known code families case-insensitive; Monotype is a foundry, not mono.\n    stem = re.sub(r'[-_ ]+', '', Path(name).stem.lower())\n    roots = ('droidsansmono', 'notosansmono', 'notoserifmono', 'notomono',\n             'robotomono', 'cutivemono', 'sourcecodepro', 'courier', 'consolas', 'monaco')\n    if any(stem.startswith(root) for root in roots):\n        return True\n    # Split CamelCase before lowercasing: DroidSansMono is code, Monotype is not.\n")
replace('common/hyperos_theme_font_bridge.sh', "    [ -L \"$HTF_ALIAS\" ] || { printf 'not-applicable\\n'; return 0; }", "    if [ ! -L \"$HTF_ALIAS\" ]; then\n        # On HyperOS the framework can create the alias itself after boot.\n        if [ -n \"$(getprop ro.mi.os.version.name 2>/dev/null)$(getprop ro.miui.ui.version.name 2>/dev/null)\" ]; then\n            printf 'pending\\n'\n        else\n            printf 'not-applicable\\n'\n        fi\n        return 0\n    fi")
replace('common/google_font_provider_service.sh', "    printf '[%s] one-shot state=%s reason=%s; no resident observer\\n'", "    if [ \"$1\" = partial ]; then\n        printf '[WARN] HyperOS 主题字体路由未确认：任务已退出，无常驻重试（%s）\\n' \"$2\" >> \"$MODDIR/logs/fontswitch.log\" 2>/dev/null || true\n    fi\n    printf '[%s] one-shot state=%s reason=%s; no resident observer\\n'")
replace('common/hyperos_metrics_batch.py', "    if not valid_coverage(coverage):\n        return {}\n    st = path.stat()", "    if not valid_coverage(coverage):\n        return {'textCoverage': 'unverified-no-stock-character-facts'}\n    st = path.stat()")
replace('common/hyperos_metrics_batch.py', "    return {'coreLatinChecked': coverage['latinCount'] == 52,", "    return {'textCoverage': 'checked-core-characters',\n            'latinCount': sum(65 <= cp <= 90 or 97 <= cp <= 122 for cp in points),\n            'digitCount': sum(48 <= cp <= 57 for cp in points),\n            'coreLatinChecked': coverage['latinCount'] == 52,")
replace('scripts/hyperos_coverage_regression_test.py', "for n in ('DroidSansMono.ttf','NotoSansMono-Regular.ttf','RobotoMono-Regular.ttf'):", "for n in ('DroidSansMono.ttf','NotoSansMono-Regular.ttf','RobotoMono-Regular.ttf',\n                  'robotomono-regular.ttf','sourcecodepro-bold.ttf'):")
replace('scripts/hyperos_coverage_regression_test.py', "        self.assertEqual(probe(),'pending')\n        self.assertEqual(other.read_bytes(),b'foreign')", "        self.assertEqual(probe(),'pending')\n        self.assertEqual(other.read_bytes(),b'foreign')\n        alias.unlink()\n        self.assertEqual(probe(),'pending', 'known HyperOS may create alias after boot')")
# Withdrawal metadata, other tests and Android sources remain unchanged.
for name in expected:
    shutil.copy2(p/name,Path(name))
print('Reconciled',len(expected),'reviewed source files; no release or main write.')
