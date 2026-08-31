#!/system/bin/sh
# Final atomic self-mount implementation for the private LuoShu payload.
# Loaded after mount_self_atomic.sh and font_runtime_policy.sh.
set +e

type _lfrp_payload_root >/dev/null 2>&1 || return 0 2>/dev/null || exit 0
type _luoshu_atomic_manifest >/dev/null 2>&1 || return 0 2>/dev/null || exit 0

luoshu_self_mount_ensure() {
    _lsme_module=$(_luoshu_self_module)
    _lsme_payload=$(_lfrp_payload_root)
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
        _luoshu_self_log '私有字体负载已完整挂载，跳过重复事务'
        return 0
    fi

    [ "$_lsme_same_boot" -eq 0 ] || _luoshu_atomic_rollback "$_lsme_mount_list"
    : > "$_lsme_mount_list" 2>/dev/null || return 1
    : > "$_lsme_manifest_temp" 2>/dev/null || return 1
    _lsme_mounted=''
    _lsme_failed=''
    _lsme_component_count=0
    _lsme_bind_count=0
    _lsme_any_fonts_ok=0

    for _lsme_partition in $(_lfrp_partitions); do
        _lsme_has_payload=0
        for _lsme_subdir in fonts etc; do
            _lsme_source="$_lsme_payload/$_lsme_partition/$_lsme_subdir"
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
            _lsme_source="$_lsme_payload/$_lsme_partition/$_lsme_subdir"
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
                if type _luoshu_capture_lower_dir >/dev/null 2>&1; then
                    _luoshu_capture_lower_dir "$_lsme_target" \
                        "${_lsme_partition}-${_lsme_subdir}" || \
                        _luoshu_self_log \
                            "私有字体挂载无法保留原厂 lower：$_lsme_partition/$_lsme_subdir"
                fi
                if _luoshu_atomic_bind_tree "$_lsme_source" "$_lsme_target"; then
                    _lsme_bind_count=$((_lsme_bind_count + 1))
                else
                    _lsme_bind_rc=$?
                    if [ "$_lsme_bind_rc" -eq 2 ] 2>/dev/null; then
                        _luoshu_self_log \
                            "自挂载跳过无本机 bind 目标的附加组件：$_lsme_partition/$_lsme_subdir"
                        continue
                    fi
                    _lsme_failed="$_lsme_partition/$_lsme_subdir-bind-incomplete"
                    break
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
            [ "$_lsme_subdir" = fonts ] && _lsme_any_fonts_ok=1
        done
        [ -z "$_lsme_failed" ] || break
    done

    [ "$_lsme_component_count" -gt 0 ] 2>/dev/null || _lsme_failed="${_lsme_failed:-payload-empty}"
    [ "$_lsme_any_fonts_ok" -eq 1 ] 2>/dev/null || _lsme_failed="${_lsme_failed:-font-partition-required}"
    if [ -z "$_lsme_failed" ]; then
        _luoshu_atomic_verify_manifest_retry "$_lsme_manifest_temp" || _lsme_failed=pid1-visibility-mismatch
    fi

    if [ -n "$_lsme_failed" ]; then
        _luoshu_atomic_rollback "$_lsme_mount_list"
        rm -f "$_lsme_manifest" "$_lsme_manifest_temp" 2>/dev/null || true
        _luoshu_self_state_write failed rollback "$_lsme_mounted" "$_lsme_failed"
        _luoshu_self_log "私有字体自挂载事务失败并已完整回滚：failed=$_lsme_failed mounted=$_lsme_mounted"
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
    _luoshu_self_log "私有字体自挂载原子事务成功：mounted=$_lsme_mounted"
    return 0
}
