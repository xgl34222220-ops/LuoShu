#!/system/bin/sh
# LuoShu HyperOS coverage floor.
# Keep the batched scanner as the fast path, then union it with the v2.8 per-document scan on
# HyperOS. The per-document result is authoritative for scan health, so batch protocol/path
# regressions cannot silently reduce the set of physical UI font slots that gets materialized.
set +e

_luoshu_hcf_font_ok() {
    _hcf_file="$1"
    if type _luoshu_fast_font_ok >/dev/null 2>&1; then
        _luoshu_fast_font_ok "$_hcf_file"
        return $?
    fi
    [ -s "$_hcf_file" ] || return 1
    if type _luoshu_filesize >/dev/null 2>&1; then
        _hcf_size=$(_luoshu_filesize "$_hcf_file")
        case "$_hcf_size" in ''|*[!0-9]*) return 1 ;; esac
        [ "$_hcf_size" -ge 1024 ]
        return $?
    fi
    return 0
}

luoshu_dynamic_targets_apply() {
    _ldt_module="$(_luoshu_safety_module)"
    _ldt_config="$(_luoshu_safety_config)"
    _ldt_backup="$_ldt_config/font-config-source"
    _ldt_tool="$_ldt_module/common/font_config_targets.py"
    _ldt_manifest_tmp="$_ldt_config/font-target-aliases.conf.tmp.$$"
    _ldt_coverage_tmp="$_ldt_config/font-target-coverage.conf.tmp.$$"
    _ldt_records="$_ldt_config/.font-target-records.$$"
    _ldt_seen="$_ldt_config/.font-target-seen.$$"
    _ldt_jobs="$_ldt_config/.font-target-jobs.$$"
    _ldt_map="$_ldt_config/.font-target-map.$$"
    _ldt_out="$_ldt_config/.font-targets.$$.txt"
    [ -f "$_ldt_tool" ] && type _luoshu_font_config_exec >/dev/null 2>&1 || return 2
    type font_config_capture_original >/dev/null 2>&1 && font_config_capture_original >/dev/null 2>&1 || true

    luoshu_dynamic_targets_clear
    mkdir -p "$_ldt_config" 2>/dev/null || return 1
    : > "$_ldt_manifest_tmp" 2>/dev/null || return 1
    : > "$_ldt_records" 2>/dev/null || return 1
    : > "$_ldt_seen" 2>/dev/null || return 1
    : > "$_ldt_jobs" 2>/dev/null || return 1
    : > "$_ldt_map" 2>/dev/null || return 1

    _ldt_batch_configs=0
    _ldt_batch_scan_failed=0
    _ldt_v28_configs=0
    _ldt_v28_scan_failed=0
    _ldt_v28_extra=0

    # 3.x fast path: scan every captured XML in one interpreter and normalize the batch protocol
    # into a common record stream. Any TARGET whose document cannot be resolved back to its
    # partition is counted as a batch failure rather than disappearing from coverage accounting.
    while IFS='|' read -r _ldt_key _ldt_real _ldt_overlay _ldt_font_dir; do
        _ldt_input="$_ldt_backup/$_ldt_key"
        [ -s "$_ldt_input" ] || continue
        printf '%s\n' "$_ldt_input" >> "$_ldt_jobs"
        printf '%s\t%s\t%s\n' "$_ldt_input" "$_ldt_key" "$_ldt_font_dir" >> "$_ldt_map"
    done <<EOF_LUOSHU_HCF_BATCH
$(_luoshu_font_config_specs)
EOF_LUOSHU_HCF_BATCH

    : > "$_ldt_out"
    if [ -s "$_ldt_jobs" ]; then
        _luoshu_font_config_exec "$_ldt_tool" --batch "$_ldt_jobs" > "$_ldt_out" 2>/dev/null || \
            _ldt_batch_scan_failed=$((_ldt_batch_scan_failed + 1))
    fi

    _ldt_cur=''
    _ldt_key=''
    _ldt_font_dir=''
    while IFS="$(printf '\t')" read -r _ldt_tag _ldt_input _ldt_a _ldt_b _ldt_c; do
        case "$_ldt_tag" in
            DOC)
                if [ "$_ldt_a" = ok ]; then
                    _ldt_batch_configs=$((_ldt_batch_configs + 1))
                else
                    _ldt_batch_scan_failed=$((_ldt_batch_scan_failed + 1))
                fi
                continue
                ;;
            TARGET) ;;
            *) continue ;;
        esac
        if [ "$_ldt_input" != "$_ldt_cur" ]; then
            _ldt_cur="$_ldt_input"
            _ldt_key=$(awk -F'\t' -v k="$_ldt_input" '$1 == k { print $2; exit }' "$_ldt_map" 2>/dev/null)
            _ldt_font_dir=$(awk -F'\t' -v k="$_ldt_input" '$1 == k { print $3; exit }' "$_ldt_map" 2>/dev/null)
        fi
        if [ -z "$_ldt_key" ] || [ -z "$_ldt_font_dir" ]; then
            _ldt_batch_scan_failed=$((_ldt_batch_scan_failed + 1))
            continue
        fi
        printf '%s\t%s\t%s\t%s\t%s\tbatch\n' \
            "$_ldt_key" "$_ldt_font_dir" "$_ldt_a" "$_ldt_b" "$_ldt_c" >> "$_ldt_records"
    done < "$_ldt_out"

    # HyperOS coverage floor: replay the v2.8 per-document protocol and union its targets with the
    # fast-path records. This intentionally costs a few extra interpreter starts on HyperOS only;
    # it is the compatibility backstop for OEM XML/partition layouts that the batch protocol loses.
    if [ "${IS_HYPEROS:-false}" = true ]; then
        while IFS='|' read -r _ldt_key _ldt_real _ldt_overlay _ldt_font_dir; do
            _ldt_input="$_ldt_backup/$_ldt_key"
            [ -s "$_ldt_input" ] || continue
            _ldt_legacy_out="$_ldt_config/.font-target-v28.$$.txt"
            rm -f "$_ldt_legacy_out" 2>/dev/null || true
            if ! _luoshu_font_config_exec "$_ldt_tool" --input "$_ldt_input" > "$_ldt_legacy_out" 2>/dev/null; then
                _ldt_v28_scan_failed=$((_ldt_v28_scan_failed + 1))
                rm -f "$_ldt_legacy_out" 2>/dev/null || true
                continue
            fi
            _ldt_v28_configs=$((_ldt_v28_configs + 1))
            while IFS='|' read -r _ldt_file _ldt_weight _ldt_family; do
                [ -n "$_ldt_file" ] || continue
                printf '%s\t%s\t%s\t%s\t%s\tv28\n' \
                    "$_ldt_key" "$_ldt_font_dir" "$_ldt_file" "$_ldt_weight" "$_ldt_family" >> "$_ldt_records"
            done < "$_ldt_legacy_out"
            rm -f "$_ldt_legacy_out" 2>/dev/null || true
        done <<EOF_LUOSHU_HCF_V28
$(_luoshu_font_config_specs)
EOF_LUOSHU_HCF_V28
        _ldt_configs="$_ldt_v28_configs"
        _ldt_scan_failed="$_ldt_v28_scan_failed"
        _ldt_mode='hyperos-v28-union'
    else
        _ldt_configs="$_ldt_batch_configs"
        _ldt_scan_failed="$_ldt_batch_scan_failed"
        _ldt_mode='batch'
    fi

    # Materialize the union once. De-duplicate by final module-relative slot so batch + v2.8
    # discovery never double-counts the same physical target.
    _ldt_targets=0
    _ldt_mapped=0
    while IFS="$(printf '\t')" read -r _ldt_key _ldt_font_dir _ldt_file _ldt_weight _ldt_family _ldt_origin; do
        [ -n "$_ldt_font_dir" ] && [ -n "$_ldt_file" ] || continue
        case "$_ldt_file" in
            */*|*'..'*|LuoShu-*.ttf|LuoShuMono-*.ttf) continue ;;
            *.ttf|*.otf|*.ttc) ;;
            *) continue ;;
        esac
        case "$_ldt_weight" in 100|200|300|400|500|600|700|800|900) ;; *) _ldt_weight=400 ;; esac
        _ldt_rel="${_ldt_font_dir#$_ldt_module/}/$_ldt_file"
        grep -Fqx "$_ldt_rel" "$_ldt_seen" 2>/dev/null && continue
        printf '%s\n' "$_ldt_rel" >> "$_ldt_seen"
        _ldt_targets=$((_ldt_targets + 1))
        [ "$_ldt_origin" != v28 ] || _ldt_v28_extra=$((_ldt_v28_extra + 1))

        _ldt_source="$_ldt_module/system/fonts/LuoShu-${_ldt_weight}.ttf"
        _ldt_dest="$_ldt_font_dir/$_ldt_file"
        _luoshu_hcf_font_ok "$_ldt_source" || continue
        mkdir -p "$_ldt_font_dir" 2>/dev/null || continue
        rm -f "$_ldt_dest" 2>/dev/null || true
        if ln "$_ldt_source" "$_ldt_dest" 2>/dev/null || cp -f "$_ldt_source" "$_ldt_dest" 2>/dev/null; then
            chmod 0644 "$_ldt_dest" 2>/dev/null || true
            if _luoshu_hcf_font_ok "$_ldt_dest"; then
                printf '%s|%s|%s|%s\n' "$_ldt_rel" "$_ldt_key" "$_ldt_weight" "$_ldt_family" >> "$_ldt_manifest_tmp"
                _ldt_mapped=$((_ldt_mapped + 1))
            else
                rm -f "$_ldt_dest" 2>/dev/null || true
            fi
        fi
    done < "$_ldt_records"

    rm -f "$_ldt_jobs" "$_ldt_map" "$_ldt_out" "$_ldt_records" "$_ldt_seen" 2>/dev/null || true

    if [ "$_ldt_mapped" -eq 0 ]; then
        while IFS='|' read -r _ldt_rel _ldt_rest; do
            rm -f "$_ldt_module/$_ldt_rel" 2>/dev/null || true
        done < "$_ldt_manifest_tmp"
        rm -f "$_ldt_manifest_tmp" "$_ldt_coverage_tmp" 2>/dev/null || true
        _luoshu_safety_log ERROR "动态字体目标映射失败：mode=$_ldt_mode targets=$_ldt_targets mapped=0 scanFailed=$_ldt_scan_failed"
        return 1
    fi

    if [ "$_ldt_mapped" -eq "$_ldt_targets" ] && [ "$_ldt_scan_failed" -eq 0 ]; then
        _ldt_coverage_status=full
    else
        _ldt_coverage_status=partial
    fi

    {
        printf 'configs=%s\n' "$_ldt_configs"
        printf 'discovered=%s\n' "$_ldt_targets"
        printf 'targets=%s\n' "$_ldt_targets"
        printf 'mapped=%s\n' "$_ldt_mapped"
        printf 'status=%s\n' "$_ldt_coverage_status"
        printf 'scanFailed=%s\n' "$_ldt_scan_failed"
        printf 'mode=%s\n' "$_ldt_mode"
        printf 'batchConfigs=%s\n' "$_ldt_batch_configs"
        printf 'batchScanFailed=%s\n' "$_ldt_batch_scan_failed"
        printf 'v28Configs=%s\n' "$_ldt_v28_configs"
        printf 'v28ScanFailed=%s\n' "$_ldt_v28_scan_failed"
        printf 'fallbackAdded=%s\n' "$_ldt_v28_extra"
        printf 'time=%s\n' "$(date +%s)"
    } > "$_ldt_coverage_tmp" 2>/dev/null || return 1
    mv -f "$_ldt_manifest_tmp" "$_ldt_config/font-target-aliases.conf" 2>/dev/null || return 1
    mv -f "$_ldt_coverage_tmp" "$_ldt_config/font-target-coverage.conf" 2>/dev/null || return 1
    chmod 0644 "$_ldt_config/font-target-aliases.conf" "$_ldt_config/font-target-coverage.conf" 2>/dev/null || true

    [ "$_ldt_targets" -gt 0 ] || return 2
    if [ "$_ldt_coverage_status" = full ]; then
        if [ "${IS_HYPEROS:-false}" = true ]; then
            _luoshu_safety_log INFO "HyperOS 已按 2.8 覆盖下限完整映射 $_ldt_mapped/$_ldt_targets 个 UI 字体目标（fallbackAdded=$_ldt_v28_extra）"
        else
            _luoshu_safety_log INFO "已按设备真实 XML 完整映射 $_ldt_mapped/$_ldt_targets 个 UI 字体目标"
        fi
        return 0
    fi

    if [ "${IS_HYPEROS:-false}" = true ]; then
        _luoshu_safety_log ERROR "HyperOS 覆盖未达到 2.8 下限：targets=$_ldt_targets mapped=$_ldt_mapped scanFailed=$_ldt_scan_failed；拒绝把 partial 当成功"
        return 1
    fi
    _luoshu_safety_log WARN "已按设备真实 XML 部分映射 $_ldt_mapped/$_ldt_targets 个 UI 字体目标"
    return 0
}
