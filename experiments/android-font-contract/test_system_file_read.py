"""Host regressions for Android exec-out's misleading permission-error status."""
import ast
from pathlib import Path
import unittest
SOURCE=Path(__file__).with_name('run_system_emulator.py').read_text()
TREE=ast.parse(SOURCE)
class SystemFileReadTest(unittest.TestCase):
 def helper(self, adb):
  fn=next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=='read_system_file')
  ns={'adb':adb};exec(compile(ast.Module(body=[fn],type_ignores=[]),'<helper>','exec'),ns)
  return ns['read_system_file']
 def test_readability_is_checked_before_binary_read(self):
  calls=[]
  def adb(*args):
   calls.append(args);return b'' if args[0]=='shell' else b'<familyset>\x00\n'
  self.assertEqual(b'<familyset>\x00\n', self.helper(adb)('/system/etc/font_fallback.xml'))
  self.assertEqual([('shell','test','-r','/system/etc/font_fallback.xml'),('exec-out','cat','/system/etc/font_fallback.xml')],calls)
 def test_permission_failure_never_compares_error_text_as_font_xml(self):
  calls=[]
  def adb(*args):
   calls.append(args);raise RuntimeError('read denied')
  with self.assertRaisesRegex(RuntimeError,'read denied'):self.helper(adb)('/system/etc/font_fallback.xml')
  self.assertEqual(1,len(calls))
 def test_restore_reacquires_root_after_reboot_before_verification(self):
  final=next(n for n in TREE.body if isinstance(n,ast.Try)).finalbody
  restored=next(n for n in final if isinstance(n,ast.If))
  body=restored.body[0].body
  calls=[n.value.func.id for n in body if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name)]
  reboot=calls.index('reboot')
  self.assertEqual('root',calls[reboot+1])
class RootReconnectTest(unittest.TestCase):
 def helper(self,adb):
  fn=next(n for n in ast.parse(Path(__file__).with_name('run_system_emulator.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='root')
  ns={'adb':adb};exec(compile(ast.Module(body=[fn],type_ignores=[]),'<root-helper>','exec'),ns);return ns['root']
 def test_existing_root_does_not_restart_transport(self):
  calls=[]
  def adb(*args,**kwargs):calls.append(args);return b'0' if args==('shell','id','-u') else b''
  self.helper(adb)();self.assertNotIn(('root',),calls)
 def test_closed_root_transport_recovers_only_after_uid_proof(self):
  calls=[];uids=iter([b'2000',b'0'])
  def adb(*args,**kwargs):
   calls.append((args,kwargs))
   if args==('shell','id','-u'):return next(uids)
   if args==('root',):return b'adb: unable to connect for root: closed'
   return b''
  self.helper(adb)();self.assertEqual(1,sum(x[0]==('root',) for x in calls));self.assertFalse(next(x[1]['check'] for x in calls if x[0]==('root',)))
 def test_unprivileged_uid_never_passes(self):
  calls=[]
  def adb(*args,**kwargs):calls.append(args);return b'2000' if args==('shell','id','-u') else b''
  with self.assertRaisesRegex(RuntimeError,'bounded reconnect'):self.helper(adb)()
  self.assertEqual(2,calls.count(('root',)))
 def test_explicit_root_denial_is_not_retried(self):
  calls=[]
  def adb(*args,**kwargs):
   calls.append(args)
   return b'cannot run as root in production builds' if args==('root',) else b'2000'
  with self.assertRaises(PermissionError):self.helper(adb)()
  self.assertEqual(1,calls.count(('root',)))

if __name__=='__main__':unittest.main()
