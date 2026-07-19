#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-stability)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE="$TMP/module"
mkdir -p "$MODULE/common" "$MODULE/config"
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

# 原生 App 字体管理器必须使用原生索引，且不再携带 WebUI 预览、热刷新或回滚入口。
grep -q 'native_font_index.json' "$ROOT/common/font_manager.sh"
grep -q 'native_font_index.key' "$ROOT/common/font_manager.sh"
! grep -qE 'webroot|sync_preview_fonts|restart_ui|previous_font\.conf' "$ROOT/common/font_manager.sh"
! grep -qE '重启界面|刷新字体缓存|回滚' "$ROOT/common/luoshu_cli.sh"
test ! -d "$ROOT/webroot"
test ! -e "$ROOT/scripts/prepare_webui.sh"

# 单包内置 App 安装器必须正确处理当前版本、覆盖更新、延迟安装和签名失败。
sh "$ROOT/scripts/app_installer_test.sh"

# 原生 App 字体索引只在文件集合实际变化时失效。
sh "$ROOT/scripts/font_library_cache_test.sh"

echo 'LuoShu App-only stability checks passed.'
