#!/usr/bin/env python3
"""Real sealed payload + activation/mount entrypoints; synthetic build properties."""
import hashlib,json,os,shutil,subprocess,sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'common'),str(ROOT/'scripts')]
import fixed_static_xml_pipeline_test as pipeline_fixture
import universal_font_deployment as deploy

class DeviceGenerationTest(unittest.TestCase):
 def setUp(self):
  self.fixture=pipeline_fixture.PipelineTest('test_shared_compile_payload_and_runtime');self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
  self.root=self.fixture.root;self.mod=self.root/'module';self.mod.mkdir();(self.mod/'config').mkdir()
  (self.mod/'common').symlink_to(ROOT/'common',target_is_directory=True)
  shutil.copytree(self.fixture.payload,self.mod/'.luoshu-payload-next')
  self.old=self.mod/'.luoshu-payload';self.old.mkdir();(self.old/'original').write_bytes(b'previous-live-payload')
  self.d=self.fixture.deployment;self.cfg=self.mod/'config';self.key=self.fixture.plan['device']['buildKey']
  (self.cfg/'active_font.conf').write_text('Previous\n')
  (self.cfg/'font_runtime_legacy_v14_4.conf').write_text('enabled=true\n')
  (self.cfg/'universal-font-next.conf').write_text('font=mix\npreviousFont=Previous\npreviousMode=legacy\npreviousLegacy=true\ndeploymentId='+self.d['deploymentId']+'\npayloadDigest='+self.d['payloadDigest']+'\n')
  self.bin=self.root/'bin';self.bin.mkdir();self.getprop=self.bin/'getprop'
  self.env=dict(os.environ,MODDIR=str(self.mod),MODULE_DIR=str(self.mod),LUOSHU_PYTHON=sys.executable,PATH=str(self.bin)+':'+os.environ['PATH'])
  for name in ('self','private','universal'):(self.root/'state'/name).mkdir(parents=True)
  self.env.update(LUOSHU_SELF_MOUNT_STATE_ROOT=str(self.root/'state/self'),LUOSHU_PRIVATE_STATE_ROOT=str(self.root/'state/private'),LUOSHU_UNIVERSAL_MOUNT_STATE_ROOT=str(self.root/'state/universal'))
  self.property(self.key)
  # Fixed XML mounting now requires the actual stock snapshot and readable
  # Enforcing labels before the (mocked) system mount callback is reached.
  self.stock_etc=self.root/'stock-visible/system/etc';self.stock_etc.mkdir(parents=True)
  for logical,doc in self.fixture.route['documents'].items():
   if doc['operations']:shutil.copyfile(doc['sourcePath'],self.stock_etc/Path(logical).name)
  self.env['LUOSHU_SELF_MOUNT_VISIBLE_ROOT']=str(self.root/'stock-visible')
  for name,body in [('getenforce','echo Enforcing'),('id','echo 0'),('ls','case "$1" in -Zd) echo "u:object_r:system_file:s0 $2" ;; *) exec /bin/ls "$@" ;; esac')]:
   tool=self.bin/name;tool.write_text('#!/bin/sh\n'+body+'\n');tool.chmod(0o755)
 def property(self,value,exitcode=0):
  self.getprop.write_text('#!/bin/sh\nprintf "%s\\n" '+repr(value)+'\nexit '+str(exitcode)+'\n');self.getprop.chmod(0o755)
 def activate(self):
  return subprocess.run(['sh','-c','. "$MODDIR/common/universal_next_boot.sh"; universal_font_next_boot_activate'],env=self.env,capture_output=True,text=True,timeout=30)
 def preserved(self):
  self.assertEqual((self.old/'original').read_bytes(),b'previous-live-payload')
  self.assertEqual((self.cfg/'active_font.conf').read_text(),'Previous\n')
  self.assertEqual((self.cfg/'font_runtime_legacy_v14_4.conf').read_text(),'enabled=true\n')
  self.assertFalse((self.cfg/'universal-font-runtime.conf').exists())
 def blocked_legacy(self):
  return subprocess.run(['sh','-c','. "$MODDIR/common/universal_next_boot.sh"; universal_font_next_boot_blocks_legacy'],env=self.env,capture_output=True,text=True,timeout=10).returncode==0
 def test_unknown_failed_boot_blocks_and_valid_regeneration_clears_it(self):
  failed=self.cfg/'universal-font-next.failed.conf';failed.write_text('state=failed\nbootId=unknown\n')
  self.assertTrue(self.blocked_legacy())
  self.assertEqual(self.activate().returncode,0)
  self.assertFalse(failed.exists());self.assertFalse(self.blocked_legacy())
 def test_previous_boot_failure_is_not_a_permanent_legacy_lock(self):
  (self.cfg/'universal-font-next.failed.conf').write_text('state=failed\nbootId=prior-boot-fixture\n')
  self.assertFalse(self.blocked_legacy())
 def test_same_firmware_activates_real_sealed_payload(self):
  r=self.activate();self.assertEqual(r.returncode,0,r.stderr)
  self.assertTrue((self.old/'.luoshu-runtime/deployment/deployment.json').is_file())
  self.assertIn('state=active',(self.cfg/'universal-font-runtime.conf').read_text())
 def test_changed_firmware_rejects_without_overwriting_live(self):
  self.property('different-OTA-build');self.assertNotEqual(self.activate().returncode,0);self.preserved()
 def test_unavailable_current_build_rejects(self):
  self.property('',1);self.assertNotEqual(self.activate().returncode,0);self.preserved()
 def test_failed_getprop_cannot_supply_a_matching_key(self):
  self.property(self.key,1);self.assertNotEqual(self.activate().returncode,0);self.preserved()
 def test_empty_current_build_rejects(self):
  self.property('');self.assertNotEqual(self.activate().returncode,0);self.preserved()
 def test_unknown_current_build_rejects(self):
  self.property('unknown');self.assertNotEqual(self.activate().returncode,0);self.preserved()
 def test_missing_sealed_build_contract_rejects(self):
  bad=dict(self.d);bad.pop('verificationContracts')
  with self.assertRaisesRegex(deploy.DeploymentError,'封印缺失'):deploy.validate_device_generation(bad,self.fixture.payload)
 def test_empty_sealed_build_key_rejects(self):
  payload=self.fixture.payload;path=payload/'.luoshu-runtime/deployment/font-plan.json';plan=json.loads(path.read_text());plan['device']['buildKey']='';path.write_text(json.dumps(plan))
  d=json.loads(json.dumps(self.d));d['verificationContracts']['fontPlan']['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
  with self.assertRaisesRegex(deploy.DeploymentError,'身份未知'):deploy.validate_device_generation(d,payload)
 def test_rejected_activation_never_falls_into_unverified_legacy_hooks(self):
  (self.cfg/'font_runtime_legacy_v14_4.conf').unlink()
  core=self.mod/'.luoshu-runtime/core';core.mkdir(parents=True)
  for name in ('post-fs-data.sh','post-mount.sh','service.sh'):
   shutil.copy2(ROOT/name,self.mod/name)
   (core/name).write_text('#!/bin/sh\ntouch "'+str(self.root/'legacy-ran')+'"\nexit 99\n')
  self.property('different-OTA-build')
  (self.cfg/'device-font-load-verification.conf').write_text('state=verified\nmode=aligned\nactiveFont=Previous\n')
  first=subprocess.run(['sh',str(self.mod/'post-fs-data.sh')],env=self.env,capture_output=True,text=True,timeout=30)
  self.assertFalse((self.root/'legacy-ran').exists(),first.stderr)
  self.assertIn('state=failed',(self.cfg/'self-mount.conf').read_text())
  self.assertIn('state=failed',(self.cfg/'device-font-load-verification.conf').read_text())
  self.assertEqual((self.old/'original').read_bytes(),b'previous-live-payload')
  for name in ('post-fs-data.sh','post-mount.sh','service.sh'):
   result=subprocess.run(['sh',str(self.mod/name)],env=self.env,capture_output=True,text=True,timeout=30)
   self.assertNotEqual(result.returncode,0)
   self.assertFalse((self.root/'legacy-ran').exists(),name)
 def test_top_level_activation_hook_and_rollback_protocol(self):
  shutil.copy2(ROOT/'post-fs-data.sh',self.mod/'post-fs-data.sh')
  mount=self.root/'system-mount'
  mount.write_text('#!/bin/sh\nprintf mount\\n >> "'+str(self.root/'calls')+'"\n');mount.chmod(0o755)
  env=dict(self.env,LUOSHU_UNIVERSAL_TEST_MANAGER='Magisk',LUOSHU_UNIVERSAL_TEST_SYSTEM_MOUNT_COMMAND=str(mount))
  result=subprocess.run(['sh',str(self.mod/'post-fs-data.sh')],env=env,capture_output=True,text=True,timeout=30)
  self.assertEqual(result.returncode,0,result.stderr)
  self.assertIn('state=active',(self.cfg/'universal-font-runtime.conf').read_text())
  self.assertIn('state=mounted',(self.cfg/'universal-font-mount.conf').read_text())
  # No next payload means a repeated activation does not replace current bytes.
  before=(self.old/'.luoshu-runtime/deployment/deployment.json').read_bytes()
  self.assertEqual(self.activate().returncode,2)
  self.assertEqual((self.old/'.luoshu-runtime/deployment/deployment.json').read_bytes(),before)
  result=subprocess.run(['sh',str(ROOT/'common/universal_mount_runtime.sh'),'rollback'],env=env,capture_output=True,text=True,timeout=30)
  self.assertEqual(result.returncode,0,result.stderr)
  self.assertIn('state=rolled-back',(self.cfg/'universal-font-mount.conf').read_text())
  self.assertIn('mount',(self.root/'calls').read_text())
 def test_live_payload_rechecked_before_any_mount(self):
  shutil.rmtree(self.old);shutil.copytree(self.fixture.payload,self.old)
  (self.cfg/'universal-font-runtime.conf').write_text('state=active\npipeline=universal-font-deployment-v1\nfont=mix\ndeploymentId='+self.d['deploymentId']+'\npayloadDigest='+self.d['payloadDigest']+'\n')
  command=self.root/'mount-marker';command.write_text('#!/bin/sh\ntouch "'+str(self.root/'mounted')+'"\n');command.chmod(0o755)
  self.property('different-OTA-build')
  env=dict(self.env,LUOSHU_UNIVERSAL_TEST_MANAGER='Magisk',LUOSHU_UNIVERSAL_TEST_SYSTEM_MOUNT_COMMAND=str(command))
  r=subprocess.run(['sh',str(ROOT/'common/universal_mount_runtime.sh'),'hook','post-fs-data'],env=env,capture_output=True,text=True,timeout=30)
  self.assertNotEqual(r.returncode,0);self.assertFalse((self.root/'mounted').exists())
  self.assertIn('state=failed',(self.cfg/'universal-font-mount.conf').read_text())

if __name__=='__main__':unittest.main(verbosity=2)
