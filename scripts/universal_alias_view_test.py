#!/usr/bin/env python3
"""ROM aliases across scanner, sealed identity and actual compiler input."""
from copy import deepcopy
from pathlib import Path
import os, shutil, sys, unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'scripts')]
import universal_fixed_mixed_shell_test as fixed
import universal_font_compiler as compiler
import universal_font_deployment as deployment
import stock_font_provenance as proof
import stock_font_view as view
import stock_geometry_profile as geometry
import stock_provenance_fixture as fixture
import font_inventory as inventory
import font_inventory_scan as scanner

class AliasPipelineTests(unittest.TestCase):
    def setUp(self):
        self.case=fixed.FixedMixedShellTest();self.case.setUp();self.addCleanup(self.case.tearDown)
        self.root=self.case.root;self.state=self.root/'state'
        self.system=self.state/'lower/system-fonts';self.product=self.state/'lower/product-fonts'
        self.system.mkdir(parents=True);self.product.mkdir()
        self.logical='/system/fonts/MiSansLatinVF.ttf';self.alias=self.system/'MiSansLatinVF.ttf'
        self.alias.symlink_to('/product/fonts/OEM.ttf');self.oem=self.product/'OEM.ttf';shutil.copyfile(self.case.stock,self.oem)
        self.info=self.root/'mountinfo'
        self.info.write_text('1 0 0:1 / / rw - tmpfs tmpfs rw\n2 1 253:0 / /system ro - erofs /dev/block/dm-0 ro\n3 1 253:1 / /product ro - erofs /dev/block/dm-1 ro\n'
          +f'4 1 253:0 /fonts {self.system} rw - erofs /dev/block/dm-0 ro\n5 1 253:1 /fonts {self.product} rw - erofs /dev/block/dm-1 ro\n'
          +'6 3 253:9 /replacement /product/fonts/OEM.ttf rw - ext4 /dev/block/data rw\n')
        for item in [patch.dict(os.environ,{'LUOSHU_MOUNTINFO':str(self.info),'LUOSHU_SELF_MOUNT_STATE_ROOT':str(self.state)}),
                     patch.object(proof,'verify_stock_path',fixture._original_verify),
                     patch.object(compiler.font_inventory,'MIRROR_PREFIXES',())]:
            item.start();self.addCleanup(item.stop)
    def capture(self):
        roots=[inventory.FontRoot('system',Path('/system/fonts'),self.system),inventory.FontRoot('product',Path('/product/fonts'),self.product)]
        resolved=inventory._stock_font_path(roots[0],self.alias,roots)
        self.assertEqual(resolved,self.oem)
        identity=proof.stock_identity(self.logical,resolved,0,'synthetic',provenance_path=self.alias,view_resolver=compiler._alias_view_candidates)
        self.assertTrue(identity['provenance']['verified'],identity)
        self.assertEqual(identity['captureRevision'],2)
        target=deepcopy(self.case.target);target['path']=self.logical
        target['targetContract']['stockIdentity']=identity
        target['targetContract']['stockGeometryProfile']=geometry.capture_geometry_profile(resolved,0,identity)
        return target
    def compile(self,target):
        out=self.root/'output';out.mkdir(exist_ok=True)
        artifact=compiler._physical_artifact(target,self.case.plan)
        return compiler._compile_unit({'artifact':artifact,'target':target,'deploymentKinds':['physical-slot'],'routeNodes':[]},{},out,False)
    def test_absolute_cross_rom_alias_uses_sealed_terminal_not_live(self):
        target=self.capture();before=self.oem.read_bytes()
        with view.session(self.root):
            actual=compiler._resolve_stock(self.logical,{},False)
            self.assertEqual(actual,self.oem)
            verified=compiler._verify_stock_identity(target,actual,0)
            self.assertEqual(verified['currentProvenance']['resolvedLogicalPath'],'/product/fonts/OEM.ttf')
            result=self.compile(target);self.assertEqual(result['status'],'ready',result)
        self.assertEqual(self.oem.read_bytes(),before);self.assertEqual(os.readlink(self.alias),'/product/fonts/OEM.ttf')
    def test_absolute_multi_hop_maps_each_rom_view(self):
        target=self.capture();terminal=self.system/'Terminal.ttf';self.oem.rename(terminal)
        self.oem.symlink_to('/system/fonts/Terminal.ttf')
        with view.session(self.root):
            actual=compiler._resolve_stock(self.logical,{},False)
            self.assertEqual(actual,terminal)
            result=self.compile(target);self.assertEqual(result['status'],'ready',result)
    def test_changed_alias_between_resolution_and_read_is_rejected(self):
        target=self.capture()
        with view.session(self.root):
            actual=compiler._resolve_stock(self.logical,{},False)
            second=self.product/'Other.ttf';shutil.copyfile(self.oem,second)
            self.alias.unlink();self.alias.symlink_to('/product/fonts/Other.ttf')
            with self.assertRaisesRegex(compiler.CompilerError,'resolved-file-mismatch'):
                compiler._verify_stock_identity(target,actual,0)
    def test_changed_terminal_bytes_reject_before_render(self):
        target=self.capture();self.oem.write_bytes(self.oem.read_bytes()+b'changed')
        with patch.object(compiler,'_compile_stock_shell',side_effect=AssertionError('must not render')) as render:
            result=self.compile(target)
        self.assertEqual(result['status'],'blocked');self.assertIn('digest mismatch',result['reason']);self.assertEqual(render.call_count,0)
    def test_coloros_alias_changed_to_userdata_recovers_only_sealed_rom(self):
        self.logical='/system/fonts/SysFont-Hans-Regular.ttf'
        self.alias.rename(self.system/'SysFont-Hans-Regular.ttf')
        self.alias=self.system/'SysFont-Hans-Regular.ttf'
        target=self.capture()
        self.alias.unlink();self.alias.symlink_to('/data/system/font/Custom.ttf')
        with view.session(self.root):
            with self.assertRaisesRegex(compiler.CompilerError,'not-ROM'):
                compiler._resolve_stock(self.logical,{},False)
            actual=compiler._resolve_stock(self.logical,{},False,target=target)
            self.assertEqual(actual,self.oem)
            verified=compiler._verify_stock_identity(target,actual,0)
            self.assertEqual(verified['currentProvenance']['stockResolution'],'sealed-ROM-terminal')
            result=self.compile(target)
            self.assertEqual(result['status'],'ready',result)
        self.assertEqual(os.readlink(self.alias),'/data/system/font/Custom.ttf')

    def test_changed_coloros_alias_retains_exact_original_during_deployment(self):
        target=self.capture();before=self.oem.read_bytes()
        self.alias.unlink();self.alias.symlink_to('/data/system/font/Custom.ttf')
        identity=target['targetContract']['stockIdentity']
        original={'target':target,'targetPath':self.logical,'faceIndex':0,
                  'sha256':identity['sha256'],'assetRoot':'/system/fonts',
                  'fileName':'LuoShu-Original-'+identity['sha256']+'.ttf'}
        route={'schema':'fixed-static-xml-route-plan-v1','retainedOriginals':{'stock:fixture':original}}
        stage=self.root/'retained-stage';stage.mkdir();records={}
        deployment._copy_retained_originals(route,stage,records)
        output=stage/'system/fonts'/original['fileName']
        self.assertEqual(output.read_bytes(),before)
        self.assertEqual(next(iter(records.values()))['kind'],'xml-original')
        self.assertEqual(self.oem.read_bytes(),before)
        self.oem.write_bytes(before+b'changed')
        rejected=self.root/'rejected-stage';rejected.mkdir()
        with self.assertRaisesRegex(compiler.CompilerError,'digest mismatch'):
            deployment._copy_retained_originals(route,rejected,{})
        self.assertFalse(list(rejected.rglob('*.ttf')))

    def test_sealed_terminal_recovery_rejects_changed_bytes_and_unverified_capture(self):
        target=self.capture()
        self.alias.unlink();self.alias.symlink_to('/data/system/font/Custom.ttf')
        with view.session(self.root):
            bad=deepcopy(target);bad['targetContract']['stockIdentity']['provenance']['verified']=False
            with self.assertRaises(compiler.CompilerError):
                compiler._resolve_stock(self.logical,{},False,target=bad)
            self.oem.write_bytes(self.oem.read_bytes()+b'changed')
            with self.assertRaisesRegex(compiler.CompilerError,'digest mismatch'):
                compiler._resolve_stock(self.logical,{},False,target=target)

    def test_sealed_terminal_recovery_needs_complete_matching_rom_identity(self):
        target=self.capture()
        self.alias.unlink();self.alias.symlink_to('/data/system/font/Custom.ttf')
        for change in ('aliasChain','terminalProvenance','device','filesystemPath','logicalPath'):
            bad=deepcopy(target);identity=bad['targetContract']['stockIdentity']
            if change=='logicalPath':identity[change]='/system/fonts/Unrelated.ttf'
            elif change in ('device','filesystemPath'):
                identity['provenance']['terminalProvenance'][change]='changed'
            else:identity['provenance'].pop(change)
            with self.subTest(change=change),view.session(self.root):
                with self.assertRaises(compiler.CompilerError):
                    compiler._resolve_stock(self.logical,{},False,target=bad)
        with self.assertRaises(compiler.CompilerError):
            compiler._resolve_stock(self.logical,{},False,target=target)

    def test_sealed_terminal_recovery_rechecks_lineage_before_each_read(self):
        target=self.capture()
        self.alias.unlink();self.alias.symlink_to('/data/system/font/Custom.ttf')
        with view.session(self.root):
            actual=compiler._resolve_stock(self.logical,{},False,target=target)
            self.info.write_text(self.info.read_text()+f'7 1 253:9 /replacement {self.oem} ro - ext4 /dev/block/data rw\n')
            with self.assertRaisesRegex(compiler.CompilerError,'provenance rejected'):
                compiler._verify_stock_identity(target,actual,0)

    def test_capture_revision_requires_trusted_rescan_once(self):
        target=self.capture();metrics={'head':{},'coverage':{'synthetic':True}}
        inventory_data={'specializedSnapshotRevision':1, 'specializedSnapshots':{}, 'xmlMemberSnapshotRevision':1,'xmlMemberSnapshots':{},'metricsRevision':scanner.METRICS_REVISION,'slots':{'x':{'metrics':metrics,'stockIdentity':target['targetContract']['stockIdentity'],'stockGeometryProfile':{}}},'mainSlot':{'metrics':metrics}}
        with patch.object(scanner.base,'valid_coverage',return_value=True):
            self.assertTrue(scanner._has_current_metrics(inventory_data))
            inventory_data['slots']['x']['stockIdentity'].pop('captureRevision')
            self.assertFalse(scanner._has_current_metrics(inventory_data))

if __name__=='__main__':unittest.main(verbosity=2)
