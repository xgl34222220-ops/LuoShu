#!/usr/bin/env python3
"""Fail-closed OEM identity, archived geometry consumption and strict failure tests."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import os
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'scripts')]
from fontTools.ttLib import TTFont
import universal_font_compiler as c
import universal_font_compiler_test as fixture
import universal_fixed_mixed_shell_test as fixed
import stock_geometry_profile as archive

class StockContractTest(unittest.TestCase):
    def setUp(self):
        self.case=fixed.FixedMixedShellTest();self.case.setUp();self.addCleanup(self.case.tearDown)
        self.root=self.case.root;self.target=deepcopy(self.case.target)
    def compile(self,target=None,stock=None):
        target=target or self.target;artifact=c._physical_artifact(target,self.case.plan)
        out=self.root/'out';out.mkdir(exist_ok=True)
        return c._compile_unit({'artifact':artifact,'target':target,'deploymentKinds':['physical-slot'],'routeNodes':[]},
                               {target['path']:stock or self.case.stock},out,False)
    def test_missing_false_or_mismatched_identity_never_reaches_rendering(self):
        changes=[lambda t:t['targetContract'].pop('stockIdentity'),
                 lambda t:t['targetContract']['stockIdentity']['provenance'].update(verified=False),
                 lambda t:t['targetContract']['stockIdentity'].update(sha256='0'*64),
                 lambda t:t['targetContract']['stockIdentity'].update(faceIndex=1),
                 lambda t:t['targetContract']['stockIdentity'].update(logicalPath='/system/fonts/Wrong.ttf')]
        for change in changes:
            target=deepcopy(self.target);change(target)
            with patch.object(c,'_compile_stock_shell',side_effect=AssertionError('must not render')) as render:
                result=self.compile(target)
            self.assertEqual(result['status'],'blocked',result);self.assertEqual(render.call_count,0)
    def test_current_view_is_rechecked_and_lexical_alias_reaches_verifier(self):
        with patch.object(c.stock_font_provenance,'verify_stock_path',side_effect=ValueError('naked lower directory')):
            result=self.compile()
        self.assertEqual(result['status'],'blocked');self.assertIn('naked lower directory',result['reason'])
        alias=self.root/'original-alias.ttf';alias.symlink_to(self.case.stock)
        with patch.object(c.stock_font_provenance,'verify_stock_path',return_value={'verified':True}) as verify:
            result=self.compile(stock=alias)
        self.assertEqual(result['status'],'ready',result)
        self.assertEqual(Path(verify.call_args.args[1]),alias)
    def test_unproven_lower_does_not_shadow_a_verified_mirror(self):
        lower=self.root/'bare-lower.ttf';lower.write_bytes(self.case.stock.read_bytes())
        mirror=self.root/'mirror';candidate=mirror/self.target['path'].lstrip('/')
        candidate.parent.mkdir(parents=True);candidate.write_bytes(self.case.stock.read_bytes())
        def verify(logical,actual):
            if Path(actual)==lower:raise ValueError('unproven lower')
            self.assertEqual(Path(actual),candidate)
            return {'verified':True}
        with patch.object(c,'_lower_stock_candidate',return_value=lower),             patch.object(c.font_inventory,'MIRROR_PREFIXES',[mirror]),             patch.object(c.stock_font_provenance,'verify_stock_path',side_effect=verify):
            self.assertEqual(c._resolve_stock(self.target['path'],{},False),candidate)
        with patch.object(c,'_lower_stock_candidate',return_value=lower),             patch.object(c.font_inventory,'MIRROR_PREFIXES',[]),             patch.object(c.stock_font_provenance,'verify_stock_path',side_effect=ValueError('unproven')):
            with self.assertRaises(c.CompilerError):c._resolve_stock(self.target['path'],{},False)

    def test_valid_default_archive_is_used_but_output_is_still_reopened(self):
        identity=self.target['targetContract']['stockIdentity']
        saved=archive.capture_geometry_profile(self.case.stock,0,identity)
        self.target['targetContract']['stockGeometryProfile']=saved
        verified=c._verify_stock_identity(self.target,self.case.stock,0)
        with patch.object(c,'_instantiate_probe_font',side_effect=AssertionError('default archive should be used')):
            font,location=c._stock_geometry_font(self.case.stock,0,400,{},source_font=None,role='latin',
                target_contract=self.target['targetContract'],verified_identity=verified)
            try:self.assertEqual(c._profile_from_font(font),saved['profile'])
            finally:font.close()
        actual=c._validate_output_face
        with patch.object(c,'_validate_output_face',wraps=actual) as readback:
            result=self.compile()
        self.assertEqual(result['status'],'ready',result);self.assertEqual(readback.call_count,1)
    def test_stale_archive_or_nondefault_location_falls_back_to_actual_measurement(self):
        self.target['targetContract']['stockGeometryProfile']=archive.capture_geometry_profile(
            self.case.stock,0,self.target['targetContract']['stockIdentity'])
        verified=c._verify_stock_identity(self.target,self.case.stock,0)
        for mode in ('hash','face','schema','location'):
            contract=deepcopy(self.target['targetContract']);weight=400
            if mode=='hash':contract['stockGeometryProfile']['stockSha256']='0'*64
            if mode=='face':contract['stockGeometryProfile']['faceIndex']=1
            if mode=='schema':contract['stockGeometryProfile']['profile']['probeSchema']='old'
            if mode=='location':weight=700
            original=c._instantiate_probe_font
            with patch.object(c,'_instantiate_probe_font',wraps=original) as measured:
                font,_=c._stock_geometry_font(self.case.stock,0,weight,{},role='latin',
                    target_contract=contract,verified_identity=verified)
                font.close()
            self.assertEqual(measured.call_count,1,mode)
    def test_strict_preflight_checks_all_origins_before_any_unit_compiles(self):
        units=[]
        for i in range(2):
            target=deepcopy(self.target)
            artifact=c._physical_artifact(target,self.case.plan)
            units.append({'target':target,'artifact':artifact,'deploymentKinds':['physical-slot'],'routeNodes':[]})
        units[1]['target']['targetContract']['stockIdentity']['sha256']='0'*64
        with patch.object(c,'_compile_unit',side_effect=AssertionError('no compile')) as compile_unit:
            with self.assertRaisesRegex(c.CompilerError,'digest mismatch'):
                c._mixed_preflight(units,{self.target['path']:self.case.stock},False)
        self.assertEqual(compile_unit.call_count,0)
    def test_strict_runtime_failure_marks_remaining_units_uncompiled_and_never_ready(self):
        plan,route=fixture.build_plans(self.case.source,
            fixture.slot_from_stock(self.case.logical,self.case.stock,family='sans-serif',source_xml=None,declared='Stock.ttf'),'latin',None)
        unit=c._collect_units(plan,route)[0]
        units=[deepcopy(unit) for _ in range(3)]
        for i,u in enumerate(units):u['artifact']['artifactId']+=str(i)
        def fail(unit,*args):
            a=unit['artifact'];return {'artifactId':a['artifactId'],'targetPath':unit['target']['path'],
                'role':'latin','deploymentKinds':['physical-slot'],'routeNodes':[],'contract':a,
                'status':'blocked','reason':'synthetic geometry failure','output':'','sha256':'','bytes':0}
        with patch.dict(os.environ,{'LUOSHU_UNIVERSAL_MIX_STRICT':'1'}),patch.object(c,'_collect_units',return_value=units),\
             patch.object(c,'_mixed_preflight'),patch.object(c,'_compile_unit',side_effect=fail) as render:
            result=c.compile_all(plan,route,{self.target['path']:self.case.stock},self.root/'strict',False)
        self.assertEqual(render.call_count,1);self.assertFalse(result['summary']['deploymentReady'])
        self.assertEqual(result['summary']['blockedCount'],3)
        self.assertTrue(all(a.get('compileDisposition')=='skipped-after-atomic-failure' for a in result['artifacts'][1:]))
        c.validate_manifest(result,plan,route)

if __name__=='__main__':unittest.main(verbosity=2)
