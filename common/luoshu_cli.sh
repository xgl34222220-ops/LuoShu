#!/system/bin/sh
# 洛书 v14.1 CLI
set +e
MODDIR="${MODDIR:-/data/adb/modules/LuoShu}"
cmd="$1"; shift 2>/dev/null || true
case "$cmd" in
    列表|list) sh "$MODDIR/common/font_manager.sh" action list refresh ;;
    当前|current) sh "$MODDIR/common/font_manager.sh" action current ;;
    切换|switch) sh "$MODDIR/common/font_switch_v141.sh" start "$1" ;;
    组合|mix) sh "$MODDIR/common/font_mix.sh" start "$1" "$2" "$3" ;;
    默认|恢复默认|reset) sh "$MODDIR/common/font_switch_v141.sh" start default ;;
    报告|report) sh "$MODDIR/common/font_manager.sh" action report ;;
    重启界面|restart-ui) sh "$MODDIR/common/font_manager.sh" action restart_ui ;;
    *)
        echo '洛书 v14.1'
        echo '用法：洛书 列表 | 当前 | 切换 <字体> | 组合 <中文> <英文> <数字> | 恢复默认 | 报告 | 重启界面'
        ;;
esac
