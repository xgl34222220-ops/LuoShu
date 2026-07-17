#!/system/bin/sh
# 洛书 v14.1 测试版 3 - APatch post-mount / ColorOS 残留同步
set +e
MODDIR="${0%/*}"
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/rom_adapters.sh" ] && . "$MODDIR/common/rom_adapters.sh"
[ -f "$MODDIR/common/mount_compat.sh" ] && { MODULE_DIR="$MODDIR" . "$MODDIR/common/mount_compat.sh"; }
type check_coloros >/dev/null 2>&1 && check_coloros
ACTIVE=$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
[ -n "$ACTIVE" ] || ACTIVE=default

if [ "${IS_COLOROS:-false}" = true ] && [ -d /data/fonts ]; then
    # 每次启动先按洛书管理清单清除旧目标，再只同步当前组合真正存在的文件。
    # 解决上一次英文/数字字体残留后抢占中文的问题。
    for _name in $(get_all_coloros_names); do
        _src="$MODDIR/system/fonts/${_name}.ttf"
        _dest="/data/fonts/${_name}.ttf"
        if [ "$ACTIVE" = default ] || [ ! -f "$_src" ]; then
            rm -f "$_dest" 2>/dev/null || true
        else
            if type link_or_copy_font >/dev/null 2>&1; then
                link_or_copy_font "$_src" "$_dest" 2>/dev/null || true
            else
                rm -f "$_dest" 2>/dev/null || true
                ln "$_src" "$_dest" 2>/dev/null || cp -f "$_src" "$_dest" 2>/dev/null || true
                chmod 0644 "$_dest" 2>/dev/null || true
            fi
        fi
    done
fi

type luoshu_sync_mount_payload >/dev/null 2>&1 && luoshu_sync_mount_payload 2>/dev/null || true
[ -f "$MODDIR/common/preview_cache.sh" ] && MODDIR="$MODDIR" sh "$MODDIR/common/preview_cache.sh" prune >/dev/null 2>&1 || true
[ -f "$MODDIR/common/module_status.sh" ] && MODDIR="$MODDIR" sh "$MODDIR/common/module_status.sh" "$ACTIVE" >/dev/null 2>&1 || true
exit 0
