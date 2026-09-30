#!/usr/bin/env python3
"""Scan-time glyph archive is byte/face-bound and numerically matches compiler probes."""
import hashlib
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'scripts')]
from fontTools.ttLib import TTFont
import stock_geometry_profile as archive
import universal_font_compiler as compiler
import universal_fixed_mixed_shell_test as fixed
import universal_probe_performance_test as performance

class StockGeometryProfileTest(unittest.TestCase):
    def setUp(self):
        self.case=fixed.FixedMixedShellTest(); self.case.setUp(); self.addCleanup(self.case.tearDown)
    def identity(self,path,face=0):
        return dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),faceIndex=face)
    def test_static_default_profile_matches_and_input_is_unchanged(self):
        path=self.case.source; before=path.read_bytes()
        result=archive.capture_geometry_profile(path,0,self.identity(path))
        with TTFont(path,lazy=True,recalcBBoxes=False) as font:
            self.assertEqual(result['profile'],compiler._profile_from_font(font))
        self.assertEqual(result['location'],{})
        self.assertEqual(path.read_bytes(),before)
    def test_variable_default_profile_matches_full_instance_with_metric_axes(self):
        metric=performance.ProbePerformanceTest(); metric.setUp(); self.addCleanup(metric.doCleanups)
        metric.add_metric_axes(); path=metric.case.stock; before=path.read_bytes()
        result=archive.capture_geometry_profile(path,0,self.identity(path))
        with TTFont(path,lazy=True,recalcBBoxes=False) as font:
            full=compiler.instantiateVariableFont(font,result['location'],inplace=False,optimize=True)
            try:self.assertEqual(result['profile'],compiler._profile_from_font(full))
            finally:full.close()
        self.assertEqual(path.read_bytes(),before)
    def test_stale_hash_and_wrong_face_never_become_archive(self):
        path=self.case.source; identity=self.identity(path)
        path.write_bytes(path.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'changed before'):archive.capture_geometry_profile(path,0,identity)
        with self.assertRaisesRegex(ValueError,'face'):archive.capture_geometry_profile(path,1,self.identity(path,0))
        with self.assertRaisesRegex(ValueError,'no requested face'):archive.capture_geometry_profile(path,1,self.identity(path,1))

if __name__=='__main__':unittest.main(verbosity=2)
