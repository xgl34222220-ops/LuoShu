#!/bin/sh
# Synthetic support diagnostics only; no private device logs and no real mounts.
set -eu
ROOT=$(CDPATH= cd -- "${0%/*}/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT INT TERM
LOG="$TMP/diagnostic.log"
_luoshu_self_log() { printf '%s\n' "$*" >> "$LOG"; }
. "$ROOT/common/mount_self_backend.sh"
set -eu
_luoshu_mount_cmd() { printf 'mount: /private/user-input/font.ttf: Invalid argument\n' >&2; return 32; }
if _luoshu_backend_mount_attempt overlay system-fonts -t overlay fixture; then
    echo 'failed mount was accepted' >&2; exit 1
else
    rc=$?
fi
test "$rc" = 32
grep -q 'stage=overlay component=system-fonts result=failed exitCode=32 errorClass=invalid-argument' "$LOG"
! grep -q 'private\|user-input\|font.ttf' "$LOG"
_luoshu_mount_cmd() { return 0; }
_luoshu_backend_mount_attempt overlay system-fonts -t overlay fixture
grep -q 'stage=overlay component=system-fonts result=mounted' "$LOG"

# Model a payload above the unchanged 256 MiB bound, without allocating it.
mkdir -p "$TMP/source" "$TMP/state"
_luoshu_memory_tree_inventory() { : > "$2"; }
du() { printf '270000\tfixture\n'; }
_luoshu_mount_cmd() { printf 'unexpected-mount\n' >> "$TMP/mounts"; return 0; }
_lsme_mount_list="$TMP/state/mounts.list"
LUOSHU_REQUIRED_PAYLOAD_FILES=1
if _luoshu_overlay_memory_layer "$TMP/source" "$TMP/state/memory" "$TMP/state"; then
    echo 'oversize memory layer was accepted' >&2; exit 1
fi
grep -q 'stage=memory-budget payloadAllocatedKiB=270000 requestedKiB=304774 totalKiB=304774 limitKiB=262144 memAvailableKiB=[0-9]' "$LOG"
grep -q 'stage=memory-budget result=rejected reason=bounded-memory-limit' "$LOG"
test ! -e "$TMP/mounts"
test ! -e "$TMP/state/memory"
echo 'self_mount_backend_diagnostic_test: PASS (redacted errors, exit codes, unchanged memory bound)'
