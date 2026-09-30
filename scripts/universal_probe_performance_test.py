#!/usr/bin/env python3
"""Numerical/byte equivalence for probe-only measurements and request-local reuse.

No phone speed threshold. Large synthetic batch benchmarking is separate.
"""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import hashlib
import json
import os
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'scripts')]
from fontTools.ttLib import TTFont,newTable
from fontTools.ttLib.tables import otTables as ot
import universal_font_compiler as compiler
import universal_font_compiler_test as fixture
import universal_fixed_mixed_shell_test as fixed
import universal_shared_han_probe_test as han
from stock_provenance_fixture import synthetic_identity

class ProbePerformanceTest(unittest.TestCase):
    def setUp(self):
        self.case=fixed.FixedMixedShellTest();self.case.setUp();self.addCleanup(self.case.tearDown)
        self.root=self.case.root
    def add_metric_axes(self):
        with TTFont(self.case.stock) as font:
            font.ensureDecompiled()
            avar=font['avar']=newTable('avar')
            avar.segments={str(a.axisTag):{-1:-1,-.5:-.75,0:0,.5:.75,1:1} for a in font['fvar'].axes}
            mvar=font['MVAR']=newTable('MVAR');mvar.table=ot.MVAR();t=mvar.table
            t.Version=0x10000;t.Reserved=0;t.ValueRecordSize=8
            t.VarStore=deepcopy(font['HVAR'].table.VarStore)
            t.VarStore.VarData[0].Item[0]=[20];t.VarStore.VarData[0].Item[1]=[-10];t.VarStore.VarData[0].Item[2]=[10]
            t.ValueRecord=[]
            for tag,index in [('hasc',0),('hcla',0),('hdsc',1),('hcld',2)]:
                record=ot.MetricsValueRecord();record.ValueTag=tag;record.VarIdx=index;t.ValueRecord.append(record)
            t.ValueRecord.sort(key=lambda r:r.ValueTag);t.ValueRecordCount=len(t.ValueRecord)
            font.save(self.case.stock)
    def test_full_profile_and_reopened_checks_equal_across_all_axes(self):
        self.add_metric_axes();before=self.case.stock.read_bytes()
        locations=[{'wght':100,'wdth':75,'slnt':0,'ital':0},
                   {'wght':400,'wdth':100,'slnt':0,'ital':0},
                   {'wght':650,'wdth':112.5,'slnt':-5,'ital':.5},
                   {'wght':900,'wdth':125,'slnt':-10,'ital':1}]
        for axes in locations:
            profiles=[];measurements=[];vertical=[]
            for optimized in (False,True):
                with patch.object(compiler,'_PROBE_ONLY_ENABLED',optimized):
                    font,location=compiler._stock_geometry_font(self.case.stock,0,int(axes['wght']),axes)
                    try:
                        profiles.append(compiler._profile_from_font(font))
                        vertical.append(dict(font['vmtx'].metrics))
                    finally:font.close()
                    artifact={'requiredWeight':int(axes['wght']),'requiredAxes':[{'tag':k,'stylevalue':v} for k,v in axes.items()]}
                    measurements.append(compiler._validate_output_face(self.case.stock,0,{},artifact,profiles[-1],axes,'latin'))
            self.assertEqual(profiles[0],profiles[1],axes)
            self.assertEqual(measurements[0],measurements[1],axes)
            for name,value in vertical[1].items():self.assertEqual(value,vertical[0][name])
        self.assertEqual(self.case.stock.read_bytes(),before)
    def test_shared_han_sampling_uses_full_cmap_even_when_only_probes_are_instanced(self):
        points=tuple(range(0x9F00,0xA000))
        old=fixture.ASCII_POINTS
        try:
            fixture.ASCII_POINTS=points
            stock=self.root/'rare-vf.ttf';source=self.root/'rare-source.ttf'
            fixture.make_font(stock,family='Rare',variable=True)
            fixture.make_font(source,family='Rare')
        finally:fixture.ASCII_POINTS=old
        profiles=[];counts=[]
        for enabled in (False,True):
            with patch.object(compiler,'_PROBE_ONLY_ENABLED',enabled),TTFont(source) as src:
                font,_=compiler._stock_geometry_font(stock,0,700,{},source_font=src,role='cjk')
                try:
                    profiles.append(compiler._paired_geometry_profiles(font,src,'cjk'));counts.append(len(font.getGlyphOrder()))
                    compiler._validate_output_face(stock,0,{}, {'requiredWeight':700},profiles[-1][0],{},'cjk')
                finally:font.close()
        self.assertEqual(profiles[0],profiles[1]);self.assertLess(counts[1],counts[0])
        self.assertEqual(len(profiles[1][0]['sharedProbePoints']['cjk']),64)
    def unit(self,index,weight=400):
        target=deepcopy(self.case.target);target['path']=f'/system/fonts/Reuse{index}.ttf'
        target['targetContract']['stockIdentity']=synthetic_identity(target['path'],self.case.stock,0)
        artifact=compiler._physical_artifact(target,self.case.plan);artifact['requiredWeight']=weight
        return {'target':target,'artifact':artifact,'deploymentKinds':['physical-slot'],'routeNodes':[]}
    def compile(self,unit,out,cache=None):
        out.mkdir(exist_ok=True)
        return compiler._compile_unit(unit,{unit['target']['path']:self.case.stock},out,False,cache)
    def test_cache_reuses_only_identical_render_but_revalidates_each_contract(self):
        cache={};real=compiler._replace_role_glyphs
        units=[self.unit(0,400),self.unit(1,700)]
        with patch.object(compiler,'_replace_role_glyphs',wraps=real) as render:
            a=self.compile(units[0],self.root/'cached',cache);b=self.compile(units[1],self.root/'cached',cache)
            self.assertEqual(a['status'],'ready',a);self.assertEqual(b['status'],'ready',b)
            self.assertEqual(render.call_count,1)
            self.assertTrue(b['report']['renderReuse']['hit'])
        plain=self.compile(units[1],self.root/'plain')
        self.assertEqual(plain['status'],'ready',plain)
        self.assertEqual(Path(b['output']).read_bytes(),Path(plain['output']).read_bytes())
        self.assertEqual(b['report']['validation'],plain['report']['validation'])
        bad=self.unit(2);bad['artifact']['requiredPostScriptName']='NotTheStockName'
        result=self.compile(bad,self.root/'cached',cache)
        self.assertEqual(result['status'],'blocked');self.assertIn('PostScriptName',result['reason'])
    def test_cache_is_invalidated_by_source_stock_or_geometry_and_checks_file_integrity(self):
        cache={};a=self.compile(self.unit(0),self.root/'cached',cache);self.assertEqual(a['status'],'ready')
        output=Path(a['output']);output.write_bytes(output.read_bytes()+b'changed')
        result=self.compile(self.unit(1),self.root/'cached',cache)
        self.assertEqual(result['status'],'blocked');self.assertIn('cache integrity',result['reason'])
        cache={};a=self.compile(self.unit(3),self.root/'cached',cache)
        with TTFont(self.case.stock) as font:
            font['name'].setName('Different OEM',1,3,1,0x409);font.save(self.case.stock)
        b=self.compile(self.unit(4),self.root/'cached',cache)
        self.assertEqual(b['status'],'ready',b);self.assertFalse(b['report']['renderReuse']['hit'])
        # Exact measured geometry participates in the cache key.
        real=compiler._geometry_plan
        def shifted(*args,**kwargs):
            g=real(*args,**kwargs);g['transforms']['latinCap']['shiftY']+=1;return g
        with patch.object(compiler,'_geometry_plan',side_effect=shifted):
            c=self.compile(self.unit(5),self.root/'cached',cache)
        self.assertEqual(c['status'],'ready',c);self.assertFalse(c['report']['renderReuse']['hit'])
        self.case.source.write_bytes(self.case.source.read_bytes()+b'changed')
        d=self.compile(self.unit(6),self.root/'cached',cache)
        self.assertEqual(d['status'],'blocked');self.assertIn('内容已变化',d['reason'])
    def test_prepared_donor_reuse_is_bounded_and_independent_of_oem_container(self):
        cache={};first=self.compile(self.unit(0),self.root/'donor-cache',cache)
        self.assertEqual(first['status'],'ready',first)
        with TTFont(self.case.stock) as font:
            font['name'].setName('Second OEM container',1,3,1,0x409);font.save(self.case.stock)
        unit=self.unit(1)
        cached=self.compile(unit,self.root/'donor-cache',cache)
        plain=self.compile(unit,self.root/'donor-plain')
        self.assertEqual(cached['status'],'ready',cached);self.assertEqual(plain['status'],'ready',plain)
        self.assertFalse(cached['report']['renderReuse']['hit'])
        self.assertGreater(cached['report']['replaced']['preparedDonorReuse']['hits'],0)
        self.assertEqual(Path(cached['output']).read_bytes(),Path(plain['output']).read_bytes())
        entry=cache['_sourceMeasurements']
        self.assertLessEqual(entry['glyphBytes'],compiler._PREPARED_GLYPH_CACHE_BYTES)
        self.assertLessEqual(entry['boundsBytes'],compiler._SOURCE_BOUNDS_CACHE_BYTES)
        self.assertTrue(all(isinstance(item[0],bytes) for item in entry['glyphs'].values()))
        with patch.object(compiler,'_PREPARED_GLYPH_CACHE_BYTES',1),patch.object(compiler,'_SOURCE_BOUNDS_CACHE_BYTES',1):
            bounded={};result=self.compile(self.unit(2),self.root/'no-admission',bounded)
        self.assertEqual(result['status'],'ready',result)
        self.assertEqual(bounded['_sourceMeasurements']['glyphBytes'],0)
        self.assertEqual(bounded['_sourceMeasurements']['boundsBytes'],0)

    def test_already_fitted_source_has_identity_second_fit_for_each_measured_slot(self):
        source=self.root/'fit-source.ttf';stock=self.root/'fit-stock.ttf'
        fixture.make_font(source,family='User',y_min=-120,y_max=720)
        fixture.make_font(stock,family='OEM',y_min=-80,y_max=800)
        logical='/system/fonts/Fit.ttf';slot=fixture.slot_from_stock(logical,stock,family='sans-serif',source_xml=None,declared='Fit.ttf')
        plan,route=fixture.build_plans(source,slot,'latin',None)
        first=compiler.compile_all(plan,route,{logical:stock},self.root/'first',False)['artifacts'][0]
        self.assertEqual(first['status'],'ready',first)
        fitted=Path(first['output']);plan,route=fixture.build_plans(fitted,slot,'latin',None)
        second=compiler.compile_all(plan,route,{logical:stock},self.root/'second',False)['artifacts'][0]
        self.assertEqual(second['status'],'ready',second)
        for name in ('latinCap','latinX','latinDescender','digits'):
            transform=second['report']['geometry']['transforms'][name]
            self.assertAlmostEqual(transform['relativeScaleY'],1,places=6)
            self.assertLessEqual(abs(transform['shiftY']),1)
        with TTFont(first['output']) as a,TTFont(second['output']) as b:
            for cp in map(ord,'Agx147'):
                self.assertEqual(a['glyf'][a.getBestCmap()[cp]].getCoordinates(a['glyf'])[0],b['glyf'][b.getBestCmap()[cp]].getCoordinates(b['glyf'])[0])
    def test_donor_point_count_change_does_not_decode_gvar_against_new_outline(self):
        from fontTools.pens.ttGlyphPen import TTGlyphPen
        with TTFont(self.case.source) as font:
            for name in font.getGlyphOrder():
                if not font['glyf'][name].numberOfContours: continue
                pen=TTGlyphPen(None);pen.moveTo((50,0));pen.lineTo((550,0));pen.lineTo((300,700));pen.closePath()
                font['glyf'][name]=pen.glyph()
            font.save(self.case.source)
        digest=hashlib.sha256(self.case.source.read_bytes()).hexdigest()
        self.case.target['source']['fileUid']='sha256:'+digest
        self.case.target['source']['mixedSelection']['fontSha256']=digest
        result=self.compile(self.unit(0),self.root/'different-topology')
        self.assertEqual(result['status'],'ready',result)
        with TTFont(result['output']) as font:
            name=font.getBestCmap()[ord('A')]
            self.assertEqual(len(font['glyf'][name].getCoordinates(font['glyf'])[0]),3)
            self.assertFalse(font['gvar'].variations.get(name))

    def test_phase_trace_keeps_request_identity_and_completion(self):
        env={'LUOSHU_UNIVERSAL_MIX_STRICT':'1','LUOSHU_MIX_REQUEST_ID':'trace-request',
             'LUOSHU_SWITCH_PROGRESS_FILE':str(self.root/'progress.conf')}
        with patch.dict(os.environ,env):
            result=self.compile(self.unit(0),self.root/'trace')
        self.assertEqual(result['status'],'ready',result)
        records=[json.loads(x) for x in (self.root/'universal-compile-trace.jsonl').read_text().splitlines()]
        self.assertTrue(all(r['requestId']=='trace-request' for r in records))
        self.assertEqual(records[0]['event'],'unit-start');self.assertEqual(records[-1]['event'],'unit-end')
        self.assertEqual(records[-1]['status'],'ready');self.assertGreater(records[-1]['elapsedSeconds'],0)
        self.assertIn('output-validation',{r.get('phase') for r in records})

if __name__=='__main__':unittest.main(verbosity=2)
