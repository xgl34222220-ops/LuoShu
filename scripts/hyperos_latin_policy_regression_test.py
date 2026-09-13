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
from hyperos_physical_policy import safe_physical_font_name, preserved_dynamic_alias

SHELL = ROOT / 'common/legacy_v14_4/hyperos_full_coverage.sh'
RESTORED = (
    'NotoSansMono-Regular.ttf', 'NotoSansMono-Bold.ttf', 'NotoSansMono.ttf',
    'NotoSansDisplay-Regular.ttf', 'NotoSansDisplay-Bold.otf', 'NotoSansDisplay.otf',
    'NotoSansCondensed-Regular.ttf', 'NotoSansSemiCondensed-Medium.ttf',
    'NotoSansExtraCondensed-Bold.otf', 'NotoSansVF.ttf', 'NotoSansVariable.ttf',
    'NotoSansVariable-Regular.otf', 'NotoSansUIVF.ttf', 'NotoSansMonoVF.ttf',
    'NotoSansDisplayVF.ttf', 'NotoSansCondensedVF.ttf',
    'DroidSansMono.ttf', 'DroidSansFallback.ttf',
    'Roboto-SemiCondensed.ttf', 'GoogleSans-SemiCondensed.ttf',
)
PRESERVED = (
    'MiSansVF.ttf', 'MiSansLatinVF.ttf', 'MiSansTCVF.ttf', 'MiSansL3.otf',
    'XiaomiSans-Regular.ttf', 'MiLanProVF.ttf', 'MitypeVF.ttf', 'MiClock.ttf',
    'Roboto-Regular.ttf', 'RobotoMono-Regular.ttf', 'RobotoFlex-Regular.ttf',
    'GoogleSans-Regular.ttf', 'GoogleSansText-VF.ttf', 'GoogleSansFlex-Regular.ttf',
    'NotoSans-Regular.ttf', 'NotoSansUI-Regular.ttf', 'NotoSansCJKsc-Regular.otf',
    'NotoSansSC-Regular.otf', 'NotoSansTC-Regular.otf', 'NotoSansHK-Regular.otf',
    'DroidSans.ttf', 'DroidSans-Regular.ttf', 'DroidSans-Bold.ttf',
    'Clockopia.ttf', 'AndroidClock.ttf', '100.ttf', '350.ttf', '400.ttf', '900.ttf',
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


def shell_result(names: tuple[str, ...]) -> list[bool]:
    # Do not source another compatibility layer or inspect host font files.
    with tempfile.TemporaryDirectory() as temp:
        env = os.environ.copy()
        for key in ('LUOSHU_REAL_MODDIR', 'MODDIR', 'MODULE_DIR', 'PWD'):
            env[key] = temp
        proc = subprocess.run(
            ['sh', '-c', '. "$1"; shift; for name do '
             'if _lhcc_safe_dynamic_name "$name"; then printf "1\\n"; '
             'else printf "0\\n"; fi; done', 'sh', str(SHELL), *names],
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
        names = RESTORED + PRESERVED + EXCLUDED
        self.assertEqual(shell_result(names), [safe_physical_font_name(name) for name in names])

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
                 'printf "%s\\n" NotoSansMono-Regular.ttf; }; _lhcc_names_for_root "$2"',
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
        path = ROOT / 'common/font_inventory_scan_v3.py'
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
        self.assertTrue(current({'romKind': 'hyperos', 'hyperosCoverageRevision': 4}))
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
