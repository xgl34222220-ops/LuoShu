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

_luoshu_font_config_specs() {
    _lfc_module="$(_luoshu_font_config_module)"
    _lfc_system_etc="${LUOSHU_SYSTEM_ETC_ROOT:-/system/etc}"
    printf 'fonts.xml|%s/fonts.xml|%s/system/etc/fonts.xml\n' "$_lfc_system_etc" "$_lfc_module"
    printf 'font_fallback.xml|%s/font_fallback.xml|%s/system/etc/font_fallback.xml\n' "$_lfc_system_etc" "$_lfc_module"
}

_luoshu_font_config_validate() {
    _lfc_xml="$1"
    _lfc_fonts="${2:-}"
    _lfc_module="$(_luoshu_font_config_module)"
    _lfc_tool="$_lfc_module/common/font_config_overlay.py"
    [ -f "$_lfc_xml" ] && [ -f "$_lfc_tool" ] || return 1
    if [ -n "$_lfc_fonts" ]; then
        _luoshu_font_config_exec "$_lfc_tool" --input "$_lfc_xml" --validate-only \
            --font-prefix LuoShu --font-dir "$_lfc_fonts" >/dev/null 2>&1
    else
        _luoshu_font_config_exec "$_lfc_tool" --input "$_lfc_xml" --validate-only >/dev/null 2>&1
    fi
}

font_config_capture_original() {
    _lfc_module="$(_luoshu_font_config_module)"
    _lfc_backup_dir="${CONFIG_DIR:-$_lfc_module/config}/font-config-source/system/etc"
    mkdir -p "$_lfc_backup_dir" 2>/dev/null || return 1
    _lfc_found=0
    while IFS='|' read -r _lfc_name _lfc_real _lfc_overlay; do
        [ -f "$_lfc_real" ] || continue
        _lfc_found=$((_lfc_found + 1))
        _lfc_backup="$_lfc_backup_dir/$_lfc_name"
        [ -s "$_lfc_backup" ] && _luoshu_font_config_validate "$_lfc_backup" && continue
        grep -q 'LuoShu-[1-9][0-9][0-9]\.ttf' "$_lfc_real" 2>/dev/null && continue
        _lfc_temp="${_lfc_backup}.tmp.$$"
        cp -f "$_lfc_real" "$_lfc_temp" 2>/dev/null || continue
        if _luoshu_font_config_validate "$_lfc_temp"; then
            chmod 0644 "$_lfc_temp" 2>/dev/null || true
            mv -f "$_lfc_temp" "$_lfc_backup" 2>/dev/null || true
        else
            rm -f "$_lfc_temp" 2>/dev/null || true
        fi
    done <<EOF_LUOSHU_FONT_CONFIG
$(_luoshu_font_config_specs)
EOF_LUOSHU_FONT_CONFIG
    [ "$_lfc_found" -gt 0 ]
}

font_config_disable() {
    _lfc_module="$(_luoshu_font_config_module)"
    _lfc_state="${CONFIG_DIR:-$_lfc_module/config}/font-config-overlay.conf"
    while IFS='|' read -r _lfc_name _lfc_real _lfc_overlay; do
        if [ -f "$_lfc_overlay" ] && grep -q 'LuoShu-[1-9][0-9][0-9]\.ttf' "$_lfc_overlay" 2>/dev/null; then
            rm -f "$_lfc_overlay" 2>/dev/null || true
        fi
    done <<EOF_LUOSHU_FONT_CONFIG
$(_luoshu_font_config_specs)
EOF_LUOSHU_FONT_CONFIG
    for _lfc_weight in 100 200 300 400 500 600 700 800 900; do
        rm -f "$_lfc_module/system/fonts/LuoShu-${_lfc_weight}.ttf" 2>/dev/null || true
    done
    rm -f "$_lfc_state" 2>/dev/null || true
}

font_config_generate() {
    _lfc_family="$1"
    _lfc_module="$(_luoshu_font_config_module)"
    _lfc_config="${CONFIG_DIR:-$_lfc_module/config}"
    _lfc_backup_dir="$_lfc_config/font-config-source/system/etc"
    _lfc_fonts="$_lfc_module/system/fonts"
    _lfc_tool="$_lfc_module/common/font_config_overlay.py"
    _lfc_stage="$_lfc_config/font-config-stage.$$"
    font_config_capture_original || return 1
    mkdir -p "$_lfc_stage" "$_lfc_module/system/etc" 2>/dev/null || return 1

    for _lfc_weight in 100 200 300 400 500 600 700 800 900; do
        _lfc_font="$_lfc_fonts/LuoShu-${_lfc_weight}.ttf"
        [ -s "$_lfc_font" ] || { rm -f "$_lfc_stage"/* 2>/dev/null; rmdir "$_lfc_stage" 2>/dev/null; return 1; }
    done

    _lfc_changed=0
    while IFS='|' read -r _lfc_name _lfc_real _lfc_overlay; do
        _lfc_input="$_lfc_backup_dir/$_lfc_name"
        [ -s "$_lfc_input" ] || continue
        _lfc_output="$_lfc_stage/$_lfc_name"
        if _luoshu_font_config_exec "$_lfc_tool" --input "$_lfc_input" --output "$_lfc_output" \
            --font-prefix LuoShu --font-dir "$_lfc_fonts" >/dev/null 2>&1 && \
            [ -s "$_lfc_output" ] && _luoshu_font_config_validate "$_lfc_output" "$_lfc_fonts"; then
            _lfc_changed=$((_lfc_changed + 1))
        fi
    done <<EOF_LUOSHU_FONT_CONFIG
$(_luoshu_font_config_specs)
EOF_LUOSHU_FONT_CONFIG

    [ "$_lfc_changed" -gt 0 ] || { rm -f "$_lfc_stage"/* 2>/dev/null; rmdir "$_lfc_stage" 2>/dev/null; return 1; }
    while IFS='|' read -r _lfc_name _lfc_real _lfc_overlay; do
        _lfc_ready="$_lfc_stage/$_lfc_name"
        if [ -s "$_lfc_ready" ]; then
            _lfc_temp="${_lfc_overlay}.tmp.$$"
            cp -f "$_lfc_ready" "$_lfc_temp" 2>/dev/null || return 1
            chmod 0644 "$_lfc_temp" 2>/dev/null || true
            mv -f "$_lfc_temp" "$_lfc_overlay" 2>/dev/null || return 1
        elif [ -f "$_lfc_overlay" ] && grep -q 'LuoShu-' "$_lfc_overlay" 2>/dev/null; then
            rm -f "$_lfc_overlay" 2>/dev/null || true
        fi
    done <<EOF_LUOSHU_FONT_CONFIG
$(_luoshu_font_config_specs)
EOF_LUOSHU_FONT_CONFIG
    rm -f "$_lfc_stage"/* 2>/dev/null || true
    rmdir "$_lfc_stage" 2>/dev/null || true
    {
        printf 'mode=enabled\nfamily=%s\nconfigs=%s\ntime=%s\n' \
            "$_lfc_family" "$_lfc_changed" "$(date +%s)"
    } > "$_lfc_config/font-config-overlay.conf" 2>/dev/null || true
    chmod 0644 "$_lfc_config/font-config-overlay.conf" 2>/dev/null || true
    _luoshu_font_config_log INFO "无 Hook 字体配置已生成：$_lfc_changed 份 XML"
    return 0
}

font_config_boot_guard() {
    _lfc_active="${1:-default}"
    _lfc_module="$(_luoshu_font_config_module)"
    _lfc_fonts="$_lfc_module/system/fonts"
    font_config_capture_original >/dev/null 2>&1 || true
    [ "$_lfc_active" != default ] || { font_config_disable; return 0; }
    _lfc_seen=0
    _lfc_bad=0
    while IFS='|' read -r _lfc_name _lfc_real _lfc_overlay; do
        [ -f "$_lfc_overlay" ] || continue
        grep -q 'LuoShu-[1-9][0-9][0-9]\.ttf' "$_lfc_overlay" 2>/dev/null || continue
        _lfc_seen=$((_lfc_seen + 1))
        _luoshu_font_config_validate "$_lfc_overlay" "$_lfc_fonts" || _lfc_bad=$((_lfc_bad + 1))
    done <<EOF_LUOSHU_FONT_CONFIG
$(_luoshu_font_config_specs)
EOF_LUOSHU_FONT_CONFIG
    if [ "$_lfc_bad" -gt 0 ]; then
        _lfc_backup_dir="${CONFIG_DIR:-$_lfc_module/config}/font-config-source/system/etc"
        while IFS='|' read -r _lfc_name _lfc_real _lfc_overlay; do
            [ -s "$_lfc_backup_dir/$_lfc_name" ] || continue
            cp -f "$_lfc_backup_dir/$_lfc_name" "$_lfc_overlay" 2>/dev/null || true
            chmod 0644 "$_lfc_overlay" 2>/dev/null || true
        done <<EOF_LUOSHU_FONT_CONFIG
$(_luoshu_font_config_specs)
EOF_LUOSHU_FONT_CONFIG
        _luoshu_font_config_log ERROR '字体 XML 校验失败，已恢复设备原始配置并保留文件槽映射'
        return 1
    fi
    [ "$_lfc_seen" -eq 0 ] || _luoshu_font_config_log INFO "无 Hook 字体配置启动校验通过：$_lfc_seen 份 XML"
    return 0
}
