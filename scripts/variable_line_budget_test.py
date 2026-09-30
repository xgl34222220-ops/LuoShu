#!/usr/bin/env python3
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'common'))
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import otTables as ot
from fontTools.varLib.builder import buildVarData, buildVarRegionList, buildVarStore
from variable_line_budget import mvar_ranges


def font_with_regions(regions, values, axis_tags=('wght',), tag='hasc'):
    font=TTFont()
    fvar=font['fvar']=newTable('fvar')
    fvar.axes=[SimpleNamespace(axisTag=axis) for axis in axis_tags]
    mvar=font['MVAR']=newTable('MVAR'); table=mvar.table=ot.MVAR()
    table.Version=0x00010000;table.Reserved=0;table.ValueRecordSize=8
    table.VarStore=buildVarStore(buildVarRegionList(regions,list(axis_tags)),
        [buildVarData(list(range(len(regions))),[values],optimize=False)])
    record=ot.MetricsValueRecord();record.ValueTag=tag;record.VarIdx=0
    table.ValueRecord=[record];table.ValueRecordCount=1
    return font


class BudgetTests(unittest.TestCase):
    def test_mutually_exclusive_regions_no_false_clipping(self):
        f=font_with_regions([{'wght':(-1,-1,0)},{'wght':(0,1,1)}],[-200,-200])
        bounds,report=mvar_ranges(f,['hasc'])
        self.assertEqual(bounds['hasc'],(-200,0))
        self.assertEqual(report['method'],'exact-mvar-breakpoint-grid')
        self.assertGreaterEqual(1000+bounds['hasc'][0],750)
        self.assertLess(1000+sum([-200,-200]),750)  # old rejection reproduced
    def test_overlapping_regions_keep_real_clipping(self):
        f=font_with_regions([{'wght':(0,1,1)},{'wght':(0,1,1)}],[-200,-200])
        bounds,_=mvar_ranges(f,['hasc'])
        self.assertEqual(bounds['hasc'],(-400,0))
        self.assertLess(1000+bounds['hasc'][0],750)
    def test_multiaxis_intersections_and_defaults(self):
        f=font_with_regions([{'wght':(0,1,1),'wdth':(0,1,1)},
                             {'wght':(0,1,1),'wdth':(-1,-1,0)}],[-200,100],('wght','wdth'))
        bounds,report=mvar_ranges(f,['hasc','hdsc'])
        self.assertEqual(bounds,{'hasc':(-200,100),'hdsc':(0,0)})
        self.assertEqual(report['pointCount'],9)
    def test_interior_peak_is_included(self):
        f=font_with_regions([{'wght':(0,.5,1)}],[-250])
        self.assertEqual(mvar_ranges(f,['hasc'])[0]['hasc'],(-250,0))
    def test_high_dimensional_grid_falls_back_safely(self):
        axes=tuple('a%03d'%i for i in range(8))
        f=font_with_regions([{axis:(0,.5,1) for axis in axes}],[-200],axes)
        bounds,report=mvar_ranges(f,['hasc'])
        self.assertEqual(bounds['hasc'],(-200,0))
        self.assertEqual(report['fallbackReason'],'point-budget-exceeded')
        self.assertGreater(report['candidatePointCount'],4096)
        self.assertEqual(report['pointCount'],0)
    def test_interior_discontinuity_retains_conservative_bound(self):
        f=font_with_regions([{'wght':(.5,.5,1)}],[-200])
        bounds,report=mvar_ranges(f,['hasc'])
        self.assertEqual(bounds['hasc'],(-200,0))
        self.assertEqual(report['fallbackReason'],'interior-discontinuous-region')
    def test_unrequested_tables_and_input_unchanged(self):
        f=font_with_regions([{'wght':(0,1,1)}],[-200])
        before=f['MVAR'].compile(f)
        bounds,_=mvar_ranges(f,['hasc'])
        self.assertEqual(f['MVAR'].compile(f),before)
        self.assertEqual(mvar_ranges(f,['unrelated'])[0],{'unrelated':(0,0)})
        self.assertEqual(mvar_ranges(TTFont(),['hasc'])[0],{'hasc':(0,0)})
    def test_no_variation_index_has_zero_delta(self):
        f=font_with_regions([{'wght':(0,1,1)}],[-200])
        f['MVAR'].table.ValueRecord[0].VarIdx=0xFFFFFFFF
        self.assertEqual(mvar_ranges(f,['hasc'])[0]['hasc'],(0,0))

if __name__=='__main__':unittest.main(verbosity=2)
