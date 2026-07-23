#!/system/bin/sh
# LuoShu v2.2 integration bridge.
# Load after ROM adapters, font_config_runtime, weight preparation and final hotfixes.
set +e

_dfpb_module="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
[ -f "$_dfpb_module/common/device_font_payload_runtime.sh" ] && . "$_dfpb_module/common/device_font_payload_runtime.sh"

# Force one background rebuild when upgrading from the uniform-metrics payload.
LUOSHU_PAYLOAD_SCHEMA_CURRENT="device-template-v1-baseline-v7-mono-v6"

# Prefer the already prepared 100-900 files, then ROM-specific anchors. This keeps
# direct, variable and composite flows on the same source selection contract.
_dfpr_anchor_lines() {
    _dfpr_store="$1"
    _dfpr_module_dir="$(_dfpr_module)"
    _dfpr_fonts="$_dfpr_module_dir/system/fonts"
    for _dfpr_pair in \
        '100:thin' '200:extralight' '300:light' '400:regular' '500:medium' \
        '600:semibold' '700:bold' '800:extrabold' '900:black'; do
        _dfpr_weight=${_dfpr_pair%%:*}
        _dfpr_name=${_dfpr_pair#*:}
        for _dfpr_path in \
            "$_dfpr_fonts/LuoShu-${_dfpr_weight}.ttf" \
            "$_dfpr_store/wght-${_dfpr_weight}.font" \
            "$_dfpr_store/compact-wght-${_dfpr_weight}.font" \
            "$_dfpr_store/${_dfpr_name}.font" \
            "$_dfpr_store/compact-${_dfpr_name}.font"; do
            if [ -s "$_dfpr_path" ]; then
                printf '%s|%s\n' "$_dfpr_weight" "$_dfpr_path"
                break
            fi
        done
    done
    if [ ! -s "$_dfpr_fonts/LuoShu-400.ttf" ]; then
        for _dfpr_path in "$_dfpr_store/regular.font" "$_dfpr_store/compact-regular.font" "$_dfpr_store/mix-composite.font"; do
            [ -s "$_dfpr_path" ] || continue
            printf '400|%s\n' "$_dfpr_path"
            break
        done
    fi
}

# Clear v2 paths before delegating to the legacy cleanup implementation.
font_config_disable() {
    type device_font_payload_clear >/dev/null 2>&1 && device_font_payload_clear
    type luoshu_dynamic_targets_clear >/dev/null 2>&1 && luoshu_dynamic_targets_clear
    if type _luoshu_font_config_disable_base >/dev/null 2>&1; then
        _luoshu_font_config_disable_base
    fi
}

# Composite/finalize flows already prepare deterministic 100-900 sources. Prefer the
# device engine; unsupported CFF/TTC sources fall back to the established XML path.
font_config_enable_for_payload() {
    _dfpb_family="${1:-unknown}"
    type font_config_prepare_payload_weights >/dev/null 2>&1 || return 1
    font_config_prepare_payload_weights || {
        font_config_disable
        return 1
    }
    if type device_font_payload_build_install >/dev/null 2>&1; then
        device_font_payload_build_install "$_dfpb_family"
        _dfpb_rc=$?
        case "$_dfpb_rc" in
            0) return 0 ;;
            1) font_config_disable; return 1 ;;
            2) ;;
        esac
    fi
    type font_config_generate >/dev/null 2>&1 || return 1
    font_config_generate "$_dfpb_family"
}

# Unified direct-font dispatch. The legacy adapter first prepares physical hidden
# slots and source anchors; v2 then replaces every captured XML/dynamic family with
# stock-aligned derivatives. A soft v2 refusal keeps the complete legacy mapping.
apply_font_by_rom() {
    _dfpb_src="$1"
    _dfpb_dest="$2"
    _dfpb_mode="${3:-full}"
    _dfpb_family="${4:-}"
    if [ "${IS_HYPEROS:-false}" = true ]; then
        copy_as_hyperos "$_dfpb_src" "$_dfpb_dest" "$_dfpb_mode" "$_dfpb_family"
    elif [ "${IS_COLOROS:-false}" = true ]; then
        copy_as_coloros "$_dfpb_src" "$_dfpb_dest" "$_dfpb_mode" "$_dfpb_family"
    else
        copy_as_generic "$_dfpb_src" "$_dfpb_dest" "$_dfpb_mode"
    fi
    _dfpb_adapter_rc=$?
    [ "$_dfpb_adapter_rc" -eq 0 ] || return "$_dfpb_adapter_rc"
    [ "$_dfpb_mode" = quick ] || return 0
    type device_font_payload_build_install >/dev/null 2>&1 || return 0
    device_font_payload_build_install "${_dfpb_family:-direct}"
    _dfpb_engine_rc=$?
    case "$_dfpb_engine_rc" in
        0)
            type _log_step >/dev/null 2>&1 && _log_step '  已生成并安装本机原厂槽位对齐负载'
            return 0
            ;;
        2)
            type _log_step >/dev/null 2>&1 && _log_step '  当前字体暂不支持逐槽位轮廓生成，保留完整兼容映射'
            return 0
            ;;
        *)
            type _log_step >/dev/null 2>&1 && _log_step '  设备专属负载提交失败，正在恢复上一套字体'
            return 1
            ;;
    esac
}

# Final validation override. v2 files use content hashes from their own installed
# manifest; legacy payloads retain the existing metadata-only fast path.
luoshu_payload_validate_current() {
    _lpv_active="${1:-unknown}"
    _lpv_module="$(_luoshu_safety_module)"
    _lpv_config="$(_luoshu_safety_config)"
    [ "$_lpv_active" != default ] || return 0
    if type device_font_payload_is_installed >/dev/null 2>&1 && device_font_payload_is_installed; then
        device_font_payload_validate_installed || return 1
        LUOSHU_PAYLOAD_VALIDATED_ACTIVE="$_lpv_active"
        return 0
    fi
    _lpv_fonts=0
    for _lpv_part in $(_luoshu_payload_parts); do
        _lpv_dir="$_lpv_module/$_lpv_part/fonts"
        [ -d "$_lpv_dir" ] || continue
        for _lpv_file in "$_lpv_dir"/*.ttf "$_lpv_dir"/*.otf "$_lpv_dir"/*.ttc; do
            [ -f "$_lpv_file" ] || continue
            if type _luoshu_fast_font_ok >/dev/null 2>&1; then
                _luoshu_fast_font_ok "$_lpv_file" || return 1
            else
                _lpv_size=$(_luoshu_filesize "$_lpv_file")
                case "$_lpv_size" in ''|*[!0-9]*) return 1 ;; esac
                [ "$_lpv_size" -ge 1024 ] || return 1
            fi
            _lpv_fonts=$((_lpv_fonts + 1))
        done
    done
    [ "$_lpv_fonts" -gt 0 ] || return 1
    _lpv_targets=$(sed -n 's/^targets=//p' "$_lpv_config/font-target-coverage.conf" 2>/dev/null | head -n1)
    _lpv_mapped=$(sed -n 's/^mapped=//p' "$_lpv_config/font-target-coverage.conf" 2>/dev/null | head -n1)
    case "$_lpv_targets" in ''|*[!0-9]*) _lpv_targets=0 ;; esac
    case "$_lpv_mapped" in ''|*[!0-9]*) _lpv_mapped=0 ;; esac
    [ "$_lpv_targets" -eq "$_lpv_mapped" ] || return 1
    while IFS='|' read -r _lpv_key _lpv_real _lpv_overlay _lpv_font_dir; do
        [ -f "$_lpv_overlay" ] || continue
        grep -Eq 'LuoShu(Mono)?-[1-9][0-9][0-9]\.ttf' "$_lpv_overlay" 2>/dev/null || continue
        _luoshu_font_config_validate "$_lpv_overlay" "$_lpv_font_dir" || return 1
    done <<EOF_DFPB_VALIDATE
$(_luoshu_font_config_specs)
EOF_DFPB_VALIDATE
    LUOSHU_PAYLOAD_VALIDATED_ACTIVE="$_lpv_active"
    return 0
}

# Include v2 slot XML and the private dynamic config view in the boot manifest.
luoshu_payload_build_manifest() {
    _lpm_module="$(_luoshu_safety_module)"
    _lpm_config="$(_luoshu_safety_config)"
    _lpm_tmp="$_lpm_config/font-payload-manifest.conf.tmp.$$"
    _lpm_checksum_cache="$_lpm_config/.font-payload-checksums.$$"
    : > "$_lpm_tmp" 2>/dev/null || return 1
    : > "$_lpm_checksum_cache" 2>/dev/null || { rm -f "$_lpm_tmp"; return 1; }
    for _lpm_part in $(_luoshu_payload_parts); do
        _lpm_fonts="$_lpm_module/$_lpm_part/fonts"
        if [ -d "$_lpm_fonts" ]; then
            find "$_lpm_fonts" -type f 2>/dev/null | while IFS= read -r _lpm_file; do
                case "$_lpm_file" in *.ttf|*.otf|*.ttc|*.TTF|*.OTF|*.TTC) ;; *) continue ;; esac
                _lpm_rel=${_lpm_file#$_lpm_module/}
                _lpm_sum=$(_luoshu_cached_checksum "$_lpm_file" "$_lpm_checksum_cache")
                [ -n "$_lpm_sum" ] && printf '%s|%s\n' "$_lpm_rel" "$_lpm_sum"
            done >> "$_lpm_tmp"
        fi
        _lpm_etc="$_lpm_module/$_lpm_part/etc"
        if [ -d "$_lpm_etc" ]; then
            find "$_lpm_etc" -maxdepth 1 -type f -name '*.xml' 2>/dev/null | while IFS= read -r _lpm_file; do
                case "${_lpm_file##*/}" in
                    .luoshu-data-fonts-config.xml) ;;
                    *) grep -Eq 'LuoShu(Mono)?-|LuoShuSlot-' "$_lpm_file" 2>/dev/null || continue ;;
                esac
                _lpm_rel=${_lpm_file#$_lpm_module/}
                _lpm_sum=$(_luoshu_cached_checksum "$_lpm_file" "$_lpm_checksum_cache")
                [ -n "$_lpm_sum" ] && printf '%s|%s\n' "$_lpm_rel" "$_lpm_sum"
            done >> "$_lpm_tmp"
        fi
    done
    rm -f "$_lpm_checksum_cache" 2>/dev/null || true
    [ -s "$_lpm_tmp" ] || { rm -f "$_lpm_tmp" 2>/dev/null; return 1; }
    mv -f "$_lpm_tmp" "$_lpm_config/font-payload-manifest.conf" 2>/dev/null || return 1
    chmod 0644 "$_lpm_config/font-payload-manifest.conf" 2>/dev/null || true
}

# Snapshot v2 state files together with the module partition tree so any failed
# switch restores the previous engine mode and dynamic-mount contract as well.
luoshu_payload_transaction_begin() {
    [ -z "$LUOSHU_PAYLOAD_TXN" ] || return 1
    LUOSHU_PAYLOAD_VALIDATED_ACTIVE=''
    _lpt_module="$(_luoshu_safety_module)"
    _lpt_config="$(_luoshu_safety_config)"
    LUOSHU_PAYLOAD_TXN="$_lpt_config/.payload-transaction.$$"
    rm -rf "$LUOSHU_PAYLOAD_TXN" 2>/dev/null || true
    mkdir -p "$LUOSHU_PAYLOAD_TXN/tree" "$LUOSHU_PAYLOAD_TXN/config" 2>/dev/null || { LUOSHU_PAYLOAD_TXN=''; return 1; }
    : > "$LUOSHU_PAYLOAD_TXN/paths"
    for _lpt_part in $(_luoshu_payload_parts); do
        for _lpt_sub in fonts etc; do
            _lpt_rel="$_lpt_part/$_lpt_sub"
            _lpt_src="$_lpt_module/$_lpt_rel"
            if [ -d "$_lpt_src" ]; then
                mkdir -p "$LUOSHU_PAYLOAD_TXN/tree/$_lpt_part" 2>/dev/null || return 1
                cp -al "$_lpt_src" "$LUOSHU_PAYLOAD_TXN/tree/$_lpt_rel" 2>/dev/null ||
                cp -af "$_lpt_src" "$LUOSHU_PAYLOAD_TXN/tree/$_lpt_rel" 2>/dev/null || {
                    mkdir -p "$LUOSHU_PAYLOAD_TXN/tree/$_lpt_rel" 2>/dev/null || return 1
                    cp -rfp "$_lpt_src/." "$LUOSHU_PAYLOAD_TXN/tree/$_lpt_rel/" 2>/dev/null || return 1
                }
                printf 'present|%s\n' "$_lpt_rel" >> "$LUOSHU_PAYLOAD_TXN/paths"
            else
                printf 'absent|%s\n' "$_lpt_rel" >> "$LUOSHU_PAYLOAD_TXN/paths"
            fi
        done
    done
    for _lpt_name in \
        active_font.conf font_mix.conf font-config-overlay.conf font-target-aliases.conf \
        font-target-coverage.conf font-payload-manifest.conf font-payload-boot.conf \
        font-payload-schema.conf text_reboot_required.conf device-font-engine.conf \
        device-font-installed.conf device-font-dynamic-mount.conf; do
        if [ -f "$_lpt_config/$_lpt_name" ]; then
            cp -fp "$_lpt_config/$_lpt_name" "$LUOSHU_PAYLOAD_TXN/config/$_lpt_name" 2>/dev/null || return 1
            printf 'present|config/%s\n' "$_lpt_name" >> "$LUOSHU_PAYLOAD_TXN/paths"
        else
            printf 'absent|config/%s\n' "$_lpt_name" >> "$LUOSHU_PAYLOAD_TXN/paths"
        fi
    done
    return 0
}

# Quarantine must also remove the private /data/fonts config view and its state.
luoshu_payload_quarantine() {
    _lpq_module="$(_luoshu_safety_module)"
    _lpq_config="$(_luoshu_safety_config)"
    _lpq_fail=$(cat "$_lpq_config/font-boot-failures" 2>/dev/null)
    case "$_lpq_fail" in ''|*[!0-9]*) _lpq_fail=0 ;; esac
    _lpq_fail=$((_lpq_fail + 1))
    printf '%s\n' "$_lpq_fail" > "$_lpq_config/font-boot-failures" 2>/dev/null || true
    type device_font_payload_clear >/dev/null 2>&1 && device_font_payload_clear
    for _lpq_part in $(_luoshu_payload_parts); do
        rm -rf "$_lpq_module/$_lpq_part/fonts" 2>/dev/null || true
        _lpq_etc="$_lpq_module/$_lpq_part/etc"
        [ -d "$_lpq_etc" ] || continue
        for _lpq_xml in "$_lpq_etc"/*.xml; do
            [ -f "$_lpq_xml" ] || continue
            grep -Eq 'LuoShu(Mono)?-|LuoShuSlot-' "$_lpq_xml" 2>/dev/null && rm -f "$_lpq_xml" 2>/dev/null || true
        done
    done
    if type luoshu_meta_content_roots >/dev/null 2>&1; then
        for _lpq_root in $(luoshu_meta_content_roots); do
            [ -d "$_lpq_root" ] || continue
            for _lpq_part in $(_luoshu_payload_parts); do
                rm -rf "$_lpq_root/$_lpq_part/fonts" 2>/dev/null || true
                _lpq_etc="$_lpq_root/$_lpq_part/etc"
                [ -d "$_lpq_etc" ] || continue
                for _lpq_xml in "$_lpq_etc"/*.xml; do
                    [ -f "$_lpq_xml" ] || continue
                    grep -Eq 'LuoShu(Mono)?-|LuoShuSlot-' "$_lpq_xml" 2>/dev/null && rm -f "$_lpq_xml" 2>/dev/null || true
                done
            done
        done
    fi
    printf 'default\n' > "$_lpq_config/active_font.conf" 2>/dev/null || true
    rm -f "$_lpq_config/font-payload-boot.conf" "$_lpq_config/font-payload-manifest.conf" \
          "$_lpq_config/font-payload-schema.conf" "$_lpq_config/font-payload-rebuild-pending.conf" \
          "$_lpq_config/font-target-aliases.conf" "$_lpq_config/font-target-coverage.conf" \
          "$_lpq_config/font-config-overlay.conf" 2>/dev/null || true
    {
        printf 'state=quarantined\n'
        printf 'failures=%s\n' "$_lpq_fail"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_lpq_config/font-payload-quarantine.conf" 2>/dev/null || true
    _luoshu_safety_log ERROR "检测到上次字体负载未完成开机，已撤销全部字体覆盖（failure=$_lpq_fail）"
}

unset _dfpb_module
