#!/system/bin/sh
# Compatibility alias for old callers. Every apply uses the inventory stage and
# next-boot transaction; a missing safe core cannot fall back to a ROM filename map.
set +e
MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
    else
        MODDIR=/data/adb/modules/LuoShu
    fi
fi
export MODDIR
SAFE_SWITCH="$MODDIR/common/legacy_v14_4/font_switch_safe.sh"
case "${1:-}:${2:-}" in
    action:switch)
        [ -f "$SAFE_SWITCH" ] || {
            printf '{"status":"error","message":"通用字体切换组件缺失，请重新安装模块"}\n'
            exit 1
        }
        exec sh "$SAFE_SWITCH" "$@"
        ;;
    *) printf '{"status":"error","message":"无效的字体切换命令"}\n'; exit 2 ;;
esac
