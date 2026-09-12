#!/usr/bin/env python3
"""Archive and retire the explicitly approved v4.2.0 branches after publication.

Without --apply this performs remote reads and prints a plan. No branch mutation
is possible before the release, publishing workflow, metadata and PR checks pass.
Every deletion uses an explicit SHA lease, in one atomic remote push.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

from sync_update_metadata import build_metadata


class CleanupRefused(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CleanupRefused(message)


def command(args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True, check=False, timeout=120)
    if result.returncode:
        # Do not echo subprocess output: git/gh failures can include credential URLs.
        raise CleanupRefused(f"{args[0]} operation failed (exit {result.returncode}); no unleased retry")
    return result.stdout


class GitHub:
    def __init__(self, repository: str):
        self.root = f"repos/{repository}"

    def get(self, suffix: str):
        return json.loads(command(["gh", "api", self.root + suffix]))

    def listing(self, suffix: str) -> list:
        pages = json.loads(command(["gh", "api", "--paginate", "--slurp", self.root + suffix]))
        require(all(isinstance(page, list) for page in pages), "Unexpected paginated response")
        return [item for page in pages for item in page]

    def file(self, ref: str, path: str) -> str:
        payload = self.get(f"/contents/{quote(path, safe='/')}?ref={quote(ref, safe='')}")
        require(payload.get("encoding") == "base64", f"Unsupported encoding for {path}")
        return base64.b64decode(payload["content"]).decode("utf-8")

    def ancestor(self, ancestor: str, descendant: str) -> bool:
        if ancestor == descendant:
            return True
        result = self.get(f"/compare/{ancestor}...{descendant}")
        return result.get("status") in {"ahead", "identical"} and result.get("merge_base_commit", {}).get("sha") == ancestor

    def tag_sha(self, tag: str) -> str:
        obj = self.get(f"/git/ref/tags/{quote(tag, safe='')}")["object"]
        for _ in range(8):
            if obj.get("type") == "commit":
                return obj["sha"]
            require(obj.get("type") == "tag", "Release tag does not resolve to a commit")
            obj = self.get(f"/git/tags/{obj['sha']}")["object"]
        raise CleanupRefused("Release tag nesting is invalid")

    def close_pr(self, number: int) -> None:
        command(["gh", "api", "--method", "PATCH", self.root + f"/pulls/{number}", "-f", "state=closed"])


def validate_manifest(manifest: dict) -> None:
    require(manifest.get("schema") == 1, "Unsupported cleanup manifest")
    require(manifest.get("repository") == "xgl34222220-ops/LuoShu", "Cleanup is scoped to LuoShu")
    require(manifest.get("default_branch") == "main", "Default branch must remain main")
    require(manifest.get("tag") == "v4.2.0", "Only v4.2.0 cleanup is authorized")
    require(manifest.get("archive_prefix") == "archive/v4.2.0/", "Invalid archive prefix")
    names = []
    for item in manifest["branches"]:
        name = item["name"]
        require(name != "main" and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", name) is not None, "Unsafe branch name")
        require(".." not in name and not name.endswith(("/", ".lock")), "Unsafe branch ref")
        require(bool(item.get("rationale")), f"No retirement rationale for {name}")
        if "sha" in item:
            require(re.fullmatch(r"[0-9a-f]{40}", item["sha"]) is not None, f"Invalid pinned SHA for {name}")
        else:
            require(item.get("merged_pr") == 217 and name == "fix/font-switch-provider-diagnostics", "Unknown dynamic branch")
        names.append(name)
    require(len(names) == len(set(names)), "Duplicate cleanup branch")
    require({p["number"] for p in manifest["obsolete_prs"]} == {202, 203}, "Unexpected PR closure authorization")


def same_repo_side(pr: dict, side: str, repository: str, ref: str) -> bool:
    value = pr.get(side, {})
    return value.get("ref") == ref and (value.get("repo") or {}).get("full_name") == repository


def check_obsolete_pr(spec: dict, pr: dict, repository: str, main_sha: str, api: GitHub) -> None:
    require(pr.get("number") == spec["number"], "Unexpected obsolete PR response")
    require(same_repo_side(pr, "head", repository, spec["head"]) and same_repo_side(pr, "base", repository, spec["base"]),
            f"PR{spec['number']} head/base was changed")
    if "head_sha" in spec:
        require(pr["head"].get("sha") == spec["head_sha"], f"PR{spec['number']} contains new work")
    else:
        # Reverse-sync PR203 tracks main, which necessarily moves during this release.
        require(pr["head"].get("sha") == main_sha, "Reverse-sync PR head is not the verified main")
        require(api.ancestor(spec["head_ancestor"], main_sha), "Reverse-sync PR main history was rewritten")
    require(pr.get("merged") is False, f"Obsolete PR{spec['number']} was merged unexpectedly")


def plan_cleanup(manifest: dict, api: GitHub, *, tag: str, release_sha: str, run_id: int) -> dict:
    validate_manifest(manifest)
    repository = manifest["repository"]
    require(tag == manifest["tag"], "Release tag does not match cleanup authorization")
    require(re.fullmatch(r"[0-9a-f]{40}", release_sha) is not None, "Invalid publishing SHA")
    repo = api.get("")
    require(repo.get("full_name") == repository and repo.get("default_branch") == "main", "Repository/default branch mismatch")
    run = api.get(f"/actions/runs/{run_id}")
    require(run.get("status") == "completed" and run.get("conclusion") == "success", "Publishing workflow did not succeed")
    require(run.get("path") == manifest["release_workflow"] and run.get("name") == "Publish signed release", "Unexpected publishing workflow")
    require(run.get("head_sha") == release_sha and (run.get("repository") or {}).get("full_name") == repository,
            "Publishing workflow repository/SHA mismatch")
    require((run.get("head_repository") or {}).get("full_name") == repository, "Fork workflow cannot authorize cleanup")
    require(api.tag_sha(tag) == release_sha, "Published tag moved or differs from publishing SHA")
    release = api.get(f"/releases/tags/{tag}")
    require(release.get("tag_name") == tag and release.get("draft") is False and release.get("prerelease") is False
            and bool(release.get("published_at")), "A published stable release is required")
    assets = {a["name"]: a for a in release.get("assets", [])}
    release_root = f"https://github.com/{repository}/releases/download/{tag}"
    for name in (f"LuoShu-{tag}.zip", f"LuoShu-{tag}.zip.sha256", f"LuoShu-App-{tag}.apk", f"LuoShu-App-{tag}.apk.sha256"):
        asset = assets.get(name, {})
        require(asset.get("state") == "uploaded" and asset.get("size", 0) > 0
                and asset.get("browser_download_url") == f"{release_root}/{name}", f"Missing published asset: {name}")
    branches = {b["name"]: b for b in api.listing("/branches?per_page=100")}
    require("main" in branches, "main branch is missing")
    main_sha = branches["main"]["commit"]["sha"]
    require(api.ancestor(release_sha, main_sha), "The stable release is not on main")
    props = dict(line.split("=", 1) for line in api.file(release_sha, "module.prop").splitlines() if "=" in line)
    require(props.get("version") == tag, "Published module version differs from v4.2.0")
    require(props.get("versionCode") == "40200", "Unexpected v4.2.0 version code")
    expected = build_metadata(repository=repository, version=tag, version_code=40200, tag=tag, notes_file=f"RELEASE_NOTES_{tag}.md")
    require(json.loads(api.file(main_sha, "update.json")) == expected, "Online update.json has not synchronized to this release")
    pr217 = api.get("/pulls/217")
    require(pr217.get("merged") is True and bool(pr217.get("merged_at")), "PR217 must be merged before cleanup")
    require(same_repo_side(pr217, "head", repository, "fix/font-switch-provider-diagnostics")
            and same_repo_side(pr217, "base", repository, "main"), "PR217 head/base mismatch")
    merged_head = pr217["head"]["sha"]
    require(api.ancestor(merged_head, release_sha), "PR217 head is not contained in the release; squash/rebase requires manual review")
    require(api.ancestor(pr217["merge_commit_sha"], release_sha), "PR217 merge is not contained in the release")
    obsolete = {p["number"]: p for p in manifest["obsolete_prs"]}
    open_prs = api.listing("/pulls?state=open&per_page=100")
    names = {item["name"] for item in manifest["branches"]}
    closing = []
    for pr in open_prs:
        touches = any((pr.get(side, {}).get("repo") or {}).get("full_name") == repository
                      and pr.get(side, {}).get("ref") in names for side in ("head", "base"))
        if not touches:
            continue
        require(pr["number"] in obsolete, f"Unknown open PR{pr['number']} uses a retirement branch")
        spec = obsolete[pr["number"]]
        # List responses omit the explicit merged boolean; retrieve the full PR.
        full = api.get(f"/pulls/{pr['number']}")
        check_obsolete_pr(spec, full, repository, main_sha, api)
        closing.append(pr["number"])
    entries = []
    for item in manifest["branches"]:
        name = item["name"]
        expected_sha = item.get("sha", merged_head)
        branch = branches.get(name)
        if branch is not None:
            require(branch.get("protected") is False, f"Protected branch retained: {name}")
            require(branch["commit"]["sha"] == expected_sha, f"Branch moved; retaining unknown work: {name}")
        entries.append({"name": name, "sha": expected_sha, "archive": manifest["archive_prefix"] + name,
                        "delete": branch is not None, "rationale": item["rationale"]})
    return {"repository": repository, "tag": tag, "release_sha": release_sha, "run_id": run_id,
            "main_sha": main_sha, "close_prs": sorted(closing), "branches": entries}


def remote_refs(repository: str) -> dict[str, str]:
    allowed = {f"https://github.com/{repository}.git", f"https://github.com/{repository}", f"git@github.com:{repository}.git"}
    # ls-remote/fetch must read the same repository that push mutates. Multiple
    # push URLs are rejected because git would update every configured endpoint.
    for push in (False, True):
        flags = ["--push"] if push else []
        urls = command(["git", "remote", "get-url", *flags, "--all", "origin"]).splitlines()
        require(len(urls) == 1 and urls[0] in allowed,
                f"origin {'push' if push else 'fetch'} URL is not the single authorized repository")
    refs = {}
    for line in command(["git", "ls-remote", "--refs", "origin"]).splitlines():
        sha, ref = line.split("\t", 1)
        refs[ref] = sha
    return refs


def check_remote_plan(plan: dict, refs: dict[str, str]) -> None:
    require(refs.get("refs/heads/main") == plan["main_sha"], "main moved since release verification; rerun the plan")
    for item in plan["branches"]:
        head = refs.get("refs/heads/" + item["name"])
        require(head == (item["sha"] if item["delete"] else None), f"Branch changed after planning: {item['name']}")
        archive = refs.get("refs/tags/" + item["archive"])
        require(archive is None or archive == item["sha"], f"Archive tag collision: {item['archive']}")


def apply_cleanup(manifest: dict, api: GitHub, plan: dict) -> None:
    refs = remote_refs(plan["repository"])
    check_remote_plan(plan, refs)
    missing = [b for b in plan["branches"] if "refs/tags/" + b["archive"] not in refs]
    if missing:
        for item in missing:
            command(["git", "fetch", "--no-tags", "origin", item["sha"]])
        # Explicit empty tag leases prevent replacement if another process creates a tag.
        command(["git", "push", "--atomic", *[f"--force-with-lease=refs/tags/{b['archive']}:" for b in missing],
                 "origin", *[f"{b['sha']}:refs/tags/{b['archive']}" for b in missing]])
    fresh = plan_cleanup(manifest, api, tag=plan["tag"], release_sha=plan["release_sha"], run_id=plan["run_id"])
    require(fresh == plan, "Release/PR/branch state changed while archiving; rerun the plan")
    refs = remote_refs(plan["repository"])
    check_remote_plan(plan, refs)
    require(all(refs.get("refs/tags/" + b["archive"]) == b["sha"] for b in plan["branches"]), "Archive verification failed")
    for number in plan["close_prs"]:
        spec = next(p for p in manifest["obsolete_prs"] if p["number"] == number)
        current = api.get(f"/pulls/{number}")
        check_obsolete_pr(spec, current, plan["repository"], plan["main_sha"], api)
        require(current.get("state") == "open", f"PR{number} state changed before closure")
        api.close_pr(number)
    # Confirm there are no newly opened PRs and all release evidence still holds.
    final = plan_cleanup(manifest, api, tag=plan["tag"], release_sha=plan["release_sha"], run_id=plan["run_id"])
    require(not final["close_prs"] and final["branches"] == plan["branches"] and final["main_sha"] == plan["main_sha"],
            "State changed before deletion; archives retained, no branch deletion attempted")
    check_remote_plan(final, remote_refs(plan["repository"]))
    deleting = [b for b in final["branches"] if b["delete"]]
    if deleting:
        command(["git", "push", "--atomic", *[f"--force-with-lease=refs/heads/{b['name']}:{b['sha']}" for b in deleting],
                 "origin", *[f":refs/heads/{b['name']}" for b in deleting]])
    remaining = remote_refs(plan["repository"])
    require(all("refs/heads/" + b["name"] not in remaining for b in final["branches"]), "A branch was recreated after cleanup; retained for review")
    require(all(remaining.get("refs/tags/" + b["archive"]) == b["sha"] for b in final["branches"]), "Post-cleanup archive verification failed")
    print(f"Archived {len(final['branches'])} branch heads; removed {len(deleting)} obsolete branches; main retained.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("config/release_branch_cleanup_v4.2.0.json"))
    parser.add_argument("--tag", default="v4.2.0")
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--release-run-id", required=True, type=int)
    parser.add_argument("--apply", action="store_true", help="Archive, close approved obsolete PRs, then delete using exact leases")
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        validate_manifest(manifest)
        api = GitHub(manifest["repository"])
        plan = plan_cleanup(manifest, api, tag=args.tag, release_sha=args.release_sha, run_id=args.release_run_id)
        check_remote_plan(plan, remote_refs(plan["repository"]))
        print(json.dumps({"mode": "apply" if args.apply else "plan", **plan}, ensure_ascii=False, indent=2))
        if args.apply:
            apply_cleanup(manifest, api, plan)
        return 0
    except (CleanupRefused, KeyError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"Cleanup refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
