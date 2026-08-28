#!/system/bin/sh
# HyperOS 3 full physical UI coverage for the safe v14.4 runtime.
# Source the proven compatibility layer, then broaden only its target discovery.
set +e

_hfc_dir="${0%/*}"
_hfc_base="$_hfc_dir/hyperos_clock_compat.sh"
[ -f "$_hfc_base" ] && . "$_hfc_base"

# Replace only upright UI/clock/typeface aliases. Keep language-specific, emoji,
# symbol, icon, serif and italic resources on the ROM to avoid missing-glyph crashes.
_lhcc_safe_dynamic_name() {
    _lhcc_name="$1"
    _lhcc_lower=$(printf '%s' "$_lhcc_name" | tr '[:upper:]' '[:lower:]')
    case "$_lhcc_lower" in
        *italic*|*oblique*|*emoji*|*symbol*|*icon*|*serif*) return 1 ;;
        *arabic*|*hebrew*|*thai*|*devanagari*|*bengali*|*tamil*|*telugu*|*malayalam*|\
        *gujarati*|*gurmukhi*|*kannada*|*khmer*|*lao*|*tibetan*|*myanmar*|\
        *japanese*|*korean*|*hangul*|*hiragana*|*katakana*) return 1 ;;
    esac
    case "$_lhcc_name" in
        MiSans*.ttf|MiSans*.otf|MiSans*.ttc|\
        XiaomiSans*.ttf|XiaomiSans*.otf|XiaomiSans*.ttc|\
        MiLanPro*.ttf|MiLanPro*.otf|MiLanPro*.ttc|\
        Mitype*.ttf|Mitype*.otf|Mitype*.ttc|\
        MiClock*.ttf|MiClock*.otf|MiClock*.ttc|\
        AndroidClock*.ttf|AndroidClock*.otf|AndroidClock*.ttc|Clockopia.ttf|\
        Roboto*.ttf|Roboto*.otf|Roboto*.ttc|\
        GoogleSans*.ttf|GoogleSans*.otf|GoogleSans*.ttc|\
        NotoSans*.ttf|NotoSans*.otf|NotoSans*.ttc|\
        SourceSansPro*.ttf|SourceSansPro*.otf|SourceSansPro*.ttc|DroidSans*.ttf|\
        100.ttf|200.ttf|300.ttf|350.ttf|400.ttf|500.ttf|600.ttf|700.ttf|800.ttf|900.ttf)
            return 0
            ;;
    esac
    return 1
}

_lhcc_names_for_root() {
    _lhcc_real="$1"
    {
        _lhcc_static_names
        [ -d "$_lhcc_real" ] || exit 0
        for _lhcc_path in "$_lhcc_real"/*; do
            [ -f "$_lhcc_path" ] || continue
            _lhcc_name=${_lhcc_path##*/}
            case "$_lhcc_name" in *.ttf|*.otf|*.ttc) ;; *) continue ;; esac
            _lhcc_safe_dynamic_name "$_lhcc_name" || continue
            printf '%s\n' "$_lhcc_name"
        done
    } | awk 'NF && !seen[$0]++'
}

luoshu_hyperos_full_payload_ensure() {
    type luoshu_hyperos_clock_payload_ensure >/dev/null 2>&1 || return 0
    luoshu_hyperos_clock_payload_ensure "$@"
}

# Keep the compatibility API used by existing routers, now backed by full discovery.
luoshu_hyperos_legacy_payload_ensure() {
    luoshu_hyperos_full_payload_ensure "$@"
}