#!/usr/bin/env python3
"""Source wiring guard; runtime/parser behavior is separately exercised in Kotlin/Python."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
K=ROOT/'android-app/app/src/main/java/io/github/xgl34222220/luoshu'
class DiagnosticWiringTest(unittest.TestCase):
 def test_preflight_is_saved_before_any_component_reconciliation(self):
  source=(K/'GoogleFontCompatibilityMaintenance.kt').read_text()
  self.assertLess(source.index('evidence.captureBeforeMaintenance(appUser)'),source.index('googleFontCommand("reconcile-owned", appUser)'))
  self.assertIn('catch (cancelled: CancellationException)',source)
 def test_capture_helper_never_calls_mutating_provider_actions(self):
  source=(K/'GoogleFontDiagnosticEvidence.kt').read_text()
  for forbidden in ('reconcile-owned','reapply-owned','pm disable','google_font_provider_bridge','google_font_provider_service'):
   self.assertNotIn(forbidden,source)
  self.assertIn('AtomicFile(File(this.context.filesDir',source)
  self.assertIn('NonCancellable + Dispatchers.IO',source)
 def test_one_explicit_export_is_a_real_page_action(self):
  page=(K/'ui/settings/GoogleFontCompatibilityPage.kt').read_text()
  model=(K/'ui/settings/GoogleFontCompatibilityModel.kt').read_text()
  self.assertIn('导出复发诊断',page)
  self.assertIn('model.exportDiagnostic(context)',page)
  self.assertIn('GoogleFontDiagnosticEvidence(context).export(appUser)',model)
  self.assertIn('!model.diagnosticBusy',page)
if __name__=='__main__': unittest.main()
