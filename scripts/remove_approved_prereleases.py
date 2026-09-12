#!/usr/bin/env python3
"""Remove the five explicitly approved prereleases, keeping stable releases/tags.

The default invocation only reads the API and prints the fixed deletion plan.
--apply rechecks each release immediately before deleting its release record and
assets. No tag, branch or stable release API can be mutated by this script.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPOSITORY = "xgl34222220-ops/LuoShu"
APPROVED = {
    387499938: "v4.2.3-RC1",
    387482281: "v4.2.2-RC1",
    387468654: "v4.2.1-RC1",
    370614535: "v2.4.1-Beta-1",
    359987560: "v2.3.5-Alpha5",
}


class CleanupRefused(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CleanupRefused(message)


def validate_manifest(manifest: dict) -> list[dict]:
    require(manifest.get("schema") == 1, "Unsupported cleanup manifest")
    require(manifest.get("repository") == REPOSITORY, "Cleanup repository mismatch")
    require(manifest.get("scope") == "remove-approved-prereleases-preserve-stable-and-tags", "Cleanup scope mismatch")
    items = manifest.get("releases", [])
    require(isinstance(items, list) and len(items) == len(APPROVED), "The five approved releases must be listed exactly once")
    require(all(isinstance(item, dict) and type(item.get("id")) is int for item in items), "Invalid release ID")
    require({item["id"]: item.get("tag") for item in items} == APPROVED, "Release ID/tag scope differs from the reviewed authorization")
    return items


class GitHub:
    def __init__(self, token: str):
        self.root = f"https://api.github.com/repos/{REPOSITORY}"
        self.token = token

    def request(self, suffix: str, method: str = "GET"):
        # Keep mutation endpoints fixed even if a future caller passes bad input.
        if method != "GET":
            require(method == "DELETE" and suffix in {f"/releases/{key}" for key in APPROVED}, "Mutation outside approved release IDs")
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "LuoShu-approved-prerelease-cleanup"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(self.root + suffix, headers=headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                data = response.read()
                if method == "DELETE":
                    require(response.status == 204, "Release deletion did not return HTTP 204")
                    return None
                return json.loads(data)
        except HTTPError as exc:
            if method == "GET" and exc.code == 404 and suffix.startswith("/releases/") and "?" not in suffix:
                return None
            # Do not print the request, response body or token-bearing headers.
            raise CleanupRefused(f"GitHub {method} failed (HTTP {exc.code})") from None
        except URLError:
            raise CleanupRefused(f"GitHub {method} could not complete; rerun to recheck remote state") from None

    def get(self, suffix: str):
        return self.request(suffix)

    def listing(self) -> list[dict]:
        result = []
        for page in range(1, 101):
            items = self.get(f"/releases?per_page=100&page={page}")
            require(isinstance(items, list), "Invalid release listing response")
            result.extend(items)
            if len(items) < 100:
                return result
        raise CleanupRefused("Release listing exceeded pagination limit")

    def delete(self, release_id: int) -> None:
        require(release_id in APPROVED, "Unapproved release ID")
        self.request(f"/releases/{release_id}", "DELETE")


def check_release(item: dict, remote: dict | None) -> bool:
    if remote is None:
        return False
    require(remote.get("id") == item["id"] and remote.get("tag_name") == item["tag"], f"Release identity changed: {item['tag']}")
    require(remote.get("prerelease") is True and remote.get("draft") is False, f"Retaining release that is no longer a published prerelease: {item['tag']}")
    return True


def verify_listing(releases: list[dict]) -> None:
    for release in releases:
        require(isinstance(release, dict), "Invalid release entry")
        if release.get("prerelease") is True:
            require(APPROVED.get(release.get("id")) == release.get("tag_name"), "An unreviewed prerelease appeared; refresh the approved scope before cleanup")
        if release.get("id") in APPROVED:
            check_release({"id": release["id"], "tag": APPROVED[release["id"]]}, release)


def cleanup(manifest: dict, api: GitHub, *, apply: bool) -> dict:
    items = validate_manifest(manifest)
    repository = api.get("")
    require(repository.get("full_name") == REPOSITORY and repository.get("default_branch") == "main", "Repository/default branch mismatch")
    before = api.listing()
    verify_listing(before)
    stable = {release["id"]: release["tag_name"] for release in before if release.get("prerelease") is False}
    present = []
    absent = []
    # Complete the full preflight before the first destructive request.
    for item in items:
        if check_release(item, api.get(f"/releases/{item['id']}")):
            present.append(item)
        else:
            absent.append(item["tag"])
    plan = {"repository": REPOSITORY, "mode": "apply" if apply else "plan", "remove": present, "already_absent": absent, "stable_release_count": len(stable), "tags": "retained"}
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if not apply:
        return plan
    removed = []
    for item in present:
        if not check_release(item, api.get(f"/releases/{item['id']}")):
            continue  # Another run already removed it; never recreate or retarget.
        api.delete(item["id"])
        require(api.get(f"/releases/{item['id']}") is None, f"Release still exists after deletion: {item['tag']}")
        removed.append(item["tag"])
        print(f"Removed prerelease: {item['tag']}")
    after = api.listing()
    verify_listing(after)
    require(not any(item.get("prerelease") is True for item in after), "A prerelease remains; do not expand deletion automatically")
    stable_after = {release["id"]: release["tag_name"] for release in after if release.get("prerelease") is False}
    require(all(stable_after.get(release_id) == tag for release_id, tag in stable.items()), "Stable release state changed during cleanup; review remote state")
    print(f"Verified: {len(removed)} prereleases removed; {len(stable)} existing stable releases retained; all tags retained.")
    return {**plan, "removed": removed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("config/prerelease_cleanup_2026-09-12.json"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        token = os.environ.get("GH_TOKEN", "")
        require(not args.apply or bool(token), "GH_TOKEN is required to apply cleanup")
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        cleanup(manifest, GitHub(token), apply=args.apply)
        return 0
    except (CleanupRefused, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(f"Cleanup stopped: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
