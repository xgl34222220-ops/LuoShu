"""Host protocol regressions; Android mount evidence is a separate CI gate."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import module_namespace_verify as verify
import run_module_namespace as runner

class NamespaceProtocolTest(unittest.TestCase):
 def setUp(self):
  # These are host protocol fixtures, not root/native namespace evidence.
  # GitHub's unprivileged runner cannot inspect init's mount namespace.
  readlink=verify.os.readlink
  def host_namespace(path):
   if str(path) in ('/proc/self/ns/mnt','/proc/1/ns/mnt'):return 'host-protocol-fixture'
   return readlink(path)
  scoped=patch.object(verify.os,'readlink',side_effect=host_namespace);scoped.start();self.addCleanup(scoped.stop)
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);self.module=self.root/'module';self.module.mkdir()
  self.visible=self.root/'new.ttf';self.visible.write_bytes(b'compiled')
  self.original=self.root/'original.xml';self.original.write_bytes(b'original')
  self.payload=self.module/'.luoshu-payload';(self.payload/'.luoshu-runtime/deployment').mkdir(parents=True)
  self.asset=self.payload/'system/fonts/new.ttf';self.asset.parent.mkdir(parents=True);self.asset.write_bytes(b'compiled')
  (self.payload/'.luoshu-runtime/deployment/deployment.json').write_text(json.dumps({'files':[{'logicalPath':str(self.visible),'payloadPath':'system/fonts/new.ttf','sha256':hashlib.sha256(b'compiled').hexdigest()}]}))
  (self.module/'namespace-contract.json').write_text(json.dumps({'newAssetPaths':[str(self.visible)],'originalHashes':{str(self.original):hashlib.sha256(b'original').hexdigest()}}))
  (self.module/'config').mkdir();(self.module/'config/universal-font-mount.conf').write_text('state=mounted\n')
 def mounted(self,ro=True):
  read=Path.read_text
  def contents(path,*args,**kwargs):
   if str(path)=='/proc/self/mountinfo':return '1 0 0:1 / '+str(self.root)+' '+('ro' if ro else 'rw')+' - overlay overlay ro\n'
   return read(path,*args,**kwargs)
  with patch.object(Path,'read_text',contents):verify.verify(self.module,'mounted')
 def test_complete_readonly_payload(self):
  self.mounted();report=json.loads((self.module/'namespace-result.json').read_text())
  self.assertEqual(report['phases'][0]['state'],'passed');self.assertFalse(report['globalAppConsumerTested'])
 def test_writable_mount_is_not_success(self):
  with self.assertRaisesRegex(AssertionError,'not read-only'):self.mounted(False)
 def test_missing_required_asset_is_not_success(self):
  self.visible.unlink()
  with self.assertRaises(FileNotFoundError):self.mounted()
 def test_restore_rejects_late_visible_asset(self):
  with self.assertRaises(AssertionError):verify.verify(self.module,'restored')
  self.visible.unlink();verify.verify(self.module,'restored')
 def test_integrity_rejection_must_precede_all_mounts(self):
  self.visible.unlink();(self.module/'mount-calls.jsonl').write_text('{}\n')
  with self.assertRaisesRegex(AssertionError,'called mount'):verify.verify(self.module,'integrity-failure')
 def test_unowned_staging_collision_is_never_deleted(self):
  calls=[]
  def adb(*args,**kwargs):
   calls.append(args)
   if args==('shell','test','!','-e',runner.REMOTE):raise RuntimeError('already exists')
   return b''
  with self.assertRaisesRegex(RuntimeError,'already exists'):
   runner.run(adb,lambda:None,lambda:None,lambda p:b'',self.payload,{'files':[]},{},{},self.root)
  self.assertFalse(any('rm' in args for args in calls))
if __name__=='__main__':unittest.main()
