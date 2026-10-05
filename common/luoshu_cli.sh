#!/system/bin/sh
# 洛书 RC2 安全命令行入口。
set +e

MODDIR="${MODDIR:-/data/adb/modules/LuoShu}"
[ -f "${0%/*}/../module.prop" ] && MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
MANAGER="$MODDIR/common/font_manager.sh"
SWITCH="$MODDIR/common/font_switch_task.sh"
BRIDGE="$MODDIR/common/app_bridge.sh"

help_text() {
    echo "洛书：状态｜列表｜应用 <字体名>｜恢复默认｜日志"
    echo "字体变更完成后必须完整重启手机。"
}

case "${1:-状态}" in
    状态|status|current)
        sh "$BRIDGE" status
        ;;
    列表|list)
        sh "$MANAGER" action list
        ;;
    应用|切换|apply|switch)
        [ -n "${2:-}" ] || { echo "未指定字体" >&2; exit 1; }
        check=$(sh "$MANAGER" action validate "$2" 2>/dev/null)
        printf '%s\n' "$check" | grep -q '"valid":true' || { echo "字体未通过安全检查" >&2; exit 1; }
        sh "$SWITCH" start "$2"
        echo "任务已在后台启动，请使用“洛书 状态”查看，完成后完整重启手机。"
        ;;
    恢复默认|恢复|default)
        sh "$SWITCH" start default
        echo "恢复任务已启动，完成后请完整重启手机。"
        ;;
    日志|logs)
        sh "$BRIDGE" logs "${2:-80}"
        ;;
    帮助|help|-h|--help)
        help_text
        ;;
    *)
        help_text
        exit 1
        ;;
esac
exit $?
