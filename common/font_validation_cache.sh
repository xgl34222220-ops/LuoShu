#!/system/bin/sh
# LuoShu validated-font cache.
# A full global-font validation result may be reused only while the exact source file identity is
# unchanged. Replacing, rewriting or touching the font invalidates the entry and runs the full gate.
set +e

luoshu_font_validation_cache_path() {
    _lfvcp_module="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
    printf '%s/config/font-validation-cache.conf\n' "$_lfvcp_module"
}

luoshu_font_validation_identity() {
    _lfvi_file="$1"
    if command -v stat >/dev/null 2>&1; then
        stat -c '%d:%i:%s:%Y:%Z' "$_lfvi_file" 2>/dev/null && return 0
    fi
    if command -v toybox >/dev/null 2>&1; then
        toybox stat -c '%d:%i:%s:%Y:%Z' "$_lfvi_file" 2>/dev/null && return 0
    fi
    return 1
}

luoshu_font_validation_read() {
    _lfvr_key="$1"
    _lfvr_cache="$(luoshu_font_validation_cache_path)"
    sed -n "s/^${_lfvr_key}=//p" "$_lfvr_cache" 2>/dev/null | head -n1 | tr -d '\r\n'
}

luoshu_font_validation_cache_restore() {
    _lfvcr_file="$1"
    _lfvcr_cache="$(luoshu_font_validation_cache_path)"
    [ -s "$_lfvcr_cache" ] || return 1
    [ "$(luoshu_font_validation_read valid)" = true ] || return 1
    [ "$(luoshu_font_validation_read path)" = "$_lfvcr_file" ] || return 1
    _lfvcr_now="$(luoshu_font_validation_identity "$_lfvcr_file")" || return 1
    [ -n "$_lfvcr_now" ] && [ "$_lfvcr_now" = "$(luoshu_font_validation_read identity)" ] || return 1

    FONT_CHECK_FORMAT="$(luoshu_font_validation_read format)"
    FONT_CHECK_SIZE="$(luoshu_font_validation_read bytes)"
    FONT_CHECK_VARIABLE="$(luoshu_font_validation_read variable)"
    FONT_CHECK_COLOR="$(luoshu_font_validation_read color)"
    FONT_CHECK_WARNING="$(luoshu_font_validation_read warning)"
    FONT_CHECK_COVERAGE="$(luoshu_font_validation_read coverage)"
    FONT_CHECK_ERROR=''
    LUOSHU_FONT_VALIDATION_CACHE_HIT=true
    export LUOSHU_FONT_VALIDATION_CACHE_HIT
    return 0
}

luoshu_font_validation_cache_store() {
    _lfvcs_file="$1"
    _lfvcs_identity="$(luoshu_font_validation_identity "$_lfvcs_file")" || return 1
    _lfvcs_cache="$(luoshu_font_validation_cache_path)"
    _lfvcs_tmp="${_lfvcs_cache}.tmp.$$"
    mkdir -p "${_lfvcs_cache%/*}" 2>/dev/null || return 1
    {
        printf 'valid=true\n'
        printf 'path=%s\n' "$(printf '%s' "$_lfvcs_file" | tr '\n\r' '  ')"
        printf 'identity=%s\n' "$_lfvcs_identity"
        printf 'format=%s\n' "${FONT_CHECK_FORMAT:-UNKNOWN}"
        printf 'bytes=%s\n' "${FONT_CHECK_SIZE:-0}"
        printf 'variable=%s\n' "${FONT_CHECK_VARIABLE:-false}"
        printf 'color=%s\n' "${FONT_CHECK_COLOR:-false}"
        printf 'warning=%s\n' "$(printf '%s' "${FONT_CHECK_WARNING:-}" | tr '\n\r' '  ')"
        printf 'coverage=%s\n' "$(printf '%s' "${FONT_CHECK_COVERAGE:-}" | tr '\n\r' '  ')"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_lfvcs_tmp" 2>/dev/null || return 1
    mv -f "$_lfvcs_tmp" "$_lfvcs_cache" 2>/dev/null || return 1
    chmod 0644 "$_lfvcs_cache" 2>/dev/null || true
}

luoshu_font_validate_global_cached() {
    _lfvgc_file="$1"
    LUOSHU_FONT_VALIDATION_CACHE_HIT=false
    export LUOSHU_FONT_VALIDATION_CACHE_HIT
    if luoshu_font_validation_cache_restore "$_lfvgc_file"; then
        return 0
    fi
    type font_validate_global >/dev/null 2>&1 || return 127
    font_validate_global "$_lfvgc_file" || return $?
    luoshu_font_validation_cache_store "$_lfvgc_file" >/dev/null 2>&1 || true
    return 0
}
