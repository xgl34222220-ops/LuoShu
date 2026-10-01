#!/usr/bin/env python3
"""Scan-to-compile view recovery with modeled mount syscalls, real ROM proof/SHA."""
from copy import deepcopy
from pathlib import Path
import json, os, shutil, signal, subprocess, sys, tempfile, time, unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'scripts')]
import stock_font_view as view
import stock_inventory_scan as scan
import stock_font_provenance as proof
import stock_geometry_profile as geometry
import universal_font_compiler as compiler
import universal_fixed_mixed_shell_test as fixed
import stock_provenance_fixture as fixture

class ViewTests(unittest.TestCase):
    def setUp(self):
        self.case=fixed.FixedMixedShellTest();self.case.setUp();self.addCleanup(self.case.tearDown)
        self.root=self.case.root;self.info=self.root/'mountinfo'
        self.logical=Path('/system/fonts/SysFont-Hant-Regular.ttf')
        self.live=self.root/'replacement.ttf';self.live.write_bytes(b'live replacement')
        self.base='1 0 0:1 / / rw - tmpfs tmpfs rw\n2 1 253:0 / /system ro - erofs /dev/block/dm-0 ro\n3 2 253:9 /replacement /system/fonts/SysFont-Hant-Regular.ttf rw - ext4 /dev/block/dm-9 rw\n'
        self.rows={};self.sync();self.calls=0
        self.env=patch.dict(os.environ,{'LUOSHU_MOUNTINFO':str(self.info),'LUOSHU_SELF_MOUNT_STATE_ROOT':str(self.root/'no-lower')});self.env.start();self.addCleanup(self.env.stop)
        # Undo other geometry fixtures' proof seam: use the real verifier here.
        self.realproof=patch.object(proof,'verify_stock_path',fixture._original_verify);self.realproof.start();self.addCleanup(self.realproof.stop)
        original_stat=Path.stat
        def stat(path,*args,**kwargs):
            if path==self.logical:return original_stat(self.live,*args,**kwargs)
            if path==self.logical.parent:return original_stat(self.root,*args,**kwargs)
            return original_stat(path,*args,**kwargs)
        self.fs=patch.object(Path,'stat',stat);self.fs.start();self.addCleanup(self.fs.stop)
        self.mount=patch.object(scan,'_run_mount',side_effect=self.mount_call);self.mount.start();self.addCleanup(self.mount.stop)
        self.unmount=patch.object(scan,'_run_umount',side_effect=self.unmount_call);self.unmount.start();self.addCleanup(self.unmount.stop)
        self.command=patch.object(view,'detach_snapshot',side_effect=self.unmount_call);self.command.start();self.addCleanup(self.command.stop)
        self.mirrors=patch.object(compiler.font_inventory,'MIRROR_PREFIXES',());self.mirrors.start();self.addCleanup(self.mirrors.stop)
    def sync(self):self.info.write_text(self.base+''.join(self.rows.values()))
    def mount_call(self,*args):
        if args[:2]==('-o','private'):return True
        self.calls+=1;dest=Path(args[-1]);dest.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(self.case.stock,dest/self.logical.name)
        self.rows[str(dest)]=f'{10+self.calls} 1 253:0 /fonts {dest} rw - erofs /dev/block/dm-0 ro\n';self.sync();return True
    def unmount_call(self,path):
        self.rows.pop(str(path),None);self.sync()
        for child in Path(path).iterdir():child.unlink() # simulate underlying empty mountpoint
    def command_call(self,args,**kwargs):
        self.assertEqual(args[0],'umount');self.unmount_call(Path(args[1]));return subprocess.CompletedProcess(args,0)
    def captured_target(self):
        scan._INSTALL_SNAPSHOTS.clear()
        with patch.dict(os.environ,{'LUOSHU_INSTALL_STOCK_SNAPSHOT_ROOT':str(self.root/'scan')}):
            actual=scan._safe_pick_actual_root(self.logical.parent,None,True)
            font=actual/self.logical.name
            target=deepcopy(self.case.target);target['path']=str(self.logical)
            identity=proof.stock_identity(self.logical,font,0,'test-build')
            self.assertTrue(identity['provenance']['verified'])
            target['targetContract']['stockIdentity']=identity
            target['targetContract']['stockGeometryProfile']=geometry.capture_geometry_profile(font,0,identity)
            scan._cleanup_install_snapshots();self.assertFalse(font.exists())
        return target
    def compile_target(self,target):
        artifact=compiler._physical_artifact(target,self.case.plan)
        out=self.root/'out';out.mkdir(exist_ok=True)
        return compiler._compile_unit({'artifact':artifact,'target':target,'deploymentKinds':['physical-slot'],'routeNodes':[]},{},out,False)
    def test_scan_cleanup_then_recover_compile_same_sha_face_and_cleanup(self):
        target=self.captured_target()
        with view.session(self.root) as current:
            stock=compiler._resolve_stock(str(self.logical),{},False)
            compiler._verify_stock_identity(target,stock,0)
            result=self.compile_target(target);self.assertEqual(result['status'],'ready',result)
            self.assertEqual(len(current.owned),1);self.assertEqual(self.calls,2)
            owned=list(current.owned)
        self.assertFalse(self.rows);self.assertTrue(all(not path.exists() for path in owned))
        self.assertEqual(self.live.read_bytes(),b'live replacement')
    def test_changed_ota_bytes_and_wrong_face_rejected_after_recovery(self):
        for kind in ['sha','face']:
            target=self.captured_target()
            target['targetContract']['stockIdentity'].update({ 'sha256':'0'*64 } if kind=='sha' else {'faceIndex':1})
            with view.session(self.root):
                result=self.compile_target(target)
                self.assertEqual(result['status'],'blocked');self.assertIn('digest mismatch' if kind=='sha' else 'face mismatch',result['reason'])
            self.assertFalse(self.rows)
    def test_failure_cleans_only_request_view(self):
        target=self.captured_target();old=self.root/'existing-lower';old.mkdir();(old/'keep').write_text('keep')
        with self.assertRaisesRegex(RuntimeError,'abort'):
            with view.session(self.root):
                compiler._resolve_stock(str(self.logical),{},False);raise RuntimeError('abort')
        self.assertFalse(self.rows);self.assertEqual((old/'keep').read_text(),'keep')
    def test_unmount_failure_never_deletes_mounted_contents(self):
        self.captured_target()
        with patch.object(view,'detach_snapshot',return_value=False):
            with view.session(self.root) as current:
                stock=compiler._resolve_stock(str(self.logical),{},False);before=stock.read_bytes()
            self.assertEqual(stock.read_bytes(),before);self.assertTrue(self.rows)
        for path in list(self.rows):self.unmount_call(path)
    def test_unproven_or_timed_out_bind_never_recursively_deletes(self):
        for kind in ('unproven','timeout'):
            base=self.root/kind;base.mkdir()
            real_mount=self.mount_call
            def mount(*args):
                result=real_mount(*args)
                return False if kind=='timeout' and args[0]=='--bind' else result
            original_stat=Path.stat
            def same_stat(path,*args,**kwargs):
                if path.name==self.logical.name:return original_stat(self.case.stock,*args,**kwargs)
                return original_stat(path,*args,**kwargs)
            with patch.object(scan,'_run_mount',side_effect=mount), patch.object(scan,'_run_umount'), patch.object(Path,'stat',same_stat):
                result=scan._bind_parent_stock_snapshot(self.logical.parent,snapshot_base=base)
            self.assertIsNone(result)
            mounted=base/'system-fonts';self.assertEqual((mounted/self.logical.name).read_bytes(),self.case.stock.read_bytes())
            scan._INSTALL_SNAPSHOTS.append(mounted)
            with patch.object(scan,'_run_umount'):scan._cleanup_install_snapshots()
            self.assertTrue((mounted/self.logical.name).exists())
            self.unmount_call(mounted)

    def test_covering_overlay_cannot_be_recovered_and_reason_is_actionable(self):
        self.base+='4 2 0:4 / /system/fonts rw - tmpfs tmpfs rw\n';self.sync()
        with view.session(self.root):
            with self.assertRaisesRegex(compiler.CompilerError,'current:stock-provenance-filesystem-lineage-mismatch.*recovered:missing'):
                compiler._resolve_stock(str(self.logical),{},False)
        self.assertEqual(self.calls,0)
    def test_proven_clean_current_namespace_does_not_require_legacy_flag(self):
        with patch.object(proof,'verify_stock_path',return_value={'verified':True}):
            self.assertEqual(compiler._resolve_stock(str(self.case.stock),{},False),self.case.stock)
        with patch.object(proof,'verify_stock_path',side_effect=ValueError('replacement mount')):
            with self.assertRaisesRegex(compiler.CompilerError,'current:replacement mount'):
                compiler._resolve_stock(str(self.case.stock),{},True)

class SignalTests(unittest.TestCase):
    def test_sigterm_cleans_owned_view_and_restores_session(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);marker=root/'unmounted'
            script=f'''import sys,time,subprocess\nfrom pathlib import Path\nsys.path.insert(0,{str(ROOT/'common')!r})\nimport stock_font_view as v\ndef unmount(*a,**k):\n Path({str(marker)!r}).write_text('cleaned')\n return subprocess.CompletedProcess(a,0)\nv.detach_snapshot=unmount\nwith v.session(Path({raw!r})) as s:\n s.base=Path({raw!r})/'owned';s.base.mkdir()\n p=s.base/'system-fonts';p.mkdir();s.owned.append(p)\n print('ready',flush=True)\n time.sleep(30)\n'''
            p=subprocess.Popen([sys.executable,'-c',script],stdout=subprocess.PIPE,text=True)
            try:
                self.assertEqual(p.stdout.readline().strip(),'ready');p.send_signal(signal.SIGTERM)
                self.assertEqual(p.wait(timeout=5),143);self.assertEqual(marker.read_text(),'cleaned')
                self.assertFalse((root/'owned').exists())
            finally:
                if p.poll() is None:p.kill();p.wait()
                p.stdout.close()

if __name__=='__main__':unittest.main(verbosity=2)
