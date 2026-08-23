#!/system/bin/sh
# LuoShu self-mount backend.
# Uses the same read-only lower-layer model as KernelSU's reference meta-overlayfs:
# module content first, captured stock tree last, and source name KSU for unified cleanup.
set +e

luoshu_self_mount_stage_for_manager() {
    case "${1:-unknown}" in
        APatch|KernelSU|KernelSU*|SukiSU|SukiSU*)
            printf 'post-mount\n'
            ;;
        *)
            # Magisk does not provide a module post-mount hook. Unknown legacy
            # managers retain the existing early path for compatibility.
            printf 'post-fs-data\n'
            ;;
    esac
}

_luoshu_overlay_mount_dir() {
    _lsomb_source="$1"
    _lsomb_target="$2"
    _lsomb_key="$3"
    _lsomb_state=$(_luoshu_self_state_root)
    _lsomb_lower="$_lsomb_state/lower/$_lsomb_key"

    [ -d "$_lsomb_source" ] && [ -d "$_lsomb_target" ] || return 1
    _luoshu_umount_cmd "$_lsomb_lower" >/dev/null 2>&1 || true
    rm -rf "$_lsomb_lower" 2>/dev/null || true
    mkdir -p "$_lsomb_lower" 2>/dev/null || return 1

    # Keep a stable reference to the currently visible stock/metamodule tree before
    # placing LuoShu's own layer on the same target.
    _luoshu_mount_cmd -o bind "$_lsomb_target" "$_lsomb_lower" >/dev/null 2>&1 || return 1

    # No upperdir/workdir is needed: LuoShu only needs a merged read-only boot view.
    # Changes made by the App are intentionally picked up after the requested reboot.
    if _luoshu_mount_cmd -t overlay KSU \
        -o "lowerdir=$_lsomb_source:$_lsomb_lower" \
        "$_lsomb_target" >/dev/null 2>&1; then
        # self_mount_ensure appends the visible target too. Recording the captured
        # lower first guarantees reverse-order uninstall: target, then lower bind.
        if [ -n "${_lsme_mount_list:-}" ]; then
            printf '%s\n' "$_lsomb_lower" >> "$_lsme_mount_list" 2>/dev/null || true
        fi
        return 0
    fi

    _luoshu_umount_cmd "$_lsomb_lower" >/dev/null 2>&1 || true
    rm -rf "$_lsomb_lower" 2>/dev/null || true
    return 1
}

# v3.3.0 stores the real runtime tree under .luoshu-payload and only exposes a
# temporary bind view at <module>/<partition>. KernelSU post-mount can run in a
# mount namespace where that temporary module bind is absent. The previous
# atomic transaction then saw an empty public system/fonts directory, declared
# payload-empty/system-fonts-required and rolled the entire font transaction back.
#
# Always prefer the persistent private payload as the self-mount source. Keep the
# public view only as a compatibility fallback for legacy installs/tests.
_luoshu_self_payload_source() {
    _lsps_module="$1"
    _lsps_partition="$2"
    _lsps_subdir="$3"
    _lsps_private="$_lsps_module/.luoshu-payload/$_lsps_partition/$_lsps_subdir"
    _lsps_public="$_lsps_module/$_lsps_partition/$_lsps_subdir"

    if [ -d "$_lsps_private" ] && \
       find "$_lsps_private" -type f -print -quit 2>/dev/null | grep -q .; then
        printf '%s\n' "$_lsps_private"
    else
        printf '%s\n' "$_lsps_public"
    fi
}

# Deliberate final-layer override of mount_self_atomic.sh. All transaction,
# rollback and PID-1 visibility checks stay identical; only payload source
# resolution changes so KernelSU/APatch do not depend on a private module-view
# bind surviving across hook namespaces.
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

    if ! _luoshu_atomic_mount_authorized "$_lsme_module"; then
        [ "$_lsme_same_boot" -eq 0 ] || _luoshu_atomic_rollback "$_lsme_mount_list"
        : > "$_lsme_mount_list" 2>/dev/null || true
        rm -f "$_lsme_manifest" "$_lsme_manifest_temp" 2>/dev/null || true
        _luoshu_self_state_write deferred none '' "$LUOSHU_SELF_MOUNT_DEFER_REASON"
        _luoshu_self_log "自挂载已安全延后：reason=$LUOSHU_SELF_MOUNT_DEFER_REASON"
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
            _lsme_source=$(_luoshu_self_payload_source "$_lsme_module" "$_lsme_partition" "$_lsme_subdir")
            if [ -d "$_lsme_source" ] && find "$_lsme_source" -type f -print -quit 2>/dev/null | grep -q .; then
                _lsme_has_payload=1
                break
            fi
        done
        [ "$_lsme_has_payload" -eq 1 ] || continue

        _lsme_root=$(_luoshu_partition_root "$_lsme_partition") || {
            if [ "$_lsme_partition" = system ]; then
                _lsme_failed="$_lsme_partition/root-unavailable"
                break
            fi
            _luoshu_self_log "自挂载跳过本机不存在的可选分区：$_lsme_partition"
            continue
        }
        for _lsme_subdir in fonts etc; do
            _lsme_source=$(_luoshu_self_payload_source "$_lsme_module" "$_lsme_partition" "$_lsme_subdir")
            [ -d "$_lsme_source" ] && find "$_lsme_source" -type f -print -quit 2>/dev/null | grep -q . || continue
            _lsme_target="$_lsme_root/$_lsme_subdir"
            [ -d "$_lsme_target" ] || {
                if _luoshu_atomic_component_required "$_lsme_partition" "$_lsme_subdir"; then
                    _lsme_failed="$_lsme_partition/$_lsme_subdir-target-missing"
                    break
                fi
                _luoshu_self_log "自挂载跳过本机不存在的可选目标：$_lsme_partition/$_lsme_subdir"
                continue
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
