#!/system/bin/sh
# LuoShu metamodule compatibility layer.
#
# The canonical module tree lives under /data/adb/modules/LuoShu. Some
# metamodules use a second persistent content tree, while others read the
# canonical tree directly. This file detects that contract, updates payloads
# transactionally, and verifies every partition after reboot.
set +e

LUOSHU_MOUNT_MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
LUOSHU_MOUNT_LOG="${LUOSHU_MOUNT_LOG:-$LUOSHU_MOUNT_MODDIR/logs/mount_compat.log}"
LUOSHU_MOUNT_LOCK="$LUOSHU_MOUNT_MODDIR/.mount_compat.lock"
LUOSHU_MOUNT_TIMEOUT="${LUOSHU_MOUNT_TIMEOUT:-55}"
LUOSHU_MOUNT_PREFLIGHT_ERROR=''
LUOSHU_MOUNT_DETECTION_WARNING=''
LUOSHU_MOUNT_STARTED_AT=0
LUOSHU_MOUNT_DEADLINE=0

case "$LUOSHU_MOUNT_TIMEOUT" in
    ''|*[!0-9]*) LUOSHU_MOUNT_TIMEOUT=55 ;;
esac
if [ -z "${LUOSHU_META_TEST_ENGINE:-}" ] && [ "$LUOSHU_MOUNT_TIMEOUT" -lt 10 ] 2>/dev/null; then
    LUOSHU_MOUNT_TIMEOUT=10
fi
[ "$LUOSHU_MOUNT_TIMEOUT" -ge 1 ] 2>/dev/null || LUOSHU_MOUNT_TIMEOUT=1
[ "$LUOSHU_MOUNT_TIMEOUT" -le 300 ] 2>/dev/null || LUOSHU_MOUNT_TIMEOUT=300

luoshu_mount_log() {
    _lml_message="$1"
    mkdir -p "${LUOSHU_MOUNT_LOG%/*}" 2>/dev/null || true
    printf '[%s] %s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" \
        "$_lml_message" >> "$LUOSHU_MOUNT_LOG" 2>/dev/null || true
}

luoshu_module_id() {
    _lmi_id=$(sed -n 's/^id=//p' "$LUOSHU_MOUNT_MODDIR/module.prop" 2>/dev/null | head -n1 | tr -d '\r\n')
    [ -n "$_lmi_id" ] || _lmi_id=${LUOSHU_MOUNT_MODDIR##*/}
    printf '%s\n' "$_lmi_id"
}

luoshu_payload_partitions() {
    printf '%s\n' 'system system_ext product vendor odm oem my_product my_engineering my_company my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust hw_product'
}

luoshu_detect_root_manager() {
    if [ -n "${APATCH:-}" ] || [ -d /data/adb/ap ] || [ -d /data/adb/apatch ]; then
        printf 'APatch\n'
    elif [ -n "${KSU:-}" ] || [ -d /data/adb/ksu ]; then
        printf 'KernelSU\n'
    elif [ -n "${MAGISK_VER_CODE:-}" ] || [ -d /data/adb/magisk ]; then
        printf 'Magisk\n'
    else
        printf 'unknown\n'
    fi
}

_luoshu_module_prop_id() {
    sed -n 's/^id=//p' "$1/module.prop" 2>/dev/null | head -n1 | tr -d '\r\n'
}

_luoshu_module_enabled() {
    [ -f "$1/module.prop" ] && [ ! -e "$1/disable" ] && [ ! -e "$1/remove" ]
}

_luoshu_module_metadata_matches() {
    _lmmm_path="$1"
    shift
    _luoshu_module_enabled "$_lmmm_path" || return 1
    _lmmm_metadata=$(sed -n 's/^\(id\|name\|description\)=/\1=/p' "$_lmmm_path/module.prop" 2>/dev/null \
        | tr '[:upper:]' '[:lower:]' | tr '\n' ' ')
    for _lmmm_token in "$@"; do
        case "$_lmmm_metadata" in
            *"$_lmmm_token"*) return 0 ;;
        esac
    done
    return 1
}

luoshu_mountpoint_ready() {
    _lmr_path="$1"
    [ -n "${LUOSHU_META_TEST_ROOT:-}" ] && return 0
    [ -e "$_lmr_path" ] || return 1
    if command -v mountpoint >/dev/null 2>&1; then
        mountpoint -q "$_lmr_path" 2>/dev/null && return 0
    fi
    awk -v path="$_lmr_path" '$2 == path { found=1 } END { exit !found }' /proc/mounts 2>/dev/null
}

_luoshu_magic_mount_present() {
    for _lmmp_path in /data/adb/modules/*; do
        [ -d "$_lmmp_path" ] || continue
        _luoshu_module_metadata_matches "$_lmmp_path" \
            magic_mount magic-mount 'magic mount' id=meta-mm && return 0
    done
    [ -f /data/adb/magic_mount/config.toml ] && {
        [ -x /data/adb/metamodule/meta-mm ] ||
        [ -x /data/adb/metamodule/meta-mm-rs ] ||
        [ -x /data/adb/modules/magic_mount_rs/meta-mm ]
    }
}

_luoshu_mountify_present() {
    for _lmp_path in \
        /data/adb/modules/mountify \
        /data/adb/modules/Mountify \
        /data/adb/modules/*mountify*; do
        [ -d "$_lmp_path" ] || continue
        _luoshu_module_metadata_matches "$_lmp_path" mountify && return 0
    done
    return 1
}

_luoshu_hybrid_mount_present() {
    command -v hybrid-mount >/dev/null 2>&1 && return 0
    for _lhmp_path in \
        /data/adb/modules/meta-hybrid_mount \
        /data/adb/modules/hybrid_mount \
        /data/adb/modules/*hybrid*mount*; do
        [ -d "$_lhmp_path" ] || continue
        _luoshu_module_metadata_matches "$_lhmp_path" \
            hybrid_mount hybrid-mount 'hybrid mount' && return 0
    done
    return 1
}

luoshu_hybrid_backend() {
    if [ -n "${LUOSHU_META_TEST_BACKEND:-}" ]; then
        printf '%s\n' "$LUOSHU_META_TEST_BACKEND"
        return 0
    fi

    for _lhb_file in \
        /data/adb/hybrid-mount/config.toml \
        /data/adb/hybrid-mount/config.conf \
        /data/adb/modules/meta-hybrid_mount/config.toml \
        /data/adb/modules/meta-hybrid_mount/config.conf \
        /data/adb/modules/hybrid_mount/config.toml; do
        [ -f "$_lhb_file" ] || continue
        _lhb_value=$(sed -n 's/^[[:space:]]*\(backend\|mount_backend\|mount_mode\|mode\)[[:space:]]*=[[:space:]]*//p' "$_lhb_file" 2>/dev/null \
            | tail -n1 | cut -d'#' -f1 | tr -d "\"'[:space:]" | tr '[:upper:]' '[:lower:]')
        case "$_lhb_value" in
            *overlay*) printf 'overlayfs\n'; return 0 ;;
            *magic*) printf 'magic-mount\n'; return 0 ;;
            *kasumi*) printf 'kasumi\n'; return 0 ;;
        esac
    done
    printf 'unknown\n'
}

_luoshu_meta_overlayfs_active() {
    _lmoa_id=$(_luoshu_module_prop_id /data/adb/metamodule)
    case "$_lmoa_id" in
        meta-overlay|meta-overlayfs|meta-overlayfsUltra) ;;
        *) return 1 ;;
    esac
    [ ! -e /data/adb/metamodule/disable ] || return 1
    [ ! -e /data/adb/metamodule/remove ] || return 1
    [ -d /data/adb/metamodule/mnt ] || return 1
    luoshu_mountpoint_ready /data/adb/metamodule/mnt && return 0
    [ -f /data/adb/metamodule/modules.img ] || [ -L /data/adb/metamodule ]
}

_luoshu_mount_candidates() {
    if [ -n "${LUOSHU_META_TEST_CANDIDATES:-}" ]; then
        printf '%s\n' "$LUOSHU_META_TEST_CANDIDATES"
        return 0
    fi

    _lmc_candidates=''
    _luoshu_meta_overlayfs_active && _lmc_candidates="$_lmc_candidates meta-overlayfs"
    _luoshu_hybrid_mount_present && _lmc_candidates="$_lmc_candidates hybrid-mount"
    _luoshu_mountify_present && _lmc_candidates="$_lmc_candidates mountify"
    _luoshu_magic_mount_present && _lmc_candidates="$_lmc_candidates magic-mount"
    printf '%s\n' "$_lmc_candidates"
}

luoshu_mount_detection_warning() {
    _lmdw_candidates=$(_luoshu_mount_candidates)
    _lmdw_count=$(printf '%s\n' "$_lmdw_candidates" | awk '{ print NF }')
    [ "${_lmdw_count:-0}" -le 1 ] && return 0
    printf '检测到多个已启用挂载模块：%s\n' \
        "$(printf '%s\n' "$_lmdw_candidates" | sed 's/^ *//; s/  */、/g')"
}

luoshu_detect_mount_engine() {
    LUOSHU_MOUNT_DETECTION_WARNING=''
    if [ -n "${LUOSHU_META_TEST_ENGINE:-}" ]; then
        printf '%s\n' "$LUOSHU_META_TEST_ENGINE"
        return 0
    fi
    if [ -n "${MODULE_CONTENT_DIR:-}" ] && [ -n "${MODULE_METADATA_DIR:-}" ]; then
        printf 'dual-dir-metamodule\n'
        return 0
    fi

    _ldme_candidates=$(_luoshu_mount_candidates)
    _ldme_count=$(printf '%s\n' "$_ldme_candidates" | awk '{ print NF }')
    if [ "${_ldme_count:-0}" -gt 1 ]; then
        LUOSHU_MOUNT_DETECTION_WARNING=$(luoshu_mount_detection_warning)
        luoshu_mount_log "$LUOSHU_MOUNT_DETECTION_WARNING"
    fi

    case " $_ldme_candidates " in
        *' meta-overlayfs '*) printf 'meta-overlayfs\n' ;;
        *' hybrid-mount '*) printf 'hybrid-mount\n' ;;
        *' mountify '*) printf 'mountify\n' ;;
        *' magic-mount '*) printf 'magic-mount\n' ;;
        *) printf 'native-module-mount\n' ;;
    esac
}

luoshu_mount_backend() {
    _lmb_engine="${1:-$(luoshu_detect_mount_engine)}"
    case "$_lmb_engine" in
        hybrid-mount) luoshu_hybrid_backend ;;
        meta-overlayfs|dual-dir-metamodule) printf 'overlayfs\n' ;;
        mountify) printf 'mountify\n' ;;
        magic-mount|magic-mount-rs) printf 'magic-mount\n' ;;
        *) printf 'native\n' ;;
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

luoshu_meta_content_roots() {
    _lmcr_engine=$(luoshu_detect_mount_engine)
    case "$_lmcr_engine" in
        meta-overlayfs|dual-dir-metamodule) ;;
        *) return 0 ;;
    esac

    _lmcr_base=$(luoshu_dual_content_base)
    _lmcr_id=$(luoshu_module_id)
    case "$_lmcr_base" in
        */"$_lmcr_id") _lmcr_root="$_lmcr_base" ;;
        *) _lmcr_root="$_lmcr_base/$_lmcr_id" ;;
    esac
    [ "$_lmcr_root" = "$LUOSHU_MOUNT_MODDIR" ] || printf '%s\n' "$_lmcr_root"
}

luoshu_mount_lock_acquire() {
    if [ -f "$LUOSHU_MOUNT_LOCK" ]; then
        _lmla_pid=$(cat "$LUOSHU_MOUNT_LOCK" 2>/dev/null)
        if [ -n "$_lmla_pid" ] && kill -0 "$_lmla_pid" 2>/dev/null; then
            return 1
        fi
        rm -f "$LUOSHU_MOUNT_LOCK" 2>/dev/null || true
    fi
    printf '%s\n' "$$" > "$LUOSHU_MOUNT_LOCK" 2>/dev/null
}

luoshu_mount_lock_release() {
    rm -f "$LUOSHU_MOUNT_LOCK" 2>/dev/null || true
}

luoshu_mountify_value() {
    _lmv_key="$1"
    for _lmv_file in \
        /data/adb/mountify/config.sh \
        /data/adb/modules/mountify/config.sh \
        /data/adb/modules/Mountify/config.sh; do
        [ -f "$_lmv_file" ] || continue
        sed -n "s/^[[:space:]]*${_lmv_key}[[:space:]]*=[[:space:]]*[\"']\{0,1\}\([^\"'#[:space:]]*\).*/\1/p" "$_lmv_file" 2>/dev/null | tail -n1
        return 0
    done
    return 1
}

luoshu_mountify_module_selected() {
    _lmms_id=$(luoshu_module_id)
    _lmms_mode=$(luoshu_mountify_value mountify_mounts)
    [ -n "$_lmms_mode" ] || _lmms_mode=2
    [ "$_lmms_mode" != 1 ] && return 0

    for _lmms_file in \
        /data/adb/mountify/modules.txt \
        /data/adb/modules/mountify/modules.txt \
        /data/adb/modules/Mountify/modules.txt; do
        [ -f "$_lmms_file" ] || continue
        grep -Fxq "$_lmms_id" "$_lmms_file" 2>/dev/null && return 0
    done
    return 1
}

luoshu_recover_explicit_disable() {
    [ -e "$LUOSHU_MOUNT_MODDIR/disable" ] || return 0
    rm -f "$LUOSHU_MOUNT_MODDIR/disable" 2>/dev/null || {
        LUOSHU_MOUNT_PREFLIGHT_ERROR='无法解除洛书模块的 disable 标记'
        return 1
    }
    rm -f \
        "$LUOSHU_MOUNT_MODDIR/config/font-boot-failures" \
        "$LUOSHU_MOUNT_MODDIR/config/font-payload-quarantine.conf" 2>/dev/null || true
    luoshu_mount_log '已解除洛书 disable 标记'
}

luoshu_recover_magic_mount_markers() {
    _lrmm_engine="$1"
    case "$_lrmm_engine" in
        magic-mount|magic-mount-rs) ;;
        *) return 0 ;;
    esac

    for _lrmm_marker in skip_mount mount_error; do
        [ -e "$LUOSHU_MOUNT_MODDIR/$_lrmm_marker" ] || continue
        rm -f "$LUOSHU_MOUNT_MODDIR/$_lrmm_marker" 2>/dev/null || {
            LUOSHU_MOUNT_PREFLIGHT_ERROR="无法清理 Magic Mount 遗留标记：$_lrmm_marker"
            return 1
        }
    done
}

_luoshu_partition_has_payload() {
    _lphp_partition="$1"
    [ -d "$LUOSHU_MOUNT_MODDIR/$_lphp_partition" ] || return 1
    find "$LUOSHU_MOUNT_MODDIR/$_lphp_partition" -type f -print -quit 2>/dev/null | grep -q .
}

luoshu_used_partitions() {
    _lup_content_root="${1:-}"
    for _lup_partition in $(luoshu_payload_partitions); do
        if _luoshu_partition_has_payload "$_lup_partition"; then
            printf '%s\n' "$_lup_partition"
        elif [ -n "$_lup_content_root" ] && [ -e "$_lup_content_root/$_lup_partition" ]; then
            printf '%s\n' "$_lup_partition"
        fi
    done
}

_luoshu_meta_declared_partitions() {
    printf '%s\n' "${LUOSHU_META_EXTRA_PARTITIONS:-}"
    for _lmdp_file in \
        /data/adb/metamodule/config.toml \
        /data/adb/metamodule/config.conf \
        /data/adb/modules/meta-overlayfs/config.toml; do
        [ -f "$_lmdp_file" ] || continue
        awk -F'"' '/partition|mount/ { for (i=2; i<=NF; i+=2) if ($i ~ /^[A-Za-z0-9_]+$/) print $i }' "$_lmdp_file"
    done
}

luoshu_meta_partition_supported() {
    _lmps_partition="$1"
    case "$_lmps_partition" in
        system|vendor|product|system_ext|odm|oem) return 0 ;;
    esac
    _lmps_declared=$(_luoshu_meta_declared_partitions | tr '\n' ' ')
    case " $_lmps_declared " in
        *" $_lmps_partition "*) return 0 ;;
    esac
    return 1
}

luoshu_engine_partitions() {
    _lep_engine="${1:-$(luoshu_detect_mount_engine)}"
    case "$_lep_engine" in
        meta-overlayfs|dual-dir-metamodule)
            for _lep_partition in $(luoshu_payload_partitions); do
                luoshu_meta_partition_supported "$_lep_partition" && printf '%s\n' "$_lep_partition"
            done
            ;;
        *) luoshu_payload_partitions ;;
    esac
}

luoshu_magic_mount_ensure_partitions() {
    _lmep_engine="$1"
    case "$_lmep_engine" in
        magic-mount|magic-mount-rs) ;;
        *) return 0 ;;
    esac

    _lmep_config="${LUOSHU_MAGIC_MOUNT_CONFIG:-/data/adb/magic_mount/config.toml}"
    [ -f "$_lmep_config" ] || return 0
    _lmep_lock="$_lmep_config.luoshu.lock"
    if [ -f "$_lmep_lock" ]; then
        _lmep_pid=$(cat "$_lmep_lock" 2>/dev/null)
        if [ -n "$_lmep_pid" ] && kill -0 "$_lmep_pid" 2>/dev/null; then
            LUOSHU_MOUNT_PREFLIGHT_ERROR='Magic Mount 配置正在被修改'
            return 1
        fi
        rm -f "$_lmep_lock" 2>/dev/null || true
    fi
    printf '%s\n' "$$" > "$_lmep_lock" 2>/dev/null || return 1

    _lmep_current=$(awk '
        /^[[:space:]]*partitions[[:space:]]*=/ { capture=1 }
        capture { printf "%s ", $0 }
        capture && /]/ { exit }
    ' "$_lmep_config" 2>/dev/null)
    _lmep_list=''
    for _lmep_item in $(printf '%s\n' "$_lmep_current" | awk -F'"' '{ for (i=2; i<=NF; i+=2) print $i }'); do
        case "$_lmep_item" in ''|*[!A-Za-z0-9_]*) continue ;; esac
        case " $_lmep_list " in
            *" $_lmep_item "*) ;;
            *) _lmep_list="$_lmep_list $_lmep_item" ;;
        esac
    done

    _lmep_added=''
    for _lmep_partition in $(luoshu_used_partitions); do
        [ "$_lmep_partition" = system ] && continue
        case " $_lmep_list " in
            *" $_lmep_partition "*) ;;
            *)
                _lmep_list="$_lmep_list $_lmep_partition"
                _lmep_added="${_lmep_added}${_lmep_added:+,}$_lmep_partition"
                ;;
        esac
    done
    if [ -z "$_lmep_added" ]; then
        rm -f "$_lmep_lock" 2>/dev/null || true
        return 0
    fi

    _lmep_array=''
    for _lmep_item in $_lmep_list; do
        _lmep_array="${_lmep_array}${_lmep_array:+, }\"$_lmep_item\""
    done
    _lmep_temp="$_lmep_config.luoshu.$$"
    [ -f "$_lmep_config.luoshu.bak" ] || cp -pf "$_lmep_config" "$_lmep_config.luoshu.bak" 2>/dev/null || true
    awk -v replacement="partitions = [$_lmep_array]" '
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
        rm -f "$_lmep_temp" "$_lmep_lock" 2>/dev/null || true
        LUOSHU_MOUNT_PREFLIGHT_ERROR='无法更新 Magic Mount 配置'
        return 1
    }
    if [ "$(grep -c '^[[:space:]]*partitions[[:space:]]*=' "$_lmep_temp" 2>/dev/null)" -ne 1 ]; then
        rm -f "$_lmep_temp" "$_lmep_lock" 2>/dev/null || true
        LUOSHU_MOUNT_PREFLIGHT_ERROR='Magic Mount 配置校验失败'
        return 1
    fi
    chmod --reference="$_lmep_config" "$_lmep_temp" 2>/dev/null || chmod 0644 "$_lmep_temp" 2>/dev/null || true
    mv -f "$_lmep_temp" "$_lmep_config" 2>/dev/null || {
        rm -f "$_lmep_temp" "$_lmep_lock" 2>/dev/null || true
        LUOSHU_MOUNT_PREFLIGHT_ERROR='无法提交 Magic Mount 配置'
        return 1
    }
    rm -f "$_lmep_lock" 2>/dev/null || true
    luoshu_mount_log "Magic Mount 增加分区：$_lmep_added"
}

luoshu_mount_preflight() {
    _lmp_active="${1:-unknown}"
    LUOSHU_MOUNT_PREFLIGHT_ERROR=''
    _lmp_engine=$(luoshu_detect_mount_engine)
    _lmp_manager=$(luoshu_detect_root_manager)

    luoshu_recover_explicit_disable || return 1
    [ "$_lmp_active" = default ] || luoshu_recover_magic_mount_markers "$_lmp_engine" || return 1
    [ ! -e "$LUOSHU_MOUNT_MODDIR/remove" ] || {
        LUOSHU_MOUNT_PREFLIGHT_ERROR='模块存在 remove 标记'
        return 1
    }
    if [ "$_lmp_active" != default ] && [ -e "$LUOSHU_MOUNT_MODDIR/mount_error" ]; then
        LUOSHU_MOUNT_PREFLIGHT_ERROR='模块存在 mount_error 标记'
        return 1
    fi

    case "$_lmp_engine" in
        meta-overlayfs|dual-dir-metamodule|hybrid-mount|magic-mount|magic-mount-rs)
            if [ "$_lmp_active" != default ] && [ -e "$LUOSHU_MOUNT_MODDIR/skip_mount" ]; then
                LUOSHU_MOUNT_PREFLIGHT_ERROR='检测到 skip_mount'
                return 1
            fi
            ;;
        mountify)
            if [ "$_lmp_active" != default ]; then
                if [ "$_lmp_manager" = Magisk ] && [ -e "$LUOSHU_MOUNT_MODDIR/skip_mountify" ]; then
                    LUOSHU_MOUNT_PREFLIGHT_ERROR='检测到 skip_mountify'
                    return 1
                fi
                luoshu_mountify_module_selected || {
                    LUOSHU_MOUNT_PREFLIGHT_ERROR='Mountify 白名单未包含 LuoShu'
                    return 1
                }
            fi
            ;;
    esac

    [ "$_lmp_active" = default ] || luoshu_magic_mount_ensure_partitions "$_lmp_engine" || return 1

    case "$_lmp_engine" in
        meta-overlayfs|dual-dir-metamodule)
            _lmp_base=$(luoshu_dual_content_base)
            luoshu_mountpoint_ready "$_lmp_base" || {
                LUOSHU_MOUNT_PREFLIGHT_ERROR="元模块内容镜像未挂载：$_lmp_base"
                return 1
            }
            [ -w "$_lmp_base" ] || {
                LUOSHU_MOUNT_PREFLIGHT_ERROR="元模块内容镜像不可写：$_lmp_base"
                return 1
            }
            _lmp_unsupported=''
            for _lmp_partition in $(luoshu_used_partitions); do
                luoshu_meta_partition_supported "$_lmp_partition" || \
                    _lmp_unsupported="${_lmp_unsupported}${_lmp_unsupported:+,}$_lmp_partition"
            done
            [ -z "$_lmp_unsupported" ] || {
                LUOSHU_MOUNT_PREFLIGHT_ERROR="meta-overlayfs 未声明支持分区：$_lmp_unsupported"
                return 1
            }
            ;;
    esac
}

_luoshu_now() {
    date +%s 2>/dev/null || echo 0
}

luoshu_mount_budget_begin() {
    LUOSHU_MOUNT_STARTED_AT=$(_luoshu_now)
    LUOSHU_MOUNT_DEADLINE=$((LUOSHU_MOUNT_STARTED_AT + LUOSHU_MOUNT_TIMEOUT))
}

luoshu_mount_remaining() {
    _lmr_now=$(_luoshu_now)
    _lmr_left=$((LUOSHU_MOUNT_DEADLINE - _lmr_now))
    [ "$_lmr_left" -gt 0 ] || _lmr_left=0
    printf '%s\n' "$_lmr_left"
}

luoshu_kill_tree() {
    _lkt_pid="$1"
    if command -v pgrep >/dev/null 2>&1; then
        for _lkt_child in $(pgrep -P "$_lkt_pid" 2>/dev/null); do
            luoshu_kill_tree "$_lkt_child"
        done
    fi
    kill -TERM "$_lkt_pid" 2>/dev/null || true
    sleep 1
    kill -KILL "$_lkt_pid" 2>/dev/null || true
}

luoshu_run_bounded() {
    _lrb_seconds="$1"
    shift
    [ "$_lrb_seconds" -gt 0 ] || return 124

    if command -v timeout >/dev/null 2>&1; then
        timeout "$_lrb_seconds" "$@"
        return $?
    fi
    if command -v toybox >/dev/null 2>&1 && toybox timeout --help >/dev/null 2>&1; then
        toybox timeout "$_lrb_seconds" "$@"
        return $?
    fi

    "$@" &
    _lrb_pid=$!
    _lrb_elapsed=0
    while kill -0 "$_lrb_pid" 2>/dev/null && [ "$_lrb_elapsed" -lt "$_lrb_seconds" ]; do
        sleep 1
        _lrb_elapsed=$((_lrb_elapsed + 1))
    done
    if kill -0 "$_lrb_pid" 2>/dev/null; then
        luoshu_kill_tree "$_lrb_pid"
        wait "$_lrb_pid" 2>/dev/null || true
        return 124
    fi
    wait "$_lrb_pid"
}

luoshu_copy_tree_bounded() {
    _lctb_source="$1"
    _lctb_destination="$2"
    _lctb_remaining=$(luoshu_mount_remaining)
    [ "$_lctb_remaining" -gt 0 ] || return 124
    luoshu_run_bounded "$_lctb_remaining" cp -af "$_lctb_source" "$_lctb_destination"
}

luoshu_copy_partition_atomic() {
    _lcpa_source="$1"
    _lcpa_destination="$2"
    _lcpa_parent=${_lcpa_destination%/*}
    _lcpa_name=${_lcpa_destination##*/}
    _lcpa_temp="$_lcpa_parent/.${_lcpa_name}.luoshu.$$"
    _lcpa_backup="$_lcpa_parent/.${_lcpa_name}.luoshu-backup.$$"

    mkdir -p "$_lcpa_parent" 2>/dev/null || return 1
    rm -rf "$_lcpa_temp" "$_lcpa_backup" 2>/dev/null || true
    luoshu_copy_tree_bounded "$_lcpa_source" "$_lcpa_temp" || {
        _lcpa_result=$?
        rm -rf "$_lcpa_temp" 2>/dev/null || true
        return "$_lcpa_result"
    }
    chmod -R u=rwX,go=rX "$_lcpa_temp" 2>/dev/null || true

    if [ -e "$_lcpa_destination" ]; then
        mv "$_lcpa_destination" "$_lcpa_backup" 2>/dev/null || {
            rm -rf "$_lcpa_temp" 2>/dev/null || true
            return 1
        }
    fi
    if mv "$_lcpa_temp" "$_lcpa_destination" 2>/dev/null; then
        rm -rf "$_lcpa_backup" 2>/dev/null || true
        return 0
    fi

    rm -rf "$_lcpa_destination" 2>/dev/null || true
    [ ! -e "$_lcpa_backup" ] || mv "$_lcpa_backup" "$_lcpa_destination" 2>/dev/null || true
    rm -rf "$_lcpa_temp" 2>/dev/null || true
    return 1
}

_luoshu_probe_path() {
    if [ "$1" = system ]; then
        printf '/system/etc/luoshu/mount-probe.conf\n'
    else
        printf '/%s/etc/luoshu/mount-probe.conf\n' "$1"
    fi
}

luoshu_write_mount_probes() {
    _lwmp_active="${1:-unknown}"
    _lwmp_engine=$(luoshu_detect_mount_engine)
    _lwmp_id=$(luoshu_module_id)
    _lwmp_nonce="$(_luoshu_now)-$$"
    _lwmp_manifest="$LUOSHU_MOUNT_MODDIR/config/mount-probes-expected.conf"
    _lwmp_temp="$_lwmp_manifest.tmp.$$"
    _lwmp_count=0

    mkdir -p "$LUOSHU_MOUNT_MODDIR/config" 2>/dev/null || return 1
    : > "$_lwmp_temp" 2>/dev/null || return 1
    for _lwmp_partition in $(luoshu_used_partitions); do
        _lwmp_directory="$LUOSHU_MOUNT_MODDIR/$_lwmp_partition/etc/luoshu"
        mkdir -p "$_lwmp_directory" 2>/dev/null || return 1
        {
            printf 'id=%s\n' "$_lwmp_id"
            printf 'font=%s\n' "$_lwmp_active"
            printf 'engine=%s\n' "$_lwmp_engine"
            printf 'partition=%s\n' "$_lwmp_partition"
            printf 'nonce=%s-%s\n' "$_lwmp_nonce" "$_lwmp_partition"
        } > "$_lwmp_directory/mount-probe.conf.tmp.$$" 2>/dev/null || return 1
        mv -f "$_lwmp_directory/mount-probe.conf.tmp.$$" "$_lwmp_directory/mount-probe.conf" 2>/dev/null || return 1
        chmod 0644 "$_lwmp_directory/mount-probe.conf" 2>/dev/null || true
        printf '%s|%s-%s|%s\n' \
            "$_lwmp_partition" "$_lwmp_nonce" "$_lwmp_partition" \
            "$(_luoshu_probe_path "$_lwmp_partition")" >> "$_lwmp_temp"
        _lwmp_count=$((_lwmp_count + 1))
    done

    if [ "$_lwmp_count" -eq 0 ]; then
        _lwmp_directory="$LUOSHU_MOUNT_MODDIR/system/etc/luoshu"
        mkdir -p "$_lwmp_directory" 2>/dev/null || return 1
        {
            printf 'id=%s\n' "$_lwmp_id"
            printf 'font=%s\n' "$_lwmp_active"
            printf 'engine=%s\n' "$_lwmp_engine"
            printf 'partition=system\n'
            printf 'nonce=%s-system\n' "$_lwmp_nonce"
        } > "$_lwmp_directory/mount-probe.conf" 2>/dev/null || return 1
        printf 'system|%s-system|/system/etc/luoshu/mount-probe.conf\n' "$_lwmp_nonce" >> "$_lwmp_temp"
    fi

    mv -f "$_lwmp_temp" "$_lwmp_manifest" 2>/dev/null || return 1
    chmod 0644 "$_lwmp_manifest" 2>/dev/null || true
    cp -f \
        "$LUOSHU_MOUNT_MODDIR/system/etc/luoshu/mount-probe.conf" \
        "$LUOSHU_MOUNT_MODDIR/config/mount-probe-expected.conf" 2>/dev/null || true
}

# Compatibility with callers from earlier releases.
luoshu_write_mount_probe() {
    luoshu_write_mount_probes "$@"
}

luoshu_mount_record() {
    _lmr_state="$1"
    _lmr_detail="$2"
    _lmr_root="$3"
    _lmr_synced="$4"
    _lmr_failed="$5"
    _lmr_partitions="${6:-}"
    _lmr_verified="${7:-}"
    _lmr_failed_partitions="${8:-}"
    _lmr_unsupported="${9:-}"
    _lmr_time=$(_luoshu_now)
    _lmr_duration=0
    [ "$LUOSHU_MOUNT_STARTED_AT" -gt 0 ] && _lmr_duration=$((_lmr_time - LUOSHU_MOUNT_STARTED_AT))
    _lmr_warning="$LUOSHU_MOUNT_DETECTION_WARNING"
    [ -n "$_lmr_warning" ] || _lmr_warning=$(luoshu_mount_detection_warning)

    mkdir -p "$LUOSHU_MOUNT_MODDIR/config" 2>/dev/null || true
    {
        printf 'manager=%s\n' "$(luoshu_detect_root_manager)"
        printf 'engine=%s\n' "$(luoshu_detect_mount_engine)"
        printf 'backend=%s\n' "$(luoshu_mount_backend)"
        printf 'state=%s\n' "$_lmr_state"
        printf 'detail=%s\n' "$_lmr_detail"
        printf 'warning=%s\n' "$_lmr_warning"
        printf 'contentRoot=%s\n' "$_lmr_root"
        printf 'synced=%s\n' "$_lmr_synced"
        printf 'failed=%s\n' "$_lmr_failed"
        printf 'partitions=%s\n' "$_lmr_partitions"
        printf 'verifiedPartitions=%s\n' "$_lmr_verified"
        printf 'failedPartitions=%s\n' "$_lmr_failed_partitions"
        printf 'unsupportedPartitions=%s\n' "$_lmr_unsupported"
        printf 'durationSeconds=%s\n' "$_lmr_duration"
        printf 'time=%s\n' "$_lmr_time"
    } > "$LUOSHU_MOUNT_MODDIR/config/mount_compat.conf.tmp.$$" 2>/dev/null && \
        mv -f "$LUOSHU_MOUNT_MODDIR/config/mount_compat.conf.tmp.$$" \
            "$LUOSHU_MOUNT_MODDIR/config/mount_compat.conf" 2>/dev/null || true
}

luoshu_sync_mount_payload() {
    _lsmp_active="${1:-$(head -n1 "$LUOSHU_MOUNT_MODDIR/config/active_font.conf" 2>/dev/null)}"
    [ -n "$_lsmp_active" ] || _lsmp_active=default
    _lsmp_engine=$(luoshu_detect_mount_engine)
    _lsmp_synced=0
    _lsmp_failed=0
    _lsmp_root=''
    _lsmp_partitions=''
    _lsmp_failed_partitions=''

    luoshu_mount_budget_begin
    luoshu_mount_lock_acquire || return 1
    trap 'luoshu_mount_lock_release' EXIT HUP INT TERM

    if ! luoshu_mount_preflight "$_lsmp_active"; then
        luoshu_mount_record failed "$LUOSHU_MOUNT_PREFLIGHT_ERROR" '' 0 1
        luoshu_mount_lock_release
        trap - EXIT HUP INT TERM
        return 1
    fi
    if ! luoshu_write_mount_probes "$_lsmp_active"; then
        luoshu_mount_record failed '无法生成分区挂载探针' '' 0 1
        luoshu_mount_lock_release
        trap - EXIT HUP INT TERM
        return 1
    fi

    case "$_lsmp_engine" in
        meta-overlayfs|dual-dir-metamodule)
            _lsmp_root=$(luoshu_meta_content_roots | head -n1)
            [ -n "$_lsmp_root" ] && mkdir -p "$_lsmp_root" 2>/dev/null || _lsmp_failed=1
            if [ "$_lsmp_failed" -eq 0 ]; then
                for _lsmp_partition in $(luoshu_used_partitions "$_lsmp_root"); do
                    _lsmp_partitions="${_lsmp_partitions}${_lsmp_partitions:+,}$_lsmp_partition"
                    _lsmp_source="$LUOSHU_MOUNT_MODDIR/$_lsmp_partition"
                    _lsmp_destination="$_lsmp_root/$_lsmp_partition"
                    if [ -d "$_lsmp_source" ]; then
                        if luoshu_copy_partition_atomic "$_lsmp_source" "$_lsmp_destination"; then
                            _lsmp_synced=$((_lsmp_synced + 1))
                        else
                            _lsmp_result=$?
                            _lsmp_failed=$((_lsmp_failed + 1))
                            _lsmp_failed_partitions="${_lsmp_failed_partitions}${_lsmp_failed_partitions:+,}$_lsmp_partition"
                            if [ "$_lsmp_result" -eq 124 ]; then
                                LUOSHU_MOUNT_PREFLIGHT_ERROR="元模块同步超过 ${LUOSHU_MOUNT_TIMEOUT} 秒总时限"
                            fi
                            break
                        fi
                    elif ! rm -rf "$_lsmp_destination" 2>/dev/null; then
                        _lsmp_failed=$((_lsmp_failed + 1))
                        _lsmp_failed_partitions="${_lsmp_failed_partitions}${_lsmp_failed_partitions:+,}$_lsmp_partition"
                        break
                    fi
                done
            fi
            ;;
        *)
            for _lsmp_partition in $(luoshu_used_partitions); do
                _lsmp_partitions="${_lsmp_partitions}${_lsmp_partitions:+,}$_lsmp_partition"
            done
            ;;
    esac

    luoshu_mount_lock_release
    trap - EXIT HUP INT TERM
    if [ "$_lsmp_failed" -gt 0 ]; then
        luoshu_mount_record failed \
            "${LUOSHU_MOUNT_PREFLIGHT_ERROR:-元模块内容更新失败，已保留旧分区目录}" \
            "$_lsmp_root" "$_lsmp_synced" "$_lsmp_failed" \
            "$_lsmp_partitions" '' "$_lsmp_failed_partitions"
        return 1
    fi

    case "$_lsmp_engine" in
        meta-overlayfs|dual-dir-metamodule)
            luoshu_mount_record prepared \
                '已原子写入元模块真实内容镜像，等待重启逐分区验证' \
                "$_lsmp_root" "$_lsmp_synced" 0 "$_lsmp_partitions"
            ;;
        *)
            luoshu_mount_record prepared \
                '当前引擎直接读取标准模块目录，等待重启逐分区验证' \
                '' 0 0 "$_lsmp_partitions"
            ;;
    esac
    luoshu_mount_log \
        "engine=$_lsmp_engine backend=$(luoshu_mount_backend "$_lsmp_engine") synced=$_lsmp_synced partitions=$_lsmp_partitions"
}

luoshu_restore_mount_payload() {
    _lrmp_active=$(head -n1 "$LUOSHU_MOUNT_MODDIR/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_lrmp_active" ] || _lrmp_active=default
    luoshu_sync_mount_payload "$_lrmp_active"
}

luoshu_mount_verify_active() {
    _lmva_active="${1:-$(head -n1 "$LUOSHU_MOUNT_MODDIR/config/active_font.conf" 2>/dev/null)}"
    [ -n "$_lmva_active" ] || _lmva_active=default
    if [ "$_lmva_active" = default ]; then
        luoshu_mount_record verified '系统默认字体无需挂载验证' '' 0 0
        return 0
    fi

    _lmva_manifest="$LUOSHU_MOUNT_MODDIR/config/mount-probes-expected.conf"
    if [ ! -s "$_lmva_manifest" ]; then
        luoshu_mount_record unverified '缺少分区挂载探针清单' '' 0 1 '' '' manifest
        return 1
    fi

    _lmva_partitions=''
    _lmva_verified=''
    _lmva_failed=''
    _lmva_failed_count=0
    while IFS='|' read -r _lmva_partition _lmva_expected _lmva_visible_path; do
        [ -n "$_lmva_partition" ] || continue
        _lmva_partitions="${_lmva_partitions}${_lmva_partitions:+,}$_lmva_partition"
        if [ -n "${LUOSHU_VISIBLE_PROBE:-}" ] && [ "$_lmva_partition" = system ]; then
            _lmva_visible="$LUOSHU_VISIBLE_PROBE"
        elif [ -n "${LUOSHU_VISIBLE_PROBE_ROOT:-}" ]; then
            _lmva_visible="${LUOSHU_VISIBLE_PROBE_ROOT%/}$_lmva_visible_path"
        else
            _lmva_visible="$_lmva_visible_path"
        fi
        _lmva_seen=$(sed -n 's/^nonce=//p' "$_lmva_visible" 2>/dev/null | head -n1)
        _lmva_seen_partition=$(sed -n 's/^partition=//p' "$_lmva_visible" 2>/dev/null | head -n1)
        if [ "$_lmva_expected" = "$_lmva_seen" ] && [ "$_lmva_partition" = "$_lmva_seen_partition" ]; then
            _lmva_verified="${_lmva_verified}${_lmva_verified:+,}$_lmva_partition"
        else
            _lmva_failed="${_lmva_failed}${_lmva_failed:+,}$_lmva_partition"
            _lmva_failed_count=$((_lmva_failed_count + 1))
        fi
    done < "$_lmva_manifest"

    if [ "$_lmva_failed_count" -eq 0 ]; then
        luoshu_mount_record verified \
            '所有字体负载分区均已从系统路径读取' '' 0 0 \
            "$_lmva_partitions" "$_lmva_verified"
        return 0
    fi
    luoshu_mount_record unverified \
        "部分字体分区未挂载：$_lmva_failed" '' 0 "$_lmva_failed_count" \
        "$_lmva_partitions" "$_lmva_verified" "$_lmva_failed"
    return 1
}

# A completed Android boot is not enough. The selected mount engine must expose
# every generated probe before the payload transaction is trusted.
font_config_mark_boot_success() {
    _lmbs_config="${CONFIG_DIR:-$LUOSHU_MOUNT_MODDIR/config}"
    _lmbs_state=$(sed -n 's/^state=//p' "$_lmbs_config/font-payload-boot.conf" 2>/dev/null | head -n1)
    [ "$_lmbs_state" = booting ] || return 0
    _lmbs_font=$(sed -n 's/^font=//p' "$_lmbs_config/font-payload-boot.conf" 2>/dev/null | head -n1)
    luoshu_mount_verify_active "${_lmbs_font:-unknown}" || return 1
    printf 'state=confirmed\nfont=%s\ntime=%s\n' \
        "${_lmbs_font:-unknown}" "$(_luoshu_now)" \
        > "$_lmbs_config/font-payload-boot.conf.tmp.$$" 2>/dev/null || return 1
    mv -f "$_lmbs_config/font-payload-boot.conf.tmp.$$" \
        "$_lmbs_config/font-payload-boot.conf" 2>/dev/null || return 1
    rm -f \
        "$_lmbs_config/font-boot-failures" \
        "$_lmbs_config/font-payload-quarantine.conf" 2>/dev/null || true
    printf 'time=%s\n' "$(_luoshu_now)" > "$_lmbs_config/font-last-boot-success.conf" 2>/dev/null || true
    chmod 0644 \
        "$_lmbs_config/font-payload-boot.conf" \
        "$_lmbs_config/font-last-boot-success.conf" 2>/dev/null || true
}

_luoshu_json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

luoshu_mount_status_json() {
    _lmsj_config="$LUOSHU_MOUNT_MODDIR/config/mount_compat.conf"
    _lmsj_get() {
        sed -n "s/^$1=//p" "$_lmsj_config" 2>/dev/null | head -n1
    }
    _lmsj_state=$(_lmsj_get state)
    _lmsj_detail=$(_lmsj_get detail)
    _lmsj_warning=$(_lmsj_get warning)
    _lmsj_root=$(_lmsj_get contentRoot)
    _lmsj_backend=$(_lmsj_get backend)
    _lmsj_partitions=$(_lmsj_get partitions)
    _lmsj_verified=$(_lmsj_get verifiedPartitions)
    _lmsj_failed_partitions=$(_lmsj_get failedPartitions)
    _lmsj_unsupported=$(_lmsj_get unsupportedPartitions)
    _lmsj_synced=$(_lmsj_get synced)
    _lmsj_failed=$(_lmsj_get failed)
    _lmsj_duration=$(_lmsj_get durationSeconds)
    _lmsj_time=$(_lmsj_get time)

    printf '{"manager":"%s","engine":"%s","backend":"%s","state":"%s","detail":"%s","warning":"%s","contentRoot":"%s","partitions":"%s","verifiedPartitions":"%s","failedPartitions":"%s","unsupportedPartitions":"%s","synced":%s,"failed":%s,"durationSeconds":%s,"time":%s}' \
        "$(_luoshu_json_escape "$(luoshu_detect_root_manager)")" \
        "$(_luoshu_json_escape "$(luoshu_detect_mount_engine)")" \
        "$(_luoshu_json_escape "${_lmsj_backend:-$(luoshu_mount_backend)}")" \
        "$(_luoshu_json_escape "${_lmsj_state:-unknown}")" \
        "$(_luoshu_json_escape "$_lmsj_detail")" \
        "$(_luoshu_json_escape "$_lmsj_warning")" \
        "$(_luoshu_json_escape "$_lmsj_root")" \
        "$(_luoshu_json_escape "$_lmsj_partitions")" \
        "$(_luoshu_json_escape "$_lmsj_verified")" \
        "$(_luoshu_json_escape "$_lmsj_failed_partitions")" \
        "$(_luoshu_json_escape "$_lmsj_unsupported")" \
        "${_lmsj_synced:-0}" "${_lmsj_failed:-0}" \
        "${_lmsj_duration:-0}" "${_lmsj_time:-0}"
}

_luoshu_hyperos_helper="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}/common/hyperos_global.sh"
[ -f "$_luoshu_hyperos_helper" ] && . "$_luoshu_hyperos_helper"
_luoshu_font_config_partitions="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}/common/font_config_partitions.sh"
[ -f "$_luoshu_font_config_partitions" ] && . "$_luoshu_font_config_partitions"

if [ "${0##*/}" = mount_compat.sh ]; then
    case "${1:-status}" in
        status)
            luoshu_mount_status_json
            printf '\n'
            ;;
        detect)
            printf 'engine=%s\n' "$(luoshu_detect_mount_engine)"
            printf 'backend=%s\n' "$(luoshu_mount_backend)"
            printf 'warning=%s\n' "$(luoshu_mount_detection_warning)"
            ;;
        verify)
            luoshu_mount_verify_active "${2:-}"
            ;;
        *)
            printf 'usage: %s {status|detect|verify [font]}\n' "$0" >&2
            exit 2
            ;;
    esac
fi
