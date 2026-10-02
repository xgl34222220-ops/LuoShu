import subprocess
import tempfile
from pathlib import Path
import unittest
from commit_fault import mv_wrapper


class CommitFaultTests(unittest.TestCase):
    def test_only_exact_commit_once(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            marker = root / 'hit'
            wrapper = root / 'mv'
            wrapper.write_text(mv_wrapper(str(root), str(marker), '/bin/mv'))
            src = root / '.luoshu-payload-stage.123'
            dst = root / '.luoshu-payload-next'
            src.mkdir()
            failed = subprocess.run(['sh', str(wrapper), str(src), str(dst)])
            self.assertEqual(failed.returncode, 73)
            self.assertTrue(src.is_dir())
            self.assertFalse(dst.exists())
            self.assertIn(str(src), marker.read_text())
            retry = subprocess.run(['sh', str(wrapper), str(src), str(dst)])
            self.assertEqual(retry.returncode, 0)
            self.assertTrue(dst.is_dir())

    def test_other_rename_delegates_without_hit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            marker = root / 'hit'
            wrapper = root / 'mv'
            wrapper.write_text(mv_wrapper(str(root), str(marker), '/bin/mv'))
            src = root / 'ordinary'
            src.write_text('evidence')
            dst = root / 'destination'
            self.assertEqual(subprocess.run(['sh', str(wrapper), '-f', str(src), str(dst)]).returncode, 0)
            self.assertEqual(dst.read_text(), 'evidence')
            self.assertFalse(marker.exists())
