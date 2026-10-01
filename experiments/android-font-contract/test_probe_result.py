import unittest
from probe_result import validate_probe_result
class ProbeResultTest(unittest.TestCase):
 def test_current_success(self):
  r={'probeRequestId':'new','status':'passed'}
  self.assertIs(validate_probe_result('INSTRUMENTATION_CODE: -1\n',r,'new','passed'),r)
 def test_crashed_process_cannot_reuse_old_pass(self):
  with self.assertRaisesRegex(RuntimeError,'did not finish'):
   validate_probe_result('INSTRUMENTATION_RESULT: shortMsg=Process crashed.\nINSTRUMENTATION_CODE: 0\n',{'probeRequestId':'old','status':'passed'},'new','passed')
 def test_success_exit_does_not_make_stale_report_current(self):
  with self.assertRaisesRegex(RuntimeError,'stale'):
   validate_probe_result('INSTRUMENTATION_CODE: -1\n',{'probeRequestId':'old','status':'passed'},'new','passed')
 def test_current_failed_gate_remains_failure(self):
  with self.assertRaisesRegex(RuntimeError,'did not satisfy'):
   validate_probe_result('INSTRUMENTATION_CODE: -1\n',{'probeRequestId':'new','status':'failed'},'new','passed')

 def test_custom_stream_success_requires_fresh_report_without_footer(self):
  r={'probeRequestId':'new','status':'passed'}
  self.assertIs(validate_probe_result('{"status":"passed"}\n',r,'new','passed'),r)
  with self.assertRaisesRegex(RuntimeError,'stale'):
   validate_probe_result('{"status":"passed"}\n',r,'different','passed')
