#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd); TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-stability); trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MODULE="$TMP/module"; PUBLIC="$TMP/public"; mkdir -p "$MODULE/common" "$MODULE/config" "$MODULE/logs" "$MODULE/webroot" "$MODULE/system/bin" "$PUBLIC/fonts" "$PUBLIC/emoji" "$PUBLIC/reports"
cp "$ROOT/common/stability.sh" "$MODULE/common/stability.sh"; cp "$ROOT/common/module_status.sh" "$MODULE/common/module_status.sh"; cp "$ROOT/common/v14_switch.sh" "$MODULE/common/v14_switch.sh"; cp "$ROOT/common/v14_mix.sh" "$MODULE/common/v14_mix.sh"; cp "$ROOT/common/font_mix.sh" "$MODULE/common/font_mix.sh"
printf '#!/bin/sh\nprintf '\''{"status":"ok"}\\n'\''\n' > "$MODULE/common/font_manager.sh"; chmod 755 "$MODULE/common"/*
printf 'id=LuoShu\nname=洛书\nversion=v14\nversionCode=14000\nauthor=惜故里丶\ndescription=Android 全局字体管理，当前字体：系统默认字体\n' > "$MODULE/module.prop"; printf 'Alpha\n' > "$MODULE/config/active_font.conf"; printf 'default\n' > "$MODULE/config/active_emoji.conf"
run_stability(){ MODDIR="$MODULE" LUOSHU_PUBLIC_DIR="$PUBLIC" sh "$MODULE/common/stability.sh" "$@"; }
STATUS0=$(run_stability status); printf '%s' "$STATUS0" | grep -q '"fontFiles":0'; printf dummy > "$PUBLIC/fonts/one.ttf"; STATUS1=$(run_stability status); printf '%s' "$STATUS1" | grep -q '"fontFiles":1'
printf '#!/bin/sh\ntouch "%s/manager-called"\nprintf '\''{"status":"ok"}\\n'\''\n' "$TMP" > "$MODULE/common/font_manager.sh"; chmod 755 "$MODULE/common/font_manager.sh"
cat > "$MODULE/config/switch_task.conf" <<'EOT'
task=test-task
state=success
font=Beta
message=字体已准备
started=100
finished=101
EOT
TASK=$(MODDIR="$MODULE" sh "$MODULE/common/v14_switch.sh" status test-task); printf '%s' "$TASK" | grep -q '"state":"success"'; test ! -e "$TMP/manager-called"
cat > "$MODULE/config/font_mix.conf" <<'EOT'
cjk=中文甲
latin=Latin B
digit=DIN C
EOT
printf 'mix\n' > "$MODULE/config/active_font.conf"
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
MIX=$(MODDIR="$MODULE" sh "$MODULE/common/v14_mix.sh" status mix-task); printf '%s' "$MIX" | grep -q '"cjk":"中文甲"'; test ! -e "$TMP/manager-called"; grep -q '当前字体：组合：中文甲 / Latin B / DIN C' "$MODULE/module.prop"
mkdir -p "$MODULE/webroot/fonts" "$MODULE/webroot/emoji"; printf cache > "$MODULE/config/webui_font_list.json"; printf key > "$MODULE/config/webui_font_list.key"; run_stability clear_cache >/dev/null; test ! -e "$MODULE/config/webui_font_list.json"
printf '#!/bin/sh\nprintf '\''{"status":"ok","data":{"fonts":[]}}\\n'\''\n' > "$MODULE/common/font_manager.sh"; chmod 755 "$MODULE/common/font_manager.sh"; run_stability scan_test | grep -q '"status":"ok"'; run_stability report | grep -q '"status":"ok"'
TMP_STAGE="$TMP/stage"; mkdir -p "$TMP_STAGE/webroot"; cp "$ROOT/module.prop" "$TMP_STAGE/module.prop"; cp -R "$ROOT/webroot/." "$TMP_STAGE/webroot/"; sh "$ROOT/scripts/prepare_webui.sh" "$TMP_STAGE/webroot"; grep -q 'environment.js?v=14000' "$TMP_STAGE/webroot/index.html"; grep -q 'v14.js?v=14000' "$TMP_STAGE/webroot/index.html"; ! grep -q 'stability.js?v=' "$TMP_STAGE/webroot/index.html"; ! grep -q 'stability-critical-style' "$TMP_STAGE/webroot/index.html"; echo 'LuoShu v14 stability checks passed.'
