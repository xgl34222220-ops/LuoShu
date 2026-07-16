#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-stability)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE="$TMP/module"
PUBLIC="$TMP/public"
mkdir -p "$MODULE/common" "$MODULE/config" "$MODULE/logs" "$MODULE/webroot" "$MODULE/system/bin" \
         "$PUBLIC/fonts" "$PUBLIC/emoji" "$PUBLIC/reports"
cp "$ROOT/common/stability.sh" "$MODULE/common/stability.sh"
printf '#!/bin/sh\nprintf '\''{"status":"ok"}\\n'\''\n' > "$MODULE/common/font_manager.sh"
chmod 755 "$MODULE/common/stability.sh" "$MODULE/common/font_manager.sh"
printf 'version=v13.6 Beta6\nversionCode=13606\n' > "$MODULE/module.prop"
printf 'Alpha\n' > "$MODULE/config/active_font.conf"
printf 'default\n' > "$MODULE/config/active_emoji.conf"

run_stability() {
    MODDIR="$MODULE" LUOSHU_PUBLIC_DIR="$PUBLIC" sh "$MODULE/common/stability.sh" "$@"
}

FIRST=$(run_stability boot_snapshot)
printf '%s' "$FIRST" | grep -q '"status":"ok"'
STATUS0=$(run_stability status)
printf '%s' "$STATUS0" | grep -q '"fontFiles":0'
printf '%s' "$STATUS0" | grep -q '"snapshotExists":true'
printf '%s' "$STATUS0" | grep -q '"snapshotMatchesCurrent":true'
printf '%s' "$STATUS0" | grep -q '"rollbackAvailable":false'
printf '%s' "$STATUS0" | grep -q '"snapshotSavedAt":'

printf 'dummy' > "$PUBLIC/fonts/one.ttf"
STATUS1=$(run_stability status)
printf '%s' "$STATUS1" | grep -q '"fontFiles":1'

index=2
while [ "$index" -le 20 ]; do
    printf 'dummy' > "$PUBLIC/fonts/font-${index}.otf"
    index=$((index + 1))
done
STATUS20=$(run_stability status)
printf '%s' "$STATUS20" | grep -q '"fontFiles":20'

printf 'Beta\n' > "$MODULE/config/active_font.conf"
PENDING=$(run_stability status)
printf '%s' "$PENDING" | grep -q '"snapshotMatchesCurrent":false'

SECOND=$(run_stability save_snapshot)
printf '%s' "$SECOND" | grep -q '"status":"ok"'
ROTATED=$(run_stability status)
printf '%s' "$ROTATED" | grep -q '"currentFont":"Beta"'
printf '%s' "$ROTATED" | grep -q '"snapshotFont":"Beta"'
printf '%s' "$ROTATED" | grep -q '"previousFont":"Alpha"'
printf '%s' "$ROTATED" | grep -q '"snapshotMatchesCurrent":true'
printf '%s' "$ROTATED" | grep -q '"rollbackAvailable":true'
printf '%s' "$ROTATED" | grep -q '"previousSavedAt":'

printf 'Gamma\n' > "$MODULE/config/active_font.conf"
THIRD=$(run_stability boot_snapshot)
printf '%s' "$THIRD" | grep -q '"status":"ok"'
BOOT_ROTATED=$(run_stability status)
printf '%s' "$BOOT_ROTATED" | grep -q '"snapshotFont":"Gamma"'
printf '%s' "$BOOT_ROTATED" | grep -q '"previousFont":"Beta"'
run_stability rollback | grep -q '"status":"ok"'

mkdir -p "$MODULE/webroot/fonts" "$MODULE/webroot/emoji"
printf cache > "$MODULE/config/webui_font_list.json"
printf key > "$MODULE/config/webui_font_list.key"
run_stability clear_cache >/dev/null
test ! -e "$MODULE/config/webui_font_list.json"
test ! -e "$MODULE/config/webui_font_list.key"

SCAN=$(run_stability scan_test)
printf '%s' "$SCAN" | grep -q '"status":"ok"'
run_stability report | grep -q '"status":"ok"'
find "$PUBLIC/reports" -type f -name 'LuoShu-recovery-*.txt' | grep -q .

TMP_STAGE="$TMP/stage"
mkdir -p "$TMP_STAGE/webroot"
cp "$ROOT/module.prop" "$TMP_STAGE/module.prop"
cp -R "$ROOT/webroot/." "$TMP_STAGE/webroot/"
sh "$ROOT/scripts/prepare_webui.sh" "$TMP_STAGE/webroot"
grep -q 'stability.js?v=13606' "$TMP_STAGE/webroot/index.html"
grep -q 'app.js?v=13606' "$TMP_STAGE/webroot/index.html"
grep -q 'style.css?v=13606' "$TMP_STAGE/webroot/index.html"
grep -q 'stability-critical-style' "$TMP_STAGE/webroot/index.html"
grep -q 'v13.6 Beta6' "$TMP_STAGE/webroot/index.html"
grep -q '^versionCode=13606$' "$ROOT/module.prop"
grep -q 'data-stability-action="snapshot"' "$TMP_STAGE/webroot/stability.js"
grep -q 'save_snapshot' "$ROOT/common/stability.sh"

echo 'LuoShu stability checks passed.'
