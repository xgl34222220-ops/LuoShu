#!/bin/sh
set -eu

STAGE="$1"
CUSTOMIZE="$STAGE/customize.sh"
PROP="$STAGE/module.prop"

test -f "$CUSTOMIZE"
test -f "$PROP"
test -f "$STAGE/common/module_status.sh"
test -f "$STAGE/common/v14_switch.sh"

# 安装界面使用正式版名称，不再展示旧测试版本。
sed -i -E 's/v13\.5 Stable Hotfix3/v14/g; s/文字与 Emoji 独立管理/Android 全局字体管理/g' "$CUSTOMIZE"

# 安装结束前写入简洁模块说明，并确保新增脚本权限正常。
if ! grep -q 'module_status.sh.*SELECTED_FONT' "$CUSTOMIZE"; then
    sed -i '/^exit 0$/i\[ -f "$MODPATH/common/module_status.sh" ] \&\& MODDIR="$MODPATH" sh "$MODPATH/common/module_status.sh" "$SELECTED_FONT" >\/dev\/null 2>\&1 || true' "$CUSTOMIZE"
fi
if ! grep -q 'common/v14_switch.sh' "$CUSTOMIZE"; then
    sed -i '/chmod 755 "$MODPATH\/system\/bin\/洛书"/i\chmod 755 "$MODPATH/common/module_status.sh" "$MODPATH/common/v14_switch.sh" 2>/dev/null || true' "$CUSTOMIZE"
fi

# Root 管理器说明始终保持简洁，运行后由 module_status.sh 更新当前字体。
sed -i -E 's#^description=.*#description=Android 全局字体管理，当前字体：系统默认字体#' "$PROP"

chmod 0755 "$CUSTOMIZE" "$STAGE/common/module_status.sh" "$STAGE/common/v14_switch.sh" 2>/dev/null || true
