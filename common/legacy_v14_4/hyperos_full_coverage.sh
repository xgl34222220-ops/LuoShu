#!/system/bin/sh
# HyperOS 3 full physical UI coverage for the safe compatibility runtime.
# Source the proven compatibility layer, then broaden only its target discovery.
set +e

_hfc_dir="${0%/*}"
_hfc_base="$_hfc_dir/hyperos_clock_compat.sh"
[ -f "$_hfc_base" ] && . "$_hfc_base"

# Replace only upright, single-font TTF/OTF UI/clock/typeface aliases. TTC files can
# carry multiple faces/index contracts; replacing those with one arbitrary font file
# is unsafe, so they remain on the ROM unless a future per-device builder proves the
# face layout explicitly. Language-specific, emoji, symbol, icon, serif and italic
# resources also stay untouched to avoid missing-glyph/native parsing regressions.
_lhcc_safe_dynamic_name() {
    _lhcc_name="$1"
    _lhcc_lower=$(printf '%s' "$_lhcc_name" | tr '[:upper:]' '[:lower:]')
    case "$_lhcc_lower" in
        *italic*|*oblique*|*emoji*|*symbol*|*icon*|*serif*) return 1 ;;
        *arabic*|*hebrew*|*thai*|*devanagari*|*bengali*|*tamil*|*telugu*|*malayalam*|\
        *gujarati*|*gurmukhi*|*kannada*|*khmer*|*lao*|*tibetan*|*myanmar*|*vietnam*|\
        *japanese*|*korean*|*hangul*|*hiragana*|*katakana*) return 1 ;;
    esac
    case "$_lhcc_name" in
        MiSansJP*|MiSansJp*|MiSansKR*|MiSansKr*|*CJKJP*|*CJKKR*) return 1 ;;
        MiSans*.ttf|MiSans*.otf|\
        XiaomiSans*.ttf|XiaomiSans*.otf|\
        MiLanPro*.ttf|MiLanPro*.otf|\
        Mitype*.ttf|Mitype*.otf|\
        MiClock*.ttf|MiClock*.otf|\
        AndroidClock*.ttf|AndroidClock*.otf|Clockopia.ttf|\
        Roboto*.ttf|Roboto*.otf|\
        GoogleSans*.ttf|GoogleSans*.otf|\
        NotoSans*.ttf|NotoSans*.otf|\
        SourceSansPro*.ttf|SourceSansPro*.otf|DroidSans*.ttf|\
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
            case "$_lhcc_name" in *.ttf|*.otf) ;; *) continue ;; esac
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