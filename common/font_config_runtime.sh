#!/system/bin/sh
# 洛书无 Hook 字体配置运行层。被 source 时只定义函数。
set +e

_luoshu_font_config_module() {
    printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
}

_luoshu_font_config_python() {
    if [ -n "${LUOSHU_PYTHON:-}" ]; then
        printf '%s\n' "$LUOSHU_PYTHON"
    else
        printf '%s/common/python/bin/luoshu-python\n' "$(_luoshu_font_config_module)"
    fi
}

_luoshu_font_config_exec() {
    _lfc_module="$(_luoshu_font_config_module)"
    _lfc_python="$(_luoshu_font_config_python)"
    if [ -n "${LUOSHU_PYTHON:-}" ]; then
        "$_lfc_python" "$@"
    else
        _lfc_root="$_lfc_module/common/python"
        PYTHONHOME="$_lfc_root" \
        PYTHONPATH="$_lfc_root/lib/python3.14:$_lfc_root/lib/python3.14/site-packages" \
        LD_LIBRARY_PATH="$_lfc_root/lib:$_lfc_root/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
            "$_lfc_python" "$@"
    fi
}

_luoshu_font_config_log() {
    if type log_message >/dev/null 2>&1; then
        log_message "$1" "$2"
    elif type _log_step >/dev/null 2>&1; then
        _log_step "$2"
    fi
}

# key | real XML | module overlay XML | font directory used by that config
_luoshu_font_config_specs() {
    _lfc_module="$(_luoshu_font_config_module)"
    _lfc_system_etc="${LUOSHU_SYSTEM_ETC_ROOT:-/system/etc}"
    _lfc_product_etc="${LUOSHU_PRODUCT_ETC_ROOT:-/product/etc}"
    _lfc_system_ext_etc="${LUOSHU_SYSTEM_EXT_ETC_ROOT:-/system_ext/etc}"

    printf 'system/fonts.xml|%s/fonts.xml|%s/system/etc/fonts.xml|%s/system/fonts\n' \
        "$_lfc_system_etc" "$_lfc_module" "$_lfc_module"
    printf 'system/font_fallback.xml|%s/font_fallback.xml|%s/system/etc/font_fallback.xml|%s/system/fonts\n' \
        "$_lfc_system_etc" "$_lfc_module" "$_lfc_module"

    printf 'product/fonts.xml|%s/fonts.xml|%s/product/etc/fonts.xml|%s/product/fonts\n' \
        "$_lfc_product_etc" "$_lfc_module" "$_lfc_module"
    printf 'product/font_fallback.xml|%s/font_fallback.xml|%s/product/etc/font_fallback.xml|%s/product/fonts\n' \
        "$_lfc_product_etc" "$_lfc_module" "$_lfc_module"
    printf 'product/fonts_customization.xml|%s/fonts_customization.xml|%s/product/etc/fonts_customization.xml|%s/product/fonts\n' \
        "$_lfc_product_etc" "$_lfc_module" "$_lfc_module"
    printf 'product/font_customization.xml|%s/font_customization.xml|%s/product/etc/font_customization.xml|%s/product/fonts\n' \
        "$_lfc_product_etc" "$_lfc_module" "$_lfc_module"
    printf 'product/mi_fonts_customization.xml|%s/mi_fonts_customization.xml|%s/product/etc/mi_fonts_customization.xml|%s/product/fonts\n' \
        "$_lfc_product_etc" "$_lfc_module" "$_lfc_module"

    printf 'system_ext/fonts.xml|%s/fonts.xml|%s/system_ext/etc/fonts.xml|%s/system_ext/fonts\n' \
        "$_lfc_system_ext_etc" "$_lfc_module" "$_lfc_module"
    printf 'system_ext/font_fallback.xml|%s/font_fallback.xml|%s/system_ext/etc/font_fallback.xml|%s/system_ext/fonts\n' \
        "$_lfc_system_ext_etc" "$_lfc_module" "$_lfc_module"
    printf 'system_ext/fonts_customization.xml|%s/fonts_customization.xml|%s/system_ext/etc/fonts_customization.xml|%s/system_ext/fonts\n' \
        "$_lfc_system_ext_etc" "$_lfc_module" "$_lfc_module"
    printf 'system_ext/font_customization.xml|%s/font_customization.xml|%s/system_ext/etc/font_customization.xml|%s/system_ext/fonts\n' \
        "$_lfc_system_ext_etc" "$_lfc_module" "$_lfc_module"
}

_luoshu_font_config_validate() {
    _lfc_xml="$1"
    _lfc_fonts="${2:-}"
    _lfc_module="$(_luoshu_font_config_module)"
    _lfc_tool="$_lfc_module/common/font_config_overlay.py"
    [ -f "$_lfc_xml" ] && [ -f "$_lfc_tool" ] || return 1
    if [ -n "$_lfc_fonts" ]; then
        _luoshu_font_config_exec "$_lfc_tool" --input "$_lfc_xml" --validate-only \
            --font-prefix LuoShu --mono-font-prefix LuoShuMono --font-dir "$_lfc_fonts" >/dev/null 2>&1
    else
        _luoshu_font_config_exec "$_lfc_tool" --input "$_lfc_xml" --validate-only >/dev/null 2>&1
    fi
}

_luoshu_font_config_alias_partition() {
    _lfc_target="$1"
    _lfc_module="$(_luoshu_font_config_module)"
    _lfc_system_fonts="$_lfc_module/system/fonts"
    mkdir -p "$_lfc_target" 2>/dev/null || return 1
    for _lfc_prefix in LuoShu LuoShuMono; do
        for _lfc_weight in 100 200 300 400 500 600 700 800 900; do
            _lfc_source="$_lfc_system_fonts/${_lfc_prefix}-${_lfc_weight}.ttf"
            _lfc_dest="$_lfc_target/${_lfc_prefix}-${_lfc_weight}.ttf"
            [ -s "$_lfc_source" ] || return 1
            if [ "$_lfc_source" != "$_lfc_dest" ]; then
                rm -f "$_lfc_dest" 2>/dev/null || true
                ln "$_lfc_source" "$_lfc_dest" 2>/dev/null || cp -f "$_lfc_source" "$_lfc_dest" 2>/dev/null || return 1
            fi
            chmod 0644 "$_lfc_dest" 2>/dev/null || true
        done
    done
    return 0
}

_luoshu_font_config_remove_aliases() {
    _lfc_dir="$1"
    for _lfc_prefix in LuoShu LuoShuMono; do
        for _lfc_weight in 100 200 300 400 500 600 700 800 900; do
            rm -f "$_lfc_dir/${_lfc_prefix}-${_lfc_weight}.ttf" 2>/dev/null || true
        done
    done
}

# Validate a list of documents in one interpreter. Input lines are XML paths; the function prints
# the subset that parsed successfully. Batching matters because the per-document form cost a full
# embedded-CPython start each, and a ROM can ship a dozen font configuration files.
_luoshu_font_config_validate_batch() {
    _lfcvb_list="$1"
    _lfcvb_module="$(_luoshu_font_config_module)"
    _lfcvb_tool="$_lfcvb_module/common/font_config_overlay.py"
    [ -s "$_lfcvb_list" ] && [ -f "$_lfcvb_tool" ] || return 1
    _lfcvb_jobs="${_lfcvb_list}.jobs"
    : > "$_lfcvb_jobs" 2>/dev/null || return 1
    while IFS= read -r _lfcvb_xml; do
        [ -n "$_lfcvb_xml" ] || continue
        printf 'validate\t%s\t\n' "$_lfcvb_xml" >> "$_lfcvb_jobs"
    done < "$_lfcvb_list"
    _luoshu_font_config_exec "$_lfcvb_tool" --batch "$_lfcvb_jobs" 2>/dev/null | \
        while IFS="$(printf '\t')" read -r _lfcvb_op _lfcvb_src _lfcvb_status _lfcvb_rest; do
            [ "$_lfcvb_op" = validate ] && [ "$_lfcvb_status" = ok ] || continue
            printf '%s\n' "$_lfcvb_src"
        done
    rm -f "$_lfcvb_jobs" 2>/dev/null || true
}

font_config_capture_original() {
    _lfc_module="$(_luoshu_font_config_module)"
    _lfc_config="${CONFIG_DIR:-$_lfc_module/config}"
    _lfc_backup_root="$_lfc_config/font-config-source"
    mkdir -p "$_lfc_backup_root" 2>/dev/null || return 1
    _lfc_work="$_lfc_config/.capture.$$"
    rm -rf "$_lfc_work" 2>/dev/null || true
    mkdir -p "$_lfc_work" 2>/dev/null || return 1
    _lfc_found=0

    # Pass 1: pick the documents that need a fresh snapshot at all. No interpreter is involved.
    : > "$_lfc_work/check"
    : > "$_lfc_work/pending"
    while IFS='|' read -r _lfc_key _lfc_real _lfc_overlay _lfc_fonts; do
        [ -f "$_lfc_real" ] || continue
        _lfc_found=$((_lfc_found + 1))
        _lfc_backup="$_lfc_backup_root/$_lfc_key"
        mkdir -p "${_lfc_backup%/*}" 2>/dev/null || continue
        # Never snapshot our own upper-layer document. Keep a valid previous source when mounted.
        if grep -Eq 'LuoShu(Mono)?-[1-9][0-9][0-9]\.ttf' "$_lfc_real" 2>/dev/null; then
            continue
        fi
        if [ -s "$_lfc_backup" ]; then
            printf '%s\n' "$_lfc_backup" >> "$_lfc_work/check"
            printf '%s\t%s\t%s\n' "$_lfc_real" "$_lfc_backup" keep >> "$_lfc_work/pending"
        else
            printf '%s\t%s\t%s\n' "$_lfc_real" "$_lfc_backup" fresh >> "$_lfc_work/pending"
        fi
    done <<EOF_LUOSHU_FONT_CONFIG
$(_luoshu_font_config_specs)
EOF_LUOSHU_FONT_CONFIG

    # Pass 2: one interpreter validates every existing backup.
    : > "$_lfc_work/valid"
    if [ -s "$_lfc_work/check" ]; then
        _luoshu_font_config_validate_batch "$_lfc_work/check" > "$_lfc_work/valid" 2>/dev/null || true
    fi

    # Pass 3: stage the snapshots that are missing, stale or unusable.
    : > "$_lfc_work/verify"
    : > "$_lfc_work/commit"
    while IFS="$(printf '\t')" read -r _lfc_real _lfc_backup _lfc_state; do
        [ -n "$_lfc_real" ] || continue
        if [ "$_lfc_state" = keep ] && grep -Fxq "$_lfc_backup" "$_lfc_work/valid" 2>/dev/null; then
            command -v cmp >/dev/null 2>&1 && cmp -s "$_lfc_real" "$_lfc_backup" 2>/dev/null && continue
        fi
        _lfc_temp="${_lfc_backup}.tmp.$$"
        cp -f "$_lfc_real" "$_lfc_temp" 2>/dev/null || continue
        printf '%s\n' "$_lfc_temp" >> "$_lfc_work/verify"
        printf '%s\t%s\n' "$_lfc_temp" "$_lfc_backup" >> "$_lfc_work/commit"
    done < "$_lfc_work/pending"

    # Pass 4: one interpreter validates every staged snapshot, then the good ones are committed.
    if [ -s "$_lfc_work/verify" ]; then
        _luoshu_font_config_validate_batch "$_lfc_work/verify" > "$_lfc_work/verified" 2>/dev/null || : > "$_lfc_work/verified"
        while IFS="$(printf '\t')" read -r _lfc_temp _lfc_backup; do
            [ -n "$_lfc_temp" ] || continue
            if grep -Fxq "$_lfc_temp" "$_lfc_work/verified" 2>/dev/null; then
                chmod 0644 "$_lfc_temp" 2>/dev/null || true
                mv -f "$_lfc_temp" "$_lfc_backup" 2>/dev/null || true
            else
                rm -f "$_lfc_temp" 2>/dev/null || true
            fi
        done < "$_lfc_work/commit"
    fi

    rm -rf "$_lfc_work" 2>/dev/null || true
    [ "$_lfc_found" -gt 0 ]
}

_luoshu_font_config_disable_base() {
    _lfc_module="$(_luoshu_font_config_module)"
    _lfc_state="${CONFIG_DIR:-$_lfc_module/config}/font-config-overlay.conf"
    _lfc_dirs=''
    while IFS='|' read -r _lfc_key _lfc_real _lfc_overlay _lfc_fonts; do
        if [ -f "$_lfc_overlay" ] && grep -Eq 'LuoShu(Mono)?-[1-9][0-9][0-9]\.ttf' "$_lfc_overlay" 2>/dev/null; then
            rm -f "$_lfc_overlay" 2>/dev/null || true
        fi
        case " $_lfc_dirs " in *" $_lfc_fonts "*) ;; *) _lfc_dirs="$_lfc_dirs $_lfc_fonts" ;; esac
    done <<EOF_LUOSHU_FONT_CONFIG
$(_luoshu_font_config_specs)
EOF_LUOSHU_FONT_CONFIG
    for _lfc_dir in $_lfc_dirs; do _luoshu_font_config_remove_aliases "$_lfc_dir"; done
    rm -f "$_lfc_state" 2>/dev/null || true
}

_luoshu_font_config_generate_base() {
    _lfc_family="$1"
    _lfc_module="$(_luoshu_font_config_module)"
    _lfc_config="${CONFIG_DIR:-$_lfc_module/config}"
    _lfc_backup_root="$_lfc_config/font-config-source"
    _lfc_tool="$_lfc_module/common/font_config_overlay.py"
    _lfc_stage="$_lfc_config/font-config-stage.$$"
    font_config_capture_original || return 1

    # Weight availability is a global invariant. Never publish XML that references a half-built
    # family merely because one partition happens to be writable.
    for _lfc_prefix in LuoShu LuoShuMono; do
        for _lfc_weight in 100 200 300 400 500 600 700 800 900; do
            [ -s "$_lfc_module/system/fonts/${_lfc_prefix}-${_lfc_weight}.ttf" ] || {
                _luoshu_font_config_disable_base
                return 1
            }
        done
    done

    mkdir -p "$_lfc_stage" 2>/dev/null || return 1

    _lfc_changed=0
    _lfc_failed=0

    # One interpreter for every document. Each embedded-CPython start on a phone costs far more than
    # the rewrite itself, so a per-document invocation made the switch scale with how many font
    # configuration files the ROM happens to ship -- eight documents meant sixteen interpreter starts
    # here alone. The batch generator validates the references it emits, so the separate
    # validate-only pass is gone as well.
    _lfc_jobs="$_lfc_stage/.jobs"
    : > "$_lfc_jobs" 2>/dev/null || { rm -rf "$_lfc_stage"; return 1; }
    while IFS='|' read -r _lfc_key _lfc_real _lfc_overlay _lfc_fonts; do
        _lfc_input="$_lfc_backup_root/$_lfc_key"
        [ -s "$_lfc_input" ] || continue
        _luoshu_font_config_alias_partition "$_lfc_fonts" || { _lfc_failed=$((_lfc_failed + 1)); continue; }
        _lfc_output="$_lfc_stage/$_lfc_key"
        mkdir -p "${_lfc_output%/*}" 2>/dev/null || { _lfc_failed=$((_lfc_failed + 1)); continue; }
        printf 'generate\t%s\t%s\t%s\n' "$_lfc_input" "$_lfc_output" "$_lfc_fonts" >> "$_lfc_jobs"
    done <<EOF_LUOSHU_FONT_CONFIG
$(_luoshu_font_config_specs)
EOF_LUOSHU_FONT_CONFIG

    if [ -s "$_lfc_jobs" ]; then
        _lfc_results="$_lfc_stage/.results"
        if _luoshu_font_config_exec "$_lfc_tool" --batch "$_lfc_jobs" \
            --font-prefix LuoShu --mono-font-prefix LuoShuMono > "$_lfc_results" 2>/dev/null; then
            while IFS="$(printf '\t')" read -r _lfc_op _lfc_src _lfc_status _lfc_flag _lfc_refs _lfc_msg; do
                [ "$_lfc_op" = generate ] || continue
                if [ "$_lfc_status" = ok ] && [ "$_lfc_flag" = 1 ]; then
                    _lfc_changed=$((_lfc_changed + 1))
                else
                    _lfc_failed=$((_lfc_failed + 1))
                fi
            done < "$_lfc_results"
        else
            _lfc_failed=$((_lfc_failed + 1))
        fi
        rm -f "$_lfc_results" 2>/dev/null || true
    fi
    rm -f "$_lfc_jobs" 2>/dev/null || true

    if [ "$_lfc_changed" -eq 0 ]; then
        rm -rf "$_lfc_stage" 2>/dev/null || true
        _luoshu_font_config_disable_base
        return 1
    fi
    [ "$_lfc_failed" -eq 0 ] || _luoshu_font_config_log WARN \
        "部分分区未能生成字体别名，已按通过校验的可用分区提交 XML 覆盖：ok=$_lfc_changed failed=$_lfc_failed"

    # Commit only independently generated documents whose referenced aliases already validated.
    while IFS='|' read -r _lfc_key _lfc_real _lfc_overlay _lfc_fonts; do
        _lfc_ready="$_lfc_stage/$_lfc_key"
        if [ -s "$_lfc_ready" ]; then
            mkdir -p "${_lfc_overlay%/*}" 2>/dev/null || { rm -rf "$_lfc_stage"; _luoshu_font_config_disable_base; return 1; }
            _lfc_temp="${_lfc_overlay}.tmp.$$"
            cp -f "$_lfc_ready" "$_lfc_temp" 2>/dev/null || { rm -rf "$_lfc_stage"; _luoshu_font_config_disable_base; return 1; }
            chmod 0644 "$_lfc_temp" 2>/dev/null || true
            mv -f "$_lfc_temp" "$_lfc_overlay" 2>/dev/null || { rm -rf "$_lfc_stage"; _luoshu_font_config_disable_base; return 1; }
        elif [ -f "$_lfc_overlay" ] && grep -Eq 'LuoShu(Mono)?-' "$_lfc_overlay" 2>/dev/null; then
            rm -f "$_lfc_overlay" 2>/dev/null || true
        fi
    done <<EOF_LUOSHU_FONT_CONFIG
$(_luoshu_font_config_specs)
EOF_LUOSHU_FONT_CONFIG
    rm -rf "$_lfc_stage" 2>/dev/null || true
    {
        printf 'mode=enabled\nfamily=%s\nconfigs=%s\ntime=%s\n' \
            "$_lfc_family" "$_lfc_changed" "$(date +%s)"
    } > "$_lfc_config/font-config-overlay.conf" 2>/dev/null || true
    chmod 0644 "$_lfc_config/font-config-overlay.conf" 2>/dev/null || true
    _luoshu_font_config_log INFO "无 Hook 字体配置已生成：$_lfc_changed 份 XML"
    return 0
}

_luoshu_font_config_boot_guard_base() {
    _lfc_active="${1:-default}"
    _lfc_module="$(_luoshu_font_config_module)"
    font_config_capture_original >/dev/null 2>&1 || true
    [ "$_lfc_active" != default ] || { font_config_disable; return 0; }
    _lfc_seen=0
    _lfc_bad=0
    while IFS='|' read -r _lfc_key _lfc_real _lfc_overlay _lfc_fonts; do
        [ -f "$_lfc_overlay" ] || continue
        grep -Eq 'LuoShu(Mono)?-[1-9][0-9][0-9]\.ttf' "$_lfc_overlay" 2>/dev/null || continue
        _lfc_seen=$((_lfc_seen + 1))
        _luoshu_font_config_validate "$_lfc_overlay" "$_lfc_fonts" || _lfc_bad=$((_lfc_bad + 1))
    done <<EOF_LUOSHU_FONT_CONFIG
$(_luoshu_font_config_specs)
EOF_LUOSHU_FONT_CONFIG
    if [ "$_lfc_bad" -gt 0 ]; then
        # Removing the upper-layer XML reveals the untouched ROM document below. File-slot aliases
        # remain available as the compatibility fallback, so an invalid generated config never boots.
        while IFS='|' read -r _lfc_key _lfc_real _lfc_overlay _lfc_fonts; do
            [ -f "$_lfc_overlay" ] && grep -Eq 'LuoShu(Mono)?-' "$_lfc_overlay" 2>/dev/null && rm -f "$_lfc_overlay" 2>/dev/null || true
        done <<EOF_LUOSHU_FONT_CONFIG
$(_luoshu_font_config_specs)
EOF_LUOSHU_FONT_CONFIG
        rm -f "${CONFIG_DIR:-$_lfc_module/config}/font-config-overlay.conf" 2>/dev/null || true
        _luoshu_font_config_log ERROR '字体 XML 校验失败，已撤销配置覆盖并保留文件槽映射'
        return 1
    fi
    [ "$_lfc_seen" -eq 0 ] || _luoshu_font_config_log INFO "无 Hook 字体配置启动校验通过：$_lfc_seen 份 XML"
    return 0
}

# Load the fail-open transaction and boot-confirmation layer for every runtime caller.
_luoshu_font_safety="$(_luoshu_font_config_module)/common/font_safety.sh"
[ -f "$_luoshu_font_safety" ] && . "$_luoshu_font_safety"
