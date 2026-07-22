#!/system/bin/sh
# 洛书 v2.0.0：字体负载安全事务与启动隔离。供 post-fs-data.sh / service.sh 使用。
LUOSHU_PAYLOAD_SCHEMA_CURRENT="${LUOSHU_PAYLOAD_SCHEMA_CURRENT:-baseline-v7-mono-v3}"

_luoshu_safety_module() {
    printf '%s\n' "${MODDIR:-/data/adb/modules/LuoShu}"
}

_luoshu_safety_config() {
    printf '%s/config\n' "$(_luoshu_safety_module)"
}

_luoshu_safety_log() {
    _lsl_module="$(_luoshu_safety_module)"
    mkdir -p "$_lsl_module/logs" 2>/dev/null || return 0
    printf '[%s] [%s] %s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$1" "$2" >> "$_lsl_module/logs/fontswitch.log" 2>/dev/null || true
}

_luoshu_payload_parts() {
    printf '%s\n' system system_ext product vendor odm oem my_product
}

luoshu_payload_part_for_path() {
    case "$1" in
        system|system_ext|product|vendor|odm|oem|my_product) return 0 ;;
    esac
    return 1
}

luoshu_payload_transaction_begin() {
    _lpt_module="$(_luoshu_safety_module)"
    _lpt_config="$(_luoshu_safety_config)"
    mkdir -p "$_lpt_config" "$_lpt_module/logs" 2>/dev/null || return 1
    rm -rf "$_lpt_module/.font-payload-txn" 2>/dev/null || true
    mkdir -p "$_lpt_module/.font-payload-txn" 2>/dev/null || return 1
    for _lpt_part in $(_luoshu_payload_parts); do
        [ -d "$_lpt_module/$_lpt_part" ] || continue
        mkdir -p "$_lpt_module/.font-payload-txn/$_lpt_part" 2>/dev/null || return 1
        cp -al "$_lpt_module/$_lpt_part/." "$_lpt_module/.font-payload-txn/$_lpt_part/" 2>/dev/null || \
            cp -a "$_lpt_module/$_lpt_part/." "$_lpt_module/.font-payload-txn/$_lpt_part/" 2>/dev/null || \
            cp -rfp "$_lpt_module/$_lpt_part/." "$_lpt_module/.font-payload-txn/$_lpt_part/" 2>/dev/null || return 1
    done
    printf 'state=active\ntime=%s\n' "$(date +%s)" > "$_lpt_module/.font-payload-txn/state" 2>/dev/null || return 1
    _luoshu_safety_log INFO '字体负载事务快照已创建'
    return 0
}

luoshu_payload_transaction_abort() {
    _lpt_module="$(_luoshu_safety_module)"
    [ -d "$_lpt_module/.font-payload-txn" ] || return 0
    for _lpt_part in $(_luoshu_payload_parts); do
        [ -d "$_lpt_module/.font-payload-txn/$_lpt_part" ] || continue
        rm -rf "$_lpt_module/$_lpt_part" 2>/dev/null || true
        mv "$_lpt_module/.font-payload-txn/$_lpt_part" "$_lpt_module/$_lpt_part" 2>/dev/null || \
            cp -a "$_lpt_module/.font-payload-txn/$_lpt_part" "$_lpt_module/$_lpt_part" 2>/dev/null || true
    done
    rm -rf "$_lpt_module/.font-payload-txn" 2>/dev/null || true
    _luoshu_safety_log WARN '字体负载事务已回滚'
    return 0
}

luoshu_payload_write_manifest() {
    _lpw_module="$(_luoshu_safety_module)"
    _lpw_config="$(_luoshu_safety_config)"
    _lpw_manifest="$_lpw_config/font-payload-manifest.conf"
    _lpw_tmp="$_lpw_manifest.tmp.$$"
    : > "$_lpw_tmp" 2>/dev/null || return 1
    _lpw_count=0
    for _lpw_part in $(_luoshu_payload_parts); do
        [ -d "$_lpw_module/$_lpw_part" ] || continue
        while IFS= read -r _lpw_file; do
            [ -f "$_lpw_file" ] || continue
            _lpw_rel="${_lpw_file#$_lpw_module/}"
            _lpw_size=$(wc -c < "$_lpw_file" 2>/dev/null | tr -d '[:space:]')
            case "$_lpw_size" in ''|*[!0-9]*) _lpw_size=0 ;; esac
            printf '%s|%s\n' "$_lpw_rel" "$_lpw_size" >> "$_lpw_tmp" 2>/dev/null || return 1
            _lpw_count=$((_lpw_count + 1))
        done <<EOF_LP
$(find "$_lpw_module/$_lpw_part" -type f 2>/dev/null | LC_ALL=C sort)
EOF_LP
    done
    [ "$_lpw_count" -gt 0 ] || { rm -f "$_lpw_tmp" 2>/dev/null || true; return 1; }
    mv -f "$_lpw_tmp" "$_lpw_manifest" 2>/dev/null || return 1
    chmod 0644 "$_lpw_manifest" 2>/dev/null || true
    return 0
}

luoshu_payload_manifest_has_fonts() {
    grep -Eq '\.(ttf|otf|ttc|TTF|OTF|TTC)\|' "${1:-$(_luoshu_safety_config)/font-payload-manifest.conf}" 2>/dev/null
}

luoshu_payload_validate_manifest_fast() {
    _lpv_module="$(_luoshu_safety_module)"
    _lpv_config="$(_luoshu_safety_config)"
    _lpv_manifest="$_lpv_config/font-payload-manifest.conf"
    [ -s "$_lpv_manifest" ] || return 1
    luoshu_payload_manifest_has_fonts "$_lpv_manifest" || return 1
    _lpv_bad=0
    while IFS='|' read -r _lpv_rel _lpv_size; do
        [ -n "$_lpv_rel" ] || continue
        [ -f "$_lpv_module/$_lpv_rel" ] || { _lpv_bad=1; break; }
        _lpv_now=$(wc -c < "$_lpv_module/$_lpv_rel" 2>/dev/null | tr -d '[:space:]')
        case "$_lpv_now" in ''|*[!0-9]*) _lpv_now=-1 ;; esac
        [ "$_lpv_now" = "$_lpv_size" ] || { _lpv_bad=1; break; }
    done < "$_lpv_manifest"
    [ "$_lpv_bad" -eq 0 ]
}

luoshu_payload_validate_current() {
    _lpv_font="${1:-unknown}"
    [ "$_lpv_font" != default ] || return 0
    _lpv_module="$(_luoshu_safety_module)"
    _lpv_found=0
    _lpv_bad=0
    for _lpv_part in $(_luoshu_payload_parts); do
        [ -d "$_lpv_module/$_lpv_part/fonts" ] || continue
        for _lpv_file in "$_lpv_module/$_lpv_part/fonts"/*; do
            [ -f "$_lpv_file" ] || continue
            case "$_lpv_file" in
                *.ttf|*.otf|*.ttc|*.TTF|*.OTF|*.TTC) ;;
                *) continue ;;
            esac
            _lpv_found=1
            _lpv_size=$(wc -c < "$_lpv_file" 2>/dev/null | tr -d '[:space:]')
            case "$_lpv_size" in ''|*[!0-9]*) _lpv_size=0 ;; esac
            if [ "$_lpv_size" -lt 1024 ]; then
                _lpv_bad=1
                break
            fi
            if command -v dd >/dev/null 2>&1; then
                _lpv_magic=$(dd if="$_lpv_file" bs=4 count=1 2>/dev/null | od -An -tx1 2>/dev/null | tr -d ' \n')
                case "$_lpv_magic" in
                    00010000|4f54544f|74746366|74727565) ;;
                    *) _lpv_bad=1; break ;;
                esac
            fi
        done
        [ "$_lpv_bad" -eq 0 ] || break
    done
    [ "$_lpv_found" -eq 1 ] && [ "$_lpv_bad" -eq 0 ]
}

luoshu_payload_prepare_boot() {
    _lpp_active="${1:-default}"
    _lpp_config="$(_luoshu_safety_config)"
    if [ "$_lpp_active" = default ]; then
        rm -f "$_lpp_config/font-payload-boot.conf" "$_lpp_config/font-payload-manifest.conf" 2>/dev/null || true
        return 0
    fi
    luoshu_payload_write_manifest || return 1
    {
        printf 'state=prepared\n'
        printf 'font=%s\n' "$_lpp_active"
        printf 'time=%s\n' "$(date +%s)"
    } > "$_lpp_config/font-payload-boot.conf.tmp.$$" 2>/dev/null || return 1
    mv -f "$_lpp_config/font-payload-boot.conf.tmp.$$" "$_lpp_config/font-payload-boot.conf" 2>/dev/null || return 1
    chmod 0644 "$_lpp_config/font-payload-boot.conf" 2>/dev/null || true
    return 0
}

luoshu_payload_transaction_commit() {
    _lpt_active="${1:-unknown}"
    _lpt_module="$(_luoshu_safety_module)"
    _lpt_config="$(_luoshu_safety_config)"
    [ -d "$_lpt_module/.font-payload-txn" ] || return 1
    luoshu_payload_validate_current "$_lpt_active" || { luoshu_payload_transaction_abort; return 1; }
    luoshu_payload_prepare_boot "$_lpt_active" || { luoshu_payload_transaction_abort; return 1; }
    {
        printf 'schema=%s\n' "$LUOSHU_PAYLOAD_SCHEMA_CURRENT"
        printf 'font=%s\n' "$_lpt_active"
        printf 'time=%s\n' "$(date +%s)"
    } > "$_lpt_config/font-payload-schema.conf.tmp.$$" 2>/dev/null || { luoshu_payload_transaction_abort; return 1; }
    mv -f "$_lpt_config/font-payload-schema.conf.tmp.$$" "$_lpt_config/font-payload-schema.conf" 2>/dev/null || { luoshu_payload_transaction_abort; return 1; }
    chmod 0644 "$_lpt_config/font-payload-schema.conf" 2>/dev/null || true
    rm -rf "$_lpt_module/.font-payload-txn" 2>/dev/null || true
    _luoshu_safety_log INFO "字体负载事务已提交（font=$_lpt_active）"
    return 0
}

luoshu_payload_schema_read() {
    sed -n 's/^schema=//p' "$(_luoshu_safety_config)/font-payload-schema.conf" 2>/dev/null | head -n1 | tr -d '\r\n'
}

luoshu_payload_quarantine() {
    _lpq_module="$(_luoshu_safety_module)"
    _lpq_config="$(_luoshu_safety_config)"
    _lpq_fail=$(sed -n '1p' "$_lpq_config/font-boot-failures" 2>/dev/null | tr -d '[:space:]')
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