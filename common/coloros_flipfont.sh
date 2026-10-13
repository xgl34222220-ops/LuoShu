#!/system/bin/sh
# ColorOS / OxygenOS flip-font redirection diagnostic (read-only; no hook, no mount).
#
# OPlus init (system_ext/etc/init/init.oplus.rootdir.rc, OPLUS_FEATURE_FONT_FLIP)
# creates /data/format_unclear/font/OplusOSUI-*.ttf as links back to
# /system/fonts (Roboto-*.ttf, RobotoStatic-Regular.ttf, SysFont-Hans/Hant-*),
# and /system/fonts/SysFont-*.ttf point into that directory. When the system
# font chosen in ColorOS Settings or the Theme Store is applied, the framework
# re-points those entries at its own files. Text drawn through the flip font
# then never reads /system/fonts, so LuoShu's overlay cannot reach it: typical
# symptom "Chinese changed, English and digits still stock" because the Latin
# flip face wins and Han falls back to the (replaced) SysSans-Hans slot.
#
# This file only reports. It never writes /data/format_unclear/font.
#   coloros_flipfont.sh status   -> one JSON object on stdout
#   . coloros_flipfont.sh; luoshu_coloros_flipfont_hint -> Chinese hint lines
set +e

_lcf_init() {
    LCF_DIR="${LUOSHU_COLOROS_FLIP_DIR:-/data/format_unclear/font}"
    LCF_SYSTEM_FONTS="${LUOSHU_COLOROS_FLIP_SYSTEM_FONTS:-/system/fonts}"
    # A ROM placeholder is a few KiB; a real selected font is far larger.
    LCF_MIN_BYTES="${LUOSHU_COLOROS_FLIP_MIN_BYTES:-65536}"
}

_lcf_json_string() {
    printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr -d '\000-\037')"
}

_lcf_size() {
    stat -L -c '%s' "$1" 2>/dev/null || wc -c < "$1" 2>/dev/null | tr -d '[:space:]'
}

# Latin flip faces decide English/digits; Hans/Hant/Myanmar entries do not.
_lcf_latin_entry() {
    case "$1" in *Hans*|*Hant*|*Myanmar*) return 1 ;; esac
    return 0
}

# state|target|bytes
#   system            link into /system/fonts that resolves (overlay reaches it)
#   system-dangling   link into /system/fonts whose file is absent or loops
#   external          link outside /system/fonts that resolves (Settings/Theme font)
#   external-dangling link outside /system/fonts that does not resolve
#   file              regular file >= LCF_MIN_BYTES (a selected font copied to /data)
#   placeholder       small regular file
_lcf_classify() {
    _lcfc_path="$1"
    _lcfc_target=''
    _lcfc_bytes=0
    if [ -L "$_lcfc_path" ]; then
        _lcfc_target=$(readlink "$_lcfc_path" 2>/dev/null)
        case "$_lcfc_target" in
            /system/fonts/*|"$LCF_SYSTEM_FONTS"/*)
                _lcfc_name=${_lcfc_target##*/}
                if [ -e "$_lcfc_path" ] && { [ -e "$LCF_SYSTEM_FONTS/$_lcfc_name" ] || [ -L "$LCF_SYSTEM_FONTS/$_lcfc_name" ]; }; then
                    _lcfc_state=system
                else
                    _lcfc_state=system-dangling
                fi
                ;;
            *)
                if [ -e "$_lcfc_path" ]; then _lcfc_state=external; else _lcfc_state=external-dangling; fi
                ;;
        esac
        [ -e "$_lcfc_path" ] && _lcfc_bytes=$(_lcf_size "$_lcfc_path")
    elif [ -f "$_lcfc_path" ]; then
        _lcfc_bytes=$(_lcf_size "$_lcfc_path")
        case "$_lcfc_bytes" in ''|*[!0-9]*) _lcfc_bytes=0 ;; esac
        if [ "$_lcfc_bytes" -ge "$LCF_MIN_BYTES" ]; then _lcfc_state=file; else _lcfc_state=placeholder; fi
    else
        return 1
    fi
    case "$_lcfc_bytes" in ''|*[!0-9]*) _lcfc_bytes=0 ;; esac
    printf '%s|%s|%s\n' "$_lcfc_state" "$_lcfc_target" "$_lcfc_bytes"
}

# name|state|target|bytes|latin(0/1), one line per OplusOSUI-* / ColorOSUI-* entry.
_lcf_rows() {
    [ -d "$LCF_DIR" ] || return 0
    for _lcfr_path in "$LCF_DIR"/OplusOSUI-* "$LCF_DIR"/ColorOSUI-*; do
        [ -e "$_lcfr_path" ] || [ -L "$_lcfr_path" ] || continue
        _lcfr_name=${_lcfr_path##*/}
        _lcfr_row=$(_lcf_classify "$_lcfr_path") || continue
        _lcfr_latin=0
        _lcf_latin_entry "$_lcfr_name" && _lcfr_latin=1
        printf '%s|%s|%s\n' "$_lcfr_name" "$_lcfr_row" "$_lcfr_latin"
    done
}

# Number of Latin flip entries the /system overlay cannot reach.
_lcf_redirected_count() {
    printf '%s\n' "$1" | awk -F'|' '$5 == 1 && ($2 == "external" || $2 == "file") { n++ } END { print n + 0 }'
}

luoshu_coloros_flipfont_status() {
    _lcf_init
    _lcfs_rows=$(_lcf_rows)
    _lcfs_present=false
    [ -d "$LCF_DIR" ] && _lcfs_present=true
    _lcfs_redirected=$(_lcf_redirected_count "$_lcfs_rows")
    _lcfs_verdict=ok
    [ "$_lcfs_present" = true ] || _lcfs_verdict=absent
    [ "$_lcfs_redirected" -eq 0 ] || _lcfs_verdict=redirected
    printf '{"schema":"luoshu-coloros-flipfont-v1","dir":%s,"present":%s,"verdict":"%s","latinRedirected":%s,"entries":[' \
        "$(_lcf_json_string "$LCF_DIR")" "$_lcfs_present" "$_lcfs_verdict" "$_lcfs_redirected"
    _lcfs_first=1
    while IFS='|' read -r _lcfs_name _lcfs_state _lcfs_target _lcfs_bytes _lcfs_latin; do
        [ -n "$_lcfs_name" ] || continue
        [ "$_lcfs_first" = 1 ] || printf ','
        _lcfs_first=0
        printf '{"name":%s,"state":"%s","target":%s,"bytes":%s,"latin":%s}' \
            "$(_lcf_json_string "$_lcfs_name")" "$_lcfs_state" "$(_lcf_json_string "$_lcfs_target")" \
            "${_lcfs_bytes:-0}" "$([ "$_lcfs_latin" = 1 ] && echo true || echo false)"
    done <<EOF_LCF_ROWS
$_lcfs_rows
EOF_LCF_ROWS
    printf ']}\n'
}

# Chinese hint lines for the switch log; silent when nothing is redirected.
# Also stores the JSON next to the switch log for exported diagnostics.
luoshu_coloros_flipfont_hint() {
    _lcf_init
    _lcfh_module="${LUOSHU_REAL_MODDIR:-${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}}"
    _lcfh_report="${LUOSHU_COLOROS_FLIP_REPORT:-$_lcfh_module/logs/coloros_flipfont.json}"
    _lcfh_json=$(luoshu_coloros_flipfont_status)
    if mkdir -p "${_lcfh_report%/*}" 2>/dev/null; then
        printf '%s\n' "$_lcfh_json" > "$_lcfh_report.tmp.$$" 2>/dev/null && \
            mv -f "$_lcfh_report.tmp.$$" "$_lcfh_report" 2>/dev/null
        rm -f "$_lcfh_report.tmp.$$" 2>/dev/null
    fi
    _lcfh_rows=$(_lcf_rows)
    _lcfh_count=$(_lcf_redirected_count "$_lcfh_rows")
    [ "$_lcfh_count" -gt 0 ] || return 0
    _lcfh_names=$(printf '%s\n' "$_lcfh_rows" | awk -F'|' '$5 == 1 && ($2 == "external" || $2 == "file") { printf "%s%s", sep, $1; sep = "、" }')
    printf '%s\n' "⚠ ColorOS 系统字体设置/主题字体已接管 $_lcfh_count 个英文数字 flip 字体（$_lcfh_names），它们不在 /system/fonts，洛书无法覆盖"
    printf '%s\n' "  症状：部分应用中文已换、英文和数字仍是原字体。请在 设置→字体 改回系统自带字体（不使用主题商店字体）后重启，再重新应用洛书"
    return 0
}

if [ "${0##*/}" = coloros_flipfont.sh ]; then
    case "${1:-status}" in
        status) luoshu_coloros_flipfont_status ;;
        hint) luoshu_coloros_flipfont_hint ;;
        *) echo 'usage: coloros_flipfont.sh status|hint' >&2; exit 2 ;;
    esac
fi
