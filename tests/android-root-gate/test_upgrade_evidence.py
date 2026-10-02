"""Host-only fixture tests of preservation assertions; no Android claim."""
import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest
import upgrade_evidence as gate


class UpgradeEvidenceTests(unittest.TestCase):
    def exercise(self, value, remove_backup=False):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);module=base/'module';fonts=base/'fonts'
            (module/'config/recovery/existing').mkdir(parents=True);fonts.mkdir()
            (module/'config/recovery/existing/backup').write_text('existing synthetic recovery bytes')
            (module/'config/active_font.conf').write_text('default\n')
            (fonts/'A.ttf').write_bytes(b'original synthetic fixture')
            calls=[]
            def root(command, required=True):
                calls.append(command)
                if command.startswith('settings '):
                    self.assertIn(' get secure ',command)
                    return value
                translated=command.replace(gate.MODULE,str(module)).replace(gate.FONTS,str(fonts))
                p=subprocess.run(['sh','-c',translated],capture_output=True,text=True,timeout=5)
                if required and p.returncode:
                    raise RuntimeError(p.stderr)
                return p.stdout.strip().replace(str(module),gate.MODULE).replace(str(fonts),gate.FONTS)
            report=gate.prepare(root)
            # Simulate byte-preserving replacement plus one-time archival. The
            # actual Magisk installer/boot service is only tested by Android gate.
            old=base/'old';module.rename(old);shutil.copytree(old,module)
            if report['weight_fixture'].get('expected_archive_hashes'):
                archive=module/'config/recovery/retired-global-weight';archive.mkdir()
                for name in ('font_weight.conf','font_weight_original.conf'):
                    (module/'config'/name).rename(archive/name)
            if remove_backup:
                (module/'config/recovery/existing/backup').unlink()
                with self.assertRaises(RuntimeError):gate.verify(root,report)
            else:
                self.assertEqual(gate.verify(root,report)['result'],'PASS')
            self.assertFalse(any('settings' in c and (' put ' in c or ' delete ' in c) for c in calls))
            return report
    def test_preserves_fonts_config_recovery_and_unowned_value(self):
        result=self.exercise('42')
        self.assertEqual(result['weight_fixture']['result'],'PASS_UNOWNED_SETTING_PRESERVED_AND_OLD_CONFIG_ARCHIVED')
    def test_null_value_never_guessed(self):
        result=self.exercise('null')
        self.assertEqual(result['weight_fixture']['result'],'NOT_RUN')
    def test_missing_existing_recovery_rejected(self):
        self.exercise('null',True)
