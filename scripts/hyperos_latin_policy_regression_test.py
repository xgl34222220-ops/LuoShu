#!/usr/bin/env python3
"""Filename-policy regression, not an Android device/rendering test.

Run with the standard library only. Both the Python scanner/builder policy and
actual shell discovery are exercised; fixture filenames are not a K80 inventory.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
import hyperos_physical_policy as policy  # noqa: E402
from hyperos_physical_policy import safe_physical_font_name, preserved_dynamic_alias

SHELL = ROOT / 'common/legacy_v14_4/hyperos_full_coverage.sh'
RESTORED = (
    'NotoSansDisplay-Regular.ttf', 'NotoSansDisplay-Bold.otf', 'NotoSansDisplay.otf',
    'NotoSansCondensed-Regular.ttf', 'NotoSansSemiCondensed-Medium.ttf',
    'NotoSansExtraCondensed-Bold.otf', 'NotoSansVF.ttf', 'NotoSansVariable.ttf',
    'NotoSansVariable-Regular.otf', 'NotoSansUIVF.ttf',
    'NotoSansDisplayVF.ttf', 'NotoSansCondensedVF.ttf',
    'DroidSansFallback.ttf',
    'Roboto-SemiCondensed.ttf', 'GoogleSans-SemiCondensed.ttf',
)
PRESERVED = (
    'MiSansVF.ttf', 'MiSansLatinVF.ttf', 'MiSansTCVF.ttf',
    'XiaomiSans-Regular.ttf', 'MiLanProVF.ttf', 'MitypeVF.ttf', 'MiClock.ttf',
    'Roboto-Regular.ttf', 'RobotoFlex-Regular.ttf',
    'GoogleSans-Regular.ttf', 'GoogleSansText-VF.ttf', 'GoogleSansFlex-Regular.ttf',
    'NotoSans-Regular.ttf', 'NotoSansUI-Regular.ttf', 'NotoSansCJKsc-Regular.otf',
    'NotoSansSC-Regular.otf', 'NotoSansTC-Regular.otf', 'NotoSansHK-Regular.otf',
    'DroidSans.ttf', 'DroidSans-Regular.ttf', 'DroidSans-Bold.ttf',
    'Clockopia.ttf', 'AndroidClock.ttf', '100.ttf', '350.ttf', '400.ttf', '900.ttf',
)
# Clock / tabular Mono slots and the GB18030 rare-character store stay stock on
# both the legacy (v14.4) and v4 routes: a proportional user font in a clock
# digit slot misaligns timers and clocks; MiSansL3 carries 60k+ rare Han a user
# font lacks.
KEPT_STOCK = (
    'MitypeMonoVF.ttf',
    'MitypeClockMono.ttf', 'MitypeClockMono.otf', 'MiClockMono.ttf', 'MiClockMono.otf',
    'InterMono-SemiBold.ttf', 'BebasNeue-Mono.ttf', 'CommutersSansMono.ttf',
    'RobotoMonoClock.ttf', 'NotoSansMonoClock-Regular.ttf',
    'MiSansL3.otf',
)
# Code monospace faces behind the system ``monospace`` family (terminals,
# ReSukiSU/KernelSU flash logs via FontFamily.Monospace) are replaced again, as
# before v4.3 (1bf06137). NotoSansMono CJK/Script/Arabic variants stay excluded.
CODE_MONO = (
    'DroidSansMono.ttf', 'RobotoMono-Regular.ttf', 'RobotoMono-Bold.ttf', 'RobotoMonoVF.ttf',
    'NotoSansMono-Regular.ttf', 'NotoSansMono-Bold.ttf', 'NotoSansMono.ttf', 'NotoSansMonoVF.ttf',
)
DEFAULT_ON_GROUPS = (
    'MiuiEx-Regular.ttf', 'MiuiEx-Bold.ttf', 'MiuiEx-Light.ttf', 'Miui-Regular.ttf',
    'Miui-Bold.ttf', 'MiSansRoundedSC.ttf', 'MiSansRoundedTC.ttf', 'MiSansCondensed2T.ttf',
    'MiSansC_3.005.ttf', 'MiLanVF.ttf',
)
DEFAULT_OFF_GROUPS = (
    'Interscaled-Bold.ttf', 'Interscaled-Regular.ttf', 'C800.ttf', 'Qinghe.ttf',
    'ChamberiDisplay-Bold.ttf', 'DelaGothicOne.ttf', 'DelaGothicOne-HZ.ttf',
    'NeumaticCompressed-Bold.ttf', 'GulfsDisplay-Medium.ttf',
)
EXCLUDED = (
    'NotoSansAdlam-Regular.ttf', 'NotoSansArmenian-Regular.ttf',
    'NotoSansGeorgian-Regular.ttf', 'NotoSansEthiopic-Regular.ttf',
    'NotoSansLisu-Regular.ttf', 'NotoSansBengali-Regular.ttf',
    'NotoSansThai-Regular.ttf', 'NotoSansOriya-Regular.ttf',
    'NotoSansSymbols-Regular.ttf', 'NotoColorEmoji.ttf', 'NotoSerif-Regular.ttf',
    'NotoSansMonoCJKjp-Regular.otf', 'NotoSansMonoCJKKR-Regular.otf',
    'NotoSansMonoArabic-Regular.ttf', 'NotoSansDisplayAdlam-Regular.ttf',
    'NotoSansMonoScript-Regular.ttf', 'MiSansJP.ttf', 'MiSansKR.ttf',
    'NotoSansMono-Italic.ttf', 'NotoSansDisplay-Oblique.otf',
    'Roboto-Italic.ttf', 'NotoSansMono.ttc', 'NotoSansVF.ttc', '400.ttc',
    '/system/fonts/NotoSansMono.ttf', '../NotoSansDisplay.ttf',
    'NotoSansMono/../Roboto-Regular.ttf', 'Roboto/../Roboto-Regular.ttf',
    '', 'random.ttf', 'NotoSansMono.ttf.bak',
    'RobotoIcons-Regular.ttf', 'NotoSansMono-Icons.ttf',
    'NotoSansSemiCondensed-Icon.ttf', 'Roboto-SemiCondensed-ICON.ttf',
)


def shell_result(names: tuple[str, ...], groups_conf: str | None = None,
                 shell: Path = SHELL) -> list[bool]:
    # Do not source another compatibility layer or inspect host font files.
    with tempfile.TemporaryDirectory() as temp:
        env = os.environ.copy()
        env.pop('LUOSHU_HYPEROS_SLOT_GROUPS_CONF', None)
        if groups_conf is not None:
            conf = Path(temp) / 'groups.conf'
            conf.write_text(groups_conf)
            env['LUOSHU_HYPEROS_SLOT_GROUPS_CONF'] = str(conf)
        for key in ('LUOSHU_REAL_MODDIR', 'MODDIR', 'MODULE_DIR', 'PWD'):
            env[key] = temp
        proc = subprocess.run(
            ['sh', '-c', '. "$1"; shift; check=_lhpp_safe_name; '
             'type _lhcc_safe_dynamic_name >/dev/null 2>&1 && check=_lhcc_safe_dynamic_name; '
             'for name do '
             'if "$check" "$name"; then printf "1\\n"; '
             'else printf "0\\n"; fi; done', 'sh', str(shell), *names],
            cwd=temp, env=env, check=True, text=True, capture_output=True,
        )
    result = proc.stdout.splitlines()
    if len(result) != len(names) or any(item not in ('0', '1') for item in result):
        raise AssertionError(f'unexpected shell output: {proc.stdout!r}; {proc.stderr!r}')
    return [item == '1' for item in result]


class LatinPolicyRegressionTest(unittest.TestCase):
    def test_restored_ui_families_are_not_discarded(self):
        for name in RESTORED:
            with self.subTest(name=name):
                self.assertTrue(safe_physical_font_name(name))

    def test_existing_ui_chinese_clock_and_numeric_targets_stay_enabled(self):
        for name in PRESERVED:
            with self.subTest(name=name):
                self.assertTrue(safe_physical_font_name(name))

    def test_unrelated_languages_icons_and_unsafe_paths_stay_excluded(self):
        for name in EXCLUDED:
            with self.subTest(name=name):
                self.assertFalse(safe_physical_font_name(name))

    def test_shell_and_python_have_the_same_policy(self):
        names = (RESTORED + PRESERVED + EXCLUDED + KEPT_STOCK + CODE_MONO
                 + DEFAULT_ON_GROUPS + DEFAULT_OFF_GROUPS)
        expected = [safe_physical_font_name(name, policy.parse_groups('')) for name in names]
        for shell in [ROOT / item for item in policy.SHELL_TARGETS]:
            with self.subTest(shell=shell.name):
                self.assertEqual(shell_result(names, shell=shell), expected)

    def test_mono_clock_and_rare_han_slots_stay_stock(self):
        for name in KEPT_STOCK:
            with self.subTest(name=name):
                self.assertFalse(safe_physical_font_name(name, policy.ALL_GROUPS))
                self.assertIn(policy.classify(name), ('mono', 'rare-han'))
        self.assertEqual(shell_result(KEPT_STOCK, 'lockscreen_styles=1\n'), [False] * len(KEPT_STOCK))

    def test_code_monospace_is_replaced_and_not_retired(self):
        for name in CODE_MONO:
            with self.subTest(name=name):
                self.assertEqual(policy.classify(name), 'core')
                self.assertTrue(safe_physical_font_name(name, policy.parse_groups('')))
                self.assertNotIn(name, policy.RETIRED_NAMES)
                self.assertTrue(policy.xml_file_allowed(name, 'LuoShuSlot-ui-400.ttf'))
        for shell in [ROOT / item for item in policy.SHELL_TARGETS]:
            with self.subTest(shell=shell.name):
                self.assertEqual(shell_result(CODE_MONO, shell=shell), [True] * len(CODE_MONO))
                proc = subprocess.run(['sh', '-c', '. "$1"; _lhpp_retired_names', 'sh', str(shell)],
                                      check=True, text=True, capture_output=True)
                retired = proc.stdout.split()
                for name in ('DroidSansMono.ttf', 'RobotoMono-Regular.ttf', 'NotoSansMono-Regular.ttf'):
                    self.assertNotIn(name, retired)
                self.assertIn('MitypeMonoVF.ttf', retired)
        # Clock/tabular Mono faces stay stock even next to the code families.
        for name in ('MitypeMonoVF.ttf', 'MiClockMono.otf', 'MitypeClockMono.ttf'):
            self.assertEqual(policy.classify(name), 'mono')
            self.assertTrue(policy.xml_file_allowed(name, 'LuoShuMono-400.ttf'))
            self.assertFalse(policy.xml_file_allowed(name, 'LuoShuSlot-ui-400.ttf'))
        # Boot slot repair keeps a code-mono alias and drops a clock-mono one.
        with tempfile.TemporaryDirectory() as temp:
            overlay, real = Path(temp) / 'overlay', Path(temp) / 'real'
            overlay.mkdir()
            real.mkdir()
            names = ('DroidSansMono.ttf', 'RobotoMono-Regular.ttf', 'NotoSansMono-Regular.ttf',
                     'MitypeMonoVF.ttf', 'MiClockMono.otf')
            for name in names:
                (overlay / name).write_bytes(b'alias')
                (real / name).write_bytes(b'stock')
            env = os.environ.copy()
            env.pop('LUOSHU_HYPEROS_SLOT_GROUPS_CONF', None)
            for key in ('LUOSHU_REAL_MODDIR', 'MODDIR', 'MODULE_DIR', 'PWD'):
                env[key] = temp
            subprocess.run(['sh', '-c', '. "$1"; _lhcc_prune_policy_aliases "$2" "$3"', 'sh',
                            str(ROOT / 'common/legacy_v14_4/hyperos_clock_compat.sh'),
                            str(overlay), str(real)],
                           cwd=temp, env=env, check=True, text=True, capture_output=True)
            self.assertEqual(sorted(p.name for p in overlay.iterdir()),
                             ['DroidSansMono.ttf', 'NotoSansMono-Regular.ttf', 'RobotoMono-Regular.ttf'])
        import hyperos_metrics_batch as batch
        self.assertFalse(batch.policy_keeps_stock('DroidSansMono.ttf', policy.ALL_GROUPS))
        self.assertTrue(batch.policy_keeps_stock('MiClockMono.otf', policy.ALL_GROUPS))

    def test_optional_groups_have_documented_defaults_and_toggle(self):
        defaults = policy.parse_groups('')
        self.assertEqual(defaults, frozenset({'miui_ex', 'misans_ext'}))
        for name in DEFAULT_ON_GROUPS:
            self.assertTrue(safe_physical_font_name(name, defaults), name)
        for name in DEFAULT_OFF_GROUPS:
            self.assertFalse(safe_physical_font_name(name, defaults), name)
            self.assertEqual(policy.classify(name), 'lockscreen_styles')
        toggled = policy.parse_groups('lockscreen_styles=1\nmiui_ex=0\r\nmisans_ext=yes\n')
        self.assertEqual(toggled, frozenset({'misans_ext', 'lockscreen_styles'}))
        names = DEFAULT_ON_GROUPS + DEFAULT_OFF_GROUPS
        conf = 'lockscreen_styles=1\r\nmiui_ex=0'  # CRLF and last line without newline must count
        expected = [safe_physical_font_name(n, policy.parse_groups(conf)) for n in names]
        for shell in [ROOT / item for item in policy.SHELL_TARGETS]:
            with self.subTest(shell=shell.name):
                self.assertEqual(shell_result(names, conf, shell), expected)
        self.assertFalse(safe_physical_font_name('MiuiEx-Bold.ttf', toggled))
        self.assertTrue(safe_physical_font_name('Interscaled-Bold.ttf', toggled))
        # Clock faces are not part of the MiSansC group prefix.
        self.assertEqual(policy.classify('MiSansClockVF.ttf'), 'core')

    def test_generated_shell_blocks_are_current(self):
        proc = subprocess.run([sys.executable, str(ROOT / 'common/hyperos_physical_policy.py'), '--check'],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_scanner_and_xml_use_the_same_policy(self):
        # The scanner captures every group (enabling one later needs no rescan);
        # the XML route never points a Mono/rare-Han/disabled file at a proportional build.
        self.assertTrue(safe_physical_font_name('Interscaled-Bold.ttf', policy.ALL_GROUPS))
        self.assertFalse(policy.xml_file_allowed('MitypeMonoVF.ttf', 'LuoShuSlot-ui-400.ttf'))
        self.assertTrue(policy.xml_file_allowed('MitypeMonoVF.ttf', 'LuoShuMono-400.ttf'))
        self.assertTrue(policy.xml_file_allowed('RobotoMono-Regular.ttf', 'LuoShuSlot-ui-400.ttf'))
        self.assertFalse(policy.xml_file_allowed('MiSansL3.otf', 'LuoShuSlot-ui-400.ttf'))
        self.assertFalse(policy.xml_file_allowed('C800.ttf', 'LuoShuSlot-ui-400.ttf', policy.parse_groups('')))
        self.assertTrue(policy.xml_file_allowed('Roboto-Regular.ttf', 'LuoShuSlot-ui-400.ttf'))
        import hyperos_metrics_batch as batch
        self.assertIs(batch.MAPPER_FAMILY_PREFIXES, policy.MAPPER_FAMILY_PREFIXES)
        self.assertTrue(batch.policy_keeps_stock('MitypeMonoVF.ttf', policy.ALL_GROUPS))
        self.assertTrue(batch.policy_keeps_stock('C800.ttf', policy.parse_groups('')))
        self.assertFalse(batch.policy_keeps_stock('MiuiEx-Bold.ttf', policy.parse_groups('')))

    def test_all_restored_families_keep_italic_and_collection_guards(self):
        names = tuple(str(Path(name).with_suffix('.ttc')) for name in RESTORED)
        names += tuple(Path(name).stem + '-Italic' + Path(name).suffix for name in RESTORED)
        self.assertEqual(shell_result(names), [False] * len(names))
        self.assertTrue(all(not safe_physical_font_name(name) for name in names))

    def test_discovery_includes_real_files_and_deduplicates_static_names(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            names = RESTORED + PRESERVED + EXCLUDED[:24]
            for name in names:
                (root / name).write_bytes(b'filename fixture; not a font')
            (root / 'NotoSansMono-Directory.ttf').mkdir()
            (root / 'NotoSansMono-Broken.ttf').symlink_to(root / 'missing')
            env = os.environ.copy()
            for key in ('LUOSHU_REAL_MODDIR', 'MODDIR', 'MODULE_DIR', 'PWD'):
                env[key] = temp
            proc = subprocess.run(
                ['sh', '-c', '. "$1"; _lhcc_static_names() { '
                 'printf "%s\\n" NotoSansDisplay-Regular.ttf; }; _lhcc_names_for_root "$2"',
                 'sh', str(SHELL), str(root)],
                cwd=temp, env=env, check=True, text=True, capture_output=True,
            )
            actual = proc.stdout.splitlines()
            self.assertEqual(len(actual), len(set(actual)))
            self.assertEqual(set(actual), set(RESTORED + PRESERVED))

    @staticmethod
    def coverage_checker():
        # Execute the actual pure revision predicates, isolated from fontTools
        # and filesystem scanning. Full scanner integration stays in its suite.
        path = ROOT / 'common/font_inventory_scan.py'
        tree = ast.parse(path.read_text(), filename=str(path))
        selected = [ast.ImportFrom(module='__future__',
                                   names=[ast.alias(name='annotations')], level=0)]
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == 'HYPEROS_COVERAGE_REVISION'
                    for target in node.targets):
                selected.append(node)
            elif isinstance(node, ast.FunctionDef) and node.name in (
                    '_is_hyperos_inventory', '_has_current_hyperos_coverage'):
                selected.append(node)
        namespace = {}
        module = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
        exec(compile(module, str(path), 'exec'), namespace)
        return namespace['_has_current_hyperos_coverage']

    def test_v430_inventory_requires_refresh_and_new_inventory_is_reusable(self):
        current = self.coverage_checker()
        self.assertFalse(current({'romKind': 'hyperos', 'hyperosCoverageRevision': 3}))
        self.assertFalse(current({'romKind': 'hyperos'}))
        self.assertFalse(current({'romKind': 'hyperos', 'hyperosCoverageRevision': 4}))
        # 6: code monospace re-captured; revision-5 inventories lack its stock metrics.
        self.assertFalse(current({'romKind': 'hyperos', 'hyperosCoverageRevision': 5}))
        self.assertTrue(current({'romKind': 'hyperos', 'hyperosCoverageRevision': 6}))
        self.assertFalse(current({'romKind': 'generic', 'hyperosCoverageRevision': 3,
                                  'scanSummary': {'fontSignatures': {'hyperos': ['MiSansVF.ttf']}}}))

    def test_coverage_upgrade_does_not_force_coloros_or_generic_refresh(self):
        current = self.coverage_checker()
        self.assertTrue(current({'romKind': 'coloros', 'hyperosCoverageRevision': 3,
                                 'scanSummary': {'fontSignatures': {'hyperos': ['MiSansVF.ttf']}}}))
        self.assertTrue(current({'romKind': 'generic', 'hyperosCoverageRevision': 3}))

    def test_dynamic_hyperos_overlay_exemption_is_unchanged(self):
        logical = '/system/fonts/MiSansVF_Overlay.ttf'
        data = {'preservedDynamicAliases': {logical: {
            'source': 'hyperos-framework-symlink',
            'target': '/data/system/fonts/theme_webview/Roboto-Regular.ttf',
        }}}
        self.assertTrue(preserved_dynamic_alias(data, logical))
        self.assertFalse(preserved_dynamic_alias(data, '/system/fonts/NotoSansMono.ttf'))
        self.assertFalse(preserved_dynamic_alias({}, logical))


if __name__ == '__main__':
    unittest.main(verbosity=2)
