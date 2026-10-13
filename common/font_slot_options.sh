#!/system/bin/sh
# 可选分槽：衬线（Serif）与 Emoji。两者默认都不启用，对应的原厂字体文件保持不动：
#   - 未指定衬线字体时，NotoSerif* / MiSerif* 等衬线槽保留原厂；
#   - 未指定 Emoji 字体时，NotoColorEmoji* 等 Emoji 文件永远不会被文字字体替换。
# 用户显式指定后，下一次应用字体时才写入暂存负载，重启生效；清除后恢复原厂。
#
# source 时只定义函数。直接执行时作为命令行：
#   font_slot_options.sh status
#   font_slot_options.sh set-serif <字体ID> | clear-serif
#   font_slot_options.sh set-emoji <彩色字体文件> | clear-emoji

luoshu_slot_options_module() {
    printf '%s\n' "${LUOSHU_REAL_MODDIR:-${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}}"
}

luoshu_slot_options_conf() {
    printf '%s\n' "${LUOSHU_SLOT_OPTIONS_CONF:-$(luoshu_slot_options_module)/config/font_slot_options.conf}"
}

luoshu_slot_options_get() {
    _lsog_conf=$(luoshu_slot_options_conf)
    [ -f "$_lsog_conf" ] || return 0
    sed -n "s/^$1=//p" "$_lsog_conf" 2>/dev/null | head -n1 | tr -d '\r\n'
}

luoshu_slot_options_set() {
    _lsos_key="$1"; _lsos_value="$2"
    case "$_lsos_value" in *'
'*) return 1 ;; esac
    _lsos_conf=$(luoshu_slot_options_conf)
    mkdir -p "${_lsos_conf%/*}" 2>/dev/null || return 1
    _lsos_tmp="${_lsos_conf}.tmp.$$"
    {
        [ -f "$_lsos_conf" ] && grep -v "^${_lsos_key}=" "$_lsos_conf" 2>/dev/null
        [ -n "$_lsos_value" ] && printf '%s=%s\n' "$_lsos_key" "$_lsos_value"
        :
    } > "$_lsos_tmp" 2>/dev/null || { rm -f "$_lsos_tmp"; return 1; }
    mv -f "$_lsos_tmp" "$_lsos_conf" 2>/dev/null || { rm -f "$_lsos_tmp"; return 1; }
    chmod 0644 "$_lsos_conf" 2>/dev/null || true
}

# 原厂字体目录（测试可用 LUOSHU_SLOT_OPTIONS_ROOTS 指向夹具，空格分隔）。
luoshu_slot_options_roots() {
    if [ -n "${LUOSHU_SLOT_OPTIONS_ROOTS:-}" ]; then
        printf '%s\n' "$LUOSHU_SLOT_OPTIONS_ROOTS"
    else
        printf '%s\n' '/system/fonts /system_ext/fonts /product/fonts /my_product/fonts /vendor/fonts /mi_ext/fonts'
    fi
}

# 正体衬线槽：只认单字体 .ttf/.otf；斜体、等宽、集合字体保持原厂。
luoshu_slot_options_serif_targets() {
    for _lsost_root in $(luoshu_slot_options_roots); do
        for _lsost_path in "$_lsost_root"/*.ttf "$_lsost_root"/*.otf; do
            [ -f "$_lsost_path" ] || continue
            _lsost_name=${_lsost_path##*/}
            case "$_lsost_name" in *[Ss]erif*|*SERIF*) ;; *) continue ;; esac
            case "$_lsost_name" in
                *[Ii]talic*|*[Oo]blique*|*[Mm]ono*|*[Ss]ans*|*[Ee]moji*|*[Ss]ymbol*) continue ;;
            esac
            printf '%s\n' "$_lsost_name"
        done
    done | awk 'NF && !seen[$0]++'
}

luoshu_slot_options_emoji_targets() {
    for _lsoet_root in $(luoshu_slot_options_roots); do
        for _lsoet_path in "$_lsoet_root"/*.ttf "$_lsoet_root"/*.otf; do
            [ -f "$_lsoet_path" ] || continue
            _lsoet_name=${_lsoet_path##*/}
            case "$_lsoet_name" in *[Ee]moji*|*EMOJI*) printf '%s\n' "$_lsoet_name" ;; esac
        done
    done | awk 'NF && !seen[$0]++'
}

# 衬线槽里的中日韩字体（MiSerifSC、NotoSerifCJK…）要求用户字体覆盖汉字，
# 否则保持原厂，避免汉字回退链断开。
luoshu_slot_options_serif_needs_han() {
    case "$1" in *SC*|*TC*|*HK*|*CJK*|*Hans*|*Hant*|MiSerif*) return 0 ;; esac
    return 1
}

luoshu_slot_options_link() {
    rm -f "$2" 2>/dev/null || true
    ln "$1" "$2" 2>/dev/null || cp -f "$1" "$2" 2>/dev/null || return 1
    chmod 0644 "$2" 2>/dev/null || true
}

luoshu_slot_options_log() {
    if type _log_step >/dev/null 2>&1; then _log_step "$1"; else printf '  [洛书] %s\n' "$1"; fi
}

# 在暂存的 system/fonts 目录中写入已启用的可选槽位；未启用时什么也不做。
luoshu_slot_options_apply() {
    _lsoa_dest="$1"
    [ -d "$_lsoa_dest" ] || return 0
    [ -z "${LUOSHU_MIX_REQUEST_ID:-}" ] || return 0
    _lsoa_store="$_lsoa_dest/.luoshu-font-store"

    _lsoa_serif=$(luoshu_slot_options_get serif)
    if [ -n "$_lsoa_serif" ] && type luoshu_cap_anchors >/dev/null 2>&1; then
        _lsoa_rows=$(luoshu_cap_anchors "$_lsoa_store" "$_lsoa_serif" '100,200,300,400,500,600,700,800,900' \
            serif-wght- '' '' serif-variable.font)
        _lsoa_count=0; _lsoa_kept=0
        if [ -n "$_lsoa_rows" ]; then
            for _lsoa_name in $(luoshu_slot_options_serif_targets); do
                if luoshu_cap_is_variable_slot "$_lsoa_name" && [ -s "$_lsoa_store/serif-variable.font" ]; then
                    _lsoa_anchor="$_lsoa_store/serif-variable.font"
                else
                    _lsoa_anchor="$_lsoa_store/serif-wght-$(luoshu_cap_slot_weight "$_lsoa_name").font"
                fi
                [ -s "$_lsoa_anchor" ] || continue
                if luoshu_slot_options_serif_needs_han "$_lsoa_name" && \
                   ! luoshu_cap_exec covers --script han "$_lsoa_anchor" >/dev/null 2>&1; then
                    _lsoa_kept=$((_lsoa_kept + 1))
                    continue
                fi
                luoshu_slot_options_link "$_lsoa_anchor" "$_lsoa_dest/$_lsoa_name" && _lsoa_count=$((_lsoa_count + 1))
            done
            luoshu_slot_options_log "已写入 $_lsoa_count 个衬线槽位（衬线字体：$_lsoa_serif）"
            [ "$_lsoa_kept" -gt 0 ] && luoshu_slot_options_log "  $_lsoa_kept 个中文衬线槽因所选字体缺少汉字保持原厂"
        else
            luoshu_slot_options_log "衬线字体 $_lsoa_serif 不可用，衬线槽位保持原厂"
        fi
    fi

    _lsoa_emoji=$(luoshu_slot_options_get emoji)
    if [ -n "$_lsoa_emoji" ]; then
        if [ -s "$_lsoa_emoji" ] && luoshu_cap_exec is-color "$_lsoa_emoji" >/dev/null 2>&1; then
            mkdir -p "$_lsoa_store" 2>/dev/null || true
            _lsoa_anchor="$_lsoa_store/emoji.font"
            cp -f "$_lsoa_emoji" "$_lsoa_anchor" 2>/dev/null && chmod 0644 "$_lsoa_anchor" 2>/dev/null
            _lsoa_count=0
            if [ -s "$_lsoa_anchor" ]; then
                for _lsoa_name in $(luoshu_slot_options_emoji_targets); do
                    luoshu_slot_options_link "$_lsoa_anchor" "$_lsoa_dest/$_lsoa_name" && _lsoa_count=$((_lsoa_count + 1))
                done
            fi
            luoshu_slot_options_log "已写入 $_lsoa_count 个 Emoji 槽位"
        else
            luoshu_slot_options_log "所选 Emoji 字体不存在或不是彩色字体，Emoji 保持原厂"
        fi
    fi
    return 0
}

luoshu_slot_options_json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

luoshu_slot_options_cli() {
    _lsoc_action="${1:-status}"
    case "$_lsoc_action" in
        status) ;;
        set-serif)
            [ -n "${2:-}" ] || { printf '{"status":"error","message":"未指定衬线字体"}\n'; return 1; }
            case "$2" in *'/'*|*'..'*) printf '{"status":"error","message":"字体 ID 无效"}\n'; return 1 ;; esac
            luoshu_slot_options_set serif "$2" || { printf '{"status":"error","message":"无法写入设置"}\n'; return 1; } ;;
        clear-serif) luoshu_slot_options_set serif '' ;;
        set-emoji)
            _lsoc_file="${2:-}"
            [ -s "$_lsoc_file" ] || { printf '{"status":"error","message":"Emoji 字体文件不存在"}\n'; return 1; }
            luoshu_cap_exec is-color "$_lsoc_file" >/dev/null 2>&1 || {
                printf '{"status":"error","message":"不是彩色 Emoji 字体（缺少 COLR/CBDT/sbix/SVG 表）"}\n'; return 1; }
            luoshu_slot_options_set emoji "$_lsoc_file" || { printf '{"status":"error","message":"无法写入设置"}\n'; return 1; } ;;
        clear-emoji) luoshu_slot_options_set emoji '' ;;
        *) printf '{"status":"error","message":"未知操作"}\n'; return 1 ;;
    esac
    printf '{"status":"ok","data":{"serif":"%s","emoji":"%s","applyRequired":%s}}\n' \
        "$(luoshu_slot_options_json_escape "$(luoshu_slot_options_get serif)")" \
        "$(luoshu_slot_options_json_escape "$(luoshu_slot_options_get emoji)")" \
        "$([ "$_lsoc_action" = status ] && echo false || echo true)"
}

case "${0##*/}" in
    font_slot_options.sh)
        _lsoc_cap="$(luoshu_slot_options_module)/common/font_capability.sh"
        [ -f "$_lsoc_cap" ] && . "$_lsoc_cap"
        luoshu_slot_options_cli "$@"
        exit $?
        ;;
esac
