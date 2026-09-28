#!/usr/bin/env python3
"""Coverage regressions on synthetic ROMs, not a HyperOS device certification."""
from __future__ import annotations
import json
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'common'), str(ROOT/'scripts')]
import stable111_round2_test as fixtures
import font_role_policy as policy
from fontTools.ttLib import TTFont

class HyperOSRoleRegression(unittest.TestCase):
    setUp = fixtures.Round2.setUp
    stock = fixtures.Round2.stock
    save_inventory = fixtures.Round2.save_inventory
    build = fixtures.Round2.build

    def test_explicit_ui_fixed_pitch_keeps_selected_english_and_digits(self):
        name = 'Roboto-Regular.ttf'; logical = '/system/fonts/' + name
        stock = self.stock(name, family='sans-serif')
        original = stock.read_bytes()
        fixtures.make_font(self.fonts/'400.ttf', tuple(range(32,127)))
        self.slots[logical]['metrics']['isFixedPitch'] = True
        self.build(['MiSansVF.ttf', name])
        self.assertIn(logical, self.by_slot)
        with TTFont(self.fonts/name) as output, TTFont(self.fonts/'400.ttf') as donor:
            for cp in (*range(48,58), *range(65,91), *range(97,123)):
                self.assertEqual(fixtures.bounds(output, cp), fixtures.bounds(donor, cp))
        policy.cleanup(self.module, self.stage)
        self.assertTrue((self.fonts/name).exists(), 'final role cleanup erased the generated UI font')
        self.assertNotIn(logical, (self.stage/'.luoshu-stock-preserved.paths').read_text())
        self.assertEqual(stock.read_bytes(), original)

    def test_monotype_substring_is_not_a_code_monospace_role(self):
        for name in ('VendorMonotype.ttf', 'MonotypeSans.ttf'):
            self.stock(name, family='system-ui')
        self.build()
        for name in ('VendorMonotype.ttf', 'MonotypeSans.ttf'):
            self.assertIn('/system/fonts/'+name, self.by_slot)
        self.assertFalse(policy.is_code_monospace('VendorFace.ttf', {'families':['sans-serif-monotype']}))

    def test_inventory_verified_known_ui_does_not_require_shell_name_list(self):
        self.stock('Roboto-Regular.ttf', part='product', family='sans-serif')
        self.build(['MiSansVF.ttf'])
        self.assertIn('/product/fonts/Roboto-Regular.ttf', self.by_slot)
        self.assertFalse((self.fonts/'Roboto-Regular.ttf').exists())

    def test_unknown_fixed_pitch_without_ui_evidence_still_stays_stock(self):
        name = 'VendorFixedFace.ttf'; logical = '/system/fonts/' + name
        self.stock(name, family=''); self.slots[logical]['metrics']['isFixedPitch']=True
        fixtures.make_font(self.fonts/name); self.build()
        self.assertFalse((self.fonts/name).exists())
        self.assertIn(logical, (self.stage/'.luoshu-stock-preserved.paths').read_text())

    def test_code_family_and_clock_exceptions_remain_intact(self):
        for name in ('DroidSansMono.ttf', 'RobotoMonoVF.ttf', 'NotoSansMono-Regular.ttf'):
            self.assertTrue(policy.is_code_monospace(name))
            self.assertTrue(policy.is_code_monospace(name.lower()))
        self.assertTrue(policy.is_code_monospace('MitypeMono.ttf', {'families':['monospace']}))
        self.assertFalse(policy.is_code_monospace('MitypeMono.ttf', {'families':['mitype-mono']}))
        self.assertTrue(policy.is_code_monospace('Roboto-Regular.ttf', {'families':['monospace','sans-serif']}),
                        'shared physical code/UI file cannot be rewritten globally')

if __name__ == '__main__':
    unittest.main(verbosity=2)
