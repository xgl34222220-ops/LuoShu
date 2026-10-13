#!/bin/sh
# App bridge "reboot" (首页「立即重启」): a complete reboot that survives the
# App's supervised request. The old bridge backgrounded `svc power reboot`
# and returned; task_scope (a subreaper) then reaped the backgrounded command
# before it reached PowerManager. The reboot must run in the foreground of the
# request, fall back to toybox reboot / sys.powerctl, and report failure.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d "${TMPDIR:-/tmp}/luoshu-bridge-reboot.XXXXXX")
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

fail() {
  printf 'app bridge reboot regression: %s\n' "$*" >&2
  exit 1
}

MODULE="$TMP/module"
mkdir -p "$MODULE/config" "$MODULE/common" "$TMP/bin"
cp "$ROOT/common/app_bridge.sh" "$ROOT/common/task_scope.sh" \
  "$ROOT/common/task_scope.py" "$ROOT/common/runtime_paths.sh" \
  "$ROOT/common/runtime_paths_lock.py" "$MODULE/common/"
HOST_PYTHON=$(python3 -c 'import sys; print(sys.executable)')
export LUOSHU_TASK_SCOPE_PYTHON="$HOST_PYTHON" LUOSHU_RUNTIME_PATHS_PYTHON="$HOST_PYTHON"
unset LUOSHU_TASK_SCOPE_PID
printf 'id=LuoShu\nversion=test\nversionCode=1\n' > "$MODULE/module.prop"

stub() {
  printf '#!/bin/sh\n%s\n' "$2" > "$TMP/bin/$1"
  chmod 0755 "$TMP/bin/$1"
}
PATH="$TMP/bin:$PATH"
export PATH

# 1) svc takes a while (app_process start-up) and must not be reaped when the
#    request is supervised exactly like the App's RootShell request.
stub svc "echo \"svc \$*\" >> '$TMP/calls.log'; sleep 2; echo svc-finished >> '$TMP/calls.log'; exit 0"
stub reboot "echo \"reboot \$*\" >> '$TMP/calls.log'; exit 0"
stub setprop "echo \"setprop \$*\" >> '$TMP/calls.log'; exit 0"
LUOSHU_REBOOT_SETTLE_SECONDS=0 MODDIR="$MODULE" \
  sh "$MODULE/common/task_scope.sh" request-run app-reboot-test 20 -- \
  sh -c "MODDIR='$MODULE' sh '$MODULE/common/app_bridge.sh' reboot" >"$TMP/out1" 2>"$TMP/err1" || true
grep -qx 'svc power reboot' "$TMP/calls.log" || fail "svc power reboot was not invoked: $(cat "$TMP/calls.log" 2>/dev/null)"
grep -qx 'svc-finished' "$TMP/calls.log" || fail 'svc power reboot was reaped before it finished'
[ "$(sed -n '1p' "$TMP/calls.log")" = 'svc power reboot' ] || fail 'svc must be the first reboot path'

# 2) svc unavailable/failing: toybox reboot, then sys.powerctl, then an error.
: > "$TMP/calls.log"
stub svc "echo \"svc \$*\" >> '$TMP/calls.log'; exit 1"
stub reboot "echo \"reboot \$*\" >> '$TMP/calls.log'; exit 1"
stub setprop "echo \"setprop \$*\" >> '$TMP/calls.log'; exit 1"
set +e
out=$(LUOSHU_REBOOT_SETTLE_SECONDS=0 MODDIR="$MODULE" sh "$MODULE/common/app_bridge.sh" reboot 2>/dev/null)
rc=$?
set -e
[ "$rc" -ne 0 ] || fail 'a reboot that never happened must not exit 0'
printf '%s' "$out" | grep -q '"status":"error"' || fail "missing error JSON: $out"
[ "$(tr '\n' '|' < "$TMP/calls.log")" = 'svc power reboot|reboot |setprop sys.powerctl reboot|' ] || \
  fail "unexpected fallback order: $(tr '\n' '|' < "$TMP/calls.log")"

# 3) No soft-restart shortcuts and no backgrounding in either reboot path.
body=$(sed -n '/^full_reboot() {/,/^}/p' "$ROOT/common/app_bridge.sh")
printf '%s' "$body" | grep -q 'svc power reboot' || fail 'full_reboot lost svc power reboot'
if printf '%s' "$body" | grep -Eq 'killall|pkill|ctl\.restart|setprop ctl|stop;|start;|zygote|systemui|&[[:space:]]*$'; then
  fail 'full_reboot must be a complete foreground reboot'
fi
grep -q '^    reboot) full_reboot' "$ROOT/common/app_bridge.sh" || fail 'bridge reboot must use full_reboot'
if sed -n '/reboot_device)/,/;;/p' "$ROOT/common/font_manager_v4.sh" | grep -Eq '&[[:space:]]*$'; then
  fail 'font_manager_v4 reboot_device must not background the reboot'
fi
printf 'app bridge reboot test: ok\n'
