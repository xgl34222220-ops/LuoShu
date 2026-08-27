#!/system/bin/sh
# v4.0.0 foreground validation hotfix.
# Keep the transactional/boot manifest safety contract, but do not re-run
# embedded-Python validation for every XML and every hard-linked alias at 94%.
set +e

_luoshu_v4_font_ok() {
    _lvf_file="$1"
    if type _luoshu_fast_font_ok >/dev/null 2>&1; then
        _luoshu_fast_font_ok "$_lvf_file"
        return $?
    fi
    [ -f "$_lvf_file" ] || return 1
    if command -v stat >/dev/null 2>&1; then
        _lvf_size=$(stat -c '%s' "$_lvf_file" 2>/dev/null)
    elif command -v toybox >/dev/null 2>&1; then
        _lvf_size=$(toybox stat -c '%s' "$_lvf_file" 2>/dev/null)
    else
        _lvf_size=$(wc -c < "$_lvf_file" 2>/dev/null | tr -d '[:space:]')
    fi
    case "$_lvf_size" in ''|*[!0-9]*) return 1 ;; esac
    [ "$_lvf_size" -ge 1024 ]
}

_luoshu_v4_validate_xml_refs() {
    _lvx_xml="$1"
    _lvx_font_dir="$2"
    [ -s "$_lvx_xml" ] || return 1
    _lvx_refs=$(grep -oE 'LuoShu(Mono)?-[1-9][0-9][0-9]\.ttf' "$_lvx_xml" 2>/dev/null | sort -u)
    [ -n "$_lvx_refs" ] || return 0
    for _lvx_ref in $_lvx_refs; do
        _luoshu_v4_font_ok "$_lvx_font_dir/$_lvx_ref" || return 1
    done
    return 0
}

luoshu_payload_validate_current() {
    _lpv_active="${1:-unknown}"
    _lpv_module="$(_luoshu_safety_module)"
    _lpv_config="$(_luoshu_safety_config)"
    [ "$_lpv_active" != default ] || return 0

    # One verified anchor is enough to prove that the generated text payload exists.
    # The dynamic target manifest below verifies every mapped alias without reading
    # the same multi-megabyte inode repeatedly.
    _lpv_anchor=''
    for _lpv_candidate in \
        "$_lpv_module/system/fonts/.luoshu-font-store/mix-composite.font" \
        "$_lpv_module/system/fonts/LuoShu-400.ttf" \
        "$_lpv_module/system/fonts/Roboto-Regular.ttf" \
        "$_lpv_module/system/fonts/MiSansVF.ttf" \
        "$_lpv_module/system/fonts/SysSans-Hans-Regular.ttf" \
        "$_lpv_module/system/fonts/NotoSans-Regular.ttf"; do
        if _luoshu_v4_font_ok "$_lpv_candidate"; then
            _lpv_anchor="$_lpv_candidate"
            break
        fi
    done
    [ -n "$_lpv_anchor" ] || return 1

    _lpv_coverage="$_lpv_config/font-target-coverage.conf"
    _lpv_manifest="$_lpv_config/font-target-aliases.conf"
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
            [ -s "$_lpv_manifest" ] || return 1
            _lpv_count=$(awk 'NF { n++ } END { print n+0 }' "$_lpv_manifest" 2>/dev/null)
            case "$_lpv_count" in ''|*[!0-9]*) return 1 ;; esac
            [ "$_lpv_count" -eq "$_lpv_mapped" ] || return 1
            while IFS='|' read -r _lpv_rel _lpv_key _lpv_weight _lpv_family; do
                [ -n "$_lpv_rel" ] || continue
                case "$_lpv_rel" in */fonts/*.ttf|*/fonts/*.otf|*/fonts/*.ttc) ;; *) return 1 ;; esac
                _luoshu_v4_font_ok "$_lpv_module/$_lpv_rel" || return 1
            done < "$_lpv_manifest"
        fi
    fi

    # Stage 91 already generated and validated these XML files. At 94% only
    # verify that each generated document still exists and every LuoShu font
    # reference resolves to a real payload file. This is shell-only and bounded.
    while IFS='|' read -r _lpv_key _lpv_real _lpv_overlay _lpv_font_dir; do
        [ -f "$_lpv_overlay" ] || continue
        grep -Eq 'LuoShu(Mono)?-[1-9][0-9][0-9]\.ttf' "$_lpv_overlay" 2>/dev/null || continue
        _luoshu_v4_validate_xml_refs "$_lpv_overlay" "$_lpv_font_dir" || return 1
    done <<EOF_LUOSHU_V4_VALIDATE
$(_luoshu_font_config_specs)
EOF_LUOSHU_V4_VALIDATE

    LUOSHU_PAYLOAD_VALIDATED_ACTIVE="$_lpv_active"
    return 0
}

# A boot quarantine must remove the unsafe generated payload, but it must not
# destroy the user's selected font. Selection and effective boot state are
# separate concepts; the App can keep showing what the user selected.
luoshu_payload_quarantine() {
    _lpq_module="$(_luoshu_safety_module)"
    _lpq_config="$(_luoshu_safety_config)"
    _lpq_selected=$(head -n1 "$_lpq_config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_lpq_selected" ] || _lpq_selected=default
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

    # Preserve active_font.conf; only clear generated/effective payload state.
    rm -f "$_lpq_config/font-payload-boot.conf" "$_lpq_config/font-payload-manifest.conf" \
          "$_lpq_config/font-payload-schema.conf" "$_lpq_config/font-payload-rebuild-pending.conf" \
          "$_lpq_config/font-payload-reapply-notified.conf" \
          "$_lpq_config/font-target-aliases.conf" "$_lpq_config/font-target-coverage.conf" \
          "$_lpq_config/font-config-overlay.conf" "$_lpq_config/text_reboot_required.conf" \
          "$_lpq_config/font-boot-inconclusive.conf" "$_lpq_config/font-mount-verify-failures" 2>/dev/null || true
    {
        printf 'state=quarantined\n'
        printf 'selectedFont=%s\n' "$_lpq_selected"
        printf 'effectiveFont=stock\n'
        printf 'failures=%s\n' "$_lpq_fail"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_lpq_config/font-payload-quarantine.conf" 2>/dev/null || true
    _luoshu_safety_log ERROR "检测到字体负载启动校验失败，已撤销生成负载但保留用户字体选择（failure=$_lpq_fail）"
}
