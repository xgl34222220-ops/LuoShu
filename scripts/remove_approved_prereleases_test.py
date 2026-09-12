#!/usr/bin/env python3
"""Offline mutation-boundary and idempotence checks for prerelease retirement."""
from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import remove_approved_prereleases as target

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = json.loads((ROOT / "config/prerelease_cleanup_2026-09-12.json").read_text())


class FakeGitHub:
    def __init__(self):
        self.releases = {
            release_id: {"id": release_id, "tag_name": tag, "prerelease": True, "draft": False}
            for release_id, tag in target.APPROVED.items()
        }
        self.releases[387458444] = {"id": 387458444, "tag_name": "v4.2.0", "prerelease": False, "draft": False}
        self.releases[383803920] = {"id": 383803920, "tag_name": "v4.1.0", "prerelease": False, "draft": False}
        self.deleted = []
        self.reads = {}
        self.before_read = None

    def get(self, suffix):
        if not suffix:
            return {"full_name": target.REPOSITORY, "default_branch": "main"}
        release_id = int(suffix.removeprefix("/releases/"))
        self.reads[release_id] = self.reads.get(release_id, 0) + 1
        if self.before_read is not None:
            self.before_read(self, release_id, self.reads[release_id])
        return copy.deepcopy(self.releases.get(release_id))

    def listing(self):
        return copy.deepcopy(list(self.releases.values()))

    def delete(self, release_id):
        self.deleted.append(release_id)
        del self.releases[release_id]


class CleanupTests(unittest.TestCase):
    def run_cleanup(self, api, *, apply=True, manifest=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return target.cleanup(MANIFEST if manifest is None else manifest, api, apply=apply)

    def test_apply_removes_exact_five_and_keeps_stable(self):
        api = FakeGitHub()
        result = self.run_cleanup(api)
        self.assertEqual(set(api.deleted), set(target.APPROVED))
        self.assertEqual(len(api.deleted), 5)
        self.assertEqual(set(api.releases), {387458444, 383803920})
        self.assertEqual(len(result["removed"]), 5)

    def test_plan_is_read_only(self):
        api = FakeGitHub()
        result = self.run_cleanup(api, apply=False)
        self.assertEqual(len(result["remove"]), 5)
        self.assertEqual(api.deleted, [])

    def test_already_absent_release_is_idempotent(self):
        api = FakeGitHub()
        del api.releases[387499938]
        self.run_cleanup(api)
        self.assertEqual(len(api.deleted), 4)
        result = self.run_cleanup(api)
        self.assertEqual(result["removed"], [])
        self.assertEqual(len(api.deleted), 4)

    def test_complete_preflight_rejects_promoted_stable_before_any_delete(self):
        api = FakeGitHub()
        # The last item is promoted after listing but before individual preflight.
        def promote(fake, release_id, count):
            if release_id == 359987560 and count == 1:
                fake.releases[release_id]["prerelease"] = False
        api.before_read = promote
        with self.assertRaisesRegex(target.CleanupRefused, "no longer"):
            self.run_cleanup(api)
        self.assertEqual(api.deleted, [])

    def test_fresh_read_rejects_promotion_after_preflight(self):
        api = FakeGitHub()
        def promote(fake, release_id, count):
            if release_id == 387499938 and count == 2:
                fake.releases[release_id]["prerelease"] = False
        api.before_read = promote
        with self.assertRaisesRegex(target.CleanupRefused, "no longer"):
            self.run_cleanup(api)
        self.assertEqual(api.deleted, [])

    def test_fresh_read_rejects_retagged_release(self):
        api = FakeGitHub()
        def retag(fake, release_id, count):
            if release_id == 387499938 and count == 2:
                fake.releases[release_id]["tag_name"] = "v4.3.0"
        api.before_read = retag
        with self.assertRaisesRegex(target.CleanupRefused, "identity"):
            self.run_cleanup(api)
        self.assertEqual(api.deleted, [])

    def test_concurrent_removal_is_not_retargeted(self):
        api = FakeGitHub()
        def remove(fake, release_id, count):
            if release_id == 387499938 and count == 2:
                del fake.releases[release_id]
        api.before_read = remove
        self.run_cleanup(api)
        self.assertNotIn(387499938, api.deleted)
        self.assertEqual(len(api.deleted), 4)

    def test_unknown_prerelease_stops_before_deletion(self):
        api = FakeGitHub()
        api.releases[123] = {"id": 123, "tag_name": "v4.3.0-RC1", "prerelease": True, "draft": False}
        with self.assertRaisesRegex(target.CleanupRefused, "unreviewed"):
            self.run_cleanup(api)
        self.assertEqual(api.deleted, [])

    def test_draft_is_retained(self):
        api = FakeGitHub()
        api.releases[387499938]["draft"] = True
        with self.assertRaises(target.CleanupRefused):
            self.run_cleanup(api)
        self.assertEqual(api.deleted, [])

    def test_manifest_cannot_expand_scope_or_change_repository(self):
        changes = []
        wrong_repo = copy.deepcopy(MANIFEST)
        wrong_repo["repository"] = "other/repository"
        changes.append(wrong_repo)
        extra = copy.deepcopy(MANIFEST)
        extra["releases"].append({"id": 387458444, "tag": "v4.2.0"})
        changes.append(extra)
        swapped = copy.deepcopy(MANIFEST)
        swapped["releases"][0] = {"id": 387458444, "tag": "v4.2.0"}
        changes.append(swapped)
        duplicate = copy.deepcopy(MANIFEST)
        duplicate["releases"][0] = duplicate["releases"][1]
        changes.append(duplicate)
        for manifest in changes:
            api = FakeGitHub()
            with self.subTest(manifest=manifest), self.assertRaises(target.CleanupRefused):
                self.run_cleanup(api, manifest=manifest)
            self.assertEqual(api.deleted, [])

    def test_api_rejects_tag_branch_and_stable_deletion_without_network(self):
        api = target.GitHub("test-only")
        with patch.object(target, "urlopen") as request:
            for path in ("/git/refs/tags/v4.2.3-RC1", "/git/refs/heads/main", "/releases/387458444", "/releases"):
                with self.subTest(path=path), self.assertRaises(target.CleanupRefused):
                    api.request(path, "DELETE")
            with self.assertRaises(target.CleanupRefused):
                api.request("/releases/387499938", "PATCH")
            request.assert_not_called()

    def test_api_reads_all_release_pages(self):
        api = target.GitHub("")
        first = [{"id": number} for number in range(100)]
        with patch.object(api, "get", side_effect=[first, [{"id": 100}]]) as get:
            self.assertEqual(len(api.listing()), 101)
            self.assertEqual(get.call_count, 2)
            self.assertEqual(get.call_args.args[0], "/releases?per_page=100&page=2")

    def test_failed_deletion_verification_stops_further_mutations(self):
        api = FakeGitHub()
        def no_op(release_id):
            api.deleted.append(release_id)
        api.delete = no_op
        with self.assertRaisesRegex(target.CleanupRefused, "still exists"):
            self.run_cleanup(api)
        self.assertEqual(api.deleted, [387499938])

    def test_update_channel_has_no_deleted_release_target(self):
        # At retirement both channels use the latest stable release. They may
        # advance later; neither is allowed to retain any removed release URL.
        for filename in ("update.json", "update-prerelease.json"):
            value = json.loads((ROOT / filename).read_text())
            for tag in target.APPROVED.values():
                self.assertNotIn(f"/download/{tag}/", value["zipUrl"])


if __name__ == "__main__":
    unittest.main()
