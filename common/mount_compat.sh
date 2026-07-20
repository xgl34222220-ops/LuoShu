#!/system/bin/sh
# 洛书 v13.5 Stable Hotfix1 - 元模块 / OverlayFS 挂载兼容层
# 解决 meta-overlayfs 双目录架构中：脚本修改 /data/adb/modules/LuoShu，
# 实际挂载却读取 /data/adb/metamodule/mnt/LuoShu，导致字体切换后不生效的问题。
set +e

LUOSHU_MOUNT_MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
LUOSHU_MOUNT_LOG="${LUOSHU_MOUNT_LOG:-$LUOSHU_MOUNT_MODDIR/logs/mount_compat.log}"

luoshu_mount_log() {
    _msg="$1"
    mkdir -p "${LUOSHU_MOUNT_LOG%/*}" 2>/dev/null || true
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$_msg" >> "$LUOSHU_MOUNT_LOG" 2>/dev/null || true
}

luoshu_module_id() {
    _id=$(sed -n 's/^id=//p' "$LUOSHU_MOUNT_MODDIR/module.prop" 2>/dev/null | head -n1 | tr -d '\r\n')
    [ -n "$_id" ] || _id=$(basename "$LUOSHU_MOUNT_MODDIR")
    printf '%s\n' "$_id"
}

luoshu_is_mountpoint() {
    _path="$1"
    [ -d "$_path" ] || return 1
    if command -v mountpoint >/dev/null 2>&1; then
        mountpoint -q "$_path" 2>/dev/null && return 0
    fi
    awk -v p="$_path" '$2 == p { found=1 } END { exit found ? 0 : 1 }' /proc/mounts 2>/dev/null
}

luoshu_detect_mount_engine() {
    _id=$(luoshu_module_id)
    if [ -n "$LUOSHU_META_TEST_ROOT" ]; then
        echo "test-meta"
    elif [ -d "/data/adb/metamodule/mnt/$_id" ] || [ -d "/data/adb/modules/meta-overlay/mnt/$_id" ]; then
        echo "meta-overlayfs"
    elif [ -d /data/adb/mountify ]; then
        echo "mountify"
    elif [ -e /data/adb/modules/.hybrid_mount ] || [ -d /data/adb/modules/HybridMount ]; then
        echo "hybrid-mount"
    elif [ -f "$LUOSHU_MOUNT_MODDIR/magic" ]; then
        echo "magic-mount"
    else
        echo "native-module-mount"
    fi
}

# 输出“实际被元模块读取”的内容根目录，每行一个。
# 普通 Magisk / KernelSU Magic / Mountify 直接使用 MODDIR，无需额外复制。
luoshu_meta_content_roots() {
    _id=$(luoshu_module_id)
    _seen=""

    if [ -n "$LUOSHU_META_TEST_ROOT" ]; then
        printf '%s\n' "$LUOSHU_META_TEST_ROOT/$_id"
        return 0
    fi

    for _base in \
        "${MODULE_CONTENT_DIR:-}" \
        /data/adb/metamodule/mnt \
        /data/adb/modules/meta-overlay/mnt \
        /data/adb/modules/meta-overlayfs/mnt; do
        [ -n "$_base" ] || continue
        [ "$_base" = "$LUOSHU_MOUNT_MODDIR" ] && continue
        case " $_seen " in *" $_base "*) continue ;; esac
        _seen="$_seen $_base"
        luoshu_is_mountpoint "$_base" || continue
        [ -w "$_base" ] || continue
        printf '%s\n' "$_base/$_id"
    done
}

luoshu_copy_partition_atomic() {
    _src="$1"
    _dst="$2"
    _parent=${_dst%/*}
    _name=${_dst##*/}
    _tmp="$_parent/.${_name}.luoshu.$$"

    mkdir -p "$_parent" 2>/dev/null || return 1
    rm -rf "$_tmp" 2>/dev/null || true
    if ! cp -af "$_src" "$_tmp" 2>/dev/null; then
        rm -rf "$_tmp" 2>/dev/null || true
        mkdir -p "$_tmp" 2>/dev/null || return 1
        cp -rfp "$_src/." "$_tmp/" 2>/dev/null || { rm -rf "$_tmp" 2>/dev/null; return 1; }
    fi
    rm -rf "$_dst" 2>/dev/null || return 1
    mv "$_tmp" "$_dst" 2>/dev/null || { rm -rf "$_tmp" 2>/dev/null; return 1; }
    chmod -R u=rwX,go=rX "$_dst" 2>/dev/null || true
    return 0
}

# 将洛书的分区负载镜像到元模块真实内容目录。
# 整目录镜像可同时清理旧字体，避免恢复默认后 ext4 镜仍残留上一次字体。
luoshu_sync_mount_payload() {
    _id=$(luoshu_module_id)
    _engine=$(luoshu_detect_mount_engine)
    _roots=""
    _synced=0
    _failed=0

    for _root in $(luoshu_meta_content_roots); do
        [ -n "$_root" ] || continue
        _roots="${_roots}${_roots:+,}$_root"
        mkdir -p "$_root" 2>/dev/null || { _failed=$((_failed + 1)); continue; }
        for _part in system system_ext product vendor odm oem; do
            _src="$LUOSHU_MOUNT_MODDIR/$_part"
            _dst="$_root/$_part"
            if [ -d "$_src" ]; then
                if luoshu_copy_partition_atomic "$_src" "$_dst"; then
                    _synced=$((_synced + 1))
                else
                    _failed=$((_failed + 1))
                fi
            else
                rm -rf "$_dst" 2>/dev/null || true
            fi
        done
        printf 'source=%s\ntime=%s\n' "$LUOSHU_MOUNT_MODDIR" "$(date +%s)" > "$_root/.luoshu-payload" 2>/dev/null || true
    done

    mkdir -p "$LUOSHU_MOUNT_MODDIR/config" 2>/dev/null || true
    {
        printf 'engine=%s\n' "$_engine"
        printf 'roots=%s\n' "$_roots"
        printf 'synced=%s\n' "$_synced"
        printf 'failed=%s\n' "$_failed"
        printf 'time=%s\n' "$(date +%s)"
    } > "$LUOSHU_MOUNT_MODDIR/config/mount_compat.conf" 2>/dev/null || true

    if [ "$_failed" -gt 0 ]; then
        luoshu_mount_log "元模块负载同步部分失败：engine=$_engine roots=$_roots synced=$_synced failed=$_failed"
        return 1
    fi
    if [ -n "$_roots" ]; then
        sync 2>/dev/null || true
        luoshu_mount_log "元模块负载同步完成：engine=$_engine roots=$_roots partitions=$_synced"
    else
        luoshu_mount_log "当前挂载无需双目录同步：engine=$_engine"
    fi
    return 0
}

luoshu_mount_status_json() {
    _engine=$(luoshu_detect_mount_engine)
    _roots=""
    for _root in $(luoshu_meta_content_roots); do _roots="${_roots}${_roots:+,}$_root"; done
    _last_engine=$(sed -n 's/^engine=//p' "$LUOSHU_MOUNT_MODDIR/config/mount_compat.conf" 2>/dev/null | head -n1)
    _last_synced=$(sed -n 's/^synced=//p' "$LUOSHU_MOUNT_MODDIR/config/mount_compat.conf" 2>/dev/null | head -n1)
    _last_failed=$(sed -n 's/^failed=//p' "$LUOSHU_MOUNT_MODDIR/config/mount_compat.conf" 2>/dev/null | head -n1)
    _last_time=$(sed -n 's/^time=//p' "$LUOSHU_MOUNT_MODDIR/config/mount_compat.conf" 2>/dev/null | head -n1)
    printf '{"engine":"%s","roots":"%s","lastEngine":"%s","synced":%s,"failed":%s,"time":%s}' \
        "$_engine" "$_roots" "${_last_engine:-$_engine}" "${_last_synced:-0}" "${_last_failed:-0}" "${_last_time:-0}"
}

# font_mix.sh 在 rom_adapters.sh 之后加载本文件；这里覆盖 HyperOS 的旧映射实现，
# 保证复合字体与直接应用共用真实分区和原厂度量策略。
_hyperos_helper="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}/common/hyperos_global.sh"
[ -f "$_hyperos_helper" ] && . "$_hyperos_helper"
