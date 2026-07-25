#!/system/bin/sh
# 洛书安全卸载：恢复模块明确记录的设置与持久字体，然后完整清理模块与元模块镜像。
set +e
MODDIR="${0%/*}"
MODULE_DIR="$MODDIR"
MODULE_VERSION=$(sed -n 's/^version=//p' "$MODDIR/module.prop" 2>/dev/null | head -n1)
[ -n "$MODULE_VERSION" ] || MODULE_VERSION="unknown"

LUOSHU_MODULES_DIR="${LUOSHU_MODULES_DIR:-/data/adb/modules}"
LUOSHU_MODULES_UPDATE_DIR="${LUOSHU_MODULES_UPDATE_DIR:-/data/adb/modules_update}"
LUOSHU_METAMODULE_MNT="${LUOSHU_METAMODULE_MNT:-/data/adb/metamodule/mnt}"
LUOSHU_MAGIC_MOUNT_CONFIG="${LUOSHU_MAGIC_MOUNT_CONFIG:-/data/adb/magic_mount/config.toml}"
LUOSHU_SELF_MOUNT_STATE="${LUOSHU_SELF_MOUNT_STATE:-/data/adb/luoshu/self-mount}"

_luoshu_uninstall_hash() {
    _luh_file="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$_luh_file" 2>/dev/null | awk '{print $1}'
    elif command -v busybox >/dev/null 2>&1; then
        busybox sha256sum "$_luh_file" 2>/dev/null | awk '{print $1}'
    else
        cksum "$_luh_file" 2>/dev/null | awk '{print $1 ":" $2}'
    fi
}

_luoshu_content_root() {
    _lucr_base="${MODULE_CONTENT_DIR:-$LUOSHU_METAMODULE_MNT}"
    _lucr_base=${_lucr_base%/}
    case "$_lucr_base" in
        */LuoShu) printf '%s\n' "$_lucr_base" ;;
        *) printf '%s/LuoShu\n' "$_lucr_base" ;;
    esac
}

_luoshu_remove_tree() {
    _lurt_path=${1%/}
    [ -n "$_lurt_path" ] || return 1
    [ "$_lurt_path" != / ] || return 1
    [ "${_lurt_path##*/}" = LuoShu ] || return 1
    rm -rf "$_lurt_path" 2>/dev/null || true
}

_luoshu_self_mount_target_allowed() {
    case "$1" in
        /system/fonts|/system/fonts/*|/system/etc|/system/etc/*|\
        /system_ext/fonts|/system_ext/fonts/*|/system_ext/etc|/system_ext/etc/*|\
        /product/fonts|/product/fonts/*|/product/etc|/product/etc/*|\
        /vendor/fonts|/vendor/fonts/*|/vendor/etc|/vendor/etc/*|\
        /odm/fonts|/odm/fonts/*|/odm/etc|/odm/etc/*|\
        /oem/fonts|/oem/fonts/*|/oem/etc|/oem/etc/*|\
        /my_product/fonts|/my_product/fonts/*|/my_product/etc|/my_product/etc/*|\
        /my_engineering/fonts|/my_engineering/fonts/*|/my_engineering/etc|/my_engineering/etc/*|\
        /my_company/fonts|/my_company/fonts/*|/my_company/etc|/my_company/etc/*|\
        /my_preload/fonts|/my_preload/fonts/*|/my_preload/etc|/my_preload/etc/*|\
        /my_region/fonts|/my_region/fonts/*|/my_region/etc|/my_region/etc/*|\
        /my_stock/fonts|/my_stock/fonts/*|/my_stock/etc|/my_stock/etc/*|\
        /oplus_product/fonts|/oplus_product/fonts/*|/oplus_product/etc|/oplus_product/etc/*|\
        /oplus_engineering/fonts|/oplus_engineering/fonts/*|/oplus_engineering/etc|/oplus_engineering/etc/*|\
        /oplus_version/fonts|/oplus_version/fonts/*|/oplus_version/etc|/oplus_version/etc/*|\
        /oplus_region/fonts|/oplus_region/fonts/*|/oplus_region/etc|/oplus_region/etc/*|\
        /mi_ext/fonts|/mi_ext/fonts/*|/mi_ext/etc|/mi_ext/etc/*|\
        /cust/fonts|/cust/fonts/*|/cust/etc|/cust/etc/*|\
        /system/system_ext/fonts|/system/system_ext/fonts/*|/system/system_ext/etc|/system/system_ext/etc/*|\
        /system/product/fonts|/system/product/fonts/*|/system/product/etc|/system/product/etc/*|\
        /system/vendor/fonts|/system/vendor/fonts/*|/system/vendor/etc|/system/vendor/etc/*)
            return 0
            ;;
    esac
    return 1
}

_luoshu_cleanup_self_mount() {
    _lucsm_state=${LUOSHU_SELF_MOUNT_STATE%/}
    [ "${_lucsm_state##*/}" = self-mount ] || return 0
    _lucsm_parent=${_lucsm_state%/*}
    [ "${_lucsm_parent##*/}" = luoshu ] || return 0
    _lucsm_list="$_lucsm_state/mounts.list"
    if [ -s "$_lucsm_list" ]; then
        awk '{ line[NR]=$0 } END { for (i=NR; i>=1; i--) print line[i] }' "$_lucsm_list" 2>/dev/null | \
        while IFS= read -r _lucsm_target; do
            [ -n "$_lucsm_target" ] || continue
            _luoshu_self_mount_target_allowed "$_lucsm_target" || continue
            umount "$_lucsm_target" 2>/dev/null || true
        done
    fi
    rm -rf "$_lucsm_state" 2>/dev/null || true
    rmdir "$_lucsm_parent" 2>/dev/null || true
}

# 恢复安装洛书前记录的 Android 全局字体粗细设置。
if command -v settings >/dev/null 2>&1; then
    _fw_restore=0
    [ -f "$MODDIR/config/font_weight_original.conf" ] && \
        _fw_restore=$(sed -n 's/^adjustment=//p' "$MODDIR/config/font_weight_original.conf" 2>/dev/null | head -n1)
    case "$_fw_restore" in ''|*[!0-9-]*) _fw_restore=0 ;; esac
    settings --user current put secure font_weight_adjustment "$_fw_restore" >/dev/null 2>&1 || \
        settings put secure font_weight_adjustment "$_fw_restore" >/dev/null 2>&1 || true
fi

# 只撤销洛书记录的 /data/fonts/config/config.xml bind。目标内容、源内容和记录哈希
# 必须完全一致，避免误卸载其他模块或系统自己的挂载；这里不写入动态字体数据库。
_dynamic_state="$MODDIR/config/device-font-dynamic-mount.conf"
if [ -s "$_dynamic_state" ]; then
    _dynamic_source_rel=$(sed -n 's/^source=//p' "$_dynamic_state" 2>/dev/null | head -n1)
    _dynamic_target=$(sed -n 's/^target=//p' "$_dynamic_state" 2>/dev/null | head -n1)
    _dynamic_source_hash=$(sed -n 's/^sourceSha256=//p' "$_dynamic_state" 2>/dev/null | head -n1)
    case "$_dynamic_source_rel" in system/etc/.luoshu-data-fonts-config.xml) ;; *) _dynamic_source_rel='' ;; esac
    _dynamic_source="$MODDIR/$_dynamic_source_rel"
    _mountinfo="${LUOSHU_MOUNTINFO:-/proc/self/mountinfo}"
    if [ -n "$_dynamic_source_rel" ] && [ -s "$_dynamic_source" ] && [ -s "$_dynamic_target" ] && \
       [ "$(_luoshu_uninstall_hash "$_dynamic_source")" = "$_dynamic_source_hash" ] && \
       [ "$(_luoshu_uninstall_hash "$_dynamic_target")" = "$_dynamic_source_hash" ] && \
       awk -v path="$_dynamic_target" '$5 == path { found=1 } END { exit !found }' "$_mountinfo" 2>/dev/null; then
        umount "$_dynamic_target" 2>/dev/null || true
    fi
fi

# 恢复旧实验版本遗留的 provider 备份。v2.2 本身从不覆盖 /data/fonts/files。
if [ -f "$MODDIR/common/font_provider_cache.sh" ]; then
    . "$MODDIR/common/font_provider_cache.sh"
    luoshu_provider_cache_restore >/dev/null 2>&1 || true
fi

# Flyme 还存在 /data/customizecenter/font/flymeFont.ttf 持久槽；模块目录删除前
# 必须使用已保存的原厂副本完成原子恢复。其他 ROM 只使用 systemless 文件，无需写入。
if [ -f "$MODDIR/common/origin_flyme_global.sh" ]; then
    . "$MODDIR/common/origin_flyme_global.sh"
    if type _luoshu_detect_flyme >/dev/null 2>&1 && _luoshu_detect_flyme; then
        type _luoshu_flyme_prepare_data_restore >/dev/null 2>&1 && \
            _luoshu_flyme_prepare_data_restore >/dev/null 2>&1 || true
        type luoshu_flyme_pending_apply >/dev/null 2>&1 && \
            luoshu_flyme_pending_apply >/dev/null 2>&1 || true
    fi
fi

# 先解除洛书自己的 post-mount 兜底挂载，再删除模块负载。
_luoshu_cleanup_self_mount

# 清理洛书写入 Magic Mount 配置旁的锁、备份和临时文件。不会回滚整个
# Magic Mount 配置，避免覆盖用户卸载前自行完成的其他配置修改。
rm -f \
    "$LUOSHU_MAGIC_MOUNT_CONFIG.luoshu.lock" \
    "$LUOSHU_MAGIC_MOUNT_CONFIG.luoshu.bak" \
    "$LUOSHU_MAGIC_MOUNT_CONFIG.luoshu."* 2>/dev/null || true

# 元模块可能维护独立于 /data/adb/modules 的第二份内容树。卸载时必须同时
# 删除这份 LuoShu 镜像，否则 meta-overlayfs 仍会看到旧负载文件。
_luoshu_remove_tree "$(_luoshu_content_root)"
_luoshu_remove_tree "$LUOSHU_METAMODULE_MNT/LuoShu"

# 清理待安装副本和当前模块目录。卸载完成后不再在 MODDIR 内创建 logs，
# 避免 KernelSU、APatch 或部分元模块在卸载脚本结束后留下一个新目录。
_luoshu_remove_tree "$LUOSHU_MODULES_UPDATE_DIR/LuoShu"
_luoshu_remove_tree "$LUOSHU_MODULES_DIR/LuoShu"
_luoshu_remove_tree "$MODDIR"

# 卸载事件只写入系统日志，不再制造任何持久文件。
if command -v log >/dev/null 2>&1; then
    log -t LuoShu "洛书 $MODULE_VERSION 已卸载" >/dev/null 2>&1 || true
fi
exit 0
