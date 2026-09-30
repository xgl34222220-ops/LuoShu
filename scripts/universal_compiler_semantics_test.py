#!/usr/bin/env python3
"""Synthetic semantic counterexamples plus functional controls; no private fonts."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import hashlib
import os
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'common'), str(ROOT/'scripts')]
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables.ttProgram import Program
from fontTools.ttLib.tables._f_v_a_r import Axis
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.ttGlyphPen import TTGlyphPen
import universal_font_compiler as compiler
import universal_font_semantics as semantics
import universal_font_compiler_test as fixture
import universal_fixed_mixed_shell_test as mixed


class SemanticCompilerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='compiler-semantics-')
        self.root = Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def fonts(self, variable=False):
        source, stock = self.root/'source.ttf', self.root/'stock.ttf'
        fixture.make_font(source, family='Semantic Source', variable=variable, y_min=-100, y_max=700)
        fixture.make_font(stock, family='Semantic Stock', variable=variable, y_min=-100, y_max=700 if variable else 780)
        return source,stock
    def compile(self, source, stock):
        logical = '/system/fonts/Semantic.ttf'
        slot = fixture.slot_from_stock(logical,stock,family='sans-serif',source_xml=None,declared='Semantic.ttf')
        plan,route = fixture.build_plans(source,slot,'latin',None)
        return compiler.compile_all(plan,route,{logical:stock},self.root/'out',False)['artifacts'][0]
    @staticmethod
    def bounds(font, name):
        from fontTools.pens.boundsPen import BoundsPen
        glyphs = font.getGlyphSet(); pen = BoundsPen(glyphs);glyphs[name].draw(pen)
        return pen.bounds
    @staticmethod
    def add_deltas(path, delta, support=(0,1,1), sparse=False):
        with TTFont(path) as font:
            for name in font.getGlyphOrder()[1:]:
                n = len(font['glyf'][name].getCoordinates(font['glyf'])[0])
                values = [(0,delta)]*n + [(0,0)]*4
                if sparse: values = [(0,delta)] + [None]*(n-1) + [(0,0)]*4
                font['gvar'].variations[name] = [TupleVariation({'wght':support},values)]
            font.save(path)
    def test_extreme_and_interior_vf_ink_rejected(self):
        for support in ((0,1,1),(.2,.5,.8)):
            with self.subTest(support=support):
                source,stock = self.fonts(True);self.add_deltas(source,2000,support)
                result = self.compile(source,stock)
                self.assertEqual(result['status'],'blocked',result)
                self.assertIn('conservative line budget',result['reason'])
    def test_sparse_iup_deltas_are_included(self):
        source,stock=self.fonts(True);self.add_deltas(source,2000,sparse=True)
        self.assertIn('conservative line budget',self.compile(source,stock)['reason'])
    def test_real_safe_variation_remains_variable(self):
        source,stock=self.fonts(True);self.add_deltas(source,20, (.2,.5,.8))
        result=self.compile(source,stock);self.assertEqual(result['status'],'ready',result)
        self.assertEqual(result['report']['variableInkSafety']['method'],'all-glyph-signed-gvar-intervals')
        with TTFont(result['output']) as font:
            self.assertIn('gvar',font)
            low=instantiateVariableFont(font,{'wght':400},inplace=False)
            peak=instantiateVariableFont(font,{'wght':650},inplace=False)
            self.assertEqual(self.bounds(peak,'u0041')[3]-self.bounds(low,'u0041')[3],20)
            low.close();peak.close()
    def test_combined_axis_deltas_are_bounded(self):
        source,stock=self.fonts(True)
        with TTFont(source) as font:
            font.ensureDecompiled();axis=Axis();axis.axisTag='wdth';axis.minValue=75;axis.defaultValue=100;axis.maxValue=125;axis.flags=0;axis.axisNameID=257
            font['fvar'].axes.append(axis)
            for name in font.getGlyphOrder()[1:]:
                n=len(font['glyf'][name].getCoordinates(font['glyf'])[0]);d=[(0,150)]*n+[(0,0)]*4
                font['gvar'].variations[name]=[TupleVariation({tag:(0,1,1)},d) for tag in ('wght','wdth')]
            font.save(source)
        result=self.compile(source,stock);self.assertEqual(result['status'],'blocked');self.assertIn('line budget',result['reason'])
    @contextmanager
    def shell(self):
        case=mixed.FixedMixedShellTest();case.setUp()
        try: yield case
        finally: case.tearDown()
    @staticmethod
    def refresh(case):
        policy=deepcopy(case.target['source']['mixedSelection'])
        policy['fontSha256']=hashlib.sha256(case.source.read_bytes()).hexdigest()
        slot=fixture.slot_from_stock(case.logical,case.stock,family='sans-serif',source_xml=None,declared='SyntheticUiVF.ttf')
        case.plan,case.route=fixture.build_plans(case.source,slot,'latin',None)
        case.target=case.plan['targets'][case.logical];case.target['source']['mixedSelection']=policy
    def test_foreign_hint_program_removed_without_replacing_oem_environment(self):
        with self.shell() as case:
            with TTFont(case.source) as font:
                name=font.getBestCmap()[65];font['glyf'][name].program=Program();font['glyf'][name].program.fromAssembly(['PUSHB[ ]','127','CALL[ ]'])
                font['fpgm']=newTable('fpgm');font['fpgm'].program=Program();font['fpgm'].program.fromAssembly(['PUSHB[ ]','127','FDEF[ ]','ENDF[ ]'])
                font['maxp'].maxFunctionDefs=1;font['maxp'].maxStackElements=1;font.save(case.source)
            with TTFont(case.stock) as font:
                font['fpgm']=newTable('fpgm');font['fpgm'].program=Program();font['fpgm'].program.fromAssembly(['PUSHB[ ]','0','FDEF[ ]','ENDF[ ]'])
                font['maxp'].maxFunctionDefs=1;font['maxp'].maxStackElements=1;font.save(case.stock)
                original=font.getTableData('fpgm')
            self.refresh(case);result=case.compile();self.assertEqual(result['status'],'ready',result)
            with TTFont(result['output']) as font:
                self.assertEqual(font['glyf'][font.getBestCmap()[65]].program.getBytecode(),b'')
                self.assertEqual(font.getTableData('fpgm'),original)
    def test_nonselected_composites_keep_old_gvar_and_metric_dependencies(self):
        with self.shell() as case:
            with TTFont(case.stock) as font:
                a=font.getBestCmap()[65];omega=font.getBestCmap()[ord('Ω')]
                pen=TTGlyphPen(font.getGlyphSet());pen.addComponent(a,(1,0,0,1,0,0));font['glyf'][omega]=pen.glyph();font.save(case.stock)
            with TTFont(case.source) as font:
                g=font['glyf'][font.getBestCmap()[65]]
                for i,(x,y) in enumerate(g.coordinates):g.coordinates[i]=(x+200,y)
                font.save(case.source)
            self.refresh(case);result=case.compile();self.assertEqual(result['status'],'ready',result)
            self.assertGreater(result['report']['replaced']['dependencyIsolation']['clonedGlyphs'],0)
            with TTFont(case.stock) as original, TTFont(result['output']) as output:
                original_order=original.getGlyphOrder();self.assertEqual(output.getGlyphOrder()[:len(original_order)],original_order)
                for w in (100,400,650,900):
                    a=instantiateVariableFont(original,{'wght':w,'wdth':125,'slnt':-10,'ital':1},inplace=False)
                    b=instantiateVariableFont(output,{'wght':w,'wdth':125,'slnt':-10,'ital':1},inplace=False)
                    self.assertEqual(self.bounds(a,a.getBestCmap()[ord('Ω')]),self.bounds(b,b.getBestCmap()[ord('Ω')]))
                    self.assertEqual(a['hmtx'].metrics[a.getBestCmap()[ord('Ω')]],b['hmtx'].metrics[b.getBestCmap()[ord('Ω')]])
                    a.close();b.close()
    def test_nonselected_shared_cmap_alias_is_isolated(self):
        with self.shell() as case:
            with TTFont(case.stock) as font:
                font['HVAR'].table.AdvWidthMap=None; font['VVAR'].table.AdvHeightMap=None
                for table in font['cmap'].tables:
                    if table.isUnicode() and hasattr(table,'cmap'):table.cmap[ord('Ω')]=font.getBestCmap()[65]
                font.save(case.stock)
            with TTFont(case.source) as font:
                g=font['glyf'][font.getBestCmap()[65]]
                for i,(x,y) in enumerate(g.coordinates):g.coordinates[i]=(x+200,y)
                font.save(case.source)
            self.refresh(case);result=case.compile();self.assertEqual(result['status'],'ready',result)
            with TTFont(case.stock) as original, TTFont(result['output']) as output:
                self.assertNotEqual(output.getBestCmap()[65],output.getBestCmap()[ord('Ω')])
                self.assertEqual(self.bounds(original,original.getBestCmap()[ord('Ω')]),self.bounds(output,output.getBestCmap()[ord('Ω')]))
                location={'wght':900,'wdth':100,'slnt':0,'ital':0}
                before=instantiateVariableFont(original,location,inplace=False)
                after=instantiateVariableFont(output,location,inplace=False)
                for tag in ('hmtx','vmtx'):
                    self.assertEqual(before[tag].metrics[before.getBestCmap()[ord('Ω')]],after[tag].metrics[after.getBestCmap()[ord('Ω')]])
                before.close();after.close()
    def add_layout(self,path):
        with TTFont(path) as font:
            order=list(font.getGlyphOrder())
            for name in ('f_i','acutecomb'):
                font['glyf'][name]=deepcopy(font['glyf']['u0066']);font['hmtx'].metrics[name]=(0 if name=='acutecomb' else 620,40)
            font.setGlyphOrder(order+['f_i','acutecomb'])
            for table in font['cmap'].tables:
                if table.isUnicode() and hasattr(table,'cmap'):table.cmap[0x301]='acutecomb'
            addOpenTypeFeaturesFromString(font,'markClass acutecomb <anchor 0 0> @TOP; feature liga { sub u0066 u0069 by f_i; } liga; feature mark { pos base u0041 <anchor 300 700> mark @TOP; } mark; feature kern { pos u0041 u0056 -20; } kern;')
            font.save(path)
    def test_gsub_ligature_and_gpos_anchor_follow_geometry(self):
        source,stock=self.fonts();self.add_layout(source)
        result=self.compile(source,stock);self.assertEqual(result['status'],'ready',result)
        with TTFont(result['output']) as font:
            self.assertEqual(self.bounds(font,'f_i'),self.bounds(font,'u0066'))
            self.assertEqual(self.bounds(font,'f_i')[3],780)
            mark=next(t for lookup in font['GPOS'].table.LookupList.Lookup if lookup.LookupType==4 for t in lookup.SubTable)
            self.assertEqual(mark.BaseArray.BaseRecord[0].BaseAnchor[0].YCoordinate,780)
            self.assertEqual(font['hmtx'].metrics['acutecomb'][0],0)
            pair=next(t for lookup in font['GPOS'].table.LookupList.Lookup if lookup.LookupType==2 for t in lookup.SubTable)
            self.assertEqual(pair.PairSet[0].PairValueRecord[0].Value1.XAdvance,-20)
    def test_ambiguous_nonencoded_gsub_role_mix_rejected_narrowly(self):
        source,stock=self.fonts();self.add_layout(source)
        with TTFont(source) as font:
            # A derived ligature cannot simultaneously obey cap and descender
            # transforms when the compiler's geometry differs between them.
            addOpenTypeFeaturesFromString(font,'feature liga { sub u0041 u0067 by f_i; } liga;')
            font.save(source)
        # Direct helper fixture makes the ambiguity explicit and independent
        # of the rectangle geometry's equal transform controls.
        with TTFont(source) as font:
            with self.assertRaisesRegex(semantics.SemanticError,'ambiguous role'):
                semantics.complete_layout_probe_map(font,{'u0041':'cap','u0067':'desc'},lambda p:(1,0 if p=='cap' else 50))
    def test_malformed_tuple_support_rejected(self):
        source,_stock=self.fonts(True)
        with TTFont(source) as font:
            name='u0041';n=len(font['glyf'][name].getCoordinates(font['glyf'])[0])
            for axes in ({'wght':(.8,.2,1)}, {'xxxx':(0,1,1)}, {'wght':(0,float('nan'),1)}):
                font['gvar'].variations[name]=[TupleVariation(axes,[(0,0)]*(n+4))]
                with self.assertRaisesRegex(semantics.SemanticError,'invalid gvar support'):
                    semantics.conservative_variable_ink_bounds(font)
    def test_reopened_variable_output_is_checked_again(self):
        from unittest.mock import patch
        source,stock=self.fonts(True)
        real_save=compiler._save_font
        def corrupt_after_save(font,path):
            real_save(font,path)
            self.add_deltas(path,2000, (.2,.5,.8))
        with patch.object(compiler,'_save_font',side_effect=corrupt_after_save):
            result=self.compile(source,stock)
        self.assertEqual(result['status'],'blocked',result)
        self.assertIn('line budget',result['reason'])
        self.assertFalse(list((self.root/'out').glob('*.ttf')))
    def test_cff_nonencoded_ligature_follows_geometry(self):
        source,stock=self.root/'source.otf',self.root/'stock.otf'
        fixture.make_font(source,family='CFF Source',cff=True,y_min=-100,y_max=700)
        fixture.make_font(stock,family='CFF Stock',cff=True,y_min=-100,y_max=780)
        with TTFont(source) as font:
            font.ensureDecompiled();order=list(font.getGlyphOrder());top=font['CFF '].cff.topDictIndex[0]
            new=deepcopy(top.CharStrings['u0066'])
            top.CharStrings.charStrings['f_i']=len(top.CharStrings.charStringsIndex)
            top.CharStrings.charStringsIndex.append(new)
            top.charset=order+['f_i'];font.setGlyphOrder(order+['f_i']);font['maxp'].numGlyphs=len(order)+1;font['hmtx'].metrics['f_i']=(620,40)
            addOpenTypeFeaturesFromString(font,'feature liga { sub u0066 u0069 by f_i; } liga;')
            font.save(source)
        result=self.compile(source,stock);self.assertEqual(result['status'],'ready',result)
        with TTFont(result['output']) as font:
            self.assertIn('CFF ',font)
            self.assertEqual(self.bounds(font,'f_i'),self.bounds(font,'u0066'))
            self.assertEqual(self.bounds(font,'f_i')[3],780)
    def test_cff_seac_nonselected_dependency_rejected_narrowly(self):
        from fontTools.fontBuilder import FontBuilder
        from fontTools.pens.t2CharStringPen import T2CharStringPen
        from fontTools.misc.psCharStrings import T2CharString
        builder=FontBuilder(1000,isTTF=False);order=['.notdef','A','acute','Omega']
        builder.setupGlyphOrder(order);builder.setupCharacterMap({65:'A',0xB4:'acute',0x3A9:'Omega'})
        glyphs={}
        for name in order:
            pen=T2CharStringPen(600,None)
            if name!='.notdef':
                pen.moveTo((0,0));pen.lineTo((500,0));pen.lineTo((500,100));pen.closePath()
            glyphs[name]=pen.getCharString()
        glyphs['Omega']=T2CharString(program=[0,600,65,194,'endchar'])
        builder.setupCFF('SyntheticSeac',{'FullName':'SyntheticSeac'},glyphs,{})
        builder.setupHorizontalMetrics({name:(600,0) for name in order})
        builder.setupHorizontalHeader(ascent=900,descent=-200)
        builder.setupNameTable({'familyName':'SyntheticSeac','styleName':'Regular'})
        builder.setupOS2();builder.setupPost();builder.setupMaxp()
        with self.assertRaisesRegex(semantics.SemanticError,'nonselected CFF seac'):
            semantics.isolate_stock_dependencies(builder.font,{'A'},{65})
        # No untouched dependent glyph remains when the caller replaces both.
        self.assertEqual(semantics.isolate_stock_dependencies(builder.font,{'A','Omega'},{65,0x3A9})['clonedGlyphs'],0)

    def test_dynamic_identity_and_every_route_contract_are_checked(self):
        source,stock=self.fonts(True);self.add_deltas(source,20)
        logical='/data/fonts/files/semantic.ttf'
        slot=fixture.slot_from_stock(logical,stock,family='sans-serif',source_xml=None,declared='Semantic.ttf')
        plan,route=fixture.build_plans(source,slot,'latin',None)
        target=plan['targets'][logical]
        target['targetContract']['dynamicIdentity']={'faceIndex':0,'postScriptName':'AuthoritativePS'}
        target['targetContract']['dynamicReferences']=[{'index':0,'postScriptName':'AuthoritativePS','weight':weight,'style':'normal','axes':[]} for weight in (400,700)]
        artifact=compiler._physical_artifact(target,plan)
        self.assertEqual(len(artifact['requiredDynamicRoutes']),2)
        self.assertEqual(artifact['requiredPostScriptName'],'AuthoritativePS')
        out=self.root/'dynamic-out';out.mkdir()
        unit={'artifact':artifact,'target':target,'deploymentKinds':['physical-slot'],'routeNodes':[]}
        result=compiler._compile_unit(unit,{logical:stock},out,False)
        self.assertEqual(result['status'],'ready',result)
        with TTFont(result['output']) as font:
            self.assertIn('AuthoritativePS',compiler.template_engine.font_names(font))
            self.assertIn('fvar',font)
        # A later reference outside the actual retained axis cannot be ignored.
        artifact['requiredDynamicRoutes'][1]['axes']=[{'tag':'wght','stylevalue':'1000'}]
        result=compiler._compile_unit(unit,{logical:stock},out,False)
        self.assertEqual(result['status'],'blocked',result)
        self.assertIn('dynamic route axis',result['reason'])

    def test_real_distinct_probe_transforms_reopen_and_shape(self):
        import device_font_slot_build_base as build
        try:
            from PIL import ImageFont, features
        except ImportError:
            if os.environ.get('LUOSHU_REQUIRE_SHAPING_TEST') == '1': self.fail('required shaping test missing Pillow')
            self.skipTest('optional host raster fixture requires Pillow')
        if not features.check_feature('raqm'):
            if os.environ.get('LUOSHU_REQUIRE_SHAPING_TEST') == '1': self.fail('required shaping test missing libraqm')
            self.skipTest('optional host shaping fixture requires libraqm')
        paths=[Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),Path('/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf')]
        available=[p for p in paths if p.is_file()]
        if not available:
            if os.environ.get('LUOSHU_REQUIRE_SHAPING_TEST') == '1': self.fail('required shaping test missing real UI fonts')
            self.skipTest('optional real UI fonts unavailable')
        slot={'roles':['latin'],'transforms':{p:{'status':'ready','relativeScaleY':scale,'shiftY':shift,'relativeAdvanceScale':1}
              for p,scale,shift in [('latinCap',1.05,10),('latinX',.98,-5),('latinDescender',1.02,-10),('digits',1.03,5)]}}
        for path in available:
            with self.subTest(font=path.name),TTFont(path) as font:
                before=self.bounds(font,font.getBestCmap()[ord('A')])
                report=build.apply_outline_transforms(font,slot)
                self.assertGreater(report['glyphs'],100)
                output=self.root/(path.stem+'-transformed.ttf');font.save(output)
                with TTFont(output) as reopened:
                    after=self.bounds(reopened,reopened.getBestCmap()[ord('A')])
                    self.assertAlmostEqual(after[3],before[3]*1.05+10,delta=1)
                    self.assertNotEqual(before,after)
                # Actual HarfBuzz/FriBidi/FreeType through libraqm. This verifies
                # a readable shaped raster after reopening, not an Android proof.
                text='A\u0301 fi gj'
                original=ImageFont.truetype(str(path),48,layout_engine=ImageFont.Layout.RAQM)
                rendered=ImageFont.truetype(str(output),48,layout_engine=ImageFont.Layout.RAQM)
                a=bytes(original.getmask(text,features=['ccmp','liga','mark']))
                b=bytes(rendered.getmask(text,features=['ccmp','liga','mark']))
                self.assertTrue(any(b));self.assertNotEqual(a,b)
                self.assertGreater(report['layout']['preservedSharedMarks'],0)
                # With composition deliberately disabled, shared marks still
                # attach to original Greek bases with unchanged ink/positions.
                greek='\u03b1\u0313\u0301'
                a=bytes(original.getmask(greek,features=['-ccmp','-liga','mark','mkmk']))
                b=bytes(rendered.getmask(greek,features=['-ccmp','-liga','mark','mkmk']))
                self.assertTrue(any(a));self.assertEqual(a,b)


    def test_stock_shell_preserves_uncomposed_greek_shared_marks(self):
        try:
            from PIL import ImageFont,features
        except ImportError:
            if os.environ.get('LUOSHU_REQUIRE_SHAPING_TEST')=='1':self.fail('required Pillow unavailable')
            self.skipTest('optional host shaping dependency')
        path=Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
        if not path.is_file() or not features.check_feature('raqm'):
            if os.environ.get('LUOSHU_REQUIRE_SHAPING_TEST')=='1':self.fail('required Greek shaping fixture unavailable')
            self.skipTest('optional real Greek shaping fixture')
        source,_unused=self.fonts();self.add_layout(source)
        logical='/system/fonts/SharedMarks.ttf'
        slot=fixture.slot_from_stock(logical,path,family='sans-serif',source_xml=None,declared='SharedMarks.ttf')
        plan,_route=fixture.build_plans(source,slot,'latin',None);target=plan['targets'][logical]
        target['source']['mixedSelection']={'policy':'fixed-composite-selection-v1','requestId':'synthetic-request',
            'fontSha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'roles':{role:{'mode':'fixed','selectedAxes':{'wght':400}} for role in ('cjk','latin','digit')}}
        artifact=compiler._physical_artifact(target,plan);out=self.root/'stock-out';out.mkdir()
        result=compiler._compile_unit({'artifact':artifact,'target':target,'deploymentKinds':['physical-slot'],'routeNodes':[]},{logical:path},out,False)
        self.assertEqual(result['status'],'ready',result)
        self.assertGreater(result['report']['transformed']['layout']['preservedSharedMarks'],0)
        before=ImageFont.truetype(str(path),48,layout_engine=ImageFont.Layout.RAQM)
        after=ImageFont.truetype(result['output'],48,layout_engine=ImageFont.Layout.RAQM)
        text='\u03b1\u0301'
        a=bytes(before.getmask(text,features=['-ccmp','-liga','mark','mkmk']))
        b=bytes(after.getmask(text,features=['-ccmp','-liga','mark','mkmk']))
        self.assertTrue(any(a));self.assertEqual(a,b)
        self.assertNotEqual(bytes(before.getmask('A')),bytes(after.getmask('A')))

    def test_math_presence_preserves_explicit_math_glyphs_without_blanket_rejection(self):
        path=Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
        if not path.is_file():self.skipTest('optional real DejaVu fixture unavailable')
        import device_font_slot_build_base as build
        with TTFont(path) as font:
            protected=semantics.protected_math_glyphs(font);self.assertTrue(protected)
            before={name:self.bounds(font,name) for name in protected}
            slot={'roles':['latin'],'transforms':{name:{'status':'ready','relativeScaleY':1,'shiftY':20,'relativeAdvanceScale':1} for name in ('latinCap','latinX','latinDescender','digits')}}
            report=build.apply_outline_transforms(font,slot)
            self.assertGreater(report['glyphs'],100)
            self.assertEqual(report['layout']['preservedMathGlyphs'],len(protected))
            for name in protected:self.assertEqual(self.bounds(font,name),before[name])

if __name__=='__main__':unittest.main(verbosity=2)
