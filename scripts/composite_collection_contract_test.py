#!/usr/bin/env python3
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from fontTools.ttLib import TTCollection, TTFont

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('contract', ROOT / 'common/composite_collection_contract.py')
contract = importlib.util.module_from_spec(spec); spec.loader.exec_module(contract)
spec = importlib.util.spec_from_file_location('synthetic', ROOT / 'tests/android-root-gate/synthetic_fonts.py')
synthetic = importlib.util.module_from_spec(spec); spec.loader.exec_module(synthetic)


class CollectionContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.payload = self.base / '.luoshu-mix-stage'
        self.fonts = self.payload / 'system/fonts'
        self.fonts.mkdir(parents=True)
        self.source = self.base / 'source.ttf'
        synthetic.generate(self.source, 0)

    def tearDown(self):
        self.temp.cleanup()

    def collection(self):
        path = self.fonts / 'NotoSansCJK-Regular.ttc'
        collection = TTCollection()
        collection.fonts = [TTFont(self.source), TTFont(self.source)]
        try:
            collection.save(path)
        finally:
            collection.close()
        return path

    def test_real_collection_is_inspected_without_rewriting_any_bytes(self):
        path = self.collection(); original = path.read_bytes()
        result = contract.validate(self.payload, 'request-new')
        self.assertEqual('PASS', result['result'])
        self.assertEqual(2, result['collections'][0]['faces'])
        self.assertEqual('request-new', result['requestId'])
        self.assertEqual(original, path.read_bytes())

    def test_single_sfnt_hardlinked_under_ttc_name_is_rejected(self):
        path = self.fonts / 'NotoSansCJK-Regular.ttc'
        os.link(self.source, path)
        result = contract.validate(self.payload, 'request-new')
        self.assertEqual('FAIL', result['result'])
        self.assertIn('单字体', result['errors'][0]['reason'])
        self.assertEqual(self.source.read_bytes(), path.read_bytes())

    def test_truncated_or_out_of_range_collection_is_rejected(self):
        path = self.collection(); original = path.read_bytes()
        cases = [original[:12], original[:20], original[:4] + b'\0' * 8,
                 original[:12] + struct.pack('>I', len(original) + 1) + original[16:],
                 original[:12] + struct.pack('>I', 4) + original[16:]]
        for raw in cases:
            with self.subTest(size=len(raw)):
                path.write_bytes(raw)
                self.assertEqual('FAIL', contract.validate(self.payload, 'request')['result'])

    def test_alias_creation_failure_does_not_remove_an_existing_destination(self):
        destination = self.fonts / 'existing.ttc'
        destination.write_bytes(b'existing payload')
        result = subprocess.run(['sh', '-c', '. "$1"; _font_alias "$2" "$3"',
            'test', str(ROOT / 'common/legacy_v14_4/rom_adapters.sh'), str(self.source), str(destination)])
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(b'existing payload', destination.read_bytes())

    def test_finalizer_rejects_bad_stage_without_replacing_previous_next_payload(self):
        module = self.base
        (module / 'config').mkdir(); (module / 'logs').mkdir(); (module / 'common').mkdir()
        shutil.copyfile(ROOT / 'common/composite_collection_contract.py', module / 'common/composite_collection_contract.py')
        config = module / 'config'
        (config / 'active_font.conf').write_text('PreviousFont\n')
        (config / 'mix-stage-next.conf').write_text('requestId=new\ncjk=C\nlatin=L\ndigit=D\npreviousFont=PreviousFont\n')
        (self.payload / '.luoshu-mix-generation.conf').write_text('requestId=new\ncjk=C\nlatin=L\ndigit=D\ncompositeHash=hash\n')
        prior = module / '.luoshu-payload-next/system/fonts'
        prior.mkdir(parents=True)
        (prior / 'Roboto-Regular.ttf').write_bytes(b'prior next payload')
        (config / 'font-payload-next.conf').write_text('font=PreviousFont\nrequestId=previous\n')
        os.link(self.source, self.fonts / 'NotoSansCJK-Regular.ttc')
        before = (config / 'font-payload-next.conf').read_bytes()
        result = subprocess.run(['sh', str(ROOT / 'common/legacy_v14_4/mix_router.sh'), 'finalize'],
            env=dict(os.environ, MODDIR=str(module), LUOSHU_TASK_HELPER=str(ROOT / 'common/task_scope.py')),
            capture_output=True, text=True)
        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(b'prior next payload', (prior / 'Roboto-Regular.ttf').read_bytes())
        self.assertEqual(before, (config / 'font-payload-next.conf').read_bytes())
        self.assertEqual('PreviousFont\n', (config / 'active_font.conf').read_text())
        report = json.loads((config / 'composite-font-contract.json').read_text())
        self.assertEqual('new', report['requestId'])
        self.assertEqual('FAIL', report['result'])

    def test_interrupted_rename_cannot_publish_invalid_recovered_collection(self):
        module = self.base
        config = module / 'config'
        config.mkdir(); (module / 'logs').mkdir(); (module / 'common').mkdir()
        shutil.copyfile(ROOT / 'common/composite_collection_contract.py', module / 'common/composite_collection_contract.py')
        (config / 'active_font.conf').write_text('PreviousFont\n')
        state = config / 'mix-stage-next.conf'
        state.write_text('requestId=recover\npreviousFont=PreviousFont\n')
        next_fonts = module / '.luoshu-payload-next/system/fonts'
        next_fonts.mkdir(parents=True)
        os.link(self.source, next_fonts / 'NotoSansCJK-Regular.ttc')
        original = state.read_bytes()
        result = subprocess.run(['sh', str(ROOT / 'common/legacy_v14_4/mix_router.sh'), 'finalize'],
            env=dict(os.environ, MODDIR=str(module), LUOSHU_TASK_HELPER=str(ROOT / 'common/task_scope.py')),
            capture_output=True, text=True)
        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertFalse((config / 'font-payload-next.conf').exists())
        self.assertEqual(original, state.read_bytes())
        self.assertEqual('PreviousFont\n', (config / 'active_font.conf').read_text())
        report = json.loads((config / 'composite-font-contract.json').read_text())
        self.assertEqual('recover', report['requestId'])
        self.assertEqual('FAIL', report['result'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
