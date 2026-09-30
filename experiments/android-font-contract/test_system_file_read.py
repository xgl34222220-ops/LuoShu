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
if __name__=='__main__':unittest.main()
