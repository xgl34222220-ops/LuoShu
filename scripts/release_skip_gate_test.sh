#!/bin/sh
# release_skip_gate.sh: a main push whose version is unchanged (tag exists,
# non-release files changed) is skipped successfully; everything else still
# reaches the release job and its own checks.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d "${TMPDIR:-/tmp}/luoshu-release-gate.XXXXXX")
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

fail() {
  printf 'release skip gate regression: %s\n' "$*" >&2
  exit 1
}

REPO="$TMP/repo"
mkdir -p "$REPO/scripts"
cp "$ROOT/scripts/release_skip_gate.sh" "$ROOT/scripts/release_version_policy.py" "$REPO/scripts/"
[ ! -f "$ROOT/config/stable_version_policy.json" ] || { mkdir -p "$REPO/config"; cp "$ROOT/config/stable_version_policy.json" "$REPO/config/"; }
cp "$ROOT/module.prop" "$REPO/module.prop"
git -C "$REPO" init -q
git -C "$REPO" config user.email test@example.invalid
git -C "$REPO" config user.name test
git -C "$REPO" add -A
git -C "$REPO" commit -qm base
TAG=$(python3 "$REPO/scripts/release_version_policy.py" --module "$REPO/module.prop" --field tag --check) || \
  fail 'release_version_policy.py rejected the current module.prop'
git -C "$REPO" tag "$TAG"

gate() { # gate EVENT REF_TYPE REF_NAME -> publish value
  sh "$REPO/scripts/release_skip_gate.sh" "$1" "$2" "$3" HEAD | sed -n 's/^publish=//p'
}

# Tag exists, nothing else changed: republish path stays (publish=true).
[ "$(gate push branch main)" = true ] || fail 'republish of an unchanged tag was skipped'

# The PR #278 situation: a non-version module.prop line changes, version unchanged.
sed -i 's|^actionIcon=.*|actionIcon=branding/other-icon.webp|' "$REPO/module.prop"
grep -q '^actionIcon=branding/other-icon.webp$' "$REPO/module.prop" || printf 'actionIcon=branding/other-icon.webp\n' >> "$REPO/module.prop"
mkdir -p "$REPO/android-app" && printf 'x\n' > "$REPO/android-app/file.txt"
git -C "$REPO" add -A && git -C "$REPO" commit -qm 'icon only'
[ "$(gate push branch main)" = false ] || fail 'unchanged version with an existing tag was not skipped'
sh "$REPO/scripts/release_skip_gate.sh" push branch main HEAD | grep -q '^reason=.*nothing new to sign' || \
  fail 'skip reason missing'

# Other triggers are never skipped by the gate.
[ "$(gate workflow_dispatch branch main)" = true ] || fail 'workflow_dispatch skipped'
[ "$(gate push tag "$TAG")" = true ] || fail 'tag push skipped'
[ "$(gate push branch feature)" = true ] || fail 'non-main push skipped'

# versionCode changed without a version bump: real inconsistency, keep the job.
sed -i 's/^versionCode=.*/versionCode=99999/' "$REPO/module.prop"
git -C "$REPO" commit -qam 'code only'
[ "$(gate push branch main)" = true ] || fail 'versionCode-only change was skipped'

# The workflow wires the gate in front of the untouched release job.
WF="$ROOT/.github/workflows/release.yml"
grep -q 'scripts/release_skip_gate.sh' "$WF" || fail 'release.yml does not run the skip gate'
grep -q "needs.gate.outputs.publish == 'true'" "$WF" || fail 'release job is not gated'

printf 'Release skip gate checks passed.\n'
