#!/system/bin/sh
# 字体模块 ZIP 兼容层：保留斜体字重，并处理内部 family 名随字重变化的第三方模块。
# 在 font_import.sh 之后加载，只覆盖导入期辅助函数，不放宽字体格式与安全校验。

import_detect_family() {
    _stem="${1%.*}"
    _stem=$(printf '%s' "$_stem" | sed -E '
        s/[-_](thin|extralight|ultralight|light|regular|book|normal|medium|semibold|demibold|bold|extrabold|ultrabold|black|heavy)(italic|oblique)$//I;
        s/[-_](italic|oblique)(thin|extralight|ultralight|light|regular|book|normal|medium|semibold|demibold|bold|extrabold|ultrabold|black|heavy)$//I;
        s/[-_](italic|oblique)$//I;
        s/[-_](thin|extralight|ultralight|light|regular|book|normal|medium|semibold|demibold|bold|extrabold|ultrabold|black|heavy)$//I;
        s/[-_]w([1-9]|[1-9]00)(italic|oblique)?$//I;
        s/[-_](100|200|300|400|500|600|700|800|900)(italic|oblique)?$//I;
        s/[-_]+$//')
    [ -n "$_stem" ] || _stem="ImportedFont"
    printf '%s\n' "$_stem"
}

import_filename_has_style_suffix() {
    _stem="${1%.*}"
    printf '%s\n' "$_stem" | grep -Eiq '[-_](thin|extralight|ultralight|light|regular|book|normal|medium|semibold|demibold|bold|extrabold|ultrabold|black|heavy)(italic|oblique)?$|[-_](italic|oblique)(thin|extralight|ultralight|light|regular|book|normal|medium|semibold|demibold|bold|extrabold|ultrabold|black|heavy)$|[-_]w([1-9]|[1-9]00)(italic|oblique)?$|[-_](100|200|300|400|500|600|700|800|900)(italic|oblique)?$'
}

# 某些字体模块为每个字重写入不同的内部 family 名，但文件名仍是稳定的
# RobotoFake-Thin / RobotoFake-BlackItalic 结构。遇到明确字重后缀时，以文件名
# 归一化结果作为导入分组；无字重提示的文件仍信任字体内部 name 表。
import_probe_metadata() {
    _probe_file="$1"
    [ -f "$IMPORT_PROBE" ] || return 1
    _probe_output=""
    if [ -n "${LUOSHU_IMPORT_PYTHON:-}" ]; then
        _probe_output=$("$LUOSHU_IMPORT_PYTHON" "$IMPORT_PROBE" "$_probe_file" 2>/dev/null)
    elif [ -x "$IMPORT_PYBIN" ]; then
        _probe_output=$(PYTHONHOME="$IMPORT_PYROOT" \
            PYTHONPATH="$IMPORT_PYROOT/lib/python3.14:$IMPORT_PYROOT/lib/python3.14/site-packages" \
            LD_LIBRARY_PATH="$IMPORT_PYROOT/lib:$IMPORT_PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
            "$IMPORT_PYBIN" "$IMPORT_PROBE" "$_probe_file" 2>/dev/null)
    elif command -v python3 >/dev/null 2>&1; then
        _probe_output=$(python3 "$IMPORT_PROBE" "$_probe_file" 2>/dev/null)
    fi
    case "$_probe_output" in *'|'*'|'*'|'*'|'*) ;; *) return 1 ;; esac

    IFS='|' read -r _probe_family _probe_subfamily _probe_weight _probe_italic _probe_variable _probe_supports_cjk <<EOF_PROBE
$_probe_output
EOF_PROBE
    _probe_base=$(basename "$_probe_file")
    if import_filename_has_style_suffix "$_probe_base"; then
        _probe_family=$(import_detect_family "$_probe_base")
    fi
    case "$_probe_italic" in
        true) _probe_italic=italic ;;
        *)
            _probe_lower=$(printf '%s' "$_probe_base $_probe_subfamily" | tr '[:upper:]' '[:lower:]')
            case "$_probe_lower" in *italic*|*oblique*) _probe_italic=italic ;; *) _probe_italic=false ;; esac
            ;;
    esac
    printf '%s|%s|%s|%s|%s|%s\n' "$_probe_family" "$_probe_subfamily" "$_probe_weight" "$_probe_italic" "$_probe_variable" "${_probe_supports_cjk:-false}"
}

# 斜体是有效的文字字体，不再作为噪声整体丢弃。真实图标、Emoji 和损坏字体
# 仍由原导入器的名称、颜色表和 font_validate 门禁过滤。
import_is_italic_name() {
    return 1
}

# 保留样式信息，同时采用 Italic-Black 顺序，兼容现有 detect_font_family：
# 它会先移除 -Black，再移除 -Italic，最终仍归入同一个字体族。
import_weight_label() {
    case "$1" in
        thin) _import_label=Thin ;; extralight) _import_label=ExtraLight ;; light) _import_label=Light ;;
        regular) _import_label=Regular ;; medium) _import_label=Medium ;; semibold) _import_label=SemiBold ;;
        bold) _import_label=Bold ;; extrabold) _import_label=ExtraBold ;; black) _import_label=Black ;;
        *) _import_label=Regular ;;
    esac
    case "${_italic:-false}" in italic|oblique) printf 'Italic-%s\n' "$_import_label" ;; *) printf '%s\n' "$_import_label" ;; esac
}

# 单文件模块原逻辑固定写成 Regular。这里在真正复制前根据 OS/2 字重与斜体
# 元数据修正目标名，避免 Thin/BlackItalic 被伪装成常规 400。
import_copy_unique() {
    _src="$1"; _dest_dir="$2"; _dest_name="$3"
    _dest_stem="${_dest_name%.*}"; _dest_ext="${_dest_name##*.}"
    case "$_dest_stem" in
        *-Italic-Regular|*-Oblique-Regular)
            # family 模式已经带有样式前缀，不再做单文件 Regular 纠正。
            ;;
        *-Regular)
            _single_probe=$(import_probe_metadata "$_src" 2>/dev/null)
            if [ -n "$_single_probe" ]; then
                IFS='|' read -r _single_family _single_subfamily _single_weight _single_italic _single_variable _single_supports_cjk <<EOF_SINGLE
$_single_probe
EOF_SINGLE
                _single_role=$(import_weight_role_from_class "$_single_weight" "$(basename "$_src")")
                _saved_italic="${_italic:-false}"
                _italic="$_single_italic"
                _single_label=$(import_weight_label "$_single_role")
                _italic="$_saved_italic"
                if [ "$_single_label" != Regular ]; then
                    _dest_name="${_dest_stem%-Regular}-${_single_label}.${_dest_ext}"
                fi
            fi
            ;;
    esac

    mkdir -p "$_dest_dir" 2>/dev/null || return 1
    _stem="${_dest_name%.*}"; _ext="${_dest_name##*.}"; _target="$_dest_dir/$_dest_name"; _n=2
    while [ -e "$_target" ]; do
        _old_size=$(wc -c < "$_target" 2>/dev/null | tr -d '[:space:]')
        _new_size=$(wc -c < "$_src" 2>/dev/null | tr -d '[:space:]')
        if [ "$_old_size" = "$_new_size" ] && cmp -s "$_target" "$_src" 2>/dev/null; then
            printf '%s\n' "$_target"
            return 0
        fi
        _target="$_dest_dir/${_stem}-import${_n}.${_ext}"
        _n=$((_n + 1))
    done
    cp -f "$_src" "$_target" 2>/dev/null || return 1
    chmod 0644 "$_target" 2>/dev/null || true
    printf '%s\n' "$_target"
}
