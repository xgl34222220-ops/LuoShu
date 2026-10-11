#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT INT TERM

MODULES="$TMP/modules"
MODULES_UPDATE="$TMP/modules_update"
META_MNT="$TMP/metamodule/mnt"
CONTENT_BASE="$TMP/content"
MAGIC_CONFIG="$TMP/magic_mount/config.toml"
SELF_STATE="$TMP/luoshu/self-mount"
PRIVATE_STATE="$TMP/luoshu/private-payload"
MODDIR="$MODULES/LuoShu"

mkdir -p \
  "$MODDIR/logs" "$MODDIR/config" "$MODDIR/common" "$MODDIR/.luoshu-runtime/compat/v227" \
  "$MODULES/OtherModule" "$MODULES_UPDATE/LuoShu/system/fonts" \
  "$META_MNT/LuoShu/product/fonts" "$CONTENT_BASE/LuoShu/system/fonts" \
  "$SELF_STATE/lower/system-fonts" "$PRIVATE_STATE" "${MAGIC_CONFIG%/*}"

cp "$ROOT/uninstall.sh" "$MODDIR/uninstall.sh"
cp "$ROOT/common/private_payload.sh" "$MODDIR/common/private_payload.sh"
cp "$ROOT/.luoshu-runtime/compat/v227/uninstall.sh" "$MODDIR/.luoshu-runtime/compat/v227/uninstall.sh"
printf '%s\n' 'version=v-test' > "$MODDIR/module.prop"
printf '%s\n' 'old log' > "$MODDIR/logs/fontswitch.log"
printf '%s\n' 'keep sibling' > "$MODULES/OtherModule/module.prop"
printf '%s\n' 'partitions = ["system", "product"]' > "$MAGIC_CONFIG"
printf '%s\n' 'backup' > "$MAGIC_CONFIG.luoshu.bak"
printf '%s\n' '999999' > "$MAGIC_CONFIG.luoshu.lock"
printf '%s\n' 'temp' > "$MAGIC_CONFIG.luoshu.123"
printf '%s\n' "$SELF_STATE/lower/system-fonts" '/system/fonts' > "$SELF_STATE/mounts.list"
: > "$PRIVATE_STATE/module-view.mounts"

# A failed Google restore (pm unavailable early in boot) must never abort the
# cleanup: the manager deletes MODDIR regardless. The undo record stays outside
# the module and a self-contained one-shot restore is scheduled in service.d.
UNDO_FILE="$TMP/google-font-fallback/user-2.json"
SERVICE_D="$TMP/service.d"
BIN="$TMP/bin"
mkdir -p "${UNDO_FILE%/*}" "$MODDIR/common/python/bin" "$BIN"
chmod 0700 "${UNDO_FILE%/*}"
printf '%s\n' 'owned undo fixture' > "$UNDO_FILE"
printf '%s\n' 'restore executor fixture' > "$MODDIR/common/python/bin/luoshu-python"
chmod 0755 "$MODDIR/common/python/bin/luoshu-python"
cp "$ROOT/common/google_font_deferred_restore.sh" "$MODDIR/common/google_font_deferred_restore.sh"
printf '#!/bin/sh\nprintf "%%s\\n" "${TEST_BOOT_COMPLETED:-0}"\n' > "$BIN/getprop"
chmod 0755 "$BIN/getprop"
cat > "$MODDIR/common/google_font_fallback.sh" <<'EOF_GOOGLE'
#!/bin/sh
[ "$#" = 2 ] && [ "$1" = restore-owned ] && [ "$2" = --json ] || exit 98
printf '%s\n' "$*" >> "$TEST_GOOGLE_RESTORE_LOG"
[ "${TEST_GOOGLE_RESTORE_RC:-0}" = 0 ] || exit 1
rm -f "$TEST_GOOGLE_UNDO_FILE"
EOF_GOOGLE
PATH="$BIN:$PATH" TEST_BOOT_COMPLETED=1 \
TEST_GOOGLE_RESTORE_RC=1 TEST_GOOGLE_UNDO_FILE="$UNDO_FILE" \
TEST_GOOGLE_RESTORE_LOG="$TMP/google-restore.log" \
LUOSHU_GOOGLE_FALLBACK_STORE="${UNDO_FILE%/*}" \
LUOSHU_GOOGLE_FALLBACK_LEGACY_STORE="$TMP/legacy-google-font-fallback" \
LUOSHU_SERVICE_D="$SERVICE_D" \
LUOSHU_MODULES_DIR="$MODULES" \
LUOSHU_MODULES_UPDATE_DIR="$MODULES_UPDATE" \
LUOSHU_METAMODULE_MNT="$META_MNT" \
LUOSHU_MAGIC_MOUNT_CONFIG="$MAGIC_CONFIG" \
LUOSHU_SELF_MOUNT_STATE="$SELF_STATE" \
LUOSHU_PRIVATE_STATE_ROOT="$PRIVATE_STATE" \
MODULE_CONTENT_DIR="$CONTENT_BASE" \
sh "$MODDIR/uninstall.sh" > "$TMP/google-failure.log" 2>&1

grep -qx 'restore-owned --json' "$TMP/google-restore.log"
grep -q '开机完成后自动恢复' "$TMP/google-failure.log"
[ "$(cat "$UNDO_FILE")" = 'owned undo fixture' ]
[ -x "$SERVICE_D/luoshu-uninstall-restore.sh" ]
cmp -s "$ROOT/common/google_font_deferred_restore.sh" "$SERVICE_D/luoshu-uninstall-restore.sh"
[ ! -e "$PRIVATE_STATE" ]
[ ! -e "$MODDIR" ]
[ ! -e "$MODULES_UPDATE/LuoShu" ]
[ ! -e "$META_MNT/LuoShu" ]
[ ! -e "$CONTENT_BASE/LuoShu" ]
[ ! -e "$SELF_STATE" ]
[ -f "$MODULES/OtherModule/module.prop" ]
[ -f "$MAGIC_CONFIG" ]
[ ! -e "$MAGIC_CONFIG.luoshu.bak" ]
[ ! -e "$MAGIC_CONFIG.luoshu.lock" ]
[ ! -e "$MAGIC_CONFIG.luoshu.123" ]
grep -q 'partitions = \["system", "product"\]' "$MAGIC_CONFIG"
[ ! -d "$MODULES/LuoShu/logs" ]
echo 'LuoShu uninstall cleanup checks passed.'
