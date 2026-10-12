#!/bin/sh
# Uninstall must never stop half-way:
#   1. a task that cannot be reaped is logged, and the full v2.2.7 cleanup
#      (self-mount state, metamodule mirror, modules_update copy) still runs;
#   2. the pinned v2.2.7 cleanup falls back to font_weight_adjustment=0 when no
#      original was recorded; font_settings_policy.sh (sourced first by
#      uninstall.sh) must keep refusing that write in every case, so the
#      user's own global weight is never overwritten.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d "${TMPDIR:-/tmp}/luoshu-uninstall-resilience.XXXXXX")
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

fail() {
  printf 'uninstall resilience regression: %s\n' "$*" >&2
  exit 1
}

BIN="$TMP/bin"
mkdir -p "$BIN"
# settings: "get" prints FIXTURE_WEIGHT, "put" is logged.
cat > "$BIN/settings" <<'EOF'
#!/bin/sh
[ "${1:-}" = --user ] && shift 2
case "${1:-}" in
  get) printf '%s\n' "${FIXTURE_WEIGHT:-null}" ;;
  put) printf '%s=%s\n' "$3" "$4" >> "$FIXTURE_SETTINGS_LOG" ;;
esac
exit 0
EOF
chmod 0755 "$BIN/settings"

setup_case() { # setup_case NAME
  CASE="$TMP/$1"
  MOD="$CASE/modules/LuoShu"
  mkdir -p "$MOD/common" "$MOD/config" "$MOD/.luoshu-runtime/compat/v227"
  cp "$ROOT/uninstall.sh" "$MOD/uninstall.sh"
  cp "$ROOT/.luoshu-runtime/compat/v227/uninstall.sh" "$MOD/.luoshu-runtime/compat/v227/uninstall.sh"
  printf 'id=LuoShu\nversion=v3.0.0-test\n' > "$MOD/module.prop"
  mkdir -p "$CASE/metamodule/LuoShu/system/fonts" "$CASE/modules_update/LuoShu" "$CASE/luoshu/self-mount"
  printf 'font\n' > "$CASE/metamodule/LuoShu/system/fonts/Roboto-Regular.ttf"
  printf 'state=mounted\n' > "$CASE/luoshu/self-mount/state.conf"
  : > "$CASE/settings.log"
}

run_case() {
  PATH="$BIN:$PATH" \
  FIXTURE_SETTINGS_LOG="$CASE/settings.log" \
  LUOSHU_MODULES_DIR="$CASE/modules" \
  LUOSHU_MODULES_UPDATE_DIR="$CASE/modules_update" \
  LUOSHU_METAMODULE_MNT="$CASE/metamodule" \
  LUOSHU_SELF_MOUNT_STATE="$CASE/luoshu/self-mount" \
  LUOSHU_PRIVATE_STATE_ROOT="$CASE/luoshu/private-payload" \
  LUOSHU_GOOGLE_FALLBACK_STORE="$CASE/none" \
  LUOSHU_GOOGLE_FALLBACK_LEGACY_STORE="$CASE/none-legacy" \
    sh "$MOD/uninstall.sh" > "$CASE/out.log" 2>&1
}

# 1. Task stop fails: no early exit, full cleanup.
setup_case stuck-task
cat > "$MOD/common/background_task.sh" <<'EOF'
luoshu_stop_module_tasks() { return 1; }
EOF
FIXTURE_WEIGHT=0 run_case || { cat "$CASE/out.log" >&2; fail 'uninstall returned non-zero when a task could not be reaped'; }
grep -q '未全部回收' "$CASE/out.log" || fail 'task stop failure was not reported'
[ ! -e "$CASE/metamodule/LuoShu" ] || fail 'metamodule mirror left behind after a task stop failure'
[ ! -e "$CASE/modules_update/LuoShu" ] || fail 'modules_update copy left behind after a task stop failure'
[ ! -e "$CASE/luoshu/self-mount" ] || fail 'self-mount state left behind after a task stop failure'
[ ! -e "$MOD" ] || fail 'module directory left behind after a task stop failure'
! grep -q '^[[:space:]]*exit 1' "$ROOT/uninstall.sh" || fail 'uninstall.sh still aborts with exit 1'

# 2. font_weight_adjustment is never written by uninstall (recorded or not).
for variant in none recorded luoshu-only; do
  setup_case "weight-$variant"
  case "$variant" in
    recorded) printf 'adjustment=40\n' > "$MOD/config/font_weight_original.conf"
              printf 'adjustment=120\n' > "$MOD/config/font_weight.conf" ;;
    luoshu-only) printf 'adjustment=120\n' > "$MOD/config/font_weight.conf" ;;
  esac
  cp "$ROOT/common/font_settings_policy.sh" "$MOD/common/font_settings_policy.sh"
  FIXTURE_WEIGHT=25 run_case || { cat "$CASE/out.log" >&2; fail "uninstall failed (weight $variant)"; }
  ! grep -q '^font_weight_adjustment=' "$CASE/settings.log" || \
    fail "uninstall wrote font_weight_adjustment ($variant): $(cat "$CASE/settings.log")"
done
grep -q 'font_settings_policy.sh' "$ROOT/uninstall.sh" || fail 'uninstall.sh no longer loads the settings policy'
[ "$(grep -n 'font_settings_policy.sh' "$ROOT/uninstall.sh" | head -n1 | cut -d: -f1)" -lt \
  "$(grep -n 'compat/v227/uninstall.sh' "$ROOT/uninstall.sh" | tail -n1 | cut -d: -f1)" ] || \
  fail 'settings policy must be loaded before the v2.2.7 cleanup'

printf 'Uninstall resilience checks passed.\n'
