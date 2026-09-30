#!/usr/bin/env python3
"""Run the actual guard against temp filesystem aliases; no host /data access."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
PACKAGES=('io.github.xgl34222220.luoshu','io.github.xgl34222220.luoshu.debug','io.github.xgl34222220.luoshu.audit')

class CacheGuardTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); data=self.root/'data';(data/'user/0').mkdir(parents=True)
        (data/'data').symlink_to(data/'user/0',target_is_directory=True)
        for pkg in (*PACKAGES,'com.other.app'):
            for sub in ('native_import','font_archive','native-font-preview'):
                (data/'user/0'/pkg/'cache'/sub).mkdir(parents=True)
        bin=self.root/'bin';bin.mkdir()
        script=bin/'readlink'
        script.write_text('#!'+sys.executable+'\n'+'''import os,sys
from pathlib import Path
root=Path(os.environ['FAKE_FS_ROOT'])
p=Path(sys.argv[-1])
if not str(p).startswith('/data/'):sys.exit(1)
physical=root/str(p).lstrip('/')
try: real=physical.resolve(strict=False)
except (OSError,RuntimeError):sys.exit(1)
try: print('/'+real.relative_to(root).as_posix())
except ValueError: print(str(real))
''');script.chmod(0o755)
        self.env=os.environ|{'PATH':str(bin)+':'+os.environ['PATH'],'FAKE_FS_ROOT':str(self.root)}

    def guard(self,path,purpose):
        result=subprocess.run(['sh','-c',f'. "{ROOT}/common/app_cache_guard.sh"; luoshu_app_cache_guard "$1" "$2"; rc=$?; printf "%s" "$LUOSHU_TRUSTED_CACHE_PATH"; exit "$rc"','sh',path,purpose],env=self.env,text=True,capture_output=True)
        return result

    def test_exact_packages_aliases_and_new_destinations(self):
        for pkg in PACKAGES:
            for base in ('/data/user/0/','/data/data/'):
                for purpose,sub in (('preview','native-font-preview'),('native_import','native_import'),('font_archive','font_archive')):
                    path=f'{base}{pkg}/cache/{sub}/new/nested/file.ttf'
                    result=self.guard(path,purpose)
                    self.assertEqual(result.returncode,0,(path,result.stderr))
                    self.assertEqual(result.stdout,f'/data/user/0/{pkg}/cache/{sub}/new/nested/file.ttf')

    def test_user_zero_alias_resolves_to_data_data(self):
        data=self.root/'data'
        (data/'data').unlink()
        (data/'user/0').rename(data/'data')
        (data/'user/0').symlink_to(data/'data',target_is_directory=True)
        for pkg in PACKAGES:
            for purpose,sub in (('preview','native-font-preview'),('native_import','native_import'),('font_archive','font_archive')):
                result=self.guard(f'/data/user/0/{pkg}/cache/{sub}/file.ttf',purpose)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout,f'/data/data/{pkg}/cache/{sub}/file.ttf')

    def test_reject_lexical_and_similar_package_escape(self):
        for purpose,sub in (('preview','native-font-preview'),('native_import','native_import'),('font_archive','font_archive')):
            base=f'/data/user/0/{PACKAGES[2]}/cache/{sub}'
            for path in (base+'/../../../com.other.app/cache/file.ttf',base+'/./file.ttf',base+'//file.ttf',
                         base.replace(PACKAGES[2],PACKAGES[2]+'.evil')+'/file.ttf',
                         base.replace('/user/0/','/user/10/')+'/file.ttf',
                         base.replace('/cache/','/files/')+'/file.ttf'):
                self.assertNotEqual(self.guard(path,purpose).returncode,0,path)

    def test_parent_cache_or_purpose_symlink_cannot_redefine_root(self):
        import shutil
        for purpose,sub in (('preview','native-font-preview'),('native_import','native_import'),('font_archive','font_archive')):
            pkg=PACKAGES[2];cache=self.root/f'data/user/0/{pkg}/cache'
            child=cache/sub;shutil.rmtree(child);child.symlink_to(self.root/'data/user/0/com.other.app/cache'/sub,target_is_directory=True)
            self.assertNotEqual(self.guard(f'/data/user/0/{pkg}/cache/{sub}/file.ttf',purpose).returncode,0)
            child.unlink();child.mkdir()
        pkg=PACKAGES[0];cache=self.root/f'data/user/0/{pkg}/cache';shutil.rmtree(cache)
        cache.symlink_to(self.root/'data/user/0/com.other.app/cache',target_is_directory=True)
        self.assertNotEqual(self.guard(f'/data/data/{pkg}/cache/native_import/file.ttf','native_import').returncode,0)

    def test_leaf_symlink_outside_purpose_is_rejected(self):
        pkg=PACKAGES[1];cache=self.root/f'data/user/0/{pkg}/cache'
        target=self.root/'data/user/0/com.other.app/cache/native_import/file.ttf';target.write_text('private')
        (cache/'native_import/escape.ttf').symlink_to(target)
        self.assertNotEqual(self.guard(f'/data/user/0/{pkg}/cache/native_import/escape.ttf','native_import').returncode,0)
        (cache/'native_import/dangling.ttf').symlink_to(self.root/'outside/no-file')
        self.assertNotEqual(self.guard(f'/data/user/0/{pkg}/cache/native_import/dangling.ttf','native_import').returncode,0)

if __name__=='__main__':unittest.main(verbosity=2)
