#!/bin/sh
set -eu
STAGE="$1"; CUSTOMIZE="$STAGE/customize.sh"; PROP="$STAGE/module.prop"; MANAGER="$STAGE/common/font_manager.sh"
for file in "$CUSTOMIZE" "$PROP" "$MANAGER" "$STAGE/common/module_status.sh" "$STAGE/common/font_switch_task.sh" "$STAGE/common/font_mix.sh" "$STAGE/common/font_mix_controller.sh"; do test -f "$file"; done
sed -i -E 's/v13\.5 Stable Hotfix3/v14/g; s/文字与 Emoji 独立管理/Android 全局字体管理/g' "$CUSTOMIZE"
if ! grep -q 'module_status.sh.*SELECTED_FONT' "$CUSTOMIZE"; then sed -i '/^exit 0$/i\[ -f "$MODPATH/common/module_status.sh" ] \&\& MODDIR="$MODPATH" sh "$MODPATH/common/module_status.sh" "$SELECTED_FONT" >\/dev\/null 2>\&1 || true' "$CUSTOMIZE"; fi
if ! grep -q 'common/font_switch_task.sh' "$CUSTOMIZE"; then sed -i '/chmod 755 "$MODPATH\/system\/bin\/洛书"/i\chmod 755 "$MODPATH/common/module_status.sh" "$MODPATH/common/font_switch_task.sh" 2>/dev/null || true' "$CUSTOMIZE"; fi
if ! grep -q 'common/font_mix.sh' "$CUSTOMIZE"; then sed -i '/chmod 755 "$MODPATH\/system\/bin\/洛书"/i\chmod 755 "$MODPATH/common/font_mix.sh" "$MODPATH/common/font_mix_controller.sh" 2>/dev/null || true' "$CUSTOMIZE"; fi
if ! grep -q 'v14-lightweight-preview-sync' "$MANAGER"; then
    sed -i '/    sync_preview_fonts 2>\/dev\/null || true/,/    sync_emoji_preview_fonts 2>\/dev\/null || true/c\    # v14-lightweight-preview-sync\n    case "$action" in\n        list|emoji_list|import_list|import_zip|delete)\n            sync_preview_fonts 2>/dev/null || true\n            sync_emoji_preview_fonts 2>/dev/null || true\n            ;;\n    esac' "$MANAGER"
fi
sed -i -E 's#^description=.*#description=Android 全局字体管理，当前字体：系统默认字体#' "$PROP"
chmod 0755 "$CUSTOMIZE" "$STAGE/common/module_status.sh" "$STAGE/common/font_switch_task.sh" "$STAGE/common/font_mix.sh" "$STAGE/common/font_mix_controller.sh" 2>/dev/null || true
