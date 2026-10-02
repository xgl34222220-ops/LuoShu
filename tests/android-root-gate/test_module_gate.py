import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).parent))
from module_gate import resolve_authorized_uid, PACKAGE


class IsolatedRootGrantTests(unittest.TestCase):
    def test_exact_test_package_only(self):
        self.assertEqual(resolve_authorized_uid('package:' + PACKAGE + ' uid:10123\npackage:io.github.xgl34222220.luoshu uid:10124'), 10123)

    def test_never_substitute_official_app(self):
        with self.assertRaises(RuntimeError):
            resolve_authorized_uid('package:io.github.xgl34222220.luoshu uid:10123')

    def test_shared_uid_rejected(self):
        with self.assertRaises(RuntimeError):
            resolve_authorized_uid('package:' + PACKAGE + ' uid:10123\npackage:other.app uid:10123')

    def test_system_and_other_user_uids_rejected(self):
        for uid in (0, 1000, 9999, 110123):
            with self.assertRaises(RuntimeError):
                resolve_authorized_uid('package:' + PACKAGE + ' uid:' + str(uid))
