import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('probe', Path(__file__).with_name('probe.py'))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class RuntimeExtractionTests(unittest.TestCase):
    def test_rejects_unpinned_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'wrong.zip'
            archive.write_bytes(b'wrong')
            with self.assertRaisesRegex(RuntimeError, 'SHA256 mismatch'):
                probe.extract_runtime(archive, Path(tmp) / 'python')

    def test_rejects_x86_elf(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'x86.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('common/python/bin/luoshu-python', b'\x7fELF' + bytes(14) + b'\x3e\x00')
            old = probe.BASELINE_SHA256
            try:
                probe.BASELINE_SHA256 = hashlib.sha256(archive.read_bytes()).hexdigest()
                with self.assertRaisesRegex(RuntimeError, 'not ARM64'):
                    probe.extract_runtime(archive, Path(tmp) / 'python')
            finally:
                probe.BASELINE_SHA256 = old

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'unsafe.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('common/python/../../escape', b'bad')
            old = probe.BASELINE_SHA256
            try:
                probe.BASELINE_SHA256 = hashlib.sha256(archive.read_bytes()).hexdigest()
                with self.assertRaisesRegex(RuntimeError, 'Unsafe ZIP'):
                    probe.extract_runtime(archive, Path(tmp) / 'python')
            finally:
                probe.BASELINE_SHA256 = old


if __name__ == '__main__':
    unittest.main()
