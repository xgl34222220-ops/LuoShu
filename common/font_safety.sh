#!/system/bin/sh
# LuoShu payload safety layer: complete target mapping, transactional switching and boot rollback.
# This file is sourced after font_config_runtime.sh has defined the *_base functions.
set +e

_luoshu_safety_module() {
    printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
}

_luoshu_safety_config() {
    printf '%s/config\n' "$(_luoshu_safety_module)"
}

LUOSHU_PAYLOAD_SCHEMA_CURRENT="${LUOSHU_PAYLOAD_SCHEMA_CURRENT:-baseline-v8-boot-safe}"

luoshu_payload_schema_current() {
    printf '%s\n' "$LUOSHU_PAYLOAD_SCHEMA_CURRENT"
}

luoshu_payload_schema_read() {
    sed -n 's/^schema=//p' "$(_luoshu_safety_config)/font-payload-schema.conf" 2>/dev/null | head -n1 | tr -d '\r\n'
}

luoshu_payload_schema_write() {
    _lpsw_active="${1:-default}"
    _lpsw_config="$(_luoshu_safety_config)"
    _lpsw_tmp="$_lpsw_config/font-payload-schema.conf.tmp.$$"
    mkdir -p "$_lpsw_config" 2>/dev/null || return 1
    {
        printf 'schema=%s\n' "$LUOSHU_PAYLOAD_SCHEMA_CURRENT"
        printf 'font=%s\n' "$_lpsw_active"
        printf 'time=%s\n' "$(date +%s)"
    } > "$_lpsw_tmp" 2>/dev/null || return 1
    mv -f "$_lpsw_tmp" "$_lpsw_config/font-payload-schema.conf" 2>/dev/null || return 1
    chmod 0644 "$_lpsw_config/font-payload-schema.conf" 2>/dev/null || true
}

_luoshu_payload_parts() {
    printf '%s\n' 'system system_ext product vendor odm oem my_product my_engineering my_company my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust'
}

_luoshu_safety_log() {
    if type log_message >/dev/null 2>&1; then
        log_message "$1" "$2"
    elif type _log_step >/dev/null 2>&1; then
        _log_step "$2"
    fi
}

_luoshu_checksum() {
    _lsc_file="$1"
    if command -v cksum >/dev/null 2>&1; then
        cksum "$_lsc_file" 2>/dev/null | awk '{print $1 "|" $2}'
    elif command -v toybox >/dev/null 2>&1; then
        toybox cksum "$_lsc_file" 2>/dev/null | awk '{print $1 "|" $2}'
    else
        wc -c < "$_lsc_file" 2>/dev/null | awk '{print "0|" $1}'
    fi
}

_luoshu_filesize() {
    _lfs_file="$1"
    if command -v stat >/dev/null 2>&1; then
        stat -c '%s' "$_lfs_file" 2>/dev/null && return 0
    fi
    if command -v toybox >/dev/null 2>&1; then
        toybox stat -c '%s' "$_lfs_file" 2>/dev/null && return 0
    fi
    wc -c < "$_lfs_file" 2>/dev/null | tr -d '[:space:]'
}

_luoshu_file_identity() {
    _lfi_file="$1"
    if command -v stat >/dev/null 2>&1; then
        stat -c '%d:%i:%s:%Y:%Z' "$_lfi_file" 2>/dev/null && return 0
    fi
    if command -v toybox >/dev/null 2>&1; then
        toybox stat -c '%d:%i:%s:%Y:%Z' "$_lfi_file" 2>/dev/null && return 0
    fi
    printf 'path:%s:%s\n' "$_lfi_file" "$(_luoshu_filesize "$_lfi_file")"
}

_luoshu_cached_checksum() {
    _lcc_file="$1"
    _lcc_cache="$2"
    _lcc_identity=$(_luoshu_file_identity "$_lcc_file")
    _lcc_value=$(awk -F'|' -v key="$_lcc_identity" '$1 == key { print $2 "|" $3; exit }' "$_lcc_cache" 2>/dev/null)
    if [ -z "$_lcc_value" ]; then
        _lcc_value=$(_luoshu_checksum "$_lcc_file")
        [ -n "$_lcc_value" ] || return 1
        printf '%s|%s\n' "$_lcc_identity" "$_lcc_value" >> "$_lcc_cache" 2>/dev/null || true
    fi
    printf '%s\n' "$_lcc_value"
}

luoshu_dynamic_targets_clear() {
    _ldt_module="$(_luoshu_safety_module)"
    _ldt_manifest="$(_luoshu_safety_config)/font-target-aliases.conf"
    [ -f "$_ldt_manifest" ] || return 0
    while IFS='|' read -r _ldt_rel _ldt_key _ldt_weight _ldt_family; do
        case "$_ldt_rel" in
            */fonts/*.ttf|*/fonts/*.otf|*/fonts/*.ttc) rm -f "$_ldt_module/$_ldt_rel" 2>/dev/null || true ;;
        esac
    done < "$_ldt_manifest"
    rm -f "$_ldt_manifest" "$(_luoshu_safety_config)/font-target-coverage.conf" 2>/dev/null || true
}

luoshu_dynamic_targets_apply() {
    _ldt_module="$(_luoshu_safety_module)"
    _ldt_config="$(_luoshu_safety_config)"
    _ldt_backup="$_ldt_config/font-config-source"
    _ldt_tool="$_ldt_module/common/font_config_targets.py"
    _ldt_manifest_tmp="$_ldt_config/font-target-aliases.conf.tmp.$$"
    _ldt_coverage_tmp="$_ldt_config/font-target-coverage.conf.tmp.$$"
    [ -f "$_ldt_tool" ] && type _luoshu_font_config_exec >/dev/null 2>&1 || return 2
    type font_config_capture_original >/dev/null 2>&1 && font_config_capture_original >/dev/null 2>&1 || true

    luoshu_dynamic_targets_clear
    : > "$_ldt_manifest_tmp" 2>/dev/null || return 1
    _ldt_targets=0
    _ldt_mapped=0
    _ldt_configs=0
    _ldt_scan_failed=0

    # One interpreter scans every document. The per-document form paid a full embedded-CPython start
    # for each font configuration file the ROM ships, before a single font was touched, which is a
    # large part of why a switch grew from seconds to minutes as the partition matrix expanded.
    _ldt_jobs="$_ldt_config/.font-target-jobs.$$"
    _ldt_map="$_ldt_config/.font-target-map.$$"
    _ldt_out="$_ldt_config/.font-targets.$$.txt"
    : > "$_ldt_jobs" 2>/dev/null || return 1
    : > "$_ldt_map" 2>/dev/null || { rm -f "$_ldt_jobs"; return 1; }
    while IFS='|' read -r _ldt_key _ldt_real _ldt_overlay _ldt_font_dir; do
        _ldt_input="$_ldt_backup/$_ldt_key"
        [ -s "$_ldt_input" ] || continue
        printf '%s\n' "$_ldt_input" >> "$_ldt_jobs"
        printf '%s\t%s\t%s\n' "$_ldt_input" "$_ldt_key" "$_ldt_font_dir" >> "$_ldt_map"
    done <<EOF_LUOSHU_DYNAMIC_TARGETS
$(_luoshu_font_config_specs)
EOF_LUOSHU_DYNAMIC_TARGETS

    : > "$_ldt_out"
    if [ -s "$_ldt_jobs" ]; then
        _luoshu_font_config_exec "$_ldt_tool" --batch "$_ldt_jobs" > "$_ldt_out" 2>/dev/null || \
            _ldt_scan_failed=$((_ldt_scan_failed + 1))
    fi

    # The batch groups its output by document, so the key/font-dir lookup only repeats when the
    # document changes rather than once per target.
    _ldt_cur=''
    _ldt_key=''
    _ldt_font_dir=''
    while IFS="$(printf '\t')" read -r _ldt_tag _ldt_input _ldt_a _ldt_b _ldt_c; do
        case "$_ldt_tag" in
            DOC)
                if [ "$_ldt_a" = ok ]; then
                    _ldt_configs=$((_ldt_configs + 1))
                else
                    _ldt_scan_failed=$((_ldt_scan_failed + 1))
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
        [ -n "$_ldt_font_dir" ] || continue
        _ldt_file="$_ldt_a"
        _ldt_weight="$_ldt_b"
        _ldt_family="$_ldt_c"
        case "$_ldt_file" in
            */*|*'..'*|LuoShu-*.ttf) continue ;;
            *.ttf|*.otf|*.ttc) ;;
            *) continue ;;
        esac
        case "$_ldt_weight" in 100|200|300|400|500|600|700|800|900) ;; *) _ldt_weight=400 ;; esac
        _ldt_rel="${_ldt_font_dir#$_ldt_module/}/$_ldt_file"
        grep -Fq "$_ldt_rel|" "$_ldt_manifest_tmp" 2>/dev/null && continue
        _ldt_targets=$((_ldt_targets + 1))
        _ldt_source="$_ldt_module/system/fonts/LuoShu-${_ldt_weight}.ttf"
        _ldt_dest="$_ldt_font_dir/$_ldt_file"
        [ -s "$_ldt_source" ] || continue
        mkdir -p "$_ldt_font_dir" 2>/dev/null || continue
        rm -f "$_ldt_dest" 2>/dev/null || true
        if ln "$_ldt_source" "$_ldt_dest" 2>/dev/null || cp -f "$_ldt_source" "$_ldt_dest" 2>/dev/null; then
            chmod 0644 "$_ldt_dest" 2>/dev/null || true
            _ldt_size=$(_luoshu_filesize "$_ldt_dest")
            case "$_ldt_size" in ''|*[!0-9]*) _ldt_size=0 ;; esac
            if [ "$_ldt_size" -ge 1024 ]; then
                printf '%s|%s|%s|%s\n' "$_ldt_rel" "$_ldt_key" "$_ldt_weight" "$_ldt_family" >> "$_ldt_manifest_tmp"
                _ldt_mapped=$((_ldt_mapped + 1))
            else
                rm -f "$_ldt_dest" 2>/dev/null || true
            fi
        fi
    done < "$_ldt_out"
    rm -f "$_ldt_jobs" "$_ldt_map" "$_ldt_out" 2>/dev/null || true

    # Unmapped targets keep their stock font. Zero useful mappings is a hard failure; non-zero partial
    # coverage is committed and reported honestly instead of collapsing an unfamiliar ROM to zero.
    if [ "$_ldt_mapped" -eq 0 ]; then
        while IFS='|' read -r _ldt_rel _ldt_rest; do rm -f "$_ldt_module/$_ldt_rel" 2>/dev/null || true; done < "$_ldt_manifest_tmp"
        rm -f "$_ldt_manifest_tmp" "$_ldt_coverage_tmp" 2>/dev/null || true
        _luoshu_safety_log ERROR "åŠ¨æ€å­—ä½“ç›®æ ‡æ˜ å°„å¤±è´¥ï¼štargets=$_ldt_targets mapped=0 scanFailed=$_ldt_scan_failed"
        return 1
    fi
    if [ "$_ldt_mapped" -eq "$_ldt_targets" ] && [ "$_ldt_scan_failed" -eq 0 ]; then
        _ldt_coverage_status=full
    else
        _ldt_coverage_status=partial
        _luoshu_safety_log WARN "éƒ¨åˆ†å­—ä½“ç›®æ ‡æœªèƒ½æ˜ å°„ï¼Œæœªæ˜ å°„é¡¹ä¿ç•™åŽŸåŽ‚å­—ä½“ï¼štargets=$_ldt_targets mapped=$_ldt_mapped scanFailed=$_ldt_scan_failed"
    fi

    {
        printf 'configs=%s\n' "$_ldt_configs"
        printf 'discovered=%s\n' "$_ldt_targets"
        printf 'targets=%s\n' "$_ldt_targets"
        printf 'mapped=%s\n' "$_ldt_mapped"
        printf 'status=%s\n' "$_ldt_coverage_status"
        printf 'scanFailed=%s\n' "$_ldt_scan_failed"
        printf 'time=%s\n' "$(date +%s)"
    } > "$_ldt_coverage_tmp" 2>/dev/null || return 1
    mv -f "$_ldt_manifest_tmp" "$_ldt_config/font-target-aliases.conf" 2>/dev/null || return 1
    mv -f "$_ldt_coverage_tmp" "$_ldt_config/font-target-coverage.conf" 2>/dev/null || return 1
    chmod 0644 "$_ldt_config/font-target-aliases.conf" "$_ldt_config/font-target-coverage.conf" 2>/dev/null || true
    [ "$_ldt_targets" -gt 0 ] || return 2
    if [ "$_ldt_coverage_status" = full ]; then
        _luoshu_safety_log INFO "å·²æŒ‰è®¾å¤‡çœŸå®ž XML å®Œæ•´æ˜ å°„ $_ldt_mapped/$_ldt_targets ä¸ª UI å­—ä½“ç›®æ ‡"
    else
        _luoshu_safety_log WARN "å·²æŒ‰è®¾å¤‡çœŸå®ž XML éƒ¨åˆ†æ˜ å°„ $_ldt_mapped/$_ldt_targets ä¸ª UI å­—ä½“ç›®æ ‡"
    fi
    return 0
}

font_config_disable() {
    luoshu_dynamic_targets_clear
    if type _luoshu_font_config_disable_base >/dev/null 2>&1; then
        _luoshu_font_config_disable_base
    fi
}

font_config_generate() {
    _lfg_family="$1"
    _lfg_dynamic=0
    luoshu_dynamic_targets_apply
    _lfg_dynamic=$?
    [ "$_lfg_dynamic" -ne 1 ] || { font_config_disable; return 1; }
    if type _luoshu_font_config_generate_base >/dev/null 2>&1 && _luoshu_font_config_generate_base "$_lfg_family"; then
        return 0
    fi
    # A ROM may expose UI file slots without a safely rewritable named family. Keep any validated
    # non-zero dynamic mapping; unmapped targets remain on the stock font and are reported as partial.
    [ "$_lfg_dynamic" -eq 0 ] && return 0
    font_config_disable
    return 1
}

luoshu_payload_validate_current() {
    _lpv_active="${1:-unknown}"
    _lpv_module="$(_luoshu_safety_module)"
    _lpv_config="$(_luoshu_safety_config)"
    [ "$_lpv_active" != default ] || return 0
    _lpv_fonts=0
    for _lpv_part in $(_luoshu_payload_parts); do
        _lpv_dir="$_lpv_module/$_lpv_part/fonts"
        [ -d "$_lpv_dir" ] || continue
        for _lpv_file in "$_lpv_dir"/*.ttf "$_lpv_dir"/*.otf "$_lpv_dir"/*.ttc; do
            [ -f "$_lpv_file" ] || continue
            _lpv_size=$(_luoshu_filesize "$_lpv_file")
            case "$_lpv_size" in ''|*[!0-9]*) _lpv_size=0 ;; esac
            [ "$_lpv_size" -ge 1024 ] || return 1
            _lpv_fonts=$((_lpv_fonts + 1))
        done
    done
    [ "$_lpv_fonts" -gt 0 ] || return 1

    _lpv_coverage="$_lpv_config/font-target-coverage.conf"
    if [ -f "$_lpv_coverage" ]; then
        _lpv_targets=$(sed -n 's/^targets=//p' "$_lpv_coverage" 2>/dev/null | head -n1)
        _lpv_mapped=$(sed -n 's/^mapped=//p' "$_lpv_coverage" 2>/dev/null | head -n1)
        _lpv_status=$(sed -n 's/^status=//p' "$_lpv_coverage" 2>/dev/null | head -n1)
        case "$_lpv_targets" in ''|*[!0-9]*) return 1 ;; esac
        case "$_lpv_mapped" in ''|*[!0-9]*) return 1 ;; esac
        [ "$_lpv_mapped" -le "$_lpv_targets" ] || return 1
        case "$_lpv_status" in
            full) [ "$_lpv_mapped" -eq "$_lpv_targets" ] || return 1 ;;
            partial) [ "$_lpv_mapped" -gt 0 ] && [ "$_lpv_mapped" -lt "$_lpv_targets" ] || return 1 ;;
            '') [ "$_lpv_targets" -eq 0 ] || [ "$_lpv_mapped" -gt 0 ] || return 1 ;;
            *) return 1 ;;
        esac
        if [ "$_lpv_mapped" -gt 0 ]; then
    _lpv_manifest="$_lpv_config/font-target-aliases.conf"
    _lpv_manifest_count=$(awk 'NF { n++ } END { print n+0 }' "$_lpv_manifest" 2>/dev/null)
    case "$_lpv_manifest_count" in ''|*[!0-9]*) return 1 ;; esac
    [ "$_lpv_manifest_count" -eq "$_lpv_mapped" ] || return 1
    while IFS='|' read -r _lpv_rel _lpv_key _lpv_weight _lpv_family; do
        [ -n "$_lpv_rel" ] || continue
        case "$_lpv_rel" in */fonts/*.ttf|*/fonts/*.otf|*/fonts/*.ttc) ;; *) return 1 ;; esac
        [ -f "$_lpv_module/$_lpv_rel" ] || return 1
        if type _luoshu_fast_font_ok >/dev/null 2>&1; then
            _luoshu_fast_font_ok "$_lpv_module/$_lpv_rel" || return 1
        fi
    done < "$_lpv_manifest"
fi
    fi

    while IFS='|' read -r _lpv_key _lpv_real _lpv_overlay _lpv_font_dir; do
        [ -f "$_lpv_overlay" ] || continue
        grep -Eq 'LuoShu(Mono)?-[1-9][0-9][0-9]\.ttf' "$_lpv_overlay" 2>/dev/null || continue
        _luoshu_font_config_validate "$_lpv_overlay" "$_lpv_font_dir" || return 1
    done <<EOF_LUOSHU_VALIDATE
$(_luoshu_font_config_specs)
EOF_LUOSHU_VALIDATE
    LUOSHU_PAYLOAD_VALIDATED_ACTIVE="$_lpv_active"
    return 0
}

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
                grep -Eq 'LuoShu(Mono)?-[1-9][0-9][0-9]\.ttf' "$_lpm_file" 2>/dev/null || continue
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

luoshu_payload_validate_manifest_full() {
    _lpvm_module="$(_luoshu_safety_module)"
    _lpvm_manifest="$(_luoshu_safety_config)/font-payload-manifest.conf"
    [ -s "$_lpvm_manifest" ] || return 1
    _lpvm_seen=0
    while IFS='|' read -r _lpvm_rel _lpvm_sum _lpvm_size; do
        case "$_lpvm_rel" in */fonts/*|*/etc/*.xml) ;; *) return 1 ;; esac
        _lpvm_file="$_lpvm_module/$_lpvm_rel"
        [ -f "$_lpvm_file" ] || return 1
        _lpvm_now=$(_luoshu_checksum "$_lpvm_file")
        [ "$_lpvm_now" = "$_lpvm_sum|$_lpvm_size" ] || return 1
        _lpvm_seen=$((_lpvm_seen + 1))
    done < "$_lpvm_manifest"
    [ "$_lpvm_seen" -gt 0 ]
}

# Early boot only checks font size metadata and tiny XML checksums. Full file checksums are generated
# during the App-side transaction, never before Zygote.
luoshu_payload_validate_manifest_fast() {
    _lpvf_module="$(_luoshu_safety_module)"
    _lpvf_manifest="$(_luoshu_safety_config)/font-payload-manifest.conf"
    [ -s "$_lpvf_manifest" ] || return 1
    _lpvf_seen=0
    while IFS='|' read -r _lpvf_rel _lpvf_sum _lpvf_size; do
        case "$_lpvf_size" in ''|*[!0-9]*) return 1 ;; esac
        _lpvf_file="$_lpvf_module/$_lpvf_rel"
        [ -f "$_lpvf_file" ] || return 1
        case "$_lpvf_rel" in
            */fonts/*)
                _lpvf_now=$(_luoshu_filesize "$_lpvf_file")
                case "$_lpvf_now" in ''|*[!0-9]*) return 1 ;; esac
                [ "$_lpvf_now" -ge 1024 ] && [ "$_lpvf_now" = "$_lpvf_size" ] || return 1
                ;;
            */etc/*.xml)
                _lpvf_now=$(_luoshu_checksum "$_lpvf_file")
                [ "$_lpvf_now" = "$_lpvf_sum|$_lpvf_size" ] || return 1
                ;;
            *) return 1 ;;
        esac
        _lpvf_seen=$((_lpvf_seen + 1))
    done < "$_lpvf_manifest"
    [ "$_lpvf_seen" -gt 0 ]
}

luoshu_payload_arm() {
    _lpa_active="$1"
    _lpa_config="$(_luoshu_safety_config)"
    mkdir -p "$_lpa_config" 2>/dev/null || return 1
    # ä»»ä½•ä¸€æ¬¡æˆåŠŸçš„å­—ä½“åº”ç”¨éƒ½ä¼šæŒ‰å½“å‰æž¶æž„é‡å»ºè´Ÿè½½ï¼Œå‡çº§é—ç•™çš„"å¾…åŽå°é‡å»º"
    # æ ‡è®°å¿…é¡»éšä¹‹æ¸…é™¤ï¼Œå¦åˆ™ä¸‹æ¬¡å¼€æœºä¼šå¤šé‡å»ºä¸€æ¬¡ï¼Œé‡å»ºå¤±è´¥è¿˜ä¼šè¯¯åˆ è¿™ä»½æ–°è´Ÿè½½ã€‚
    rm -f "$_lpa_config/font-payload-rebuild-pending.conf" "$_lpa_config/font-payload-rebuild-failures" 2>/dev/null || true
    if [ "$_lpa_active" = default ]; then
        rm -f "$_lpa_config/font-payload-boot.conf" "$_lpa_config/font-payload-manifest.conf" 2>/dev/null || trv×Mí¢G§²ÚîÆ­yÕ}É½½Ð¥¸€¡±Õ½Í¡Õ}µ•Ñ…}½¹Ñ•¹Ñ}É½½ÑÌ¤ì‘¼(€€€€€€€€€€€l€µ€ˆ‘}±ÁÅ}É½½Ðˆtñð½¹Ñ¥¹Õ”(€€€€€€€€€€€™½È}±ÁÅ}Á…ÉÐ¥¸€¡}±Õ½Í¡Õ}Á…å±½…‘}Á…ÉÑÌ¤ì‘¼(€€€€€€€€€€€€€€€É´€µÉ˜€ˆ‘}±ÁÅ}É½½Ð¼‘}±ÁÅ}Á…ÉÐ½™½¹ÑÌˆ€Èø½‘•Ø½¹Õ±°ñðÑÉÕ”(€€€€€€€€€€€€€€€}±ÁÅ}•ÑŒôˆ‘}±ÁÅ}É½½Ð¼‘}±ÁÅ}Á…ÉÐ½•ÑŒˆ(€€€€€€€€€€€€€€€l€µ€ˆ‘}±ÁÅ}•ÑŒˆtñð½¹Ñ¥¹Õ”(€€€€€€€€€€€€€€€™½È}±ÁÅ}áµ°¥¸€ˆ‘}±ÁÅ}•ÑŒˆ¼¨¹áµ°ì‘¼(€€€€€€€€€€€€€€€€€€€l€µ˜€ˆ‘}±ÁÅ}áµ°ˆtñð½¹Ñ¥¹Õ”(€€€€€€€€€€€€€€€€€€€É•À€µÄ€1Õ½M¡Ô¡5½¹¼¤ü´œ€ˆ‘}±ÁÅ}áµ°ˆ€Èø½‘•Ø½¹Õ±°€˜˜É´€µ˜€ˆ‘}±ÁÅ}áµ°ˆ€Èø½‘•Ø½¹Õ±°ñðÑÉÕ”(€€€€€€€€€€€€€€€‘½¹”(€€€€€€€€€€€‘½¹”(€€€€€€€‘½¹”(€€€™¤(€€€ÁÉ¥¹Ñ˜€‘•™…Õ±Ñq¸œ€ø€ˆ‘}±ÁÅ}½¹™¥œ½…Ñ¥Ù•}™½¹Ð¹½¹˜ˆ€Èø½‘•Ø½¹Õ±°ñðÑÉÕ”(€€€É´€µ˜€ˆ‘}±ÁÅ}½¹™¥œ½™½¹ÐµÁ…å±½…µ‰½½Ð¹½¹˜ˆ€ˆ‘}±ÁÅ}½¹™¥œ½™½¹ÐµÁ…å±½…µµ…¹¥™•ÍÐ¹½¹˜ˆp(€€€€€€€€€€ˆ‘}±ÁÅ}½¹™¥œ½™½¹ÐµÁ…å±½…µÍ¡•µ„¹½¹˜ˆ€ˆ‘}±ÁÅ}½¹™¥œ½™½¹ÐµÁ…å±½…µÉ•‰Õ¥±µÁ•¹‘¥¹œ¹½¹˜ˆp(€€€€€€€€€€ˆ‘}±ÁÅ}½¹™¥œ½™½¹ÐµÑ…É•Ðµ…±¥…Í•Ì¹½¹˜ˆ€ˆ‘}±ÁÅ}½¹™¥œ½™½¹ÐµÑ…É•Ðµ½Ù•É…”¹½¹˜ˆp(€€€€€€€€€€ˆ‘}±ÁÅ}½¹™¥œ½™½¹Ðµ½¹™¥œµ½Ù•É±…ä¹½¹˜ˆ€Èø½‘•Ø½¹Õ±°ñðÑÉÕ”(€€€€ŒEÕ…É…¹Ñ¥¹”½¹±äÑ¡”•¹•É…Ñ•™½¹ÐÁ…å±½…¸¥Í…‰±¥¹œÑ¡”Ý¡½±”µ½‘Õ±”µ…­•Ì‰½Ñ (€€€€Œ€‰É•ÍÑ½É”‘•™…Õ±Ðˆ…¹Ñ¡”¹•áÐ•áÁ±¥¥Ð™½¹ÐÉ•ÑÉä¥µÁ½ÍÍ¥‰±”°Í¼„É•½Ù•É…‰±”™½¹Ð(€€€€ŒÙ…±¥‘…Ñ¥½¸™…¥±ÕÉ”µÕÍÐ¹•Ù•ÈÉ•…Ñ”Ñ¡”É½½Ðµ…¹…•ÈÌ‘¥Í…‰±”µ…É­•È¸(€€€ì(€€€€€€€ÁÉ¥¹Ñ˜€ÍÑ…Ñ”õÅÕ…É…¹Ñ¥¹•‘q¸œ(€€€€€€€ÁÉ¥¹Ñ˜€™…¥±ÕÉ•Ìô•Íq¸œ€ˆ‘}±ÁÅ}™…¥°ˆ(€€€€€€€ÁÉ¥¹Ñ˜€Ñ¥µ”ô•Íq¸œ€ˆ¡‘…Ñ”€¬•Ì€Èø½‘•Ø½¹Õ±°ñð•¡¼€À¤ˆ(€€€ô€ø€ˆ‘}±ÁÅ}½¹™¥œ½™½¹ÐµÁ…å±½…µÅÕ…É…¹Ñ¥¹”¹½¹˜ˆ€Èø½‘•Ø½¹Õ±°ñðÑÉÕ”(€€€}±Õ½Í¡Õ}Í…™•Ñå}±½œII=H€‹šŽšÖ/–"Ã’â+š²‡–¶_’öO¢Ò¢ö÷šr«–º3š"C–òšrë¾ò3–ÞËšJ“¦R–£¦£–¶_’öO¢šžn[¾ò!™…¥±ÕÉ”ô‘}±ÁÅ}™…¥³¾ò$ˆ)ô()™½¹Ñ}½¹™¥}‰½½Ñ}Õ…É ¤ì(€€€}±‰}…Ñ¥Ù”ôˆ‘ìÄèµ‘•™…Õ±Ñôˆ(€€€}±‰}½¹™¥œôˆ¡}±Õ½Í¡Õ}Í…™•Ñå}½¹™¥œ¤ˆ(€€€}±‰}ÍÑ…Ñ”ô¡Í•€µ¸€Ì½yÍÑ…Ñ”ô¼½Àœ€ˆ‘}±‰}½¹™¥œ½™½¹ÐµÁ…å±½…µ‰½½Ð¹½¹˜ˆ€Èø½‘•Ø½¹Õ±°ð¡•…€µ¸Ä¤(€€€¥˜l€ˆ‘}±‰}…Ñ¥Ù”ˆ€ô‘•™…Õ±ÐtìÑ¡•¸(€€€€€€€É´€µ˜€ˆ‘}±‰}½¹™¥œ½™½¹ÐµÁ…å±½…µ‰½½Ð¹½¹˜ˆ€ˆ‘}±‰}½¹™¥œ½™½¹ÐµÁ…å±½…µµ…¹¥™•ÍÐ¹½¹˜ˆ€Èø½‘•Ø½¹Õ±°ñðÑÉÕ”(€€€€€€€É•ÑÕÉ¸€À(€€€™¤(€€€}±‰}Í¡•µ„ô¡±Õ½Í¡Õ}Á…å±½…‘}Í¡•µ…}É•…¤(€€€¥˜l€ˆ‘}±‰}Í¡•µ„ˆ€„ô€ˆ‘1U=M!U}Ae1=}M!5}UII9PˆtìÑ¡•¸(€€€€€€€}±Õ½Í¡Õ}Í…™•Ñå}±½œII=H€‹–¶_’öO¢Ò¢ö÷šzÛšz¢þšr¾òh‘í}±‰}Í¡•µ„èµµ¥ÍÍ¥¹ô€„ô€‘1U=M!U}Ae1=}M!5}UII9Pˆ(€€€€€€€±Õ½Í¡Õ}Á…å±½…‘}ÅÕ…É…¹Ñ¥¹”(€€€€€€€É•ÑÕÉ¸€Ä(€€€™¤(€€€…Í”€ˆ‘}±‰}ÍÑ…Ñ”ˆ¥¸(€€€€€€€‰½½Ñ¥¹œ¤(€€€€€€€€€€€±Õ½Í¡Õ}Á…å±½…‘}ÅÕ…É…¹Ñ¥¹”(€€€€€€€€€€€É•ÑÕÉ¸€Ä(€€€€€€€€€€€€ìì(€€€€€€€ÁÉ•Á…É•¤(€€€€€€€€€€€±Õ½Í¡Õ}Á…å±½…‘}Ù…±¥‘…Ñ•}µ…¹¥™•ÍÑ}™…ÍÐñðì±Õ½Í¡Õ}Á…å±½…‘}ÅÕ…É…¹Ñ¥¹”ìÉ•ÑÕÉ¸€Äìô(€€€€€€€€€€€ì(€€€€€€€€€€€€€€€ÁÉ¥¹Ñ˜€ÍÑ…Ñ”õ‰½½Ñ¥¹œ(œ(€€€€€€€€€€€€€€€ÁÉ¥¹Ñ˜€™½¹Ðô•Ì(œ€ˆ‘}±‰}…Ñ¥Ù”ˆ(€€€€€€€€€€€€€€€ÁÉ¥¹Ñ˜€Ñ¥µ”ô•Ì(œ€ˆ¡‘…Ñ”€¬•Ì¤ˆ(€€€€€€€€€€€ô€ø€ˆ‘}±‰}½¹™¥œ½™½¹ÐµÁ…å±½…µ‰½½Ð¹½¹˜¹ÑµÀ¸ˆ€Èø½‘•Ø½¹Õ±°ñðì±Õ½Í¡Õ}Á…å±½…‘}ÅÕ…É…¹Ñ¥¹”ìÉ•ÑÕÉ¸€Äìô(€€€€€€€€€€€µØ€µ˜€ˆ‘}±‰}½¹™¥œ½™½¹ÐµÁ…å±½…µ‰½½Ð¹½¹˜¹ÑµÀ¸ˆ€ˆ‘}±‰}½¹™¥œ½™½¹ÐµÁ…å±½…µ‰½½Ð¹½¹˜ˆ€Èø½‘•Ø½¹Õ±°ñðì±Õ½Í¡Õ}Á…å±½…‘}ÅÕ…É…¹Ñ¥¹”ìÉ•ÑÕÉ¸€Äìô(€€€€€€€€€€€}±Õ½Í¡Õ}Í…™•Ñå}±½œ%9<€ŸšZÃ–¶_’öO¢Ò¢ö÷¢öï¦?š‚‡¦ª3¦k¢þ¾ò3ž¶'–ú¹‘É½¥ƒ–º3š"C–òšrëž†»¢ºœ(€€€€€€€€€€€€ìì(€€€€€€€½¹™¥Éµ•¤(€€€€€€€€€€€±Õ½Í¡Õ}Á…å±½…‘}Ù…±¥‘…Ñ•}µ…¹¥™•ÍÑ}™…ÍÐñðì±Õ½Í¡Õ}Á…å±½…‘}ÅÕ…É…¹Ñ¥¹”ìÉ•ÑÕÉ¸€Äìô(€€€€€€€€€€€€ìì(€€€€€€€€¨¤(€€€€€€€€€€€€Œ¸½±‘•È•¹¥¹”¡…Ì¹¼ÑÉÕÍÑ•ÑÉ…¹Í…Ñ¥½¸µ…¹¥™•ÍÐ¸I•ÍÑ½É”Ñ¡”I=4™½¹Ð½¹”¥¹ÍÑ•…(€€€€€€€€€€€€Œ½˜Á…ÉÍ¥¹œ½È¡…Í¡¥¹œ±…É”Á…å±½…‘Ì‰•™½É”iå½Ñ”¸(€€€€€€€€€€€±Õ½Í¡Õ}Á…å±½…‘}ÅÕ…É…¹Ñ¥¹”(€€€€€€€€€€€É•ÑÕÉ¸€Ä(€€€€€€€€€€€€ìì(€€€•Í…Œ(€€€É•ÑÕÉ¸€À)ô()™½¹Ñ}½¹™¥}µ…É­}‰½½Ñ}ÍÕ•ÍÌ ¤ì(€€€}±µ‰Í}½¹™¥œôˆ¡}±Õ½Í¡Õ}Í…™•Ñå}½¹™¥œ¤ˆ(€€€}±µ‰Í}ÍÑ…Ñ”ô¡Í•€µ¸€Ì½yÍÑ…Ñ”ô¼½Àœ€ˆ‘}±µ‰Í}½¹™¥œ½™½¹ÐµÁ…å±½…µ‰½½Ð¹½¹˜ˆ€Èø½‘•Ø½¹Õ±°ð¡•…€µ¸Ä¤(€€€l€ˆ‘}±µ‰Í}ÍÑ…Ñ”ˆ€ô‰½½Ñ¥¹œtñðÉ•ÑÕÉ¸€À(€€€}±µ‰Í}™½¹Ðô¡Í•€µ¸€Ì½y™½¹Ðô¼½Àœ€ˆ‘}±µ‰Í}½¹™¥œ½™½¹ÐµÁ…å±½…µ‰½½Ð¹½¹˜ˆ€Èø½‘•Ø½¹Õ±°ð¡•…€µ¸Ä¤(€€€ì(€€€€€€€ÁÉ¥¹Ñ˜€ÍÑ…Ñ”õ½¹™¥Éµ•(œ(€€€€€€€ÁÉ¥¹Ñ˜€™½¹Ðô•Ì(œ€ˆ‘í}±µ‰Í}™½¹ÐèµÕ¹­¹½Ý¹ôˆ(€€€€€€€ÁÉ¥¹Ñ˜€Ñ¥µ”ô•Ì(œ€ˆ¡‘…Ñ”€¬•Ì¤ˆ(€€€ô€ø€ˆ‘}±µ‰Í}½¹™¥œ½™½¹ÐµÁ…å±½…µ‰½½Ð¹½¹˜¹ÑµÀ¸ˆ€Èø½‘•Ø½¹Õ±°ñðÉ•ÑÕÉ¸€Ä(€€€µØ€µ˜€ˆ‘}±µ‰Í}½¹™¥œ½™½¹ÐµÁ…å±½…µ‰½½Ð¹½¹˜¹ÑµÀ¸ˆ€ˆ‘}±µ‰Í}½¹™¥œ½™½¹ÐµÁ…å±½…µ‰½½Ð¹½¹˜ˆ€Èø½‘•Ø½¹Õ±°ñðÉ•ÑÕÉ¸€Ä(€€€É´€µ˜€ˆ‘}±µ‰Í}½¹™¥œ½™½¹Ðµ‰½½Ðµ™…¥±ÕÉ•Ìˆ€ˆ‘}±µ‰Í}½¹™¥œ½™½¹ÐµÁ…å±½…µÅÕ…É…¹Ñ¥¹”¹½¹˜ˆ€Èø½‘•Ø½¹Õ±°ñðÑÉÕ”(€€€ÁÉ¥¹Ñ˜€Ñ¥µ”ô•Ì(œ€ˆ¡‘…Ñ”€¬•Ì¤ˆ€ø€ˆ‘}±µ‰Í}½¹™¥œ½™½¹Ðµ±…ÍÐµ‰½½ÐµÍÕ•ÍÌ¹½¹˜ˆ€Èø½‘•Ø½¹Õ±°ñðÑÉÕ”(€€€¡µ½€ÀØÐÐ€ˆ‘}±µ‰Í}½¹™¥œ½™½¹ÐµÁ…å±½…µ‰½½Ð¹½¹˜ˆ€ˆ‘}±µ‰Í}½¹™¥œ½™½¹Ðµ±…ÍÐµ‰½½ÐµÍÕ•ÍÌ¹½¹˜ˆ€Èø½‘•Ø½¹Õ±°ñðÑÉÕ”(€€€}±Õ½Í¡Õ}Í…™•Ñå}±½œ%9<€¹‘É½¥ƒ–ÞË–º3š"C–òšrë¾ò3–¶_’öO¢Ò¢ö÷’ê/–*‡ž†»¢º“š"C–*|œ)ô