#!/system/bin/sh
# LuoShu native App font-manager router.
# Inventory, preview, delete and weight actions stay on the current manager.
# Final font apply uses the isolated safe physical switch core, which builds the
# next-boot payload off-line and never rewrites the source tree mounted by this boot.
# Source-check compatibility markers owned by font_manager_v4.sh: native-v3 manifest-fast
# The current inventory contract remains config/native_font_index.json.
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
    else
        MODDIR="/data/adb/modules/LuoShu"
    fi
fi
LUOSHU_PUBLIC_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}"
CURRENT_MANAGER="$MODDIR/common/font_manager_v4.sh"
SAFE_SWITCH="$MODDIR/common/legacy_v14_4/font_switch_safe.sh"
LEGACY_SWITCH="$MODDIR/common/legacy_v14_4_switch.sh"
export MODDIR LUOSHU_PUBLIC_DIR

json_escape_router() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

if [ "${1:-}" = action ] && [ "${2:-}" = switch ]; then
    if [ -f "$SAFE_SWITCH" ]; then
        exec sh "$SAFE_SWITCH" "$@"
    fi
    if [ -f "$LEGACY_SWITCH" ]; then
        exec sh "$LEGACY_SWITCH" "$@"
    fi
    printf '{"status":"error","message":"%s"}\n' "$(json_escape_router '缺少字体切换核心')"
    exit 1
fi

if [ ! -f "$CURRENT_MANAGER" ]; then
    printf '{"status":"error","message":"%s"}\n' "$(json_escape_router '缺少当前字体管理后端')"
    exit 1
fi
exec sh "$CURRENT_MANAGER" "$@"