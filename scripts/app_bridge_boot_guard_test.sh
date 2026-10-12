#!/bin/sh
# App bridge: (1) refuses to stage a new payload while boot-loop safe mode is
# active (the frozen post-fs-data would activate it before the guard runs);
# (2) reports a "degraded" self-mount with failed components as partial,
# never as verified.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d "${TMPDIR:-/tmp}/luoshu-bridge-guard.XXXXXX")
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

fail() {
  printf 'app bridge boot guard regression: %s\n' "$*" >&2
  exit 1
}

MODULE="$TMP/module"
CONFIG="$MODULE/config"
mkdir -p "$CONFIG" "$MODULE/common"
cp "$ROOT/common/app_bridge.sh" "$ROOT/common/task_scope.sh" \
  "$ROOT/common/task_scope.py" "$ROOT/common/runtime_paths.sh" \
  "$ROOT/common/runtime_paths_lock.py" "$ROOT/common/boot_loop_guard.sh" "$MODULE/common/"
HOST_PYTHON=$(python3 -c 'import sys; print(sys.executable)')
export LUOSHU_TASK_SCOPE_PYTHON="$HOST_PYTHON" LUOSHU_RUNTIME_PATHS_PYTHON="$HOST_PYTHON"
unset LUOSHU_TASK_SCOPE_PID
printf 'id=LuoShu\nversion=test\nversionCode=1\n' > "$MODULE/module.prop"
for controller in font_switch_task.sh font_mix_controller.sh; do
  printf '#!/bin/sh\nprintf "%%s %%s\\n" "%s" "$*" >> "%s"\nprintf "{\\"status\\":\\"ok\\",\\"data\\":{\\"task\\":\\"t1\\"}}\\n"\n' \
    "$controller" "$TMP/controller.log" > "$MODULE/common/$controller"
done
bridge() { MODDIR="$MODULE" sh "$MODULE/common/app_bridge.sh" "$@" 2>>"$TMP/stderr.log"; }
json_field() { python3 -c 'import json,sys; print(json.load(sys.stdin).get(sys.argv[1], ""))' "$1"; }

# Normal mode: staging is allowed.
printf 'Demo\n' > "$CONFIG/active_font.conf"
out=$(bridge switch_start Demo)
[ "$(printf '%s' "$out" | json_field status)" = ok ] || fail "normal switch_start refused: $out"
grep -q '^font_switch_task.sh start Demo$' "$TMP/controller.log" || fail 'normal switch did not reach the task'

# Safe mode: a new font or a composite is refused before anything is staged.
: > "$TMP/controller.log"
printf 'state=safe-mode\n' > "$CONFIG/boot-loop-safe-mode.conf"
out=$(bridge switch_start Other)
[ "$(printf '%s' "$out" | json_field status)" = error ] || fail "safe mode switch_start not refused: $out"
[ "$(printf '%s' "$out" | json_field code)" = boot-guard-safe-mode ] || fail "safe mode refusal code missing: $out"
printf '%s' "$out" | grep -q '卡开机保护' || fail 'safe mode refusal message missing'
out=$(bridge mix_start cjk latin digit)
[ "$(printf '%s' "$out" | json_field code)" = boot-guard-safe-mode ] || fail "safe mode mix_start not refused: $out"
[ ! -s "$TMP/controller.log" ] || fail "a controller ran in safe mode: $(cat "$TMP/controller.log")"
# Restoring the system default stays possible.
out=$(bridge switch_start default)
[ "$(printf '%s' "$out" | json_field status)" = ok ] || fail "default restore refused in safe mode: $out"
grep -q '^font_switch_task.sh start default$' "$TMP/controller.log" || fail 'default restore did not reach the task'
# After re-enable, staging works again.
bridge boot_guard_reset >/dev/null
: > "$TMP/controller.log"
out=$(bridge switch_start Other)
[ "$(printf '%s' "$out" | json_field status)" = ok ] || fail "switch refused after re-enable: $out"

# Degraded self-mount with failed components: partial, not verified.
rm -f "$MODULE/common/font_switch_task.sh" "$MODULE/common/font_mix_controller.sh"
status_of() {
  bridge status | python3 -c '
import json, sys
d = json.load(sys.stdin)["data"]
print(d["fontEffectState"], d["effectiveActive"], d["verificationReason"] or "-")'
}
printf 'state=verified\nmode=mount-confirmed\nreason=physical-self-mount-active\nactiveFont=Demo\n' \
  > "$CONFIG/device-font-load-verification.conf"
printf 'Demo\n' > "$CONFIG/active_font.conf"
printf 'state=degraded\nbackend=self-overlay-bind\nmounted=system/fonts\nfailed=product/fonts\n' > "$CONFIG/self-mount.conf"
[ "$(status_of)" = 'partial Demo self-mount-degraded' ] || fail "degraded with failures reported as: $(status_of)"
# Degraded only because a bind fallback was used (nothing failed): complete.
printf 'state=degraded\nbackend=self-overlay-bind\nmounted=system/fonts:bind\nfailed=\n' > "$CONFIG/self-mount.conf"
[ "$(status_of)" = 'verified Demo physical-self-mount-active' ] || fail "bind-only degraded reported as: $(status_of)"
printf 'state=mounted\nbackend=self-overlay\n' > "$CONFIG/self-mount.conf"
[ "$(status_of)" = 'verified Demo physical-self-mount-active' ] || fail "mounted reported as: $(status_of)"

# The Root manager description says the same.
cp "$ROOT/common/module_status.sh" "$MODULE/common/"
printf 'id=LuoShu\nversion=test\nversionCode=1\ndescription=x\n' > "$MODULE/module.prop"
printf 'state=degraded\nbackend=self-overlay-bind\nmounted=system/fonts\nfailed=product/fonts\n' > "$CONFIG/self-mount.conf"
MODDIR="$MODULE" sh "$MODULE/common/module_status.sh" Demo >/dev/null 2>&1 || true
grep -q '^description=.*Demo（部分生效）' "$MODULE/module.prop" || fail "module description: $(grep '^description=' "$MODULE/module.prop")"
printf 'state=mounted\nbackend=self-overlay\n' > "$CONFIG/self-mount.conf"
MODDIR="$MODULE" sh "$MODULE/common/module_status.sh" Demo >/dev/null 2>&1 || true
! grep -q '部分生效' "$MODULE/module.prop" || fail 'complete mount still described as partial'

printf 'App bridge boot guard and partial-mount checks passed.\n'
