import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'common'))
import native_runtime_smoke as smoke


class RuntimeSmokeTest(unittest.TestCase):
    def test_real_nine_master_build_is_not_an_import_only_check(self):
        with tempfile.TemporaryDirectory() as td:
            result=smoke.variable_data_check(td)
            self.assertEqual(result['state'],'ready');self.assertEqual(result['variableGlyphCount'],1)
            self.assertIn(450,result['validatedWeights'])

    def test_host_cannot_claim_android_execution(self):
        with self.assertRaisesRegex(RuntimeError,'Android x86_64'):
            smoke.run(Path('/tmp'),Path('unused'),Path('unused'))


if __name__=='__main__':unittest.main()
