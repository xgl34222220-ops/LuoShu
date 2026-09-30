#!/usr/bin/env python3
"""Exercise exact preview destination routing without touching Android paths."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]

class PreviewDestinationTest(unittest.TestCase):
    def test_exact_packages_and_traversal(self):
        source=(ROOT/'common/app_bridge.sh').read_text()
        function=source[source.index('preview_export() {'):source.index('\nweight_axis_info()')]
        with tempfile.TemporaryDirectory() as raw:
            font=Path(raw)/'font.ttf';font.write_bytes(b'fixture')
            # No filesystem operation is performed on an Android/user directory.
            body=f'. "{ROOT}/common/app_cache_guard.sh"\n'+'''readlink() { printf '%s\\n' "$2" | sed 's#^/data/data/#/data/user/0/#'; }
find_preview_source() { printf '%s\\n' "$FONT"; }
mkdir() { :; }; cp() { :; }; chmod() { :; }
font_file_sha256() { printf digest; }
json_escape() { printf '%s' "$1"; }
'''+function+'\npreview_export Family "$1"\n'
            import os
            for base in ('/data/user/0/','/data/data/'):
                for package in ('io.github.xgl34222220.luoshu','io.github.xgl34222220.luoshu.debug','io.github.xgl34222220.luoshu.audit'):
                    target=base+package+'/cache/preview/font.ttf'
                    result=subprocess.run(['sh','-c',body,'sh',target],env=os.environ|{'FONT':str(font)},capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,(target,result.stdout,result.stderr))
                    self.assertEqual(json.loads(result.stdout)['status'],'ok')
            for target in ('/data/user/0/com.other.app/cache/font.ttf',
                           '/data/user/0/io.github.xgl34222220.luoshu.audit.evil/cache/font.ttf',
                           '/data/user/0/io.github.xgl34222220.luoshu.audit/cache/../../com.other.app/font.ttf',
                           '/data/data/io.github.xgl34222220.luoshu.audit/files/font.ttf',
                           '/data/user/10/io.github.xgl34222220.luoshu.audit/cache/font.ttf'):
                result=subprocess.run(['sh','-c',body,'sh',target],env=os.environ|{'FONT':str(font)},capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0,target)
                self.assertEqual(json.loads(result.stdout)['status'],'error')
if __name__=='__main__':unittest.main(verbosity=2)
