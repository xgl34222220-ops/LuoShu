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

LUOSHU_PAYLOAD_SCHEMA_CURRENT="${LUOSHU_PAYLOAD_SCHEMA_CURRENT:-baseline-v7-mono-v6}"

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

    while IFS='|' read -r _ldt_key _ldt_real _ldt_overlay _ldt_font_dir; do
        _ldt_input="$_ldt_backup/$_ldt_key"
        [ -s "$_ldt_input" ] || continue
        _ldt_out="$_ldt_config/.font-targets.$$.txt"
        rm -f "$_ldt_out" 2>/dev/null || true
        if ! _luoshu_font_config_exec "$_ldt_tool" --input "$_ldt_input" > "$_ldt_out" 2>/dev/null; then
            _ldt_scan_failed=$((_ldt_scan_failed + 1))
            rm -f "$_ldt_out" 2>/dev/null || true
            continue
        fi
        _ldt_configs=$((_ldt_configs + 1))
        while IFS='|' read -r _ldt_file _ldt_weight _ldt_family; do
            [ -n "$_ldt_file" ] || continue
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
                _ldt_size=$(wc -c < "$_ldt_dest" 2>/dev/null | tr -d '[:space:]')
                case "$_ldt_size" in ''|*[!0-9]*) _ldt_size=0 ;; esac
                if [ "$_ldt_size" -ge 1024 ]; then
                    printf '%s|%s|%s|%s\n' "$_ldt_rel" "$_ldt_key" "$_ldt_weight" "$_ldt_family" >> "$_ldt_manifest_tmp"
                    _ldt_mapped=$((_ldt_mapped + 1))
                else
                    rm -f "$_ldt_dest" 2>/dev/null || true
                fi
            fi
        done < "$_ldt_out"
        rm -f "$_ldt_out" 2>/dev/null || true
    done <<EOF_LUOSHU_DYNAMIC_TARGETS
$(_luoshu_font_config_specs)
EOF_LUOSHU_DYNAMIC_TARGETS

    if [ "$_ldt_scan_failed" -gt 0 ] || [ "$_ldt_mapped" -ne "$_ldt_targets" ]; then
        while IFS='|' read -r _ldt_rel _ldt_rest; do rm -f "$_ldt_module/$_ldt_rel" 2>/dev/null || true; done < "$_ldt_manifest_tmp"
        rm -f "$_ldt_manifest_tmp" "$_ldt_coverage_tmp" 2>/dev/null || true
        _luoshu_safety_log ERROR "动态字体目标映射失败：targets=$_ldt_targets mapped=$_ldt_mapped scanFailed=$_ldt_scan_failed"
        return 1
    fi

    {
        printf 'configs=%s\n' "$_ldt_configs"
        printf 'targets=%s\n' "$_ldt_targets"
        printf 'mapped=%s\n' "$_ldt_mapped"
        printf 'time=%s\n' "$(date +%s)"
    } > "$_ldt_coverage_tmp" 2>/dev/null || return 1
    mv -f "$_ldt_manifest_tmp" "$_ldt_config/font-target-aliases.conf" 2>/dev/null || return 1
    mv -f "$_ldt_coverage_tmp" "$_ldt_config/font-target-coverage.conf" 2>/dev/null || return 1
    chmod 0644 "$_ldt_config/font-target-aliases.conf" "$_ldt_config/font-target-coverage.conf" 2>/dev/null || true
    [ "$_ldt_targets" -gt 0 ] || return 2
    _luoshu_safety_log INFO "已按设备真实 XML 完整映射 $_ldt_mapped 个 UI 字体目标"
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
    # A ROM may expose UI file slots without a safely rewritable named family. Keep only a complete
    # dynamic mapping; partial mappings are rejected above.
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
            _lpv_size=$(wc -c < "$_lpv_file" 2>/dev/null | tr -d '[:space:]')
            case "$_lpv_size" in ''|*[!0-9]*) _lpv_size=0 ;; esac
            [ "$_lpv_size" -ge 1024 ] || return 1
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
    # 任何一次成功的字体应用都会按当前架构重建负载，升级遗留的"待后台重建"
    # 标记必须随之清除，否则下次开机会多重建一次，重建失败还会误删这份新负载。
    rm -f "$_lpa_config/font-payload-rebuild-pending.conf" "$_lpa_config/font-payload-rebuild-failures" 2>/dev/null || true
    if [ "$_lpa_active" = default ]; then
        rm -f "$_lpa_config/font-payload-boot.conf" "$_lpa_config/font-payload-manifest.conf" 2>/dev/null || true
        luoshu_payload_schema_write default
        return $?
    fi
    luoshu_payload_build_manifest || return 1
    {
        printf 'state=prepared\n'
        printf 'font=%s\n' "$_lpa_active"
        printf 'time=%s\n' "$(date +%s)"
    } > "$_lpa_config/font-payload-boot.conf.tmp.$$" 2>/dev/null || return 1
    mv -f "$_lpa_config/font-payload-boot.conf.tmp.$$" "$_lpa_config/font-payload-boot.conf" 2>/dev/null || return 1
    chmod 0644 "$_lpa_config/font-payload-boot.conf" 2>/dev/null || true
    luoshu_payload_schema_write "$_lpa_active"
}

LUOSHU_PAYLOAD_TXN=''
LUOSHU_PAYLOAD_VALIDATED_ACTIVE=''
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
    for _lpt_name in active_font.conf font_mix.conf font-config-overlay.conf font-target-aliases.conf font-target-coverage.conf font-payload-manifest.conf font-payload-boot.conf font-payload-schema.conf text_reboot_required.conf; do
        if [ -f "$_lpt_config/$_lpt_name" ]; then
            cp -fp "$_lpt_config/$_lpt_name" "$LUOSHU_PAYLOAD_TXN/config/$_lpt_name" 2>/dev/null || return 1
            printf 'present|config/%s\n' "$_lpt_name" >> "$LUOSHU_PAYLOAD_TXN/paths"
        else
            printf 'absent|config/%s\n' "$_lpt_name" >> "$LUOSHU_PAYLOAD_TXN/paths"
        fi
    done
    return 0
}

luoshu_payload_transaction_rollback() {
    [ -n "$LUOSHU_PAYLOAD_TXN" ] && [ -d "$LUOSHU_PAYLOAD_TXN" ] || { LUOSHU_PAYLOAD_TXN=''; return 0; }
    _lptr_module="$(_luoshu_safety_module)"
    while IFS='|' read -r _lptr_state _lptr_rel; do
        rm -rf "$_lptr_module/$_lptr_rel" 2>/dev/null || true
        if [ "$_lptr_state" = present ]; then
            mkdir -p "${_lptr_module}/${_lptr_rel%/*}" 2>/dev/null || true
            if [ -d "$LUOSHU_PAYLOAD_TXN/tree/$_lptr_rel" ]; then
                cp -af "$LUOSHU_PAYLOAD_TXN/tree/$_lptr_rel" "$_lptr_module/$_lptr_rel" 2>/dev/null || {
                    mkdir -p "$_lptr_module/$_lptr_rel" 2>/dev/null || true
                    cp -rfp "$LUOSHU_PAYLOAD_TXN/tree/$_lptr_rel/." "$_lptr_module/$_lptr_rel/" 2>/dev/null || true
                }
            elif [ -f "$LUOSHU_PAYLOAD_TXN/$_lptr_rel" ]; then
                cp -fp "$LUOSHU_PAYLOAD_TXN/$_lptr_rel" "$_lptr_module/$_lptr_rel" 2>/dev/null || true
            fi
        fi
    done < "$LUOSHU_PAYLOAD_TXN/paths"
    rm -rf "$LUOSHU_PAYLOAD_TXN" 2>/dev/null || true
    LUOSHU_PAYLOAD_TXN=''
}

luoshu_payload_transaction_abort() {
    _lpta_had=0
    if [ -n "$LUOSHU_PAYLOAD_TXN" ]; then
        _lpta_had=1
        luoshu_payload_transaction_rollback
    fi
    if [ "$_lpta_had" -eq 1 ] && type luoshu_sync_mount_payload >/dev/null 2>&1; then
        luoshu_sync_mount_payload >/dev/null 2>&1 ||
            _luoshu_safety_log ERROR '本地旧字体已恢复，但元模块旧负载回写失败；开机守卫将撤销覆盖'
    fi
}

luoshu_payload_transaction_commit() {
    _lptc_active="$1"
    [ -n "$LUOSHU_PAYLOAD_TXN" ] && [ -d "$LUOSHU_PAYLOAD_TXN" ] || return 1
    if [ "$_lptc_active" != default ] && [ "${LUOSHU_PAYLOAD_VALIDATED_ACTIVE:-}" != "$_lptc_active" ]; then
        luoshu_payload_validate_current "$_lptc_active" || return 1
    fi
    luoshu_payload_arm "$_lptc_active" || return 1
    rm -rf "$LUOSHU_PAYLOAD_TXN" 2>/dev/null || true
    LUOSHU_PAYLOAD_TXN=''
    return 0
}

luoshu_payload_quarantine() {
    _lpq_module="$(_luoshu_safety_module)"
    _lpq_config="$(_luoshu_safety_config)"
    _lpq_fail=$(cat "$_lpq_config/font-boot-failures" 2>/dev/null)
    case "$_lpq_fail" in ''|*[!0-9]*) _lpq_fail=0 ;; esac
    _lpq_fail=$((_lpq_fail + 1))
    printf '%s\n' "$_lpq_fail" > "$_lpq_config/font-boot-failures" 2>/dev/null || true

    for _lpq_part in $(_luoshu_payload_parts); do
        rm -rf "$_lpq_module/$_lpq_part/fonts" 2>/dev/null || true
        _lpq_etc="$_lpq_module/$_lpq_part/etc"
        [ -d "$_lpq_etc" ] || continue
        for _lpq_xml in "$_lpq_etc"/*.xml; do
            [ -f "$_lpq_xml" ] || continue
            grep -Eq 'LuoShu(Mono)?-' "$_lpq_xml" 2>/dev/null && rm -f "$_lpq_xml" 2>/dev/null || true
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
                    grep -Eq 'LuoShu(Mono)?-' "$_lpq_xml" 2>/dev/null && rm -f "$_lpq_xml" 2>/dev/null || true
                done
            done
        done
    fi
    printf 'default\n' > "$_lpq_config/active_font.conf" 2>/dev/null || true
    rm -f "$_lpq_config/font-payload-boot.conf" "$_lpq_config/font-payload-manifest.conf" \
          "$_lpq_config/font-payload-schema.conf" "$_lpq_config/font-payload-rebuild-pending.conf" \
          "$_lpq_config/font-target-aliases.conf" "$_lpq_config/font-target-coverage.conf" \
          "$_lpq_config/font-config-overlay.conf" 2>/dev/null || true
    # Quarantine only the generated font payload. Disabling the whole module makes both
    # "restore default" and the next explicit font retry impossible, so a recoverable font
    # validation failure must never create the root manager's disable marker.
    {
        printf 'state=quarantined\n'
        printf 'failures=%s\n' "$_lpq_fail"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_lpq_config/font-payload-quarantine.conf" 2>/dev/null || true
    _luoshu_safety_log ERROR "检测到上次字体负载未完成开机，已撤销全部字体覆盖（failure=$_lpq_fail）"
}

font_config_boot_guard() {
    _lbg_active="${1:-default}"
    _lbg_config="$(_luoshu_safety_config)"
    _lbg_state=$(sed -n 's/^state=//p' "$_lbg_config/font-payload-boot.conf" 2>/dev/null | head -n1)
    if [ "$_lbg_active" = default ]; then
        rm -f "$_lbg_config/font-payload-boot.conf" "$_lbg_config/font-payload-manifest.conf" 2>/dev/null || true
        return 0
    fi
    _lbg_schema=$(luoshu_payload_schema_read)
    if [ "$_lbg_schema" != "$LUOSHU_PAYLOAD_SCHEMA_CURRENT" ]; then
        _luoshu_safety_log ERROR "字体负载架构过期：${_lbg_schema:-missing} != $LUOSHU_PAYLOAD_SCHEMA_CURRENT"
        luoshu_payload_quarantine
        return 1
    fi
    case "$_lbg_state" in
        booting)
            luoshu_payload_quarantine
            return 1
            ;;
        prepared)
            luoshu_payload_validate_manifest_fast || { luoshu_payload_quarantine; return 1; }
            {
                printf 'state=booting
'
                printf 'font=%s
' "$_lbg_active"
                printf 'time=%s
' "$(date +%s)"
            } > "$_lbg_config/font-payload-boot.conf.tmp.$$" 2>/dev/null || { luoshu_payload_quarantine; return 1; }
            mv -f "$_lbg_config/font-payload-boot.conf.tmp.$$" "$_lbg_config/font-payload-boot.conf" 2>/dev/null || { luoshu_payload_quarantine; return 1; }
            _luoshu_safety_log INFO '新字体负载轻量校验通过，等待 Android 完成开机确认'
            ;;
        confirmed)
            luoshu_payload_validate_manifest_fast || { luoshu_payload_quarantine; return 1; }
            ;;
        *)
            # An older engine has no trusted transaction manifest. Restore the ROM font once instead
            # of parsing or hashing large payloads before Zygote.
            luoshu_payload_quarantine
            return 1
            ;;
    esac
    return 0
}

font_config_mark_boot_success() {
    _lmbs_config="$(_luoshu_safety_config)"
    _lmbs_state=$(sed -n 's/^state=//p' "$_lmbs_config/font-payload-boot.conf" 2>/dev/null | head -n1)
    [ "$_lmbs_state" = booting ] || return 0
    _lmbs_font=$(sed -n 's/^font=//p' "$_lmbs_config/font-payload-boot.conf" 2>/dev/null | head -n1)
    {
        printf 'state=confirmed
'
        printf 'font=%s
' "${_lmbs_font:-unknown}"
        printf 'time=%s
' "$(date +%s)"
    } > "$_lmbs_config/font-payload-boot.conf.tmp.$$" 2>/dev/null || return 1
    mv -f "$_lmbs_config/font-payload-boot.conf.tmp.$$" "$_lmbs_config/font-payload-boot.conf" 2>/dev/null || return 1
    rm -f "$_lmbs_config/font-boot-failures" "$_lmbs_config/font-payload-quarantine.conf" 2>/dev/null || true
    printf 'time=%s
' "$(date +%s)" > "$_lmbs_config/font-last-boot-success.conf" 2>/dev/null || true
    chmod 0644 "$_lmbs_config/font-payload-boot.conf" "$_lmbs_config/font-last-boot-success.conf" 2>/dev/null || true
    _luoshu_safety_log INFO 'Android 已完成开机，字体负载事务确认成功'
}
