#!/usr/bin/env python3
"""Real scan -> font merge -> namespace proof -> App trace regressions.

The fixture exercises the normal anonymous-glyph TrueType format (post 3.0),
source/stock glyph-name collisions, reordered source GIDs, preserved composite
dependencies, and stock Arabic shaping. No scanner or merger is mocked.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from fontTools.ttLib import TTFont
from fontTools.ttLib.reorderGlyphs import reorderGlyphs

from coverage_inventory_integration_test import CoverageFixture, LATIN, REGULAR
from inventory_font_supplement_test import fixture, outline, shape
import device_font_slot_trace as trace
import physical_font_load_verify as physical_verify


class MergerSerializationIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.f = CoverageFixture()
        self.addCleanup(self.f.close)

    def prepare(self, *, stock_anonymous=True, source_anonymous=False,
                reordered_source=False, source_cff=False):
        f = self.f
        stock = f.stock / REGULAR.lstrip('/')
        fixture(stock)
        fixture(f.source, source=True, cff=source_cff)
        han = set(range(0x4E00, 0x4E20))
        for path, donor, anonymous in ((stock, False, stock_anonymous),
                                      (f.source, True, source_anonymous)):
            with TTFont(path) as font:
                for table in font['cmap'].tables:
                    if table.isUnicode() and table.format != 14:
                        for cp in LATIN | han:
                            table.cmap.setdefault(cp, 'A' if donor else 'B')
                        if not donor:
                            table.cmap[0x3042] = 'cyrillic'
                # Stock Alpha is a composite of stock A. A becomes unencoded
                # after replacement: post 3.0 reloads it as glyph00001, while
                # the component and every layout reference keep the same GID.
                if anonymous:
                    font['post'].formatType = 3.0
                if donor and reordered_source:
                    order = font.getGlyphOrder()
                    reorderGlyphs(font, [order[0], *reversed(order[1:])])
                font.save(path)
        f.scan()
        return stock

    def run_pipeline(self, **options):
        f = self.f
        stock = self.prepare(**options)
        input_bytes = {path: path.read_bytes() for path in (stock, f.source)}
        before_live = f.snapshot_live()
        expected_shapes = {text: shape(stock, text) for text in ('ΑΒ', 'بَا', 'あ')}
        result = f.invoke()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        summary = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertNotEqual(summary.get('status'), 'error', summary)
        self.assertEqual(before_live, f.snapshot_live())
        self.assertEqual(f.inventory['romKind'], 'generic')

        output = f.path(REGULAR)
        with TTFont(stock) as old, TTFont(f.source) as donor, TTFont(output) as merged:
            self.assertEqual(set(old.getBestCmap()), set(merged.getBestCmap()))
            for cp in (ord('A'), ord('0'), 0x4E00):
                actual = outline(merged, merged.getBestCmap()[cp])
                self.assertEqual(actual, outline(donor, donor.getBestCmap()[cp]))
                self.assertNotEqual(actual, outline(old, old.getBestCmap()[cp]))
            for cp in (0x391, 0x392, 0x410, 0x627, 0x628, 0x64E, 0x3042):
                self.assertEqual(outline(merged, merged.getBestCmap()[cp]),
                                 outline(old, old.getBestCmap()[cp]), hex(cp))
        for text, expected in expected_shapes.items():
            self.assertEqual(shape(output, text), expected, text)
        for path, data in input_bytes.items():
            self.assertEqual(path.read_bytes(), data)
        row = next(row for row in f.report()['slots'] if row['slot'] == REGULAR)
        self.assertEqual(set(row['replacedRoles']), {'cjk', 'latin', 'digit'})
        self.assertTrue(row['supplemented'])
        self.assertGreaterEqual(row['retainedStockCodepoints'], 7)

        pending = trace.build_physical_trace(f.inventory, f.stage, prepared=True,
                                            active_font='selected')
        pending_slot = next(row for row in pending['slots'] if row['path'] == REGULAR)
        self.assertEqual(pending_slot['category'], 'pending')
        self.assertNotEqual(pending_slot['state'], 'loaded')

        # Stand in only for Android's namespace root; use actual complete font
        # bytes, actual output manifest, and the production verifier + trace.
        visible = f.root / 'visible'
        shutil.copytree(f.stage, f.live, dirs_exist_ok=True)
        shutil.copytree(f.live, visible)
        with patch.dict(os.environ, LUOSHU_VISIBLE_ROOT=str(visible),
                        LUOSHU_TEST_BOOT_ID='serialization-regression'):
            verified = physical_verify.verify(f.module, f.live, 'selected')
            physical_verify.save_result(f.module, verified, True)
            self.assertEqual(verified['state'], 'verified', verified)
            state = trace.build_physical_trace(f.inventory, f.live, active_font='selected')
            active_slot = next(row for row in state['slots'] if row['path'] == REGULAR)
            self.assertEqual(active_slot['state'], 'loaded')
            # Replacing the runtime-visible file with default stock must be a
            # failed slot even if its generated output is present and valid.
            (visible / REGULAR.lstrip('/')).write_bytes(stock.read_bytes())
            failed = physical_verify.verify(f.module, f.live, 'selected')
            physical_verify.save_result(f.module, failed, True)
            self.assertEqual(failed['state'], 'failed')
            state = trace.build_physical_trace(f.inventory, f.live, active_font='selected')
            active_slot = next(row for row in state['slots'] if row['path'] == REGULAR)
            self.assertEqual(active_slot['state'], 'mismatch')
            self.assertEqual(active_slot['reasonCode'], 'runtime-visible-digest-mismatch')
            self.assertFalse(active_slot['safeToRetry'])

    def test_anonymous_stock_keeps_components_and_unrelated_shaping(self):
        self.run_pipeline()

    def test_both_anonymous_with_reordered_source_gids(self):
        self.run_pipeline(source_anonymous=True, reordered_source=True)

    def test_named_stock_and_anonymous_reordered_source(self):
        self.run_pipeline(stock_anonymous=False, source_anonymous=True, reordered_source=True)

    def test_cff_donor_with_anonymous_stock_keeps_real_curves_and_shaping(self):
        self.run_pipeline(source_cff=True)

    def test_partial_source_replaces_available_glyphs_and_app_reports_retained_text(self):
        f = self.f
        stock_path = self.prepare(source_anonymous=True)
        with TTFont(f.source) as font:
            for table in font['cmap'].tables:
                if table.isUnicode() and table.format != 14:
                    table.cmap = {cp: glyph for cp, glyph in table.cmap.items() if cp in {65, 48}}
            font.save(f.source)
        result = f.invoke()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with TTFont(f.path(REGULAR)) as output, TTFont(stock_path) as stock, TTFont(f.source) as donor:
            for cp in (65, 48):
                self.assertEqual(outline(output, output.getBestCmap()[cp]),
                                 outline(donor, donor.getBestCmap()[cp]))
                self.assertNotEqual(outline(output, output.getBestCmap()[cp]),
                                    outline(stock, stock.getBestCmap()[cp]))
            for cp in (66, 0x4E00, 0x391, 0x627):
                self.assertEqual(outline(output, output.getBestCmap()[cp]),
                                 outline(stock, stock.getBestCmap()[cp]))
        for text in ('ΑΒ', 'بَا', 'あ'):
            self.assertEqual(shape(f.path(REGULAR), text), shape(stock_path, text))
        row = next(row for row in f.report()['slots'] if row['slot'] == REGULAR)
        self.assertEqual(row['replacedRoleCounts'], {'cjk': 0, 'latin': 1, 'digit': 1})
        self.assertEqual(row['retainedTargetRoleCounts'], {'cjk': 32, 'latin': 51, 'digit': 9})
        visible = f.root / 'visible'
        shutil.copytree(f.stage, f.live, dirs_exist_ok=True)
        shutil.copytree(f.live, visible)
        with patch.dict(os.environ, LUOSHU_VISIBLE_ROOT=str(visible), LUOSHU_TEST_BOOT_ID='partial-text'):
            verified = physical_verify.verify(f.module, f.live, 'selected')
            physical_verify.save_result(f.module, verified, True)
            self.assertEqual(verified['state'], 'verified')
            state = trace.build_physical_trace(f.inventory, f.live, active_font='selected')
            slot = next(row for row in state['slots'] if row['path'] == REGULAR)
            self.assertEqual(slot['state'], 'partial')
            self.assertFalse(slot['safeToRetry'])
            self.assertIn('英文 1 个字形', slot['routes'][0]['planReason'])
            self.assertIn('保留原厂：中文 32 个字形、英文 51 个字形、数字 9 个字形',
                          slot['routes'][0]['planReason'])


if __name__ == '__main__':
    unittest.main()
