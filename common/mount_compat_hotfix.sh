#!/system/bin/sh
# LuoShu v2.2.x meta-module compatibility hotfix.
#
# Mountify, Hybrid Mount and Magic Mount consume the canonical module tree
# directly. Only dual-directory overlay engines need a mirrored content tree.
# Runtime probe visibility is diagnostic and must not roll back a payload that
# already passed LuoShu's atomic font validation.
set +e

_luoshu_magic_mount_present() {
    for _lmmh_path in /data/adb/modules/*; do
        [ -d "$_lmmh_path" ] || continue
        _luoshu_module_metadata_matches "$_lmmh_path" \
            magic_mount magic-mount 'magic mount' id=meta-mm meta-mm-rs && return 0
    done
    [ -f /data/adb/magic_mount/config.toml ] && {
        [ -x /data/adb/metamodule/meta-mm ] ||
        [ -x /data/adb/metamodule/meta-mm-rs ] ||
        [ -x /data/adb/modules/magic_mount_rs/meta-mm ] ||
        [ -x /data/adb/modules/meta-mm/meta-mm ] ||
        [ -x /data/adb/modules/meta_mm/meta-mm ]
    }
}

luoshu_mountify_ensure_selected() {
    luoshu_mountify_module_selected && return 0
    _lmhes_id=$(luoshu_module_id)
    for _lmhes_file in \
        /data/adb/mountify/modules.txt \
        /data/adb/modules/mountify/modules.txt \
        /data/adb/modules/Mountify/modules.txt; do
        [ -f "$_lmhes_file" ] || continue
        if printf '%s\n' "$_lmhes_id" >> "$_lmhes_file" 2>/dev/null; then
            luoshu_mount_log "已将 $_lmhes_id 加入 Mountify 选择列表"
            return 0
        fi
    done
    LUOSHU_MOUNT_DETECTION_WARNING='Mountify 使用选择模式，但未找到可写的模块列表'
    luoshu_mount_log "$LUOSHU_MOUNT_DETECTION_WARNING"
    return 0
}

# Never rewrite another meta-module's config.toml. Magic Mount RC and later
# builds have changed config paths and partition semantics more than once.
luoshu_magic_mount_ensure_partitions() {
    return 0
}

luoshu_mount_preflight() {
    _lmhp_active="${1:-unknown}"
    _lmhp_engine=$(luoshu_detect_mount_engine)
    LUOSHU_MOUNT_PREFLIGHT_ERROR=''

    [ ! -e "$LUOSHU_MOUNT_MODDIR/remove" ] || {
        LUOSHU_MOUNT_PREFLIGHT_ERROR='模块存在 remove 标记'
        return 1
    }

    if [ "$_lmhp_active" != default ]; then
        luoshu_recover_explicit_disable || return 1
        case "$_lmhp_engine" in
            mountify|hybrid-mount|magic-mount|magic-mount-rs|native-module-mount)
                for _lmhp_marker in skip_mount skip_mountify mount_error; do
                    [ -e "$LUOSHU_MOUNT_MODDIR/$_lmhp_marker" ] || continue
                    rm -f "$LUOSHU_MOUNT_MODDIR/$_lmhp_marker" 2>/dev/null || {
                        LUOSHU_MOUNT_PREFLIGHT_ERROR="无法清理洛书挂载遗留标记：$_lmhp_marker"
                        return 1
                    }
                done
                ;;
        esac
    fi

    case "$_lmhp_engine" in
        mountify)
            [ "$_lmhp_active" = default ] || luoshu_mountify_ensure_selected || return 1
            ;;
        meta-overlayfs|dual-dir-metamodule)
            _lmhp_base=$(luoshu_dual_content_base)
            mkdir -p "$_lmhp_base" 2>/dev/null || {
                LUOSHU_MOUNT_PREFLIGHT_ERROR="无法创建元模块内容目录：$_lmhp_base"
                return 1
            }
            [ -w "$_lmhp_base" ] || {
                LUOSHU_MOUNT_PREFLIGHT_ERROR="元模块内容目录不可写：$_lmhp_base"
                return 1
            }
            ;;
    esac
    return 0
}

# v2.2.5 wrote one probe into every optional partition. Some engines cache a
# mount plan before those files appear, so one harmless missing probe caused the
# whole font transaction to be marked failed. Keep one primary diagnostic only.
luoshu_write_mount_probes() {
    _lmhwp_active="${1:-unknown}"
    _lmhwp_engine=$(luoshu_detect_mount_engine)
    _lmhwp_id=$(luoshu_module_id)
    _lmhwp_nonce="$(date +%s 2>/dev/null || echo 0)-$$-system"
    _lmhwp_dir="$LUOSHU_MOUNT_MODDIR/system/etc/luoshu"
    _lmhwp_manifest="$LUOSHU_MOUNT_MODDIR/config/mount-probes-expected.conf"

    mkdir -p "$_lmhwp_dir" "$LUOSHU_MOUNT_MODDIR/config" 2>/dev/null || return 1
    {
        printf 'id=%s\n' "$_lmhwp_id"
        printf 'font=%s\n' "$_lmhwp_active"
        printf 'engine=%s\n' "$_lmhwp_engine"
        printf 'partition=system\n'
        printf 'nonce=%s\n' "$_lmhwp_nonce"
    } > "$_lmhwp_dir/mount-probe.conf.tmp.$$" 2>/dev/null || return 1
    mv -f "$_lmhwp_dir/mount-probe.conf.tmp.$$" "$_lmhwp_dir/mount-probe.conf" 2>/dev/null || return 1
    chmod 0644 "$_lmhwp_dir/mount-probe.conf" 2>/dev/null || true
    printf 'system|%s|/system/etc/luoshu/mount-probe.conf\n' "$_lmhwp_nonce" \
        > "$_lmhwp_manifest.tmp.$$" 2>/dev/null || return 1
    mv -f "$_lmhwp_manifest.tmp.$$" "$_lmhwp_manifest" 2>/dev/null || return 1
    chmod 0644 "$_lmhwp_manifest" 2>/dev/null || true
    cp -f "$_lmhwp_dir/mount-probe.conf" \
        "$LUOSHU_MOUNT_MODDIR/config/mount-probe-expected.conf" 2>/dev/null || true
}

luoshu_write_mount_probe() {
    luoshu_write_mount_probes "$@"
}

luoshu_sync_mount_payload() {
    _lmhs_active="${1:-$(head -n1 "$LUOSHU_MOUNT_MODDIR/config/active_font.conf" 2>/dev/null)}"
    [ -n "$_lmhs_active" ] || _lmhs_active=default
    _lmhs_engine=$(luoshu_detect_mount_engine)
    _lmhs_synced=0
    _lmhs_failed=0
    _lmhs_root=''
    _lmhs_partitions=''
    _lmhs_failed_partitions=''

    luoshu_mount_budget_begin
    luoshu_mount_lock_acquire || return 1
    trap 'luoshu_mount_lock_release' EXIT HUP INT TERM

    if ! luoshu_mount_preflight "$_lmhs_active"; then
        luoshu_mount_record failed "$LUOSHU_MOUNT_PREFLIGHT_ERROR" '' 0 1
        luoshu_mount_lock_release
        trap - EXIT HUP INT TERM
        return 1
    fi

    luoshu_write_mount_probes "$_lmhs_active" || \
        luoshu_mount_log '挂载诊断探针生成失败，已继续保留标准模块负载'

    for _lmhs_partition in $(luoshu_used_partitions); do
        _lmhs_partitions="${_lmhs_partitions}${_lmhs_partitions:+,}$_lmhs_partition"
    done

    case "$_lmhs_engine" in
        meta-overlayfs|dual-dir-metamodule)
            _lmhs_root=$(luoshu_meta_content_roots | head -n1)
            [ -n "$_lmhs_root" ] && mkdir -p "$_lmhs_root" 2>/dev/null || _lmhs_failed=1
            if [ "$_lmhs_failed" -eq 0 ]; then
                for _lmhs_partition in $(luoshu_used_partitions "$_lmhs_root"); do
                    _lmhs_source="$LUOSHU_MOUNT_MODDIR/$_lmhs_partition"
                    _lmhs_destination="$_lmhs_root/$_lmhs_partition"
                    if [ -d "$_lmhs_source" ]; then
                        if luoshu_copy_partition_atomic "$_lmhs_source" "$_lmhs_destination"; then
                            _lmhs_synced=$((_lmhs_synced + 1))
                        else
                            _lmhs_result=$?
                            _lmhs_failed=$((_lmhs_failed + 1))
                            _lmhs_failed_partitions="${_lmhs_failed_partitions}${_lmhs_failed_partitions:+,}$_lmhs_partition"
                            [ "$_lmhs_result" -ne 124 ] || \
                                LUOSHU_MOUNT_PREFLIGHT_ERROR="元模块同步超过 ${LUOSHU_MOUNT_TIMEOUT} 秒总时限"
                            break
                        fi
                    elif ! rm -rf "$_lmhs_destination" 2>/dev/null; then
                        _lmhs_failed=$((_lmhs_failed + 1))
                        _lmhs_failed_partitions="${_lmhs_failed_partitions}${_lmhs_failed_partitions:+,}$_lmhs_partition"
                        break
                    fi
                done
            fi
            ;;
        *)
            # Mountify, Hybrid Mount, Magic Mount and native managers read the
            # canonical /data/adb/modules/LuoShu tree. No guessed mirror and no
            # external config mutation are necessary.
            ;;
    esac

    luoshu_mount_lock_release
    trap - EXIT HUP INT TERM

    if [ "$_lmhs_failed" -gt 0 ]; then
        luoshu_mount_record failed \
            "${LUOSHU_MOUNT_PREFLIGHT_ERROR:-元模块内容更新失败，已保留旧分区目录}" \
            "$_lmhs_root" "$_lmhs_synced" "$_lmhs_failed" \
            "$_lmhs_partitions" '' "$_lmhs_failed_partitions"
        return 1
    fi

    case "$_lmhs_engine" in
        meta-overlayfs|dual-dir-metamodule)
            luoshu_mount_record prepared \
                '已同步双目录元模块内容；启动后使用主字体可见性进行兼容验证' \
                "$_lmhs_root" "$_lmhs_synced" 0 "$_lmhs_partitions"
            ;;
        *)
            luoshu_mount_record prepared \
                '已保留标准模块目录；当前元模块直接读取 /data/adb/modules/LuoShu' \
                '' 0 0 "$_lmhs_partitions"
            ;;
    esac
    luoshu_mount_log \
        "engine=$_lmhs_engine backend=$(luoshu_mount_backend "$_lmhs_engine") synced=$_lmhs_synced partitions=$_lmhs_partitions"
    return 0
}

_luoshu_hotfix_verify_probe() {
    _lmhvp_manifest="$LUOSHU_MOUNT_MODDIR/config/mount-probes-expected.conf"
    [ -s "$_lmhvp_manifest" ] || return 1
    IFS='|' read -r _lmhvp_partition _lmhvp_expected _lmhvp_path < "$_lmhvp_manifest"
    [ -n "$_lmhvp_expected" ] || return 1
    if [ -n "${LUOSHU_VISIBLE_PROBE:-}" ]; then
        _lmhvp_visible="$LUOSHU_VISIBLE_PROBE"
    elif [ -n "${LUOSHU_VISIBLE_PROBE_ROOT:-}" ]; then
        _lmhvp_visible="${LUOSHU_VISIBLE_PROBE_ROOT%/}$_lmhvp_path"
    else
        _lmhvp_visible="$_lmhvp_path"
    fi
    _lmhvp_seen=$(sed -n 's/^nonce=//p' "$_lmhvp_visible" 2>/dev/null | head -n1)
    [ "$_lmhvp_expected" = "$_lmhvp_seen" ]
}

_luoshu_hotfix_verify_font() {
    _lmhvf_source=''
    for _lmhvf_candidate in "$LUOSHU_MOUNT_MODDIR/system/fonts"/*; do
        [ -f "$_lmhvf_candidate" ] || continue
        [ -s "$_lmhvf_candidate" ] || continue
        _lmhvf_source="$_lmhvf_candidate"
        break
    done
    [ -n "$_lmhvf_source" ] || return 1
    _lmhvf_visible="${LUOSHU_VISIBLE_SYSTEM_ROOT:-/system}/fonts/${_lmhvf_source##*/}"
    [ -s "$_lmhvf_visible" ] || return 1
    if command -v cmp >/dev/null 2>&1; then
        cmp -s "$_lmhvf_source" "$_lmhvf_visible" 2>/dev/null
        return $?
    fi
    _lmhvf_a=$(wc -c < "$_lmhvf_source" 2>/dev/null | tr -d '[:space:]')
    _lmhvf_b=$(wc -c < "$_lmhvf_visible" 2>/dev/null | tr -d '[:space:]')
    [ -n "$_lmhvf_a" ] && [ "$_lmhvf_a" = "$_lmhvf_b" ]
}

luoshu_mount_verify_active() {
    _lmhv_active="${1:-$(head -n1 "$LUOSHU_MOUNT_MODDIR/config/active_font.conf" 2>/dev/null)}"
    [ -n "$_lmhv_active" ] || _lmhv_active=default
    if [ "$_lmhv_active" = default ]; then
        luoshu_mount_record verified '系统默认字体无需挂载验证' '' 0 0
        return 0
    fi
    if _luoshu_hotfix_verify_probe; then
        luoshu_mount_record verified '主系统挂载探针可见，元模块已读取洛书标准目录' '' 0 0 system system
        return 0
    fi
    if _luoshu_hotfix_verify_font; then
        luoshu_mount_record verified '主字体文件已从系统路径读取，元模块挂载有效' '' 0 0 system system
        return 0
    fi
    luoshu_mount_record unverified \
        '暂未从固定路径读取到诊断探针；已保留字体负载，不再因元模块差异自动回滚' \
        '' 0 0 system '' system
    return 0
}

font_config_mark_boot_success() {
    _lmhbs_config="${CONFIG_DIR:-$LUOSHU_MOUNT_MODDIR/config}"
    _lmhbs_state=$(sed -n 's/^state=//p' "$_lmhbs_config/font-payload-boot.conf" 2>/dev/null | head -n1)
    [ "$_lmhbs_state" = booting ] || return 0
    _lmhbs_font=$(sed -n 's/^font=//p' "$_lmhbs_config/font-payload-boot.conf" 2>/dev/null | head -n1)
    luoshu_mount_verify_active "${_lmhbs_font:-unknown}" || true
    printf 'state=confirmed\nfont=%s\ntime=%s\n' \
        "${_lmhbs_font:-unknown}" "$(date +%s 2>/dev/null || echo 0)" \
        > "$_lmhbs_config/font-payload-boot.conf.tmp.$$" 2>/dev/null || return 1
    mv -f "$_lmhbs_config/font-payload-boot.conf.tmp.$$" \
        "$_lmhbs_config/font-payload-boot.conf" 2>/dev/null || return 1
    rm -f \
        "$_lmhbs_config/font-boot-failures" \
        "$_lmhbs_config/font-payload-quarantine.conf" 2>/dev/null || true
    printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)" \
        > "$_lmhbs_config/font-last-boot-success.conf" 2>/dev/null || true
    chmod 0644 \
        "$_lmhbs_config/font-payload-boot.conf" \
        "$_lmhbs_config/font-last-boot-success.conf" 2>/dev/null || true
    return 0
}
