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
    # A sealed Universal payload has no optional font/XML aliases: its XML may
    # reference newly compiled assets that a per-file bind cannot create.
    [ "${LUOSHU_REQUIRED_PAYLOAD_FILES:-0}" != 1 ] || return 1
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
    # Head/tail sampling can miss a different cmap, outline, or table in the
    # middle of a font. Visibility and physical-target compatibility require
    # identical complete bytes; cmp is provided by Android toybox.
    if command -v cmp >/dev/null 2>&1; then
        cmp -s "$_lsafe_left" "$_lsafe_right"
    elif command -v busybox >/dev/null 2>&1; then
        busybox cmp -s "$_lsafe_left" "$_lsafe_right"
    else
        return 1
    fi
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
    rm -f "$_lsapbs_state/overlay-intents"/* 2>/dev/null || true
    _luoshu_atomic_empty_state_dirs "$_lsapbs_state"
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
    _lsabt_seen="${_lsme_bind_targets:-$_lsabt_state/bind-targets.$$}"
    _lsabt_total=0
    _lsabt_expected=0
    _lsabt_mounted=0
    _lsabt_failed=0
    mkdir -p "$_lsabt_state" 2>/dev/null || return 1
    if [ -z "${_lsme_bind_targets:-}" ]; then
        : > "$_lsabt_seen" 2>/dev/null || return 1
        _lsabt_plan="$_lsabt_state/bind-preflight.$$"
        printf '%s|%s|bind\n' "$_lsabt_source" "$_lsabt_target" > "$_lsabt_plan" || return 1
        _luoshu_atomic_preflight_targets "$_lsabt_plan"
        _lsabt_preflight_rc=$?
        rm -f "$_lsabt_plan"
        [ "$_lsabt_preflight_rc" -eq 0 ] || return 1
    fi
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
        _lsabt_total=$((_lsabt_total + 1))
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
    rm -f "$_lsabt_files" 2>/dev/null || true
    [ -n "${_lsme_bind_targets:-}" ] || rm -f "$_lsabt_seen" 2>/dev/null || true
    [ "$_lsabt_failed" -eq 0 ] || return 1
    [ "$_lsabt_mounted" -eq "$_lsabt_expected" ] || return 1
    # Distinguish an actual bind failure from an additive-only component whose
    # files have no pre-existing ROM inode. The caller may skip the latter for
    # non-core components, but system/fonts remains mandatory.
    [ "$_lsabt_total" -gt 0 ] 2>/dev/null || return 2
    return 0
}

# Validate every logical path before issuing any payload bind. Successful
# directory overlays are already present, so independently covered aliases now
# resolve to distinct paths and remain supported. Failed overlays retain the
# ROM symlink graph and must agree on the bytes for each shared terminal.
_luoshu_atomic_preflight_targets() (
    _lsap_plan="$1"
    _lsap_state=$(_luoshu_self_state_root)
    _lsap_map="$_lsap_state/preflight-targets.$$"
    _lsap_files="$_lsap_state/preflight-files.$$"
    trap 'rm -f "$_lsap_map" "$_lsap_files"' EXIT
    : > "$_lsap_map" || exit 1
    while IFS='|' read -r _lsap_source _lsap_target _lsap_mode; do
        find "$_lsap_source" -type f > "$_lsap_files" 2>/dev/null || exit 1
        while IFS= read -r _lsap_src; do
            _lsap_rel=${_lsap_src#$_lsap_source/}
            _lsap_dst="$_lsap_target/$_lsap_rel"
            if [ ! -f "$_lsap_dst" ]; then
                _luoshu_atomic_missing_target_allowed "$_lsap_rel" "$_lsap_mode" && continue
                exit 1
            fi
            _lsap_real=$(_luoshu_atomic_real_target "$_lsap_dst")
            _lsap_prior=$(awk -F '|' -v target="$_lsap_real" '$1 == target {print $2; exit}' "$_lsap_map")
            if [ -n "$_lsap_prior" ]; then
                if ! _luoshu_atomic_files_equal "$_lsap_prior" "$_lsap_src"; then
                    _luoshu_self_log "自挂载目标冲突：$_lsap_prior 与 $_lsap_src 解析到 $_lsap_real，无法同时满足"
                    exit 1
                fi
            else
                printf '%s|%s\n' "$_lsap_real" "$_lsap_src" >> "$_lsap_map" || exit 1
            fi
        done < "$_lsap_files"
    done < "$_lsap_plan"
)

# Shared by the module-tree and private-payload entry points. Bind fallback is
# deferred until all components have been planned, preventing cross-partition
# aliases from overwriting a previously verified target later in the transaction.
_luoshu_atomic_finish_plan() {
    _lsafp_plan="$1"
    _lsafp_payload="$2"
    _lsafp_required="$3"
    _lsafp_ready="${_lsafp_plan}.ready"
    if ! _luoshu_atomic_preflight_targets "$_lsafp_plan"; then
        _lsme_failed=physical-target-conflict
        return 1
    fi
    : > "$_lsafp_ready" || return 1
    _lsme_bind_targets="$_lsme_state_root/transaction-bind-targets.$$"
    : > "$_lsme_bind_targets" || return 1
    _lsme_component_count=0
    _lsme_bind_count=0
    _lsme_any_fonts_ok=0
    _lsme_system_fonts_ok=0
    _lsme_mounted=''
    while IFS='|' read -r _lsafp_source _lsafp_target _lsafp_mode; do
        _lsafp_component=${_lsafp_source#$_lsafp_payload/}
        if [ "$_lsafp_mode" = bind ]; then
            _luoshu_atomic_bind_tree "$_lsafp_source" "$_lsafp_target"
            _lsafp_rc=$?
            if [ "$_lsafp_rc" -eq 2 ]; then
                if [ "$_lsafp_required" = system ] && [ "$_lsafp_component" = system/fonts ]; then
                    _lsme_failed=system/fonts-bind-empty
                    break
                fi
                continue
            elif [ "$_lsafp_rc" -ne 0 ]; then
                _lsme_failed="$_lsafp_component-bind-incomplete"
                break
            fi
            _lsme_bind_count=$((_lsme_bind_count + 1))
        fi
        if ! _luoshu_atomic_tree_visible "$_lsafp_source" "$_lsafp_target" "$_lsafp_mode"; then
            _lsme_failed="$_lsafp_component-visibility-mismatch"
            break
        fi
        printf '%s|%s|%s\n' "$_lsafp_source" "$_lsafp_target" "$_lsafp_mode" >> "$_lsafp_ready" || {
            _lsme_failed="$_lsafp_component-manifest-failed"; break;
        }
        _lsme_component_count=$((_lsme_component_count + 1))
        _lsme_mounted="${_lsme_mounted}${_lsme_mounted:+,}$_lsafp_component:$_lsafp_mode"
        [ "$_lsafp_component" != system/fonts ] || _lsme_system_fonts_ok=1
        case "$_lsafp_component" in */fonts) _lsme_any_fonts_ok=1 ;; esac
    done < "$_lsafp_plan"
    rm -f "$_lsme_bind_targets" 2>/dev/null || true
    _lsme_bind_targets=''
    if [ -n "$_lsme_failed" ]; then
        rm -f "$_lsafp_ready"
        return 1
    fi
    mv -f "$_lsafp_ready" "$_lsafp_plan" || { _lsme_failed=manifest-commit-failed; return 1; }
    return 0
}

# Query the mount that path resolution actually reaches. mountinfo row order
# is not an ownership guarantee. FD0 survives Android mksh's CLOEXEC high FDs.
_luoshu_visible_mount_id() (
    exec 8< "$1" || exit 1
    id=$(awk '/^mnt_id:/{print $2;found=1;exit}END{if(!found)exit 1}' /proc/self/fdinfo/0 0<&8) || exit 1
    case "$id" in ''|*[!0-9]*) exit 1 ;; esac
    printf '%s\n' "$id"
)

# Never recursively remove a directory after a failed unmount. These trees
# contain only mount points; any nonempty/busy point remains for diagnosis.
_luoshu_atomic_empty_state_dirs() (
    state="$1"
    for dir in "$state/lower" "$state/work" "$state/memory-layers"; do
        [ -d "$dir" ] || continue
        for point in "$dir"/*; do [ ! -d "$point" ] || rmdir "$point" 2>/dev/null || true; done
        rmdir "$dir" 2>/dev/null || true
    done
    # Retain the budget if a memory mount remains (e.g. an unmount failure).
    [ -d "$state/memory-layers" ] || rm -f "$state/memory-layer-kb"
)

_luoshu_atomic_rollback() {
    _lsar_list="$1"
    _lsar_state=$(_luoshu_self_state_root)
    _lsar_incomplete=0
    _lsar_skip="${_lsar_list}.owned.$$"
    : > "$_lsar_skip" || return 1
    for _lsar_intent in "$_lsar_state/overlay-intents"/*; do
        [ -f "$_lsar_intent" ] || continue
        IFS='|' read -r _lsar_source _lsar_lower _lsar_target _lsar_baseline _lsar_owned < "$_lsar_intent" || { _lsar_incomplete=1; continue; }
        # This target is handled by its ownership record, never by bare path.
        printf '%s\n' "$_lsar_target" >> "$_lsar_skip"
        _lsar_current=$(_luoshu_visible_mount_id "$_lsar_target")
        if [ "$_lsar_current" != "$_lsar_baseline" ]; then
            if { [ -z "$_lsar_owned" ] || [ "$_lsar_current" = "$_lsar_owned" ]; } && awk -v p="$_lsar_target" -v visible="$_lsar_current" -v layers="lowerdir=$_lsar_source:$_lsar_lower" '$5==p&&$1==visible{row=$0}END{at=index(row,layers);tail=substr(row,at+length(layers),1);ok=index(row," - overlay KSU ") && at && (tail=="," || tail==" " || tail=="");exit !ok}' /proc/self/mountinfo; then
                _luoshu_umount_cmd "$_lsar_target" >/dev/null 2>&1 || true
                _lsar_current=$(_luoshu_visible_mount_id "$_lsar_target")
            fi
        fi
        if [ "$_lsar_current" = "$_lsar_baseline" ]; then
            awk -v p="$_lsar_target" '$0!=p' "$_lsar_list" > "$_lsar_list.pruned.$$" &&
                mv "$_lsar_list.pruned.$$" "$_lsar_list" || { _lsar_incomplete=1; continue; }
            rm -f "$_lsar_intent"
        else
            _lsar_incomplete=1
        fi
    done
    if [ "$_lsar_incomplete" -ne 0 ]; then
        rm -f "$_lsar_skip"
        return 1
    fi
    _lsar_remaining="${_lsar_list}.remaining.$$"
    : > "$_lsar_remaining" || return 1
    if [ -s "$_lsar_list" ]; then
        awk '{ item[NR]=$0 } END { for (i=NR; i>=1; i--) if(!seen[item[i]]++) print item[i] }' "$_lsar_list" 2>/dev/null | \
        while IFS= read -r _lsar_target; do
            [ -n "$_lsar_target" ] || continue
            if grep -Fqx "$_lsar_target" "$_lsar_skip"; then
                # Retain only if its ownership record could not restore baseline.
                if grep -Fq "|$_lsar_target|" "$_lsar_state/overlay-intents"/* 2>/dev/null; then
                    printf '%s\n' "$_lsar_target" >> "$_lsar_remaining"
                fi
                continue
            fi
            _luoshu_umount_cmd "$_lsar_target" >/dev/null 2>&1 || true
            if awk -v p="$_lsar_target" '$5==p {found=1} END{exit !found}' /proc/self/mountinfo; then
                printf '%s\n' "$_lsar_target" >> "$_lsar_remaining"
            fi
        done
    fi
    # Restore original journal order for another cleanup attempt.
    awk '{ item[NR]=$0 } END { for(i=NR;i>=1;i--)print item[i] }' "$_lsar_remaining" > "$_lsar_list"
    rm -f "$_lsar_remaining"
    rm -f "$_lsar_skip"
    _luoshu_atomic_empty_state_dirs "$_lsar_state"
    [ ! -s "$_lsar_list" ] && [ "$_lsar_incomplete" -eq 0 ]

}

_luoshu_atomic_verify_manifest() {
    _lsavm_manifest="${1:-$(_luoshu_atomic_manifest)}"
    [ -s "$_lsavm_manifest" ] || return 1
    while IFS='|' read -r _lsavm_source _lsavm_target _lsavm_mode; do
        [ -n "$_lsavm_source" ] && [ -n "$_lsavm_target" ] || return 1
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
        [ "$_lsme_same_boot" -eq 0 ] || _luoshu_atomic_rollback "$_lsme_mount_list" || return 1
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

    [ "$_lsme_same_boot" -eq 0 ] || _luoshu_atomic_rollback "$_lsme_mount_list" || return 1
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
                if type _luoshu_capture_lower_dir >/dev/null 2>&1; then
                    _luoshu_capture_lower_dir "$_lsme_target" \
                        "${_lsme_partition}-${_lsme_subdir}" || \
                        _luoshu_self_log \
                            "自挂载无法保留原厂 lower：$_lsme_partition/$_lsme_subdir"
                fi
            fi
            printf '%s|%s|%s\n' "$_lsme_source" "$_lsme_target" "$_lsme_mode" \
                >> "$_lsme_manifest_temp" 2>/dev/null || {
                _lsme_failed="$_lsme_partition/$_lsme_subdir-manifest-failed"
                break
            }

        done
        [ -z "$_lsme_failed" ] || break
    done

    if [ -z "$_lsme_failed" ]; then
        _luoshu_atomic_finish_plan "$_lsme_manifest_temp" "$_lsme_module" system || \
            _lsme_failed="${_lsme_failed:-bind-plan-failed}"
    fi

    [ "$_lsme_component_count" -gt 0 ] 2>/dev/null || _lsme_failed="${_lsme_failed:-payload-empty}"
    [ "$_lsme_system_fonts_ok" -eq 1 ] 2>/dev/null || _lsme_failed="${_lsme_failed:-system/fonts-required}"
    if [ -z "$_lsme_failed" ]; then
        _luoshu_atomic_verify_manifest_retry "$_lsme_manifest_temp" || _lsme_failed=pid1-visibility-mismatch
    fi

    if [ -n "$_lsme_failed" ]; then
        if ! _luoshu_atomic_rollback "$_lsme_mount_list"; then
            _luoshu_self_state_write failed rollback-incomplete "$_lsme_mounted" "$_lsme_failed"
            _luoshu_self_log "自挂载失败，回滚未完成；保留挂载记录"
            return 1
        fi
        rm -f "$_lsme_manifest" "$_lsme_manifest_temp" 2>/dev/null || true
        _luoshu_self_state_write failed rollback "$_lsme_mounted" "$_lsme_failed"
        _luoshu_self_log "自挂载事务失败并已完整回滚：failed=$_lsme_failed mounted=$_lsme_mounted"
        return 1
    fi

    mv -f "$_lsme_manifest_temp" "$_lsme_manifest" 2>/dev/null || {
        if ! _luoshu_atomic_rollback "$_lsme_mount_list"; then
            _luoshu_self_state_write failed rollback-incomplete "$_lsme_mounted" manifest-commit-failed
            return 1
        fi
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
