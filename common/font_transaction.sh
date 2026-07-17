#!/system/bin/sh
# 洛书 v14.1：字体目录事务。先在临时目录完整生成，验证通过后再替换正式目录。
set +e

luoshu_txn_begin() {
    _name="${1:-font}"
    LUOSHU_TXN_ROOT="$MODDIR/.font-transaction/${_name}-$(date +%s)-$$"
    LUOSHU_TXN_FONTS="$LUOSHU_TXN_ROOT/system/fonts"
    rm -rf "$LUOSHU_TXN_ROOT" 2>/dev/null || true
    mkdir -p "$LUOSHU_TXN_FONTS" 2>/dev/null || return 1
    chmod 0755 "$LUOSHU_TXN_ROOT" "$LUOSHU_TXN_ROOT/system" "$LUOSHU_TXN_FONTS" 2>/dev/null || true
    export LUOSHU_TXN_ROOT LUOSHU_TXN_FONTS
}

luoshu_txn_abort() {
    [ -n "${LUOSHU_TXN_ROOT:-}" ] && rm -rf "$LUOSHU_TXN_ROOT" 2>/dev/null || true
}

luoshu_txn_verify() {
    _mode="${1:-font}"
    _count=0
    for _font in "$LUOSHU_TXN_FONTS"/*.ttf "$LUOSHU_TXN_FONTS"/*.otf "$LUOSHU_TXN_FONTS"/*.ttc; do
        [ -f "$_font" ] || continue
        _count=$((_count + 1))
        _size=$(wc -c < "$_font" 2>/dev/null | tr -d '[:space:]')
        case "$_size" in ''|*[!0-9]*) _size=0 ;; esac
        [ "$_size" -ge 4096 ] || { echo "错误：事务字体 $(basename "$_font") 文件异常" >&2; return 1; }
        if type font_validate >/dev/null 2>&1; then
            font_validate "$_font" text >/dev/null 2>&1 || { echo "错误：事务字体 $(basename "$_font") 校验失败" >&2; return 1; }
        fi
    done
    [ "$_mode" = default ] && return 0
    [ "$_count" -gt 0 ] || { echo '错误：事务目录没有生成字体文件' >&2; return 1; }
    return 0
}

_luoshu_replace_dir() {
    _new="$1"; _target="$2"; _backup="${_target}.previous.$$"
    mkdir -p "${_target%/*}" 2>/dev/null || return 1
    rm -rf "$_backup" 2>/dev/null || true
    if [ -e "$_target" ] || [ -L "$_target" ]; then
        mv "$_target" "$_backup" 2>/dev/null || return 1
    fi
    if mv "$_new" "$_target" 2>/dev/null; then
        rm -rf "$_backup" 2>/dev/null || true
        chmod 0755 "$_target" 2>/dev/null || true
        find "$_target" -type f -exec chmod 0644 {} \; 2>/dev/null || true
        return 0
    fi
    rm -rf "$_target" 2>/dev/null || true
    [ ! -e "$_backup" ] || mv "$_backup" "$_target" 2>/dev/null || true
    return 1
}

luoshu_txn_commit() {
    _target="$MODDIR/system/fonts"
    _new="$LUOSHU_TXN_FONTS"
    _luoshu_replace_dir "$_new" "$_target" || { luoshu_txn_abort; return 1; }
    rm -rf "$LUOSHU_TXN_ROOT" 2>/dev/null || true
    rm -rf "$MODDIR/system/fonts/.luoshu-emoji-store" 2>/dev/null || true
    rm -f "$MODDIR/system/fonts/NotoColorEmoji.ttf" "$MODDIR/system/fonts/NotoColorEmojiLegacy.ttf" 2>/dev/null || true
    return 0
}

luoshu_txn_cleanup_stale() {
    _root="$MODDIR/.font-transaction"
    [ -d "$_root" ] || return 0
    find "$_root" -mindepth 1 -maxdepth 1 -type d -mmin +10 -exec rm -rf {} \; 2>/dev/null || true
}
