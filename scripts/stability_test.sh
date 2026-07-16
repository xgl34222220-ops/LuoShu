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
cp "$ROOT/common/module_status.sh" "$MODULE/common/module_status.sh"
cp "$ROOT/common/v14_switch.sh" "$MODULE/common/v14_switch.sh"
printf '#!/bin/sh\nprintf '\''{"status":"ok"}\\n'\''\n' > "$MODULE/common/font_manager.sh"
chmod 755 "$MODULE/common/stability.sh" "$MODULE/common/font_manager.sh" "$MODULE/common/module_status.sh" "$MODULE/common/v14_switch.sh"
printf 'id=LuoShu\nname=洛书\nversion=v14\nversionCode=14000\nauthor=惜故里丶\ndescription=Android 全局字体管理，当前字体：系统默认字体\n' > "$MODULE/module.prop"
printf 'Alpha\n' > "$MODULE/config/active_font.conf"
printf 'default\n' > "$MODULE/config/active_emoji.conf"

run_stability() {
    MODDIR="$MODULE" LUOSHU_PUBLIC_DIR="$PUBLIC" sh "$MODULE/common/stability.sh" "$@"
}

STATUS0=$(run_stability status)
printf '%s' "$STATUS0" | grep -q '"fontFiles":0'
printf '%s' "$STATUS0" | grep -q '"currentFont":"Alpha"'

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

# v14 的任务状态查询必须只读取小型状态文件，不能重新执行字体管理器。
printf '#!/bin/sh\ntouch "%s/manager-called"\nprintf '\''{"status":"ok"}\\n'\''\n' "$TMP" > "$MODULE/common/font_manager.sh"
chmod 755 "$MODULE/common/font_manager.sh"
cat > "$MODULE/config/switch_task.conf" <<'EOF_TASK'
task=test-task
state=success
font=Beta
message=字体已准备
started=100
finished=101
EOF_TASK
TASK_STATUS=$(MODDIR="$MODULE" sh "$MODULE/common/v14_switch.sh" status test-task)
printf '%s' "$TASK_STATUS" | grep -q '"state":"success"'
printf '%s' "$TASK_STATUS" | grep -q '"font":"Beta"'
test ! -e "$TMP/manager-called"
grep -q '^description=Android 全局字体管理，当前字体：Beta$' "$MODULE/module.prop"

mkdir -p "$MODULE/webroot/fonts" "$MODULE/webroot/emoji"
printf cache > "$MODULE/config/webui_font_list.json"
printf key > "$MODULE/config/webui_font_list.key"
run_stability clear_cache >/dev/null
test ! -e "$MODULE/config/webui_font_list.json"
test ! -e "$MODULE/config/webui_font_list.key"

# 扫描测试使用可控管理器返回值。
printf '#!/bin/sh\nprintf '\''{"status":"ok","data":{"fonts":[]}}\\n'\''\n' > "$MODULE/common/font_manager.sh"
chmod 755 "$MODULE/common/font_manager.sh"
SCAN=$(run_stability scan_test)
printf '%s' "$SCAN" | grep -q '"status":"ok"'
run_stability report | grep -q '"status":"ok"'
find "$PUBLIC/reports" -type f -name 'LuoShu-recovery-*.txt' | grep -q .

TMP_STAGE="$TMP/stage"
mkdir -p "$TMP_STAGE/webroot"
cp "$ROOT/module.prop" "$TMP_STAGE/module.prop"
cp -R "$ROOT/webroot/." "$TMP_STAGE/webroot/"
sh "$ROOT/scripts/prepare_webui.sh" "$TMP_STAGE/webroot"
grep -q 'stability.js?v=14000' "$TMP_STAGE/webroot/index.html"
grep -q 'environment.js?v=14000' "$TMP_STAGE/webroot/index.html"
grep -q 'app.js?v=14000' "$TMP_STAGE/webroot/index.html"
grep -q 'v14.js?v=14000' "$TMP_STAGE/webroot/index.html"
grep -q 'v14.css?v=14000' "$TMP_STAGE/webroot/index.html"
grep -q 'style.css?v=14000' "$TMP_STAGE/webroot/index.html"
grep -q 'stability-critical-style' "$TMP_STAGE/webroot/index.html"
grep -q 'v14' "$TMP_STAGE/webroot/index.html"
grep -q '^versionCode=14000$' "$ROOT/module.prop"
! grep -q 'Hybrid Mount' "$TMP_STAGE/webroot/index.html"
! grep -q 'more-advanced' "$TMP_STAGE/webroot/index.html"

echo 'LuoShu v14 stability checks passed.'
