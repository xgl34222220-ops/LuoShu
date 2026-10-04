import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).parent))
from module_gate import resolve_authorized_uid, payload_mount_proof, PACKAGE


class CanonicalPayloadTests(unittest.TestCase):
    path = '/system/fonts/DroidSans-Bold.ttf'
    canonical = '/system/fonts/Roboto-Regular.ttf'
    digest = 'a' * 64

    def proof(self, *, canonical=None, hashes=None, rows=None):
        stock = {self.path: self.canonical, self.canonical: self.canonical}
        if hashes is None:
            hashes = {self.canonical: self.digest}
        if rows is None:
            rows = [['296', '42', '254:46',
                     '/adb/modules/LuoShu/.luoshu-payload' + self.canonical,
                     self.canonical, 'rw', '-', 'ext4', '/dev/block/dm-46', 'rw']]
        return payload_mount_proof(self.path, canonical or self.canonical,
                                   stock, self.digest, hashes, rows)

    def test_original_android_alias_uses_committed_canonical_slot(self):
        proof = self.proof()
        self.assertEqual(self.canonical, proof['stock_canonical'])
        self.assertEqual(self.canonical, proof['payload_path'])
        self.assertEqual(self.digest, proof['payload_sha256'])
        self.assertTrue(proof['mount_records'])

    def test_missing_or_wrong_canonical_bytes_fail(self):
        for hashes in ({}, {self.canonical: 'b' * 64}):
            with self.subTest(hashes=hashes), self.assertRaises(RuntimeError):
                self.proof(hashes=hashes)

    def test_changed_stock_alias_is_not_authorized_by_matching_bytes(self):
        other = '/system/fonts/Roboto-Bold.ttf'
        with self.assertRaises(RuntimeError):
            self.proof(canonical=other, hashes={other: self.digest})

    def test_conflicting_alias_payload_cannot_pass(self):
        with self.assertRaises(RuntimeError):
            self.proof(hashes={self.canonical: self.digest, self.path: 'b' * 64})

    def test_wrong_source_or_lookalike_destination_cannot_pass(self):
        for source, destination in (
            ('/adb/modules/other/.luoshu-payload' + self.canonical, self.canonical),
            ('/unrelated/adb/modules/LuoShu/.luoshu-payload' + self.canonical, self.canonical),
            ('/adb/modules/LuoShu/.luoshu-payload' + self.path, self.canonical),
            ('/adb/modules/LuoShu/.luoshu-payload/system/fonts', '/system/font'),
        ):
            rows = [['296', '42', '254:46', source, destination, 'rw']]
            with self.subTest(source=source), self.assertRaises(RuntimeError):
                self.proof(rows=rows)

    def test_directory_bind_proves_relative_canonical_source(self):
        rows = [['296', '42', '254:46', '/data/adb/modules/LuoShu/.luoshu-payload/system/fonts',
                 '/system/fonts', 'rw']]
        self.assertEqual(rows, self.proof(rows=rows)['mount_records'])

    def test_partition_symlink_keeps_original_payload_spelling(self):
        path = '/product/fonts/Example.ttf'
        canonical = '/system/product/fonts/Example.ttf'
        rows = [['296', '42', '254:46', '/adb/modules/LuoShu/.luoshu-payload' + path,
                 canonical, 'rw']]
        proof = payload_mount_proof(path, canonical, {path: canonical},
                                    self.digest, {path: self.digest}, rows)
        self.assertEqual(path, proof['payload_path'])


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
