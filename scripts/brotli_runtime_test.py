#!/usr/bin/env python3
"""Run the distributed Android decoder, optionally through qemu-aarch64.

LUOSHU_BROTLI_RUNNER=/path/to/qemu-aarch64 python3 scripts/brotli_runtime_test.py
The tiny original WOFF2 fixture has four rectangle glyphs, no third-party font.
"""
import base64
import importlib.util
import io
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'common/python'
SITE = RUNTIME / 'lib/python3.14/site-packages'
DECODER = RUNTIME / 'bin/luoshu-brotli'
RUNNER = os.environ.get('LUOSHU_BROTLI_RUNNER')
WOFF2 = base64.b64decode(
    'd09GMgABAAAAAAF0AAoAAAAAAvwAAAEsAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAABmAARApgWAE2AiQDCgsKAAQgBYEEBzIbNQIAHgVuy0MnVbQ+UQa/naIZz9Ov/c59+1BJJDyLNrwxPxEieTOaooUKJVE9U8In78S51oWJlTjA0Wb13QtA/PMlMGTAuuPv8It9h89PqedJQgFhC+M8ytoCDjLMbWw4lCCInNGvFzWZM1QlyTAADqvY7PnNYndABt4BXPQFDeangnnVBoYNK9h03PO7jtvUfXRefwUAVDCMimnMAypI5YoUmoYpEnqEqvs15YrY0Vu1Bazr6BoAIAjjb38PSz7/Hw7+w/3ao35sFC8lQqOAMPV1+uTeBASWzGhQ4wMKq6o9ATGHgGLInEYqCcS6Bd8pJh1d9M/q1Jtn+0Xmz3frdHTqF4BC76ly0jOd2dt62tn7MF3a+/op7R31btY+IMFVe9V8Ct635+w8OQMA'
)


class DecoderTests(unittest.TestCase):
    def test_packaged_architecture_and_adapter(self):
        header = DECODER.read_bytes()[:20]
        self.assertEqual(header[:5], b'\x7fELF\x02')
        self.assertEqual(struct.unpack('<H', header[18:20])[0], 183)
        self.assertEqual((SITE / 'brotli.py').read_bytes(), (ROOT / 'scripts/runtime/brotli.py').read_bytes())
        self.assertTrue(os.access(DECODER, os.X_OK))

    @unittest.skipUnless(RUNNER or platform.machine().lower() in ('aarch64', 'arm64'), 'ARM64 execution needs qemu runner on this host')
    def test_android_binary_decodes_woff2_and_rejects_invalid_streams(self):
        sys.path.insert(0, str(SITE))
        spec = importlib.util.spec_from_file_location('brotli', SITE / 'brotli.py')
        adapter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(adapter)
        actual_run = subprocess.run

        def android_run(command, **kwargs):
            self.assertEqual(command, [str(DECODER)])
            return actual_run(([RUNNER] if RUNNER else []) + command, **kwargs)

        with patch.dict(sys.modules, {'brotli': adapter}), patch.object(adapter.subprocess, 'run', side_effect=android_run):
            from fontTools.ttLib import TTFont
            font = TTFont(io.BytesIO(WOFF2))
            cmap = font.getBestCmap()
            self.assertEqual(set(cmap), {49, 65, 0x4E2D})
            for cp, bounds in ((65, (20, 0, 120, 520)), (49, (30, 0, 140, 540)), (0x4E2D, (40, 0, 160, 560))):
                glyph = font['glyf'][cmap[cp]]
                self.assertEqual((glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax), bounds)
                self.assertEqual(font['hmtx'][cmap[cp]], (500, 0))
            font.flavor = None
            output = io.BytesIO()
            font.save(output)
            self.assertEqual(TTFont(io.BytesIO(output.getvalue())).getBestCmap(), cmap)
            # Exercise the actual importer too, with a deliberately misleading
            # suffix: recognition must be based on its WOFF2 signature.
            sys.path.insert(0, str(ROOT / 'common'))
            from font_import_engine import import_file
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = root / 'font.bin'
                source.write_bytes(WOFF2)
                report = import_file(source, root / 'fonts', source.name)['data']
                self.assertEqual(report['imported'], 1)
                self.assertEqual(report['faces'][0]['sourceFormat'], 'WOFF2')
                imported = TTFont(report['faces'][0]['path'])
                self.assertEqual(imported.getBestCmap(), cmap)
                self.assertEqual(imported.getTableData('glyf'), TTFont(io.BytesIO(output.getvalue())).getTableData('glyf'))
            for invalid in (b'', b'invalid', b'\x0b\x01\x80abc', b'\x0b\x01\x80abc\x03EXTRA'):
                with self.assertRaises(adapter.error):
                    adapter.decompress(invalid)


if __name__ == '__main__':
    unittest.main()
