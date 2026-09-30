#!/usr/bin/env python3
"""Bounded actual shared-Han geometry, never a missing-probe bypass."""
import sys
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'common'), str(ROOT / 'scripts')]
import universal_font_compiler as compiler
import universal_font_compiler_test as fixture
import font_source_profile
from fontTools.ttLib import TTFont

class SharedHanTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()
    def font(self, name, points):
        old = fixture.ASCII_POINTS
        try:
            fixture.ASCII_POINTS = points
            path = self.root / name
            fixture.make_font(path, family='Rare Han Fixture')
            return path
        finally:
            fixture.ASCII_POINTS = old
    def test_rare_han_subset_is_measured_after_reopen(self):
        points = tuple(range(0x9f80, 0x9f90))
        stock = self.font('stock.ttf', points)
        source = self.font('source.ttf', points)
        face = font_source_profile.build([source])['files'][0]['faces'][0]
        face['_sourcePath'] = str(source)
        import universal_font_plan
        target = {'path':'/system/fonts/RareHan.ttf','role':'cjk','source':universal_font_plan._source_ref(face),
                  'targetContract':{'weight':400,'faceIndex':0},'families':['sans-serif']}
        artifact = {'artifactId':'ufc:test','requiredWeight':400,'requiredFaceIndex':0,'requiredAxes':[]}
        output = self.root / 'output.ttf'
        report = compiler._compile_stock_shell(target, artifact, stock, output, self.root)
        self.assertEqual(report['geometry']['sharedProbePoints']['cjk'], list(points))
        self.assertEqual(report['validation']['alignment']['probes']['cjk']['heightDeltaRatio'], 0)
        with TTFont(output) as font:
            self.assertEqual(set(font.getBestCmap()), set(points))
    def test_too_few_or_non_han_shared_probes_rejected(self):
        for points in [(0x9f80,0x9f81,0x9f82), tuple(range(0x41,0x50))]:
            a=self.font('a.ttf',points);b=self.font('b.ttf',points)
            with TTFont(a) as stock, TTFont(b) as source:
                with self.assertRaisesRegex(compiler.CompilerError,'four shared Han'):
                    compiler._paired_geometry_profiles(stock,source,'cjk')
    def test_reopened_probe_loss_rejected(self):
        points=tuple(range(0x9f80,0x9f90))
        a=self.font('a.ttf',points);b=self.font('b.ttf',points)
        with TTFont(a) as stock,TTFont(b) as source:
            profile,_=compiler._paired_geometry_profiles(stock,source,'cjk')
        empty=self.font('empty.ttf',tuple(range(0x41,0x50)))
        with self.assertRaisesRegex(compiler.CompilerError,'lost shared Han'):
            compiler._validate_output_face(empty,0,{'targetContract':{}},{'requiredWeight':400},profile,{},'cjk')

if __name__ == '__main__': unittest.main()
