#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-stability)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE="$TMP/module"
mkdir -p "$MODULE/common" "$MODULE/config" "$MODULE/webroot"
cp "$ROOT/common/module_status.sh" "$MODULE/common/module_status.sh"
cp "$ROOT/common/v14_switch.sh" "$MODULE/common/v14_switch.sh"
cp "$ROOT/common/v14_mix.sh" "$MODULE/common/v14_mix.sh"
cp "$ROOT/common/font_mix.sh" "$MODULE/common/font_mix.sh"
cp "$ROOT/module.prop" "$MODULE/module.prop"

# 状态查询不得触发真正的字体切换。
printf '#!/bin/sh\ntouch "%s/manager-called"\nprintf '\''{"status":"ok"}\\n'\''\n' "$TMP" > "$MODULE/common/font_manager.sh"
chmod 0755 "$MODULE/common"/*
cat > "$MODULE/config/switch_task.conf" <<'EOT'
task=test-task
state=success
font=Beta
message=字体已准备
started=100
finished=101
EOT
TASK=$(MODDIR="$MODULE" sh "$MODULE/common/v14_switch.sh" status test-task)
printf '%s' "$TASK" | grep -q '"state":"success"'
test ! -e "$TMP/manager-called"
grep -q '当前字体：Beta' "$MODULE/module.prop"

# 当完整多轴引擎不可用时，组合桥仍应正确返回历史任务状态。
cat > "$MODULE/config/font_mix.conf" <<'EOT'
cjk=中文甲
latin=Latin B
digit=DIN C
EOT
cat > "$MODULE/config/mix_task.conf" <<'EOT'
task=mix-task
state=success
message=字体组合已准备
cjk=中文甲
latin=Latin B
digit=DIN C
started=100
finished=101
EOT
MIX=$(MODDIR="$MODULE" sh "$MODULE/common/v14_mix.sh" status mix-task)
printf '%s' "$MIX" | grep -q '"cjk":"中文甲"'
test ! -e "$TMP/manager-called"
grep -q '当前字体：组合：中文甲 / Latin B / DIN C' "$MODULE/module.prop"

# WebUI 缓存键必须始终跟随 module.prop 的唯一 versionCode。
TMP_STAGE="$TMP/stage"
mkdir -p "$TMP_STAGE/webroot"
cp "$ROOT/module.prop" "$TMP_STAGE/module.prop"
cp -R "$ROOT/webroot/." "$TMP_STAGE/webroot/"
sh "$ROOT/scripts/prepare_webui.sh" "$TMP_STAGE/webroot"
CACHE=$(sed -n 's/^versionCode=//p' "$ROOT/module.prop" | head -n1)
grep -q "environment.js?v=$CACHE" "$TMP_STAGE/webroot/index.html"
grep -q "v14.js?v=$CACHE" "$TMP_STAGE/webroot/index.html"
grep -q "UI_VERSION = '$CACHE'" "$TMP_STAGE/webroot/environment.js"
! grep -q 'stability.js?v=' "$TMP_STAGE/webroot/index.html"
! grep -q 'stability-critical-style' "$TMP_STAGE/webroot/index.html"

echo 'LuoShu stability checks passed.'
