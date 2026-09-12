#!/usr/bin/env python3
"""Offline release cleanup authorization and exact-lease regressions."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_branch_cleanup as cleanup
from sync_update_metadata import build_metadata

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = json.loads((ROOT / "config/release_branch_cleanup_v4.2.0.json").read_text())
REPO = MANIFEST["repository"]
RELEASE = "a" * 40
MAIN = "b" * 40
MERGED_HEAD = "c" * 40
MERGE = "d" * 40


def side(ref, sha):
    return {"ref": ref, "sha": sha, "repo": {"full_name": REPO}}


class FakeGitHub:
    def __init__(self):
        self.reads = []
        self.closed = []
        self.tag = RELEASE
        self.blocked_ancestors = set()
        self.data = {
            "": {"full_name": REPO, "default_branch": "main"},
            "/actions/runs/123": {"status": "completed", "conclusion": "success", "name": "Publish signed release",
                                  "path": ".github/workflows/release.yml", "head_sha": RELEASE,
                                  "repository": {"full_name": REPO}, "head_repository": {"full_name": REPO}},
            "/releases/tags/v4.2.0": {"tag_name": "v4.2.0", "draft": False, "prerelease": False,
                                      "published_at": "2026-09-12T00:00:00Z", "assets": []},
            "/pulls/217": {"number": 217, "state": "closed", "merged": True, "merged_at": "2026-09-12T00:00:00Z",
                           "head": side("fix/font-switch-provider-diagnostics", MERGED_HEAD),
                           "base": side("main", MERGE), "merge_commit_sha": MERGE},
            "/pulls/202": {"number": 202, "state": "open", "merged": False,
                           "head": side("fix/v4.0.0-usable-release", "ac472d90ffb1edb57eb845701817081c78e9c411"),
                           "base": side("main", MAIN)},
            "/pulls/203": {"number": 203, "state": "open", "merged": False, "head": side("main", MAIN),
                           "base": side("fix/v4.0.0-usable-release", "ac472d90ffb1edb57eb845701817081c78e9c411")},
        }
        for name in ("LuoShu-v4.2.0.zip", "LuoShu-v4.2.0.zip.sha256", "LuoShu-App-v4.2.0.apk", "LuoShu-App-v4.2.0.apk.sha256"):
            self.data["/releases/tags/v4.2.0"]["assets"].append({"name": name, "size": 100, "state": "uploaded",
                "browser_download_url": f"https://github.com/{REPO}/releases/download/v4.2.0/{name}"})
        self.branches = [{"name": "main", "protected": True, "commit": {"sha": MAIN}}]
        self.branches += [{"name": b["name"], "protected": False, "commit": {"sha": b.get("sha", MERGED_HEAD)}} for b in MANIFEST["branches"]]
        self.open_prs = [copy.deepcopy(self.data["/pulls/202"]), copy.deepcopy(self.data["/pulls/203"])]
        self.props = "id=luoshu\nversion=v4.2.0\nversionCode=40200\n"
        self.metadata = build_metadata(repository=REPO, version="v4.2.0", version_code=40200, tag="v4.2.0", notes_file="RELEASE_NOTES_v4.2.0.md")

    def get(self, path):
        self.reads.append(path)
        return copy.deepcopy(self.data[path])

    def listing(self, path):
        self.reads.append(path)
        return copy.deepcopy(self.branches if path.startswith("/branches?") else self.open_prs)

    def file(self, ref, path):
        return self.props if path == "module.prop" else json.dumps(self.metadata)

    def tag_sha(self, tag):
        return self.tag

    def ancestor(self, ancestor, descendant):
        return (ancestor, descendant) not in self.blocked_ancestors

    def close_pr(self, number):
        self.closed.append(number)
        self.open_prs = [p for p in self.open_prs if p["number"] != number]
        self.data[f"/pulls/{number}"]["state"] = "closed"


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeGitHub()
        self.manifest = copy.deepcopy(MANIFEST)

    def plan(self):
        return cleanup.plan_cleanup(self.manifest, self.api, tag="v4.2.0", release_sha=RELEASE, run_id=123)

    def refused(self, pattern):
        with self.assertRaisesRegex(cleanup.CleanupRefused, pattern):
            self.plan()
        self.assertEqual(self.api.closed, [])

    def test_successful_plan_does_not_mutate_and_retains_main(self):
        plan = self.plan()
        self.assertEqual(plan["close_prs"], [202, 203])
        self.assertEqual(len(plan["branches"]), 10)
        self.assertNotIn("main", [b["name"] for b in plan["branches"]])
        self.assertEqual(plan["branches"][-1]["sha"], MERGED_HEAD)
        self.assertEqual(self.api.closed, [])

    def test_prerelease_and_draft_rejected(self):
        for field in ("draft", "prerelease"):
            with self.subTest(field=field):
                self.api = FakeGitHub()
                self.api.data["/releases/tags/v4.2.0"][field] = True
                self.refused("published stable release")

    def test_release_and_workflow_identity(self):
        for field, value, message in (("status", "in_progress", "did not succeed"),
                                      ("conclusion", "failure", "did not succeed"),
                                      ("head_sha", MAIN, "SHA mismatch"),
                                      ("path", ".github/workflows/test.yml", "Unexpected publishing")):
            with self.subTest(field=field):
                self.api = FakeGitHub()
                self.api.data["/actions/runs/123"][field] = value
                self.refused(message)

    def test_tag_mismatch_and_default_branch_rejected(self):
        self.api.tag = MAIN
        self.refused("tag moved")
        self.api.tag = RELEASE
        self.api.data[""]["default_branch"] = "develop"
        self.refused("default branch mismatch")

    def test_metadata_and_missing_release_asset_rejected(self):
        self.api.metadata["zipUrl"] = "https://example.invalid/old.zip"
        self.refused("has not synchronized")
        self.api = FakeGitHub()
        self.api.data["/releases/tags/v4.2.0"]["assets"].pop()
        self.refused("Missing published asset")

    def test_unmerged_or_squashed_current_branch_rejected(self):
        self.api.data["/pulls/217"]["merged"] = False
        self.refused("must be merged")
        self.api = FakeGitHub()
        self.api.blocked_ancestors.add((MERGED_HEAD, RELEASE))
        self.refused("head is not contained")

    def test_unknown_moved_head_and_protected_branch_rejected(self):
        self.api.branches[1]["commit"]["sha"] = "e" * 40
        self.refused("Branch moved")
        self.api = FakeGitHub()
        self.api.branches[1]["protected"] = True
        self.refused("Protected branch retained")

    def test_other_open_pr_blocks_cleanup(self):
        new = copy.deepcopy(self.api.open_prs[0])
        new["number"] = 300
        self.api.open_prs.append(new)
        self.refused("Unknown open PR300")

    def test_obsolete_pr_changed_direction_or_new_work_rejected(self):
        self.api.data["/pulls/202"]["base"]["ref"] = "other"
        self.refused("head/base was changed")
        self.api = FakeGitHub()
        self.api.data["/pulls/202"]["head"]["sha"] = "f" * 40
        self.refused("contains new work")

    def test_reverse_sync_tracks_current_main_only(self):
        self.api.data["/pulls/203"]["head"]["sha"] = "f" * 40
        self.refused("not the verified main")
        self.api = FakeGitHub()
        self.api.blocked_ancestors.add((MANIFEST["obsolete_prs"][1]["head_ancestor"], MAIN))
        self.refused("main history was rewritten")

    def test_mismatched_fetch_or_multiple_push_urls_are_refused(self):
        authorized = f"https://github.com/{REPO}.git\n"
        for fetch, push in (("https://github.com/other/repo.git\n", authorized),
                            (authorized, authorized + "https://github.com/other/repo.git\n")):
            with self.subTest(fetch=fetch, push=push):
                def git(args):
                    if args[1] == "remote":
                        return push if "--push" in args else fetch
                    self.fail("must not read refs from a mismatched origin")
                with patch.object(cleanup, "command", side_effect=git):
                    with self.assertRaisesRegex(cleanup.CleanupRefused, "single authorized repository"):
                        cleanup.remote_refs(REPO)

    def test_moved_or_conflicting_archive_ref_rejected(self):
        plan = self.plan()
        refs = {"refs/heads/main": MAIN, **{"refs/heads/" + b["name"]: b["sha"] for b in plan["branches"]}}
        b = plan["branches"][0]
        refs["refs/tags/" + b["archive"]] = "f" * 40
        with self.assertRaisesRegex(cleanup.CleanupRefused, "Archive tag collision"):
            cleanup.check_remote_plan(plan, refs)
        refs.pop("refs/tags/" + b["archive"])
        refs["refs/heads/" + b["name"]] = "f" * 40
        with self.assertRaisesRegex(cleanup.CleanupRefused, "changed after planning"):
            cleanup.check_remote_plan(plan, refs)

    def test_apply_archives_first_and_atomic_deletion_has_every_exact_lease(self):
        plan = self.plan()
        refs = {"refs/heads/main": MAIN, **{"refs/heads/" + b["name"]: b["sha"] for b in plan["branches"]}}
        calls = []
        def git(args):
            calls.append(args)
            if args[1] == "push":
                self.assertIn("--atomic", args)
                specs = args[args.index("origin") + 1:]
                for spec in specs:
                    sha, ref = spec.split(":", 1)
                    if sha:
                        self.assertIn(f"--force-with-lease={ref}:", args)
                        refs[ref] = sha
                    else:
                        self.assertEqual(self.api.closed, [202, 203])
                        self.assertTrue(all(refs.get("refs/tags/" + b["archive"]) == b["sha"] for b in plan["branches"]))
                        self.assertIn(f"--force-with-lease={ref}:{refs[ref]}", args)
                        refs.pop(ref)
            return ""
        with patch.object(cleanup, "remote_refs", side_effect=lambda repo: dict(refs)), patch.object(cleanup, "command", side_effect=git):
            cleanup.apply_cleanup(self.manifest, self.api, plan)
        self.assertEqual(refs["refs/heads/main"], MAIN)
        self.assertEqual(len([c for c in calls if c[1] == "push"]), 2)
        self.assertEqual(len([r for r in refs if r.startswith("refs/tags/archive/")]), 10)

    def test_unknown_pr_opened_during_archival_prevents_any_deletion(self):
        plan = self.plan()
        refs = {"refs/heads/main": MAIN, **{"refs/heads/" + b["name"]: b["sha"] for b in plan["branches"]}}
        calls = []
        def git(args):
            calls.append(args)
            if args[1] == "push":
                for spec in args[args.index("origin") + 1:]:
                    sha, ref = spec.split(":", 1)
                    self.assertTrue(sha)
                    refs[ref] = sha
                new = copy.deepcopy(self.api.open_prs[0]); new["number"] = 300
                self.api.open_prs.append(new)
            return ""
        with patch.object(cleanup, "remote_refs", side_effect=lambda repo: dict(refs)), patch.object(cleanup, "command", side_effect=git):
            with self.assertRaisesRegex(cleanup.CleanupRefused, "Unknown open PR300"):
                cleanup.apply_cleanup(self.manifest, self.api, plan)
        self.assertEqual(self.api.closed, [])
        self.assertTrue(all("refs/heads/" + b["name"] in refs for b in plan["branches"]))

    def test_absent_branches_are_idempotent_and_no_head_deletion(self):
        self.api.branches = self.api.branches[:1]
        self.api.open_prs = []
        plan = self.plan()
        self.assertFalse(any(b["delete"] for b in plan["branches"]))
        refs = {"refs/heads/main": MAIN, **{"refs/tags/" + b["archive"]: b["sha"] for b in plan["branches"]}}
        with patch.object(cleanup, "remote_refs", return_value=refs), patch.object(cleanup, "command") as command:
            cleanup.apply_cleanup(self.manifest, self.api, plan)
            command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
