#!/usr/bin/env python3
"""Tests for scripts/rom_coverage_gate.py (standard library only)."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import rom_coverage_gate as gate  # noqa: E402


class EvaluateTest(unittest.TestCase):
    ENTRY = {
        'fixture': ['A.ttf', 'B.ttf', 'C.ttf'],
        'replaced': ['A.ttf', 'B.ttf'],
        'keptStock': {'C.ttf': '衬线族'},
        'legacyReplaced': ['A.ttf'],
    }

    def test_unchanged_passes(self):
        errors, _notes = gate.evaluate('x', self.ENTRY, ['A.ttf', 'B.ttf'])
        self.assertEqual(errors, [])

    def test_replaced_to_stock_fails_until_reason_is_registered(self):
        errors, _notes = gate.evaluate('x', self.ENTRY, ['A.ttf'])
        self.assertEqual(len(errors), 1)
        self.assertIn('B.ttf', errors[0])
        self.assertIn('keptStock', errors[0])
        entry = dict(self.ENTRY, keptStock={'C.ttf': '衬线族', 'B.ttf': '有意保留'})
        self.assertEqual(gate.evaluate('x', entry, ['A.ttf'])[0], [])
        for reason in ('', '  ', 'TODO: 登记保留原厂的理由'):
            entry = dict(self.ENTRY, keptStock={'C.ttf': '衬线族', 'B.ttf': reason})
            self.assertEqual(len(gate.evaluate('x', entry, ['A.ttf'])[0]), 1, reason)

    def test_legacy_replaced_is_guarded_too(self):
        entry = dict(self.ENTRY, replaced=[])
        errors, _notes = gate.evaluate('x', entry, ['B.ttf'])
        self.assertTrue(any('A.ttf' in e and '1bf06137' in e for e in errors), errors)

    def test_new_replacement_is_allowed(self):
        errors, notes = gate.evaluate('x', self.ENTRY, ['A.ttf', 'B.ttf', 'C.ttf'])
        self.assertEqual(errors, [])
        self.assertTrue(any('新增替换 C.ttf' in n for n in notes), notes)


class MapperTest(unittest.TestCase):
    def test_committed_baseline_passes(self):
        self.assertEqual(gate.check(), 0)

    def test_baseline_covers_1bf06137_except_registered_keeps(self):
        data = gate.load()
        for rom, entry in data['roms'].items():
            legacy = set(entry.get('legacyReplaced') or [])
            self.assertTrue(legacy, rom)
            missing = legacy - set(entry['replaced'])
            for name in missing:
                self.assertTrue(gate._reason_ok(entry['keptStock'].get(name)), (rom, name))
        hyperos = data['roms']['hyperos']
        # Code monospace restored; only clock/tabular Mono and MiSansL3 kept on purpose.
        for name in ('DroidSansMono.ttf', 'RobotoMono-Regular.ttf', 'NotoSansMono-Regular.ttf'):
            self.assertIn(name, hyperos['replaced'])
        self.assertEqual(sorted(set(hyperos['legacyReplaced']) - set(hyperos['replaced'])),
                         ['MiClockMono.otf', 'MiSansL3.otf', 'MitypeClockMono.otf', 'MitypeMonoVF.ttf'])

    def test_reintroduced_mono_regression_is_caught(self):
        # Re-create the #290 behaviour (every *mono* kept stock) in a copy of the mapper.
        shell = ROOT / 'common/legacy_v14_4/hyperos_full_coverage.sh'
        text = shell.read_text(encoding='utf-8')
        marker = '_lhpp_safe_name() {\n'
        self.assertIn(marker, text)
        patched = text.replace(marker, marker + '    case "$1" in *[Mm][Oo][Nn][Oo]*) return 1 ;; esac\n', 1)
        entry = gate.load()['roms']['hyperos']
        with tempfile.TemporaryDirectory() as raw:
            copy = Path(raw) / shell.name
            copy.write_text(patched, encoding='utf-8')
            replaced = gate.replaced_names('hyperos', entry['fixture'], script_path=copy)
        errors, _notes = gate.evaluate('hyperos', entry, replaced)
        joined = '\n'.join(errors)
        for name in ('DroidSansMono.ttf', 'RobotoMono-Regular.ttf', 'NotoSansMono-Regular.ttf'):
            self.assertIn(name, joined)


if __name__ == '__main__':
    unittest.main(verbosity=2)
