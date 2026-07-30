#!/system/bin/sh
# LuoShu atomic self-mount transaction and strict boot visibility verification.
# Never leave a mixed ROM/LuoShu font tree visible: every required component
# succeeds together, otherwise every mount created by this attempt is rolled back.
set +e

# Legacy injected metamodule fixtures keep their strict per-partition verifier.
# Production never sets LUOSHU_META_TEST_ENGINE and always uses this atomic path.
case "${LUOSHU_META_TEST_ENGINE:-}" in
    ''|self-mount) ;;
    *) return 0 2>/dev/null || exit 0 ;;
esac

_luoshu_atomic_manifest() {
    _lsam_module=$(_luoshu_self_module)
    printf '%s/config/self-mount-required.conf\n' "$_lsam_module"
}

_luoshu_atomic_file_optional() {
    case "$1" in
        luoshu/mount-probe.conf) return 0 ;;
        *) return 1 ;;
    esac
}

_luoshu_atomic_missing_target_allowed() {
    _lsamta_rel="$1"
    _lsamta_mode="${2:-overlay}"
    _luoshu_atomic_file_optional "$_lsamta_rel" && return 0
    # A per-file bind can only replace an inode that already exists in the ROM
    # view. Payloads intentionally contain additive aliases for several ROM
    # families, so an alias absent on this device is not a failed replacement.
    # The caller still requires at least one real target per component, keeping
    # the transaction fail-closed when nothing on the device can be mounted.
    [ "$_lsamta_mode" = bind ]
}

_luoshu_atomic_real_target() {
    _lsart_path="$1"
    _lsart_real=''
    if command -v readlink >/dev/null 2>&1; then
        _lsart_real=$(readlink -f "$_lsart_path" 2>/dev/null)
    elif command -v busybox >/dev/null 2>&1; then
        _lsart_real=$(busybox readlink -f "$_lsart_path" 2>/dev/null)
    fi
    [ -n "$_lsart_real" ] || _lsart_real="$_lsart_path"
    printf '%s\n' "$_lsart_real"
}

_luoshu_atomic_target_seen() {
    _lsats_file="$1"
    _lsats_target="$2"
    [ -s "$_lsats_file" ] || return 1
    while IFS= read -r _lsats_seen; do
        [ "$_lsats_seen" = "$_lsats_target" ] && return 0
    done < "$_lsats_file"
    return 1
}

# Process real files before symlink aliases. Several OEM ROMs expose many font
# names as symlinks to one canonical variable font; binding an alias first would
# otherwise choose an arbitrary role for that shared mount target.
_luoshu_atomic_bind_file_order() {
    _lsabfo_source="$1"
    _lsabfo_target="$2"
    _lsabfo_output="$3"
    _lsabfo_all="${_lsabfo_output}.all"
    find "$_lsabfo_source" -type f 2>/dev/null > "$_lsabfo_all" || return 1
    : > "$_lsabfo_output" 2>/dev/null || return 1
    while IFS= read -r _lsabfo_src; do
        [ -n "$_lsabfo_src" ] || continue
        _lsabfo_rel=${_lsabfo_src#$_lsabfo_source/}
        [ -L "$_lsabfo_target/$_lsabfo_rel" ] || printf '%s\n' "$_lsabfo_src" >> "$_lsabfo_output"
    done < "$_lsabfo_all"
    while IFS= read -r _lsabfo_src; do
        [ -n "$_lsabfo_src" ] || continue
        _lsabfo_rel=${_lsabfo_src#$_lsabfo_source/}
        [ ! -L "$_lsabfo_target/$_lsabfo_rel" ] || printf '%s\n' "$_lsabfo_src" >> "$_lsabfo_output"
    done < "$_lsabfo_all"
    rm -f "$_lsabfo_all" 2>/dev/null || true
    return 0
}

_luoshu_atomic_hash_stream() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum 2>/dev/null | awk '{print $1}'
    elif command -v busybox >/dev/null 2>&1; then
        busybox sha256sum 2>/dev/null | awk '{print $1}'
    else
        cksum 2>/dev/null | awk '{print $1 ":" $2}'
    fi
}

_luoshu_atomic_file_size() {
    stat -c '%s' "$1" 2>/dev/null || wc -c < "$1" 2>/dev/null | tr -d '[:space:]'
}

_luoshu_atomic_quick_fingerprint() {
    _lsaqf_file="$1"
    [ -f "$_lsaqf_file" ] || return 1
    _lsaqf_size=$(_luoshu_atomic_file_size "$_lsaqf_file")
    case "$_lsaqf_size" in ''|*[!0-9]*) return 1 ;; esac
    {
        printf 'bytes=%s\n' "$_lsaqf_size"
        head -c 65536 "$_lsaqf_file" 2>/dev/null || true
        if [ "$_lsaqf_size" -gt 65536 ] 2>/dev/null; then
            tail -c 65536 "$_lsaqf_file" 2>/dev/null || true
        fi
    } | _luoshu_atomic_hash_stream
}

_luoshu_atomic_files_equal() {
    _lsafe_left="$1"
    _lsafe_right="$2"
    [ -f "$_lsafe_left" ] && [ -f "$_lsafe_right" ] || return 1
    _lsafe_left_size=$(_luoshu_atomic_file_size "$_lsafe_left")
    _lsafe_right_size=$(_luoshu_atomic_file_size "$_lsafe_right")
    [ -n "$_lsafe_left_size" ] && [ "$_lsafe_left_size" = "$_lsafe_right_size" ] || return 1
    _lsafe_left_fingerprint=$(_luoshu_atomic_quick_fingerprint "$_lsafe_left")
    _lsafe_right_fingerprint=$(_luoshu_atomic_quick_fingerprint "$_lsafe_right")
    [ -n "$_lsafe_left_fingerprint" ] && [ "$_lsafe_left_fingerprint" = "$_lsafe_right_fingerprint" ]
}

_luoshu_atomic_file_identity() {
    stat -c '%d:%i' "$1" 2>/dev/null
}

_luoshu_atomic_same_identity() {
    _lsasi_left=$(_luoshu_atomic_file_identity "$1")
    _lsasi_right=$(_luoshu_atomic_file_identity "$2")
    [ -n "$_lsasi_left" ] && [ "$_lsasi_left" = "$_lsasi_right" ]
}

_luoshu_atomic_namespace_target() {
    _lsant_path="$1"
    _lsant_root="${LUOSHU_SELF_PID1_ROOT:-/proc/1/root}"
    case "$_lsant_root" in
        /|'') printf '%s\n' "$_lsant_path" ;;
        *)
            case "$_lsant_path" in
                "$_lsant_root"/*) printf '/%s\n' "${_lsant_path#"$_lsant_root"/}" ;;
                *) printf '%s\n' "$_lsant_path" ;;
            esac
            ;;
    esac
}

_luoshu_atomic_mountinfo_has_target() {
    _lsamht_target=$(_luoshu_atomic_namespace_target "$1")
    _lsamht_file="${LUOSHU_SELF_MOUNTINFO:-/proc/1/mountinfo}"
    [ -r "$_lsamht_file" ] || return 1
    awk -v target="$_lsamht_target" '$5 == target { found=1 } END { exit !found }' \
        "$_lsamht_file" 2>/dev/null
}

_luoshu_atomic_pid1_target() {
    _lsapt_target="$1"
    _lsapt_root="${LUOSHU_SELF_PID1_ROOT:-/proc/1/root}"
    if [ -d "$_lsapt_root" ]; then
        case "$_lsapt_root" in
            /) printf '%s\n' "$_lsapt_target" ;;
            *) printf '%s%s\n' "${_lsapt_root%/}" "$_lsapt_target" ;;
        esac
    else
        printf '%s\n' "$_lsapt_target"
    fi
}

_luoshu_atomic_boot_id() {
    _lsabi_value=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')
    [ -n "$_lsabi_value" ] || _lsabi_value=unknown
    printf '%s\n' "$_lsabi_value"
}

# Return success only when the mount journal belongs to this boot. A journal
# from an older boot must be cleared without unmounting generic system targets,
# because another module may own those targets now.
_luoshu_atomic_prepare_boot_state() {
    _lsapbs_list="$1"
    _lsapbs_state=$(_luoshu_self_state_root)
    _lsapbs_file="$_lsapbs_state/boot-id"
    _lsapbs_current=$(_luoshu_atomic_boot_id)
    _lsapbs_saved=$(cat "$_lsapbs_file" 2>/dev/null | tr -d '\r\n')
    if [ -n "$_lsapbs_saved" ] && [ "$_lsapbs_saved" = "$_lsapbs_current" ]; then
        return 0
    fi
    : > "$_lsapbs_list" 2>/dev/null || true
    rm -rf "$_lsapbs_state/lower" "$_lsapbs_state/work" 2>/dev/null || true
    printf '%s\n' "$_lsapbs_current" > "${_lsapbs_file}.tmp.$$" 2>/dev/null && \
        mv -f "${_lsapbs_file}.tmp.$$" "$_lsapbs_file" 2>/dev/null || true
    return 1
}

_luoshu_atomic_tree_visible() {
    _lsatv_source="$1"
    _lsatv_target="$2"
    _lsatv_mode="${3:-overlay}"
    _lsatv_state=$(_luoshu_self_state_root)
    _lsatv_files="$_lsatv_state/verify-files.$$"
    _lsatv_seen="$_lsatv_state/verify-targets.$$"
    _lsatv_failed=0
    _lsatv_total=0
    mkdir -p "$_lsatv_state" 2>/dev/null || return 1
    : > "$_lsatv_seen" 2>/dev/null || return 1
    if [ "$_lsatv_mode" = bind ]; then
        _luoshu_atomic_bind_file_order "$_lsatv_source" "$_lsatv_target" "$_lsatv_files" || return 1
    else
        find "$_lsatv_source" -type f 2>/dev/null > "$_lsatv_files" || return 1
    fi
    while IFS= read -r _lsatv_src; do
        [ -n "$_lsatv_src" ] || continue
        _lsatv_rel=${_lsatv_src#$_lsatv_source/}
        _lsatv_dst="$_lsatv_target/$_lsatv_rel"
        if [ ! -f "$_lsatv_dst" ]; then
            if _luoshu_atomic_missing_target_allowed "$_lsatv_rel" "$_lsatv_mode"; then
                continue
            fi
            _lsatv_failed=1
            break
        fi
        if [ "$_lsatv_mode" = bind ]; then
            _lsatv_dst=$(_luoshu_atomic_real_target "$_lsatv_dst")
            if _luoshu_atomic_target_seen "$_lsatv_seen" "$_lsatv_dst"; then
                continue
            fi
            printf '%s\n' "$_lsatv_dst" >> "$_lsatv_seen" 2>/dev/null || {
                _lsatv_failed=1
                break
            }
            _luoshu_atomic_mountinfo_has_target "$_lsatv_dst" && \
                _luoshu_atomic_same_identity "$_lsatv_src" "$_lsatv_dst" || {
                _lsatv_failed=1
                break
            }
        fi
        _lsatv_total=$((_lsatv_total + 1))
        _luoshu_atomic_files_equal "$_lsatv_src" "$_lsatv_dst" || {
            _lsatv_failed=1
            break
        }
    done < "$_lsatv_files"
    rm -f "$_lsatv_files" "$_lsatv_seen" 2>/dev/null || true
    [ "$_lsatv_total" -gt 0 ] 2>/dev/null && [ "$_lsatv_failed" -eq 0 ]
}

_luoshu_atomic_bind_tree() {
    _lsabt_source="$1"
    _lsabt_target="$2"
    _lsabt_state=$(_luoshu_self_state_root)
    _lsabt_files="$_lsabt_state/bind-files.$$"
    _lsabt_seen="$_lsabt_state/bind-targets.$$"
    _lsabt_expected=0
    _lsabt_mounted=0
    _lsabt_failed=0
    mkdir -p "$_lsabt_state" 2>/dev/null || return 1
    : > "$_lsabt_seen" 2>/dev/null || return 1
    _luoshu_atomic_bind_file_order "$_lsabt_source" "$_lsabt_target" "$_lsabt_files" || return 1
    while IFS= read -r _lsabt_src; do
        [ -n "$_lsabt_src" ] || continue
        _lsabt_rel=${_lsabt_src#$_lsabt_source/}
        _lsabt_dst="$_lsabt_target/$_lsabt_rel"
        if [ ! -f "$_lsabt_dst" ] && \
           _luoshu_atomic_missing_target_allowed "$_lsabt_rel" bind; then
            continue
        fi
        [ -f "$_lsabt_dst" ] || {
            _lsabt_failed=1
            break
        }
        _lsabt_dst=$(_luoshu_atomic_real_target "$_lsabt_dst")
        if _luoshu_atomic_target_seen "$_lsabt_seen" "$_lsabt_dst"; then
            continue
        fi
        _lsabt_expected=$((_lsabt_expected + 1))
        printf '%s\n' "$_lsabt_dst" >> "$_lsabt_seen" 2>/dev/null || {
            _lsabt_failed=1
            break
        }
        if _luoshu_mount_cmd -o bind "$_lsabt_src" "$_lsabt_dst" >/dev/null 2>&1; then
            printf '%s\n' "$_lsabt_dst" >> "$_lsme_mount_list" 2>/dev/null || {
                _lsabt_failed=1
                break
            }
            _lsabt_mounted=$((_lsabt_mounted + 1))
        else
            _lsabt_failed=1
            break
        fi
    done < "$_lsabt_files"
    rm -f "$_lsabt_files" "$_lsabt_seen" 2>/dev/null || true
    [ "$_lsabt_failed" -eq 0 ] || return 1
    [ "$_lsabt_mounted" -eq "$_lsabt_expected" ] || return 1
    # Distinguish an actual bind failure from an additive-only component whose
    # files have no pre-existing ROM inode. The caller may skip the latter for
    # non-core components, but system/fonts remains mandatory.
    [ "$_lsabt_mounted" -gt 0 ] 2>/dev/null || return 2
    return 0
}

_luoshu_atomic_rollback() {
    _lsar_list="$1"
    _lsar_state=$(_luoshu_self_state_root)
    if [ -s "$_lsar_list" ]; then
        awk '{ item[NR]=$0 } END { for (i=NR; i>=1; i--) print item[i] }' "$_lsar_list" 2>/dev/null | \
        while IFS= read -r _lsar_target; do
            [ -n "$_lsar_target" ] || continue
            _luoshu_umount_cmd "$_lsar_target" >/dev/null 2>&1 || true
        done
    fi
    : > "$_lsar_list" 2>/dev/null || true
    rm -rf "$_lsar_state/lower" "$_lsar_state/work" 2>/dev/null || true
}

_luoshu_atomic_verify_manifest() {
    _lsavm_manifest="${1:-$(_luoshu_atomic_manifest)}"
    [ -s "$_lsavm_manifest" ] || return 1
    while IFS='|' read -r _lsavm_source _lsavm_target _lsavm_mode; do
        [ -n "$_lsavm_source" ] && [ -n "$_lsavm_target" ] || return 1
        if [ "${_lsavm_mode:-overlay}" = overlay ]; then
            _luoshu_atomic_mountinfo_has_target "$_lsavm_target" || return 1
        fi
        _lsavm_visible=$(_luoshu_atomic_pid1_target "$_lsavm_target")
        _luoshu_atomic_tree_visible "$_lsavm_source" "$_lsavm_visible" "${_lsavm_mode:-overlay}" || return 1
    done < "$_lsavm_manifest"
    return 0
}

_luoshu_atomic_verify_manifest_retry() {
    _lsavmr_manifest="$1"
    _lsavmr_limit="${LUOSHU_SELF_VERIFY_RETRIES:-3}"
    _lsavmr_delay="${LUOSHU_SELF_VERIFY_DELAY:-1}"
    case "$_lsavmr_limit" in ''|*[!0-9]*) _lsavmr_limit=3 ;; esac
    case "$_lsavmr_delay" in ''|*[!0-9]*) _lsavmr_delay=1 ;; esac
    [ "$_lsavmr_limit" -ge 1 ] 2>/dev/null || _lsavmr_limit=1
    _lsavmr_attempt=1
    while [ "$_lsavmr_attempt" -le "$_lsavmr_limit" ]; do
        _luoshu_atomic_verify_manifest "$_lsavmr_manifest" && return 0
        [ "$_lsavmr_attempt" -ge "$_lsavmr_limit" ] || \
            [ "$_lsavmr_delay" -eq 0 ] 2>/dev/null || sleep "$_lsavmr_delay"
        _lsavmr_attempt=$((_lsavmr_attempt + 1))
    done
    return 1
}

# Strict replacement for the old fail-open partial mount path. Fail-open now means
# a complete rollback to the ROM tree, never a mixed/degraded font configuration.
luoshu_self_mount_ensure() {
    _lsme_module=$(_luoshu_self_module)
    _lsme_active=$(head -n1 "$_lsme_module/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_lsme_active" ] || _lsme_active=default
    _lsme_state_root=$(_luoshu_self_state_root)
    _lsme_mount_list="$_lsme_state_root/mounts.list"
    _lsme_manifest=$(_luoshu_atomic_manifest)
    _lsme_manifest_temp="${_lsme_manifest}.tmp.$$"
    mkdir -p "$_lsme_state_root" "$_lsme_module/config" 2>/dev/null || return 1
    _lsme_same_boot=0
    _luoshu_atomic_prepare_boot_state "$_lsme_mount_list" && _lsme_same_boot=1

    if [ "$_lsme_active" = default ]; then
        [ "$_lsme_same_boot" -eq 0 ] || _luoshu_atomic_rollback "$_lsme_mount_list"
        : > "$_lsme_mount_list" 2>/dev/null || true
        rm -f "$_lsme_manifest" "$_lsme_manifest_temp" 2>/dev/null || true
        _luoshu_self_state_write idle none '' ''
        return 0
    fi

    if [ "$_lsme_same_boot" -eq 1 ] && \
       [ "$(_luoshu_self_state_value state)" = mounted ] && \
       _luoshu_atomic_verify_manifest "$_lsme_manifest"; then
        _luoshu_self_log '自挂载已完整存在，跳过重复挂载'
        return 0
    fi

    [ "$_lsme_same_boot" -eq 0 ] || _luoshu_atomic_rollback "$_lsme_mount_list"
    : > "$_lsme_mount_list" 2>/dev/null || return 1
    : > "$_lsme_manifest_temp" 2>/dev/null || return 1
    _lsme_mounted=''
    _lsme_failed=''
    _lsme_component_count=0
    _lsme_bind_count=0
    _lsme_system_fonts_ok=0

    for _lsme_partition in $(luoshu_payload_partitions); do
        _lsme_has_payload=0
        for _lsme_subdir in fonts etc; do
            _lsme_source="$_lsme_module/$_lsme_partition/$_lsme_subdir"
            if [ -d "$_lsme_source" ] && find "$_lsme_source" -type f -print -quit 2>/dev/null | grep -q .; then
                _lsme_has_payload=1
                break
            fi
        done
        [ "$_lsme_has_payload" -eq 1 ] || continue

        _lsme_root=$(_luoshu_partition_root "$_lsme_partition") || {
            _lsme_failed="$_lsme_partition/root-unavailable"
            break
        }
        for _lsme_subdir in fonts etc; do
            _lsme_source="$_lsme_module/$_lsme_partition/$_lsme_subdir"
            [ -d "$_lsme_source" ] && find "$_lsme_source" -type f -print -quit 2>/dev/null | grep -q . || continue
            _lsme_target="$_lsme_root/$_lsme_subdir"
            [ -d "$_lsme_target" ] || {
                _lsme_failed="$_lsme_partition/$_lsme_subdir-target-missing"
                break
            }
            _lsme_mode=overlay
            if _luoshu_overlay_mount_dir "$_lsme_source" "$_lsme_target" \
                "${_lsme_partition}-${_lsme_subdir}"; then
                printf '%s\n' "$_lsme_target" >> "$_lsme_mount_list" 2>/dev/null || {
                    _lsme_failed="$_lsme_partition/$_lsme_subdir-record-failed"
                    break
                }
            else
                _lsme_mode=bind
                if _luoshu_atomic_bind_tree "$_lsme_source" "$_lsme_target"; then
                    _lsme_bind_count=$((_lsme_bind_count + 1))
                else
                    _lsme_bind_rc=$?
                    if [ "$_lsme_bind_rc" -eq 2 ] 2>/dev/null; then
                        if [ "$_lsme_partition/$_lsme_subdir" = system/fonts ]; then
                            _lsme_failed=system/fonts-bind-empty
                            break
                        fi
                        _luoshu_self_log \
                            "自挂载跳过无本机 bind 目标的附加组件：$_lsme_partition/$_lsme_subdir"
                        continue
                    else
                        _lsme_failed="$_lsme_partition/$_lsme_subdir-bind-incomplete"
                        break
                    fi
                fi
            fi
            _luoshu_atomic_tree_visible "$_lsme_source" "$_lsme_target" "$_lsme_mode" || {
                _lsme_failed="$_lsme_partition/$_lsme_subdir-visibility-mismatch"
                break
            }
            printf '%s|%s|%s\n' "$_lsme_source" "$_lsme_target" "$_lsme_mode" \
                >> "$_lsme_manifest_temp" 2>/dev/null || {
                _lsme_failed="$_lsme_partition/$_lsme_subdir-manifest-failed"
                break
            }
            _lsme_component_count=$((_lsme_component_count + 1))
            _lsme_mounted="${_lsme_mounted}${_lsme_mounted:+,}${_lsme_partition}/${_lsme_subdir}:${_lsme_mode}"
            [ "$_lsme_partition/$_lsme_subdir" = system/fonts ] && _lsme_system_fonts_ok=1
        done
        [ -z "$_lsme_failed" ] || break
    done

    [ "$_lsme_component_count" -gt 0 ] 2>/dev/null || _lsme_failed="${_lsme_failed:-payload-empty}"
    [ "$_lsme_system_fonts_ok" -eq 1 ] 2>/dev/null || _lsme_failed="${_lsme_failed:-system/fonts-required}"
    if [ -z "$_lsme_failed" ]; then
        _luoshu_atomic_verify_manifest_retry "$_lsme_manifest_temp" || _lsme_failed=pid1-visibility-mismatch
    fi

    if [ -n "$_lsme_failed" ]; then
        _luoshu_atomic_rollback "$_lsme_mount_list"
        rm -f "$_lsme_manifest" "$_lsme_manifest_temp" 2>/dev/null || true
        _luoshu_self_state_write failed rollback "$_lsme_mounted" "$_lsme_failed"
        _luoshu_self_log "自挂载事务失败并已完整回滚：failed=$_lsme_failed mounted=$_lsme_mounted"
        return 1
    fi

    mv -f "$_lsme_manifest_temp" "$_lsme_manifest" 2>/dev/null || {
        _luoshu_atomic_rollback "$_lsme_mount_list"
        rm -f "$_lsme_manifest_temp" 2>/dev/null || true
        _luoshu_self_state_write failed rollback "$_lsme_mounted" manifest-commit-failed
        return 1
    }
    chmod 0600 "$_lsme_manifest" 2>/dev/null || true
    if [ "$_lsme_bind_count" -eq 0 ]; then
        _lsme_backend=self-overlay
    else
        _lsme_backend=self-overlay-bind
    fi
    _luoshu_self_state_write mounted "$_lsme_backend" "$_lsme_mounted" ''
    _luoshu_self_log "自挂载原子事务成功：mounted=$_lsme_mounted"
    return 0
}

# A mount is verified only when the last transaction fully committed and every
# required payload file is visible from init's root namespace.
luoshu_mount_verify_active() {
    _lsmva_active="${1:-$(head -n1 "$LUOSHU_MOUNT_MODDIR/config/active_font.conf" 2>/dev/null)}"
    [ -n "$_lsmva_active" ] || _lsmva_active=default
    if [ "$_lsmva_active" = default ]; then
        luoshu_mount_record verified '系统默认字体无需挂载验证' '' 0 0
        return 0
    fi

    _lsmva_state=$(_luoshu_self_state_value state)
    _lsmva_manifest=$(_luoshu_atomic_manifest)
    if [ "$_lsmva_state" != mounted ]; then
        luoshu_mount_record unverified "洛书自挂载未完整提交：${_lsmva_state:-missing}" '' 0 1 system '' self-mount
        return 1
    fi
    if ! _luoshu_atomic_verify_manifest "$_lsmva_manifest"; then
        _lsmva_mounted=$(_luoshu_self_state_value mounted)
        _luoshu_self_state_write failed verification "$_lsmva_mounted" pid1-visibility-mismatch
        _luoshu_self_log '自挂载验证失败：PID 1 根命名空间未读取完整字体负载'
        luoshu_mount_record unverified 'PID 1 根命名空间未读取完整洛书字体负载' '' 0 1 system '' visibility
        return 1
    fi
    luoshu_mount_record verified '洛书全部字体文件与配置已在系统主命名空间生效' '' 0 0 system system
    return 0
}
