#!/system/bin/sh
# LuoShu private payload view.
# Real partition payloads live under .luoshu-payload so metamodules never see them.
set +e

_luoshu_private_module() {
    printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
}

_luoshu_private_root() {
    _lpp_module="${1:-$(_luoshu_private_module)}"
    printf '%s/.luoshu-payload\n' "${_lpp_module%/}"
}

_luoshu_private_state_root() {
    printf '%s\n' "${LUOSHU_PRIVATE_STATE_ROOT:-/data/adb/luoshu/private-payload}"
}

luoshu_private_partitions() {
    printf '%s\n' 'system system_ext product vendor odm oem my_product my_engineering my_company my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust hw_product'
}

_luoshu_private_mount_cmd() {
    if [ -n "${LUOSHU_PRIVATE_MOUNT_COMMAND:-}" ]; then "$LUOSHU_PRIVATE_MOUNT_COMMAND" "$@"
    elif command -v mount >/dev/null 2>&1; then mount "$@"
    elif command -v toybox >/dev/null 2>&1; then toybox mount "$@"
    elif [ -x /data/adb/magisk/busybox ]; then /data/adb/magisk/busybox mount "$@"
    elif command -v busybox >/dev/null 2>&1; then busybox mount "$@"
    else return 127
    fi
}

_luoshu_private_umount_cmd() {
    if [ -n "${LUOSHU_PRIVATE_UMOUNT_COMMAND:-}" ]; then "$LUOSHU_PRIVATE_UMOUNT_COMMAND" "$@"
    elif command -v umount >/dev/null 2>&1; then umount "$@"
    elif command -v toybox >/dev/null 2>&1; then toybox umount "$@"
    elif [ -x /data/adb/magisk/busybox ]; then /data/adb/magisk/busybox umount "$@"
    elif command -v busybox >/dev/null 2>&1; then busybox umount "$@"
    else return 127
    fi
}

_luoshu_private_is_mountpoint() {
    _lpp_path="$1"
    if command -v mountpoint >/dev/null 2>&1; then
        mountpoint -q "$_lpp_path" 2>/dev/null && return 0
    fi
    awk -v path="$_lpp_path" '$2 == path { found=1 } END { exit !found }' "${LUOSHU_PRIVATE_MOUNTINFO:-/proc/mounts}" 2>/dev/null
}

luoshu_private_install_migrate() {
    _lpp_module="${1:-$(_luoshu_private_module)}"
    _lpp_root=$(_luoshu_private_root "$_lpp_module")
    mkdir -p "$_lpp_root" "$_lpp_module/config" 2>/dev/null || return 1

    for _lpp_part in $(luoshu_private_partitions); do
        _lpp_source="$_lpp_module/$_lpp_part"
        _lpp_dest="$_lpp_root/$_lpp_part"
        if [ -d "$_lpp_source" ]; then
            mkdir -p "$_lpp_dest" 2>/dev/null || return 1
            cp -af "$_lpp_source/." "$_lpp_dest/" 2>/dev/null || \
                cp -rfp "$_lpp_source/." "$_lpp_dest/" 2>/dev/null || return 1
            rm -rf "$_lpp_source" 2>/dev/null || return 1
        fi
        mkdir -p "$_lpp_source" 2>/dev/null || return 1
    done

    : > "$_lpp_module/skip_mount" 2>/dev/null || true
    : > "$_lpp_module/skip_mountify" 2>/dev/null || true
    : > "$_lpp_module/config/self-mount-owned" 2>/dev/null || true
    find "$_lpp_root" -type d -exec chmod 0755 {} \; 2>/dev/null || true
    find "$_lpp_root" -type f -exec chmod 0644 {} \; 2>/dev/null || true
    chmod 0755 "$_lpp_root/system/bin/洛书" "$_lpp_root/system/bin/luoshud" 2>/dev/null || true
    return 0
}

luoshu_private_mount_module_view() {
    _lpp_module="${1:-$(_luoshu_private_module)}"
    _lpp_root=$(_luoshu_private_root "$_lpp_module")
    _lpp_state=$(_luoshu_private_state_root)
    _lpp_list="$_lpp_state/module-view.mounts"
    _lpp_symlinks="$_lpp_state/module-view.symlinks"
    [ -d "$_lpp_root" ] || return 1
    mkdir -p "$_lpp_state" 2>/dev/null || return 1
    : > "$_lpp_list" 2>/dev/null || return 1
    : > "$_lpp_symlinks" 2>/dev/null || return 1

    _lpp_sources=0
    _lpp_exposed=0
    for _lpp_part in $(luoshu_private_partitions); do
        _lpp_source="$_lpp_root/$_lpp_part"
        _lpp_target="$_lpp_module/$_lpp_part"
        [ -d "$_lpp_source" ] || continue
        _lpp_sources=$((_lpp_sources + 1))

        if [ -L "$_lpp_target" ]; then
            _lpp_link=$(readlink "$_lpp_target" 2>/dev/null)
            if [ "$_lpp_link" = "$_lpp_source" ]; then
                printf '%s|%s\n' "$_lpp_target" "$_lpp_source" >> "$_lpp_symlinks" 2>/dev/null || true
                _lpp_exposed=$((_lpp_exposed + 1))
                continue
            fi
            rm -f "$_lpp_target" 2>/dev/null || true
        fi

        mkdir -p "$_lpp_target" 2>/dev/null || continue
        if _luoshu_private_is_mountpoint "$_lpp_target"; then
            printf '%s\n' "$_lpp_target" >> "$_lpp_list" 2>/dev/null || true
            _lpp_exposed=$((_lpp_exposed + 1))
            continue
        fi
        if _luoshu_private_mount_cmd -o bind "$_lpp_source" "$_lpp_target" >/dev/null 2>&1; then
            printf '%s\n' "$_lpp_target" >> "$_lpp_list" 2>/dev/null || true
            _lpp_exposed=$((_lpp_exposed + 1))
            continue
        fi

        # KernelSU/SukiSU 的模块刷写进程可能没有 CAP_SYS_ADMIN，bind mount 会失败。
        # 更新迁移只需要读取旧私有负载，因此目标目录为空时用临时符号链接投影。
        if rmdir "$_lpp_target" 2>/dev/null && ln -s "$_lpp_source" "$_lpp_target" 2>/dev/null; then
            printf '%s|%s\n' "$_lpp_target" "$_lpp_source" >> "$_lpp_symlinks" 2>/dev/null || true
            _lpp_exposed=$((_lpp_exposed + 1))
        else
            [ -d "$_lpp_target" ] || mkdir -p "$_lpp_target" 2>/dev/null || true
        fi
    done

    [ "$_lpp_sources" -eq 0 ] 2>/dev/null && return 0
    [ "$_lpp_exposed" -gt 0 ] 2>/dev/null
}

luoshu_private_unmount_module_view() {
    _lpp_module="${1:-$(_luoshu_private_module)}"
    _lpp_state=$(_luoshu_private_state_root)
    _lpp_list="$_lpp_state/module-view.mounts"
    _lpp_symlinks="$_lpp_state/module-view.symlinks"

    if [ -s "$_lpp_list" ]; then
        awk '{ item[NR]=$0 } END { for (i=NR; i>=1; i--) print item[i] }' "$_lpp_list" 2>/dev/null | \
        while IFS= read -r _lpp_target; do
            case "$_lpp_target" in "${_lpp_module%/}"/*) ;; *) continue ;; esac
            _luoshu_private_umount_cmd "$_lpp_target" >/dev/null 2>&1 || true
        done
    fi
    : > "$_lpp_list" 2>/dev/null || true

    if [ -s "$_lpp_symlinks" ]; then
        while IFS='|' read -r _lpp_target _lpp_source; do
            [ -n "$_lpp_target" ] || continue
            case "$_lpp_target" in "${_lpp_module%/}"/*) ;; *) continue ;; esac
            if [ -L "$_lpp_target" ]; then
                _lpp_link=$(readlink "$_lpp_target" 2>/dev/null)
                [ "$_lpp_link" = "$_lpp_source" ] && rm -f "$_lpp_target" 2>/dev/null || true
            fi
            [ -e "$_lpp_target" ] || mkdir -p "$_lpp_target" 2>/dev/null || true
        done < "$_lpp_symlinks"
    fi
    : > "$_lpp_symlinks" 2>/dev/null || true
    return 0
}
