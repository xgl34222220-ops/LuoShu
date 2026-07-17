#!/system/bin/sh
# 洛书 v14.1 - APatch post-mount 兼容阶段
set +e
MODDIR="${0%/*}"
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/rom_adapters.sh" ] && . "$MODDIR/common/rom_adapters.sh"
[ -f "$MODDIR/common/mount_compat.sh" ] && { MODULE_DIR="$MODDIR" . "$MODDIR/common/mount_compat.sh"; }
type check_coloros >/dev/null 2>&1 && check_coloros
ACTIVE=$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
[ -n "$ACTIVE" ] || ACTIVE=default
if [ "${IS_COLOROS:-false}" = true ] && [ -d /data/fonts ]; then
    for _name in $(get_all_coloros_names); do
        _src="$MODDIR/system/fonts/${_name}.ttf"; _dest="/data/fonts/${_name}.ttf"
        if [ "$ACTIVE" = default ]; then rm -f "$_dest" 2>/dev/null || true
        elif [ -f "$_src" ]; then cp -f "$_src" "$_dest" 2>/dev/null && chmod 0644 "$_dest" 2>/dev/null || true; fi
    done
fi
type luoshu_sync_mount_payload >/dev/null 2>&1 && luoshu_sync_mount_payload 2>/dev/null || true
[ -f "$MODDIR/common/module_status.sh" ] && MODDIR="$MODDIR" sh "$MODDIR/common/module_status.sh" "$ACTIVE" >/dev/null 2>&1 || true
exit 0
