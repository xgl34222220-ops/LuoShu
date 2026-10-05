#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-active-state)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
CFG="$MOD/config"
mkdir -p "$CFG" "$MOD/common" "$TMP/public/fonts"
for helper in font_active_state.sh font_manager.sh multiweight_mix_task.sh weighted_mix_task.sh \
    task_scope.sh task_scope.py runtime_paths.sh runtime_paths_lock.py background_task.sh font_switch_lock.sh font_next_transaction.sh; do
    cp "$ROOT/common/$helper" "$MOD/common/$helper"
done
mkdir -p "$MOD/common/legacy_v14_4"
cp "$ROOT/common/legacy_v14_4/font_switch_safe.sh" "$MOD/common/legacy_v14_4/font_switch_safe.sh"
printf 'id=LuoShu\nversion=test\nversionCode=1\n' > "$MOD/module.prop"
HOST_PYTHON=$(python3 -c 'import sys; print(sys.executable)')
export LUOSHU_TASK_SCOPE_PYTHON="$HOST_PYTHON" LUOSHU_RUNTIME_PATHS_PYTHON="$HOST_PYTHON"
unset LUOSHU_TASK_SCOPE_PID LUOSHU_TASK_SCOPE_PIDFILE LUOSHU_TASK_SCOPE_TASK LUOSHU_TASK_SCOPE_TMPDIR
unset LUOSHU_REAL_MODDIR LUOSHU_STATE_DIR LUOSHU_CONFIG_DIR LUOSHU_LOG_DIR LUOSHU_CACHE_DIR
unset LUOSHU_TASKS_DIR LUOSHU_TMP_DIR LUOSHU_BACKUP_DIR LUOSHU_REPORTS_DIR LUOSHU_RUNTIME_PATHS_MODULE
unset LUOSHU_SCOPE_ALLOW_HANDOFF LUOSHU_SCOPE_HANDOFF LUOSHU_SAFE_SWITCH_SCOPED LUOSHU_TASK_SCOPE_RUNNER
MODDIR="$MOD"
MODULE_DIR="$MOD"
export MODDIR MODULE_DIR

printf 'Demo\n' > "$CFG/active_font.conf"
printf 'state=confirmed\nfont=Demo\n' > "$CFG/font-payload-boot.conf"
printf 'system/fonts/Demo.ttf|hash|1234\n' > "$CFG/font-payload-manifest.conf"
printf 'state=verified\nmode=mount-confirmed\nactiveFont=Demo\n' > "$CFG/device-font-load-verification.conf"
printf 'state=mounted\n' > "$CFG/self-mount.conf"

. "$MOD/common/font_active_state.sh"
# Production libraries set +e; assertions must retain the test's fail-fast contract.
set -eu
luoshu_active_payload_verified Demo
if luoshu_active_payload_verified Other; then
    echo 'different font reused verified payload' >&2
    exit 1
fi

# The frozen physical switch core validates its source even when metadata is
# verified. Missing source must fail and still finish both real ownership scopes.
if DIRECT_RESULT=$(MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public" \
    sh "$MOD/common/font_manager.sh" action switch Demo 2>"$TMP/request-cleanup.stderr"); then
    echo 'physical switch unexpectedly reused metadata without a source font' >&2
    exit 1
else
    test "$?" -eq 1
fi
printf '%s\n' "$DIRECT_RESULT" | grep -q '"status":"error"'
printf '%s\n' "$DIRECT_RESULT" | grep -q '字体 Demo 不存在'
"$HOST_PYTHON" - "$MOD/.luoshu-state/tasks" <<'PY'
import json
from pathlib import Path
import sys

tasks = Path(sys.argv[1])
assert len(list(tasks.glob('request-*.pid.cleanup.json'))) == 1
assert len(list(tasks.glob('safe-switch-*.pid.cleanup.json'))) == 1
proofs = list(tasks.glob('*.pid.cleanup.json'))
assert len(proofs) == 2, proofs
for path in proofs:
    proof = json.loads(path.read_text())
    assert proof['cleaned'] and not proof['leftoverPids'] and not proof['cleanupErrors'] and proof['result'] == 1, proof
for pattern in ('*.pid', '*.pid.owner.json', '*.pid.task', '*.pid.boot', '*.pid.start'):
    assert not list(tasks.glob(pattern)), pattern
PY
grep -q '^Demo$' "$CFG/active_font.conf"
test ! -e "$MOD/.luoshu-payload-next"
test ! -e "$CFG/text_reboot_required.conf"

printf 'state=awaiting-explicit-apply\n' > "$CFG/font-payload-rebuild-pending.conf"
if luoshu_active_payload_verified Demo; then
    echo 'schema rebuild marker was ignored' >&2
    exit 1
fi
rm -f "$CFG/font-payload-rebuild-pending.conf"

printf 'font=Demo\n' > "$CFG/text_reboot_required.conf"
if luoshu_active_payload_verified Demo; then
    echo 'same-boot reboot marker was ignored' >&2
    exit 1
fi
rm -f "$CFG/text_reboot_required.conf"

printf 'mix\n' > "$CFG/active_font.conf"
printf 'state=confirmed\nfont=mix\n' > "$CFG/font-payload-boot.conf"
printf 'state=verified\nmode=mount-confirmed\nactiveFont=mix\n' > "$CFG/device-font-load-verification.conf"
cat > "$CFG/font_mix.conf" <<'EOF_MIX'
cjk=CJK
latin=Latin
digit=Digit
cjkWeight=400
latinWeight=500
digitWeight=600
cjkAxes=wght=400
latinAxes=wght=500
digitAxes=wght=600
cjkMode=fixed
latinMode=auto
digitMode=fixed
EOF_MIX
luoshu_mix_request_matches_active CJK Latin Digit wght=400 wght=500 wght=600 fixed auto fixed
if luoshu_mix_request_matches_active CJK Latin Other wght=400 wght=500 wght=600 fixed auto fixed; then
    echo 'different composite request reused active payload' >&2
    exit 1
fi

AUTO_RESULT=$(MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public" \
    sh "$MOD/common/multiweight_mix_task.sh" start CJK Latin Digit \
        wght=400 wght=500 wght=600 fixed auto fixed)
printf '%s\n' "$AUTO_RESULT" | grep -q '"reused":true'
grep -q '^state=success$' "$CFG/axes_task.conf"
grep -q '^percent=100$' "$CFG/axes_task.conf"
grep -q '^reused=true$' "$CFG/axes_task.conf"
AUTO_STATUS=$(MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public" \
    sh "$MOD/common/weighted_mix_task.sh" status "$(sed -n 's/^task=//p' "$CFG/axes_task.conf")")
printf '%s\n' "$AUTO_STATUS" | grep -q '"reused":true'
test ! -e "$CFG/text_reboot_required.conf"

sed -i 's/^latinMode=auto$/latinMode=fixed/' "$CFG/font_mix.conf"
FIXED_RESULT=$(MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public" \
    sh "$MOD/common/weighted_mix_task.sh" start CJK Latin Digit wght=400 wght=500 wght=600)
printf '%s\n' "$FIXED_RESULT" | grep -q '"reused":true'
grep -q '^state=success$' "$CFG/axes_task.conf"
grep -q '^reused=true$' "$CFG/axes_task.conf"
test ! -e "$CFG/text_reboot_required.conf"

sh -n "$ROOT/common/font_active_state.sh"
echo 'Verified metadata guards and identical composites reuse state; physical switch still validates its source and cleans failed requests.'
