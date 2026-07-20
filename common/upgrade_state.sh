#!/system/bin/sh
# 洛书模块升级状态迁移。
# 仅继承用户偏好和当前文字字体负载，不继承任务、锁、Emoji、图标或系统 XML。
set +e

LUOSHU_UPGRADE_ACTIVE_FONT="default"
LUOSHU_UPGRADE_PAYLOAD_COUNT=0

_luoshu_copy_upgrade_config() {
    _old="$1"
    _new="$2"
    _name="$3"
    [ -f "$_old/config/$_name" ] || return 0
    mkdir -p "$_new/config" 2>/dev/null || return 1
    cp -f "$_old/config/$_name" "$_new/config/$_name" 2>/dev/null
}

_luoshu_safe_text_payload() {
    _name=$(basename "$1" | tr '[:upper:]' '[:lower:]')
    case "$_name" in
        *emoji*|*symbol*|*icon*|*misymbol*|androidclock*|*monospace*|*robotomono*|*notoserif*)
            return 1
            ;;
    esac
    case "$_name" in
        *.ttf|*.otf|*.ttc|*.font) return 0 ;;
        *) return 1 ;;
    esac
}

_luoshu_copy_payload_tree() {
    _old="$1"
    _new="$2"
    _relative="$3"
    _source="$_old/$_relative"
    _target="$_new/$_relative"
    [ -d "$_source" ] || return 0

    find "$_source" -type f 2>/dev/null | while IFS= read -r _file; do
        _luoshu_safe_text_payload "$_file" || continue
        _tail=${_file#"$_source"/}
        [ "$_tail" != "$_file" ] || continue
        mkdir -p "$_target/${_tail%/*}" 2>/dev/null || continue
        cp -f "$_file" "$_target/$_tail" 2>/dev/null || continue
        printf '.\n'
    done
}

luoshu_migrate_upgrade_state() {
    _old="$1"
    _new="$2"
    LUOSHU_UPGRADE_ACTIVE_FONT="default"
    LUOSHU_UPGRADE_PAYLOAD_COUNT=0

    [ -d "$_old" ] || return 1
    [ -f "$_old/module.prop" ] || return 1
    mkdir -p "$_new/config" 2>/dev/null || return 1

    for _config in \
        active_font.conf recent_fonts.conf \
        font_weight.conf font_weight_original.conf \
        axes_mix.conf font_mix.conf; do
        _luoshu_copy_upgrade_config "$_old" "$_new" "$_config" || true
    done

    _active=$(head -n1 "$_old/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_active" ] || _active="default"
    # 字体族名称允许中文、空格和常规符号；这里只拒绝空值与路径分隔符，
    # 避免把配置值误当作文件路径，同时保持 POSIX sh / Android Toybox 兼容。
    case "$_active" in
        ''|*/*|*\\*) _active="default" ;;
    esac

    if [ "$_active" != "default" ]; then
        _count=0
        for _tree in system/fonts product/fonts system_ext/fonts vendor/fonts my_product/fonts; do
            _copied=$(_luoshu_copy_payload_tree "$_old" "$_new" "$_tree" | wc -l 2>/dev/null | tr -d '[:space:]')
            case "$_copied" in ''|*[!0-9]*) _copied=0 ;; esac
            _count=$((_count + _copied))
        done
        LUOSHU_UPGRADE_PAYLOAD_COUNT=$_count
        if [ "$_count" -gt 0 ]; then
            LUOSHU_UPGRADE_ACTIVE_FONT="$_active"
        else
            LUOSHU_UPGRADE_ACTIVE_FONT="default"
        fi
    fi

    printf '%s\n' "$LUOSHU_UPGRADE_ACTIVE_FONT" > "$_new/config/active_font.conf"
    chmod 0644 "$_new/config"/*.conf 2>/dev/null || true
    return 0
}
