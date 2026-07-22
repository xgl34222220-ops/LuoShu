#!/system/bin/sh
# 洛书组合字体收尾性能修复：所有大小校验只读取元数据，静态字体权重使用硬链接别名。
# 本文件在 font_config_runtime.sh、font_config_weights.sh 和分区清单之后加载，用于覆盖旧实现。
set +e

_luoshu_fast_filesize() {
    _lff_file="$1"
    if command -v stat >/dev/null 2>&1; then
        stat -c '%s' "$_lff_file" 2>/dev/null && return 0
    fi
    if command -v toybox >/dev/null 2>&1; then
        toybox stat -c '%s' "$_lff_file" 2>/dev/null && return 0
    fi
    # 仅在极旧环境没有 stat 时回退；正常 Android 不会走到这里。
    wc -c < "$_lff_file" 2>/dev/null | tr -d '[:space:]'
}

_luoshu_fast_font_ok() {
    [ -f "$1" ] || return 1
    _lff_size=$(_luoshu_fast_filesize "$1")
    case "$_lff_size" in ''|*[!0-9]*) return 1 ;; esac
    [ "$_lff_size" -ge 1024 ]
}

# ROM 文件槽通常是同一 inode 的大量硬链接，禁止逐路径读取完整字体来确认大小。
_verify_font_copy() {
    _vfc_file="$1"
    if ! _luoshu_fast_font_ok "$_vfc_file"; then
        type _log_step >/dev/null 2>&1 && _log_step "  警告：$(basename "$_vfc_file") 字体文件为空或异常小"
        return 1
    fi
    return 0
}

# 使用 stat 挑选九档来源，避免每个候选都把几十 MB 字体完整读取一遍。
_luoshu_config_weight_source() {
    _lcw_weight="$1"
    _lcw_module="$(_luoshu_config_weight_module)"
    _lcw_fonts="$_lcw_module/system/fonts"
    _lcw_role="$(_luoshu_config_weight_role "$_lcw_weight")"

    for _lcw_file in \
        "$_lcw_fonts/.luoshu-font-store/wght-${_lcw_weight}.font" \
        "$_lcw_fonts/${_lcw_weight}.ttf" \
        "$_lcw_fonts/Roboto-${_lcw_role}.ttf" \
        "$_lcw_fonts/GoogleSans-${_lcw_role}.ttf" \
        "$_lcw_fonts/GoogleSansText-${_lcw_role}.ttf" \
        "$_lcw_fonts/SysFont-${_lcw_role}.ttf" \
        "$_lcw_fonts/SysSans-En-${_lcw_role}.ttf" \
        "$_lcw_fonts/Opposans-En-${_lcw_role}.ttf" \
        "$_lcw_fonts/SourceSansPro-${_lcw_role}.ttf" \
        "$_lcw_fonts/NotoSans-${_lcw_role}.ttf"; do
        _luoshu_fast_font_ok "$_lcw_file" || continue
        printf '%s\n' "$_lcw_file"
        return 0
    done

    for _lcw_file in \
        "$_lcw_fonts/.luoshu-font-store/regular.font" \
        "$_lcw_fonts/.luoshu-font-store/mix-composite.font" \
        "$_lcw_fonts/400.ttf" \
        "$_lcw_fonts/Roboto-Regular.ttf" \
        "$_lcw_fonts/GoogleSans-Regular.ttf" \
        "$_lcw_fonts/GoogleSansText-Regular.ttf" \
        "$_lcw_fonts/SysFont-Regular.ttf" \
        "$_lcw_fonts/SysSans-En-Regular.ttf" \
        "$_lcw_fonts/MiSansVF.ttf" \
        "$_lcw_fonts/NotoSansCJK-Regular.ttc" \
        "$_lcw_fonts/NotoSans-Regular.ttf"; do
        _luoshu_fast_font_ok "$_lcw_file" || continue
        printf '%s\n' "$_lcw_file"
        return 0
    done
    return 1
}

_luoshu_fast_link_font() {
    _lfl_source="$1"
    _lfl_target="$2"
    rm -f "$_lfl_target" 2>/dev/null || true
    ln "$_lfl_source" "$_lfl_target" 2>/dev/null || cp -f "$_lfl_source" "$_lfl_target" 2>/dev/null || return 1
    chmod 0644 "$_lfl_target" 2>/dev/null || true
    _luoshu_fast_font_ok "$_lfl_target"
}

# 组合引擎产出的静态字体已经完成轮廓与度量归一化，无需再把同一大字体序列化 18 次。
# UI 九档直接引用对应静态来源；Mono 只生成一次 400 档，其余权重共享同一固定宽度文件。
font_config_prepare_payload_weights() {
    _lcw_module="$(_luoshu_config_weight_module)"
    _lcw_fonts="$_lcw_module/system/fonts"
    mkdir -p "$_lcw_fonts" "$_lcw_module/config" 2>/dev/null || return 1

    _lcw_stage="$_lcw_module/config/font-config-weights.$$"
    rm -rf "$_lcw_stage" 2>/dev/null || true
    mkdir -p "$_lcw_stage" 2>/dev/null || return 1
    type mix_stage >/dev/null 2>&1 && mix_stage weight-map '正在准备九档字体映射' 92

    for _lcw_weight in 100 200 300 400 500 600 700 800 900; do
        _lcw_source="$(_luoshu_config_weight_source "$_lcw_weight")" || { rm -rf "$_lcw_stage"; return 1; }
        _lcw_target="$_lcw_stage/LuoShu-${_lcw_weight}.ttf"
        _lcw_magic=$(dd if="$_lcw_source" bs=4 count=1 2>/dev/null)
        if [ "$_lcw_magic" = ttcf ]; then
            rm -rf "$_lcw_stage" 2>/dev/null || true
            return 1
        fi
        if type is_variable_font >/dev/null 2>&1 && is_variable_font "$_lcw_source"; then
            _luoshu_config_normalize_weight "$_lcw_source" "$_lcw_target" "$_lcw_weight" || { rm -rf "$_lcw_stage"; return 1; }
        else
            _luoshu_fast_link_font "$_lcw_source" "$_lcw_target" || { rm -rf "$_lcw_stage"; return 1; }
        fi
    done

    type mix_stage >/dev/null 2>&1 && mix_stage mono-map '正在生成等宽英文数字映射' 93
    _lcw_mono400="$_lcw_stage/LuoShuMono-400.ttf"
    _luoshu_config_make_mono_weight "$_lcw_stage/LuoShu-400.ttf" "$_lcw_mono400" 400 || { rm -rf "$_lcw_stage"; return 1; }
    for _lcw_weight in 100 200 300 500 600 700 800 900; do
        _luoshu_fast_link_font "$_lcw_mono400" "$_lcw_stage/LuoShuMono-${_lcw_weight}.ttf" || { rm -rf "$_lcw_stage"; return 1; }
    done

    for _lcw_weight in 100 200 300 400 500 600 700 800 900; do
        for _lcw_prefix in LuoShu LuoShuMono; do
            _lcw_ready="$_lcw_stage/${_lcw_prefix}-${_lcw_weight}.ttf"
            _lcw_dest="$_lcw_fonts/${_lcw_prefix}-${_lcw_weight}.ttf"
            rm -f "$_lcw_dest" 2>/dev/null || true
            mv -f "$_lcw_ready" "$_lcw_dest" 2>/dev/null || { rm -rf "$_lcw_stage"; return 1; }
        done
    done
    rmdir "$_lcw_stage" 2>/dev/null || true
    return 0
}

# 动态物理槽映射只检查 inode 元数据，不读取每个硬链接的字体内容。
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
    _ldt_targets=0; _ldt_mapped=0; _ldt_configs=0; _ldt_scan_failed=0
    while IFS='|' read -r _ldt_key _ldt_real _ldt_overlay _ldt_font_dir; do
        _ldt_input="$_ldt_backup/$_ldt_key"
        [ -s "$_ldt_input" ] || continue
        _ldt_out="$_ldt_config/.font-targets.$$.txt"
        rm -f "$_ldt_out" 2>/dev/null || true
        if ! _luoshu_font_config_exec "$_ldt_tool" --input "$_ldt_input" > "$_ldt_out" 2>/dev/null; then
            _ldt_scan_failed=$((_ldt_scan_failed + 1)); rm -f "$_ldt_out"; continue
        fi
        _ldt_configs=$((_ldt_configs + 1))
        while IFS='|' read -r _ldt_file _ldt_weight _ldt_family; do
            [ -n "$_ldt_file" ] || continue
            case "$_ldt_file" in */*|*'..'*|LuoShu-*.ttf|LuoShuMono-*.ttf) continue ;; *.ttf|*.otf|*.ttc) ;; *) continue ;; esac
            case "$_ldt_weight" in 100|200|300|400|500|600|700|800|900) ;; *) _ldt_weight=400 ;; esac
            _ldt_rel="${_ldt_font_dir#$_ldt_module/}/$_ldt_file"
            grep -Fq "$_ldt_rel|" "$_ldt_manifest_tmp" 2>/dev/null && continue
            _ldt_targets=$((_ldt_targets + 1))
            _ldt_source="$_ldt_module/system/fonts/LuoShu-${_ldt_weight}.ttf"
            _ldt_dest="$_ldt_font_dir/$_ldt_file"
            _luoshu_fast_font_ok "$_ldt_source" || continue
            mkdir -p "$_ldt_font_dir" 2>/dev/null || continue
            rm -f "$_ldt_dest" 2>/dev/null || true
            if ln "$_ldt_source" "$_ldt_dest" 2>/dev/null || cp -f "$_ldt_source" "$_ldt_dest" 2>/dev/null; then
                chmod 0644 "$_ldt_dest" 2>/dev/null || true
                if _luoshu_fast_font_ok "$_ldt_dest"; then
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

# 94% 阶段只做存在性与文件大小元数据校验；禁止对每个别名重复顺序读取整份字体。
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
            _luoshu_fast_font_ok "$_lpv_file" || return 1
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
