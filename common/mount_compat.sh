#!/system/bin/sh
# LuoShu metamodule compatibility adapters.
# Each mount engine has a different content contract; never mirror into guessed runtime paths.
set +e

LUOSHU_MOUNT_MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
LUOSHU_MOUNT_LOG="${LUOSHU_MOUNT_LOG:-$LUOSHU_MOUNT_MODDIR/logs/mount_compat.log}"
LUOSHU_MOUNT_LOCK="$LUOSHU_MOUNT_MODDIR/.mount_compat.lock"
LUOSHU_MOUNT_TIMEOUT="${LUOSHU_MOUNT_TIMEOUT:-120}"

luoshu_mount_log() {
    _lml_msg="$1"
    mkdir -p "${LUOSHU_MOUNT_LOG%/*}" 2>/dev/null || true
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$_lml_msg" >> "$LUOSHU_MOUNT_LOG" 2>/dev/null || true
}

luoshu_module_id() {
    _lmi_id=$(sed -n 's/^id=//p' "$LUOSHU_MOUNT_MODDIR/module.prop" 2>/dev/null | head -n1 | tr -d '\r\n')
    [ -n "$_lmi_id" ] || _lmi_id=$(basename "$LUOSHU_MOUNT_MODDIR")
    printf '%s\n' "$_lmi_id"
}

luoshu_payload_partitions() {
    printf '%s\n' 'system system_ext product vendor odm oem my_product my_engineering my_company my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust'
}

luoshu_detect_root_manager() {
    if [ -n "${APATCH:-}" ] || [ -d /data/adb/ap ] || [ -d /data/adb/apatch ]; then
        printf 'APatch\n'
    elif [ -n "${KSU:-}" ] || [ -d /data/adb/ksu ]; then
        printf 'KernelSU\n'
    elif [ -n "${MAGISK_VER_CODE:-}" ] || [ -d /data/adb/magisk ] || [ -x /data/adb/magisk/magisk ]; then
        printf 'Magisk\n'
    else
        printf 'unknown\n'
    fi
}

_luoshu_module_prop_id() {
    sed -n 's/^id=//p' "$1/module.prop" 2>/dev/null | head -n1 | tr -d '\r\n'
}

# Magic Mount has shipped under several module ids (including RC builds).  Detect it from
# module metadata and its persistent configuration instead of relying on two directory names.
luoshu_magic_mount_present() {
    for _lmmp_prop in /data/adb/modules/*/module.prop; do
        [ -f "$_lmmp_prop" ] || continue
        _lmmp_dir=${_lmmp_prop%/*}
        [ ! -e "$_lmmp_dir/disable" ] && [ ! -e "$_lmmp_dir/remove" ] || continue
        _lmmp_meta=$(sed -n 's/^\(id\|name\|description\)=/\1=/p' "$_lmmp_prop" 2>/dev/null | tr '[:upper:]' '[:lower:]' | tr '\n' ' ')
        case "$_lmmp_meta" in
            *magic_mount*|*magic-mount*|*magic\ mount*|*id=meta-mm*) return 0 ;;
        esac
    done
    # Some RC packages keep the stable config path while changing their module id.
    [ -f /data/adb/magic_mount/config.toml ] && {
        [ -x /data/adb/metamodule/meta-mm ] || [ -x /data/adb/metamodule/meta-mm-rs ] || \
        [ -x /data/adb/modules/magic_mount_rs/meta-mm ] || [ -x /data/adb/modules/meta-mm/meta-mm ]
    }
}

luoshu_detect_mount_engine() {
    [ -z "${LUOSHU_META_TEST_ENGINE:-}" ] || { printf '%s\n' "$LUOSHU_META_TEST_ENGINE"; return 0; }

    _ldme_meta_id=$(_luoshu_module_prop_id /data/adb/metamodule)
    case "$_ldme_meta_id" in
        meta-overlay|meta-overlayfs|meta-overlayfsUltra) printf 'meta-overlayfs\n'; return 0 ;;
    esac
    if [ -n "${MODULE_CONTENT_DIR:-}" ] && [ -n "${MODULE_METADATA_DIR:-}" ]; then
        printf 'dual-dir-metamodule\n'
        return 0
    fi
    if [ -d /data/adb/metamodule/mnt ] && { [ -f /data/adb/metamodule/modules.img ] || [ -L /data/adb/metamodule ]; }; then
        printf 'meta-overlayfs\n'
        return 0
    fi

    if [ -d /data/adb/mountify ] || [ -d /data/adb/modules/mountify ] || [ -d /data/adb/modules/Mountify ]; then
        printf 'mountify\n'
        return 0
    fi
    if command -v hybrid-mount >/dev/null 2>&1 || [ -d /data/adb/hybrid-mount ] || \
       [ -d /data/adb/modules/meta-hybrid_mount ] || [ -d /data/adb/modules/hybrid_mount ]; then
        printf 'hybrid-mount\n'
        return 0
    fi
    if luoshu_magic_mount_present; then
        printf 'magic-mount\n'
        return 0
    fi
    printf 'native-module-mount\n'
}

luoshu_engine_partitions() {
    case "${1:-$(luoshu_detect_mount_engine)}" in
        meta-overlayfs|dual-dir-metamodule)
            # Official meta-overlayfs relocates only these six partitions during installation.
            printf '%s\n' 'system vendor product system_ext odm oem'
            ;;
        *)
            luoshu_payload_partitions
            ;;
    esac
}

luoshu_dual_content_base() {
    if [ -n "${LUOSHU_META_TEST_ROOT:-}" ]; then
        printf '%s\n' "$LUOSHU_META_TEST_ROOT"
    elif [ -n "${MODULE_CONTENT_DIR:-}" ]; then
        printf '%s\n' "${MODULE_CONTENT_DIR%/}"
    else
        printf '/data/adb/metamodule/mnt\n'
    fi
}

# Only dual-directory metamodules expose a second persistent module tree.
# Mountify, Hybrid Mount and Magic Mount read /data/adb/modules directly and must never be mirrored.
luoshu_meta_content_roots() {
    _lmcr_engine=$(luoshu_detect_mount_engine)
    case "$_lmcr_engine" in meta-overlayfs|dual-dir-metamodule) ;; *) return 0 ;; esac
    _lmcr_base=$(luoshu_dual_content_base)
    _lmcr_id=$(luoshu_module_id)
    case "$_lmcr_base" in */"$_lmcr_id") _lmcr_root="$_lmcr_base" ;; *) _lmcr_root="$_lmcr_base/$_lmcr_id" ;; esac
    [ "$_lmcr_root" != "$LUOSHU_MOUNT_MODDIR" ] || return 0
    printf '%s\n' "$_lmcr_root"
}

luoshu_mount_lock_acquire() {
    if [ -f "$LUOSHU_MOUNT_LOCK" ]; then
        _lmla_pid=$(cat "$LUOSHU_MOUNT_LOCK" 2>/dev/null)
        if [ -n "$_lmla_pid" ] && kill -0 "$_lmla_pid" 2>/dev/null; then
            luoshu_mount_log "拒绝并发元模块更新：pid=$_lmla_pid"
            return 1
        fi
        rm -f "$LUOSHU_MOUNT_LOCK" 2>/dev/null || true
    fi
    printf '%s\n' "$$" > "$LUOSHU_MOUNT_LOCK" 2>/dev/null || return 1
}

luoshu_mount_lock_release() {
    rm -f "$LUOSHU_MOUNT_LOCK" 2>/dev/null || true
}

luoshu_mountpoint_ready() {
    _lmr_path="$1"
    [ -n "${LUOSHU_META_TEST_ROOT:-}" ] && return 0
    if command -v mountpoint >/dev/null 2>&1; then
        mountpoint -q "$_lmr_path" 2>/dev/null && return 0
    fi
    awk -v p="$_lmr_path" '$2 == p { found=1 } END { exit !found }' /proc/mounts 2>/dev/null
}

luoshu_mountify_value() {
    _lmv_key="$1"
    for _lmv_conf in /data/adb/mountify/config.sh /data/adb/modules/mountify/config.sh /data/adb/modules/Mountify/config.sh; do
        [ -f "$_lmv_conf" ] || continue
        sed -n "s/^[[:space:]]*${_lmv_key}[[:space:]]*=[[:space:]]*[\"']\{0,1\}\([^\"'#[:space:]]*\).*/\1/p" "$_lmv_conf" 2>/dev/null | tail -n1
        return 0
    done
    return 1
}

luoshu_mountify_module_selected() {
    _lmms_id=$(luoshu_module_id)
    _lmms_mode=$(luoshu_mountify_value mountify_mounts)
    [ -n "$_lmms_mode" ] || _lmms_mode=2
    [ "$_lmms_mode" != 1 ] && return 0
    for _lmms_list in /data/adb/mountify/modules.txt /data/adb/modules/mountify/modules.txt /data/adb/modules/Mountify/modules.txt; do
        [ -f "$_lmms_list" ] || continue
        grep -Fxq "$_lmms_id" "$_lmms_list" 2>/dev/null && return 0
    done
    return 1
}

LUOSHU_MOUNT_PREFLIGHT_ERROR=''
luoshu_recover_safety_disable() {
    [ -e "$LUOSHU_MOUNT_MODDIR/disable" ] || return 0
    _lrsd_fail=$(cat "$LUOSHU_MOUNT_MODDIR/config/font-boot-failures" 2>/dev/null)
    case "$_lrsd_fail" in ''|*[!0-9]*) _lrsd_fail=0 ;; esac
    if [ "$_lrsd_fail" -lt 2 ] && [ ! -f "$LUOSHU_MOUNT_MODDIR/config/font-payload-quarantine.conf" ]; then
        return 0
    fi
    rm -f "$LUOSHU_MOUNT_MODDIR/disable" 2>/dev/null || {
        LUOSHU_MOUNT_PREFLIGHT_ERROR='无法清理洛书安全守卫遗留的 disable 标记'
        return 1
    }
    rm -f "$LUOSHU_MOUNT_MODDIR/config/font-boot-failures" \
          "$LUOSHU_MOUNT_MODDIR/config/font-payload-quarantine.conf" 2>/dev/null || true
    luoshu_mount_log '已恢复洛书安全守卫误设的 disable 标记；允许用户主动重试字体事务'
    return 0
}

luoshu_recover_magic_mount_markers() {
    _lrmm_engine="$1"
    [ "$_lrmm_engine" = magic-mount ] || [ "$_lrmm_engine" = magic-mount-rs ] || return 0

    # A previous Mountify/native-mount attempt can leave these markers behind.  Starting an
    # explicit LuoShu font transaction is an intentional retry, so clear only LuoShu's own
    # recoverable mount markers.  disable/remove remain hard failures.
    _lrmm_cleared=''
    for _lrmm_marker in skip_mount mount_error; do
        [ -e "$LUOSHU_MOUNT_MODDIR/$_lrmm_marker" ] || continue
        rm -f "$LUOSHU_MOUNT_MODDIR/$_lrmm_marker" 2>/dev/null || {
            LUOSHU_MOUNT_PREFLIGHT_ERROR="无法清理 Magic Mount 遗留标记：$_lrmm_marker"
            return 1
        }
        _lrmm_cleared="${_lrmm_cleared}${_lrmm_cleared:+,}$_lrmm_marker"
    done
    [ -z "$_lrmm_cleared" ] || luoshu_mount_log "Magic Mount 重试已清理洛书遗留标记：$_lrmm_cleared"
    return 0
}

luoshu_magic_mount_ensure_partitions() {
    _lmep_engine="$1"
    [ "$_lmep_engine" = magic-mount ] || [ "$_lmep_engine" = magic-mount-rs ] || return 0
    _lmep_config="${LUOSHU_MAGIC_MOUNT_CONFIG:-/data/adb/magic_mount/config.toml}"
    [ -f "$_lmep_config" ] || return 0

    _lmep_current=$(awk '
        /^[[:space:]]*partitions[[:space:]]*=/ { capture=1 }
        capture { printf "%s ", $0 }
        capture && /]/ { exit }
    ' "$_lmep_config" 2>/dev/null)
    _lmep_list=''
    for _lmep_item in $(printf '%s\n' "$_lmep_current" | awk -F'"' '{ for (i=2; i<=NF; i+=2) print $i }' 2>/dev/null); do
        case "$_lmep_item" in ''|*[!A-Za-z0-9_]*) continue ;; esac
        case " $_lmep_list " in *" $_lmep_item "*) ;; *) _lmep_list="${_lmep_list}${_lmep_list:+ }$_lmep_item" ;; esac
    done

    _lmep_added=''
    for _lmep_part in system_ext product vendor odm oem my_product my_engineering my_company \
        my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust; do
        _lmep_dir="$LUOSHU_MOUNT_MODDIR/$_lmep_part"
        [ -d "$_lmep_dir" ] || continue
        find "$_lmep_dir" -type f -print -quit 2>/dev/null | grep -q . || continue
        case " $_lmep_list " in
            *" $_lmep_part "*) ;;
            *)
                _lmep_list="${_lmep_list}${_lmep_list:+ }$_lmep_part"
                _lmep_added="${_lmep_added}${_lmep_added:+,}$_lmep_part"
                ;;
        esac
    done
    [ -n "$_lmep_added" ] || return 0

    _lmep_array=''
    for _lmep_item in $_lmep_list; do
        _lmep_array="${_lmep_array}${_lmep_array:+, }\"$_lmep_item\""
    done
    _lmep_replacement="partitions = [$_lmep_array]"
    _lmep_temp="${_lmep_config}.tmp.$$"
    [ -f "${_lmep_config}.luoshu.bak" ] || cp -f "$_lmep_config" "${_lmep_config}.luoshu.bak" 2>/dev/null || true
    awk -v replacement="$_lmep_replacement" '
        BEGIN { replaced=0; skipping=0 }
        skipping { if ($0 ~ /]/) skipping=0; next }
        /^[[:space:]]*partitions[[:space:]]*=/ {
            print replacement
            replaced=1
            if ($0 !~ /]/) skipping=1
            next
        }
        { print }
        END { if (!replaced) print replacement }
    ' "$_lmep_config" > "$_lmep_temp" 2>/dev/null || {
        rm -f "$_lmep_temp" 2>/dev/null || true
        LUOSHU_MOUNT_PREFLIGHT_ERROR="无法更新 Magic Mount 分区配置：$_lmep_added"
        return 1
    }
    chmod --reference="$_lmep_config" "$_lmep_temp" 2>/dev/null || chmod 0644 "$_lmep_temp" 2>/dev/null || true
    mv -f "$_lmep_temp" "$_lmep_config" 2>/dev/null || {
        rm -f "$_lmep_temp" 2>/dev/null || true
        LUOSHU_MOUNT_PREFLIGHT_ERROR="无法提交 Magic Mount 分区配置：$_lmep_added"
        return 1
    }
    luoshu_mount_log "已补齐 Magic Mount 字体负载分区：$_lmep_added"
    return 0
}

luoshu_mount_preflight() {
    _lmp_active="${1:-unknown}"
    LUOSHU_MOUNT_PREFLIGHT_ERROR=''
    _lmp_engine=$(luoshu_detect_mount_engine)
    _lmp_manager=$(luoshu_detect_root_manager)

    # Restoring the ROM default is a cleanup transaction. It must remain available even when
    # the root manager currently ignores the module. Non-default retries only clear markers that
    # can be proven to have been created by LuoShu's own legacy safety guard.
    if [ "$_lmp_active" != default ]; then
        luoshu_recover_safety_disable || return 1
        luoshu_recover_magic_mount_markers "$_lmp_engine" || return 1
    fi

    for _lmp_marker in disable remove mount_error; do
        if [ -e "$LUOSHU_MOUNT_MODDIR/$_lmp_marker" ]; then
            [ "$_lmp_active" = default ] && continue
            LUOSHU_MOUNT_PREFLIGHT_ERROR="模块存在 $_lmp_marker 标记，元模块不会挂载洛书"
            return 1
        fi
    done

    case "$_lmp_engine" in
        meta-overlayfs|dual-dir-metamodule|hybrid-mount|magic-mount|magic-mount-rs)
            if [ "$_lmp_active" != default ] && [ -e "$LUOSHU_MOUNT_MODDIR/skip_mount" ]; then
                LUOSHU_MOUNT_PREFLIGHT_ERROR='检测到 skip_mount，当前元模块会跳过洛书负载'
                return 1
            fi
            ;;
        mountify)
            if [ "$_lmp_active" != default ]; then
                if [ "$_lmp_manager" = Magisk ]; then
                    if [ -e "$LUOSHU_MOUNT_MODDIR/skip_mountify" ]; then
                        LUOSHU_MOUNT_PREFLIGHT_ERROR='检测到 skip_mountify，Mountify 已排除洛书'
                        return 1
                    fi
                elif [ -e "$LUOSHU_MOUNT_MODDIR/skip_mount" ]; then
                    LUOSHU_MOUNT_PREFLIGHT_ERROR='检测到 skip_mount，Mountify 已排除洛书'
                    return 1
                fi
                if ! luoshu_mountify_module_selected; then
                    LUOSHU_MOUNT_PREFLIGHT_ERROR='Mountify 当前为白名单模式，但 modules.txt 未包含 LuoShu'
                    return 1
                fi
            fi
            ;;
    esac

    if [ "$_lmp_active" != default ]; then
        luoshu_magic_mount_ensure_partitions "$_lmp_engine" || return 1
    fi

    case "$_lmp_engine" in
        meta-overlayfs|dual-dir-metamodule)
            _lmp_base=$(luoshu_dual_content_base)
            if ! luoshu_mountpoint_ready "$_lmp_base"; then
                LUOSHU_MOUNT_PREFLIGHT_ERROR="元模块内容镜像未挂载：$_lmp_base；请先完整重启或重装元模块"
                return 1
            fi
            [ -w "$_lmp_base" ] || {
                LUOSHU_MOUNT_PREFLIGHT_ERROR="元模块内容镜像不可写：$_lmp_base"
                return 1
            }
            ;;
    esac
    return 0
}

luoshu_copy_tree_bounded() {
    _lctb_src="$1"
    _lctb_dst="$2"
    if command -v timeout >/dev/null 2>&1; then
        timeout "$LUOSHU_MOUNT_TIMEOUT" cp -af "$_lctb_src" "$_lctb_dst" 2>/dev/null && return 0
    elif command -v toybox >/dev/null 2>&1 && toybox timeout --help >/dev/null 2>&1; then
        toybox timeout "$LUOSHU_MOUNT_TIMEOUT" cp -af "$_lctb_src" "$_lctb_dst" 2>/dev/null && return 0
    else
        cp -af "$_lctb_src" "$_lctb_dst" 2>/dev/null && return 0
    fi
    rm -rf "$_lctb_dst" 2>/dev/null || true
    mkdir -p "$_lctb_dst" 2>/dev/null || return 1
    cp -rfp "$_lctb_src/." "$_lctb_dst/" 2>/dev/null
}

luoshu_copy_partition_atomic() {
    _lcpa_src="$1"
    _lcpa_dst="$2"
    _lcpa_parent=${_lcpa_dst%/*}
    _lcpa_name=${_lcpa_dst##*/}
    _lcpa_tmp="$_lcpa_parent/.${_lcpa_name}.luoshu.$$"
    _lcpa_backup="$_lcpa_parent/.${_lcpa_name}.luoshu-backup.$$"
    mkdir -p "$_lcpa_parent" 2>/dev/null || return 1
    rm -rf "$_lcpa_tmp" "$_lcpa_backup" 2>/dev/null || true
    luoshu_copy_tree_bounded "$_lcpa_src" "$_lcpa_tmp" || { rm -rf "$_lcpa_tmp"; return 1; }
    chmod -R u=rwX,go=rX "$_lcpa_tmp" 2>/dev/null || true
    [ ! -e "$_lcpa_dst" ] || mv "$_lcpa_dst" "$_lcpa_backup" 2>/dev/null || { rm -rf "$_lcpa_tmp"; return 1; }
    if mv "$_lcpa_tmp" "$_lcpa_dst" 2>/dev/null; then
        rm -rf "$_lcpa_backup" 2>/dev/null || true
        return 0
    fi
    rm -rf "$_lcpa_dst" 2>/dev/null || true
    [ ! -e "$_lcpa_backup" ] || mv "$_lcpa_backup" "$_lcpa_dst" 2>/dev/null || true
    rm -rf "$_lcpa_tmp" 2>/dev/null || true
    return 1
}

luoshu_write_mount_probe() {
    _lwmp_active="${1:-unknown}"
    _lwmp_engine=$(luoshu_detect_mount_engine)
    _lwmp_id=$(luoshu_module_id)
    _lwmp_nonce="$(date +%s 2>/dev/null || echo 0)-$$"
    _lwmp_dir="$LUOSHU_MOUNT_MODDIR/system/etc/luoshu"
    mkdir -p "$_lwmp_dir" "$LUOSHU_MOUNT_MODDIR/config" 2>/dev/null || return 1
    {
        printf 'id=%s\n' "$_lwmp_id"
        printf 'font=%s\n' "$_lwmp_active"
        printf 'engine=%s\n' "$_lwmp_engine"
        printf 'nonce=%s\n' "$_lwmp_nonce"
    } > "$_lwmp_dir/mount-probe.conf.tmp.$$" 2>/dev/null || return 1
    mv -f "$_lwmp_dir/mount-probe.conf.tmp.$$" "$_lwmp_dir/mount-probe.conf" 2>/dev/null || return 1
    cp -f "$_lwmp_dir/mount-probe.conf" "$LUOSHU_MOUNT_MODDIR/config/mount-probe-expected.conf" 2>/dev/null || return 1
    chmod 0644 "$_lwmp_dir/mount-probe.conf" "$LUOSHU_MOUNT_MODDIR/config/mount-probe-expected.conf" 2>/dev/null || true
}

luoshu_mount_record() {
    _lmr_state="$1"; _lmr_detail="$2"; _lmr_root="$3"; _lmr_synced="$4"; _lmr_failed="$5"
    mkdir -p "$LUOSHU_MOUNT_MODDIR/config" 2>/dev/null || true
    {
        printf 'manager=%s\n' "$(luoshu_detect_root_manager)"
        printf 'engine=%s\n' "$(luoshu_detect_mount_engine)"
        printf 'state=%s\n' "$_lmr_state"
        printf 'detail=%s\n' "$_lmr_detail"
        printf 'contentRoot=%s\n' "$_lmr_root"
        printf 'synced=%s\n' "$_lmr_synced"
        printf 'failed=%s\n' "$_lmr_failed"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$LUOSHU_MOUNT_MODDIR/config/mount_compat.conf.tmp.$$" 2>/dev/null || return 0
    mv -f "$LUOSHU_MOUNT_MODDIR/config/mount_compat.conf.tmp.$$" "$LUOSHU_MOUNT_MODDIR/config/mount_compat.conf" 2>/dev/null || true
}

luoshu_sync_mount_payload() {
    _lsmp_active="${1:-$(head -n1 "$LUOSHU_MOUNT_MODDIR/config/active_font.conf" 2>/dev/null)}"
    [ -n "$_lsmp_active" ] || _lsmp_active=default
    _lsmp_engine=$(luoshu_detect_mount_engine)
    _lsmp_synced=0
    _lsmp_failed=0
    _lsmp_root=''

    luoshu_mount_lock_acquire || return 1
    trap 'luoshu_mount_lock_release' EXIT HUP INT TERM
    if ! luoshu_mount_preflight "$_lsmp_active"; then
        luoshu_mount_record failed "$LUOSHU_MOUNT_PREFLIGHT_ERROR" '' 0 1
        luoshu_mount_log "元模块预检失败：engine=$_lsmp_engine error=$LUOSHU_MOUNT_PREFLIGHT_ERROR"
        luoshu_mount_lock_release
        trap - EXIT HUP INT TERM
        return 1
    fi
    luoshu_write_mount_probe "$_lsmp_active" || {
        luoshu_mount_record failed '无法生成挂载探针' '' 0 1
        luoshu_mount_lock_release
        trap - EXIT HUP INT TERM
        return 1
    }

    case "$_lsmp_engine" in
        meta-overlayfs|dual-dir-metamodule)
            _lsmp_root=$(luoshu_meta_content_roots | head -n1)
            [ -n "$_lsmp_root" ] || _lsmp_failed=1
            if [ "$_lsmp_failed" -eq 0 ]; then
                mkdir -p "$_lsmp_root" 2>/dev/null || _lsmp_failed=1
            fi
            if [ "$_lsmp_failed" -eq 0 ]; then
                for _lsmp_part in $(luoshu_engine_partitions "$_lsmp_engine"); do
                    _lsmp_src="$LUOSHU_MOUNT_MODDIR/$_lsmp_part"
                    _lsmp_dst="$_lsmp_root/$_lsmp_part"
                    if [ -d "$_lsmp_src" ]; then
                        if luoshu_copy_partition_atomic "$_lsmp_src" "$_lsmp_dst"; then
                            _lsmp_synced=$((_lsmp_synced + 1))
                        else
                            _lsmp_failed=$((_lsmp_failed + 1))
                            break
                        fi
                    else
                        rm -rf "$_lsmp_dst" 2>/dev/null || _lsmp_failed=$((_lsmp_failed + 1))
                    fi
                done
            fi
            ;;
        *)
            # Direct-source engines rescan the canonical module tree on the next reboot.
            _lsmp_synced=0
            ;;
    esac

    luoshu_mount_lock_release
    trap - EXIT HUP INT TERM
    if [ "$_lsmp_failed" -gt 0 ]; then
        luoshu_mount_record failed '元模块内容更新失败，已保留旧分区目录' "$_lsmp_root" "$_lsmp_synced" "$_lsmp_failed"
        luoshu_mount_log "元模块更新失败：engine=$_lsmp_engine root=$_lsmp_root synced=$_lsmp_synced failed=$_lsmp_failed"
        return 1
    fi
    if [ "$_lsmp_engine" = meta-overlayfs ] || [ "$_lsmp_engine" = dual-dir-metamodule ]; then
        luoshu_mount_record prepared '已写入元模块真实内容镜像，等待重启验证' "$_lsmp_root" "$_lsmp_synced" 0
    else
        luoshu_mount_record prepared '当前引擎直接读取标准模块目录，等待重启验证' '' 0 0
    fi
    luoshu_mount_log "元模块适配完成：engine=$_lsmp_engine root=$_lsmp_root synced=$_lsmp_synced"
    return 0
}

# Called after a payload transaction rollback. For dual-directory engines this writes the restored
# canonical tree back to the real content image; direct-source engines need no extra copy.
luoshu_restore_mount_payload() {
    _lrmp_active=$(head -n1 "$LUOSHU_MOUNT_MODDIR/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_lrmp_active" ] || _lrmp_active=default
    luoshu_sync_mount_payload "$_lrmp_active"
}

luoshu_mount_verify_active() {
    _lmva_active="${1:-$(head -n1 "$LUOSHU_MOUNT_MODDIR/config/active_font.conf" 2>/dev/null)}"
    [ -n "$_lmva_active" ] || _lmva_active=default
    [ "$_lmva_active" != default ] || { luoshu_mount_record verified '系统默认字体无需挂载验证' '' 0 0; return 0; }
    _lmva_expected="$LUOSHU_MOUNT_MODDIR/config/mount-probe-expected.conf"
    _lmva_visible="${LUOSHU_VISIBLE_PROBE:-/system/etc/luoshu/mount-probe.conf}"
    _lmva_nonce=$(sed -n 's/^nonce=//p' "$_lmva_expected" 2>/dev/null | head -n1)
    _lmva_seen=$(sed -n 's/^nonce=//p' "$_lmva_visible" 2>/dev/null | head -n1)
    if [ -n "$_lmva_nonce" ] && [ "$_lmva_nonce" = "$_lmva_seen" ]; then
        luoshu_mount_record verified '挂载探针已从系统分区读取，元模块生效' '' 0 0
        return 0
    fi
    luoshu_mount_record unverified "系统未读取到洛书挂载探针：expected=$_lmva_nonce seen=$_lmva_seen" '' 0 1
    luoshu_mount_log "挂载验证失败：engine=$(luoshu_detect_mount_engine) expected=$_lmva_nonce seen=$_lmva_seen"
    return 1
}

# Override the base confirmation: a completed Android boot is not enough; the selected mount engine
# must also expose LuoShu's probe from the real system partition before the payload is trusted.
font_config_mark_boot_success() {
    _lmbs_config="${CONFIG_DIR:-$LUOSHU_MOUNT_MODDIR/config}"
    _lmbs_state=$(sed -n 's/^state=//p' "$_lmbs_config/font-payload-boot.conf" 2>/dev/null | head -n1)
    [ "$_lmbs_state" = booting ] || return 0
    _lmbs_font=$(sed -n 's/^font=//p' "$_lmbs_config/font-payload-boot.conf" 2>/dev/null | head -n1)
    if ! luoshu_mount_verify_active "${_lmbs_font:-unknown}"; then
        type _luoshu_safety_log >/dev/null 2>&1 && _luoshu_safety_log ERROR 'Android 已开机，但元模块未挂载洛书负载；本次事务不确认'
        return 1
    fi
    {
        printf 'state=confirmed\n'
        printf 'font=%s\n' "${_lmbs_font:-unknown}"
        printf 'time=%s\n' "$(date +%s)"
    } > "$_lmbs_config/font-payload-boot.conf.tmp.$$" 2>/dev/null || return 1
    mv -f "$_lmbs_config/font-payload-boot.conf.tmp.$$" "$_lmbs_config/font-payload-boot.conf" 2>/dev/null || return 1
    rm -f "$_lmbs_config/font-boot-failures" "$_lmbs_config/font-payload-quarantine.conf" 2>/dev/null || true
    printf 'time=%s\n' "$(date +%s)" > "$_lmbs_config/font-last-boot-success.conf" 2>/dev/null || true
    chmod 0644 "$_lmbs_config/font-payload-boot.conf" "$_lmbs_config/font-last-boot-success.conf" 2>/dev/null || true
    type _luoshu_safety_log >/dev/null 2>&1 && _luoshu_safety_log INFO 'Android 已完成开机且元模块挂载验证通过，字体负载事务确认成功'
}

luoshu_mount_status_json() {
    _lmsj_conf="$LUOSHU_MOUNT_MODDIR/config/mount_compat.conf"
    _lmsj_state=$(sed -n 's/^state=//p' "$_lmsj_conf" 2>/dev/null | head -n1)
    _lmsj_detail=$(sed -n 's/^detail=//p' "$_lmsj_conf" 2>/dev/null | head -n1 | sed 's/\\/\\\\/g; s/"/\\"/g')
    _lmsj_root=$(sed -n 's/^contentRoot=//p' "$_lmsj_conf" 2>/dev/null | head -n1 | sed 's/\\/\\\\/g; s/"/\\"/g')
    _lmsj_synced=$(sed -n 's/^synced=//p' "$_lmsj_conf" 2>/dev/null | head -n1)
    _lmsj_failed=$(sed -n 's/^failed=//p' "$_lmsj_conf" 2>/dev/null | head -n1)
    _lmsj_time=$(sed -n 's/^time=//p' "$_lmsj_conf" 2>/dev/null | head -n1)
    printf '{"manager":"%s","engine":"%s","state":"%s","detail":"%s","contentRoot":"%s","synced":%s,"failed":%s,"time":%s}' \
        "$(luoshu_detect_root_manager)" "$(luoshu_detect_mount_engine)" "${_lmsj_state:-unknown}" "$_lmsj_detail" "$_lmsj_root" \
        "${_lmsj_synced:-0}" "${_lmsj_failed:-0}" "${_lmsj_time:-0}"
}

_luoshu_hyperos_helper="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}/common/hyperos_global.sh"
[ -f "$_luoshu_hyperos_helper" ] && . "$_luoshu_hyperos_helper"
_luoshu_font_config_partitions="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}/common/font_config_partitions.sh"
[ -f "$_luoshu_font_config_partitions" ] && . "$_luoshu_font_config_partitions"
