#!/system/bin/sh
# 洛书 v14.1 - 安全卸载
set +e
MODDIR="${0%/*}"; MODULE_DIR="$MODDIR"
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/rom_adapters.sh" ] && . "$MODDIR/common/rom_adapters.sh"
type check_coloros >/dev/null 2>&1 && check_coloros
if [ "${IS_COLOROS:-false}" = true ] && [ -d /data/fonts ]; then
    for _name in $(get_all_coloros_names); do rm -f "/data/fonts/${_name}.ttf" 2>/dev/null || true; done
fi
if command -v settings >/dev/null 2>&1; then
    _restore=0
    [ -f "$MODDIR/config/font_weight_original.conf" ] && _restore=$(sed -n 's/^adjustment=//p' "$MODDIR/config/font_weight_original.conf" 2>/dev/null | head -n1)
    case "$_restore" in ''|*[!0-9-]*) _restore=0 ;; esac
    settings --user current put secure font_weight_adjustment "$_restore" >/dev/null 2>&1 || settings put secure font_weight_adjustment "$_restore" >/dev/null 2>&1 || true
fi
[ ! -f "$MODDIR/common/play_font_bridge" ] || MODDIR="$MODDIR" sh "$MODDIR/common/play_font_bridge" restore >/dev/null 2>&1 || true
rm -rf "$MODDIR/.font-transaction" 2>/dev/null || true
rm -f "$MODDIR/.first_boot" "$MODDIR/.font_switch.lock" 2>/dev/null || true
mkdir -p "$MODDIR/logs" 2>/dev/null || true
printf '[%s] 洛书 v14.1 已卸载\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" >> "$MODDIR/logs/fontswitch.log" 2>/dev/null || true
exit 0
