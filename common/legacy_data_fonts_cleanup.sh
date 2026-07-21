#!/system/bin/sh
# One-time migration cleanup for files written by pre-no-Hook ColorOS builds.
# Source this file and call luoshu_cleanup_legacy_data_fonts <old-module> [data-font-root].
set +e

_luoshu_legacy_files_equal() {
    _legacy_left="$1"
    _legacy_right="$2"
    [ -f "$_legacy_left" ] && [ -f "$_legacy_right" ] || return 1
    if command -v cmp >/dev/null 2>&1; then
        cmp -s "$_legacy_left" "$_legacy_right"
        return $?
    fi
    if command -v sha256sum >/dev/null 2>&1; then
        _legacy_left_hash=$(sha256sum "$_legacy_left" 2>/dev/null | awk '{print $1}')
        _legacy_right_hash=$(sha256sum "$_legacy_right" 2>/dev/null | awk '{print $1}')
    elif command -v busybox >/dev/null 2>&1; then
        _legacy_left_hash=$(busybox sha256sum "$_legacy_left" 2>/dev/null | awk '{print $1}')
        _legacy_right_hash=$(busybox sha256sum "$_legacy_right" 2>/dev/null | awk '{print $1}')
    else
        return 1
    fi
    [ -n "$_legacy_left_hash" ] && [ "$_legacy_left_hash" = "$_legacy_right_hash" ]
}

luoshu_cleanup_legacy_data_fonts() {
    _legacy_old_module="$1"
    _legacy_data_root="${2:-/data/fonts}"
    _legacy_old_fonts="$_legacy_old_module/system/fonts"
    _legacy_removed=0

    [ -d "$_legacy_old_fonts" ] && [ -d "$_legacy_data_root" ] || {
        printf '0\n'
        return 0
    }
    type get_all_coloros_names >/dev/null 2>&1 || {
        printf '0\n'
        return 0
    }

    for _legacy_name in $(get_all_coloros_names); do
        case "$_legacy_name" in
            ''|*[!A-Za-z0-9._-]*) continue ;;
        esac
        _legacy_source="$_legacy_old_fonts/${_legacy_name}.ttf"
        _legacy_dest="$_legacy_data_root/${_legacy_name}.ttf"
        [ -f "$_legacy_source" ] && [ -f "$_legacy_dest" ] || continue
        if _luoshu_legacy_files_equal "$_legacy_source" "$_legacy_dest"; then
            rm -f "$_legacy_dest" 2>/dev/null && _legacy_removed=$((_legacy_removed + 1))
        fi
    done
    printf '%s\n' "$_legacy_removed"
}
