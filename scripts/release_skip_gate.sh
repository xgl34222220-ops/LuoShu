#!/bin/sh
# Decide whether "Publish signed release" has anything to publish.
#
# Any module.prop change on main triggers the release workflow (for example a
# new actionIcon= line). When the version did not change, its tag already
# exists and main differs from that tag by non-release files, there is nothing
# new to sign: the run must finish successfully and say so, instead of failing
# the "Read and verify release version" step with exit 2.
#
# Prints publish=true|false and reason=<text>. Only that one situation skips;
# every other case keeps publish=true so the release job's own checks still
# reject genuinely inconsistent states (tag not an ancestor, versionCode
# changed without a version bump, tag pushes, workflow_dispatch, ...).
#
# Usage: release_skip_gate.sh EVENT_NAME REF_TYPE REF_NAME SHA
set -eu
EVENT="${1:-}"
REF_TYPE="${2:-}"
REF_NAME="${3:-}"
SHA="${4:-HEAD}"
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

emit() {
    printf 'publish=%s\n' "$1"
    printf 'reason=%s\n' "$2"
    exit 0
}

[ "$EVENT" = push ] && [ "$REF_TYPE" = branch ] && [ "$REF_NAME" = main ] || \
    emit true "not a main branch push"

prop_at() { # prop_at REV KEY
    git -C "$ROOT" show "$1:module.prop" 2>/dev/null | sed -n "s/^$2=//p" | head -n1 | tr -d '\r'
}

version=$(prop_at "$SHA" version)
code=$(prop_at "$SHA" versionCode)
[ -n "$version" ] || emit true "module.prop version unreadable"
tag=$(python3 "$ROOT/scripts/release_version_policy.py" --module "$ROOT/module.prop" --field tag --check 2>/dev/null) || \
    emit true "release tag policy rejected module.prop"
tag_sha=$(git -C "$ROOT" rev-list -n1 "$tag" 2>/dev/null || true)
[ -n "$tag_sha" ] || emit true "tag $tag does not exist yet (new version)"
git -C "$ROOT" merge-base --is-ancestor "$tag_sha" "$SHA" 2>/dev/null || \
    emit true "tag $tag is not an ancestor of main"
[ "$(prop_at "$tag_sha" version)" = "$version" ] && [ "$(prop_at "$tag_sha" versionCode)" = "$code" ] || \
    emit true "version or versionCode differs from tag $tag"
changes=$(git -C "$ROOT" diff --name-only "$tag_sha" "$SHA" -- | \
    grep -Ev '^(RELEASE_NOTES_.*\.md|\.github/workflows/release\.yml)$' || true)
[ -n "$changes" ] || emit true "only release files changed since $tag (republish)"
emit false "version $version (versionCode $code) unchanged and tag $tag already published; nothing new to sign"
