#!/system/bin/sh
# App-only compatibility preparation for fonts created by older LuoShu releases.
set +e

MODULE_DIR="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
CONFIG_DIR="${CONFIG_DIR:-$MODULE_DIR/config}"
LUOSHU_PUBLIC_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}"
USER_FONTS_DIR="${USER_FONTS_DIR:-$LUOSHU_PUBLIC_DIR/fonts}"
LEGACY_FONTS_DIR="${LEGACY_FONTS_DIR:-/sdcard/Fonts}"

_app_library_safe_name() {
    _alc_raw=$(basename "$1" | tr -d '\r\n')
    _alc_ext=${_alc_raw##*.}; _alc_stem=${_alc_raw%.*}
    case "$_alc_ext" in TTF) _alc_ext=ttf ;; OTF) _alc_ext=otf ;; TTC) _alc_ext=ttc ;; esac
    _alc_stem=$(printf '%s' "$_alc_stem" | sed 's#[\\/:*?"<>|]#_#g; s/^[. ]*//; s/[. ]*$//' | cut -c1-150)
    [ -n "$_alc_stem" ] || _alc_stem=font
    printf '%s.%s\n' "$_alc_stem" "$_alc_ext"
}

_app_library_find_duplicate() {
    _ald_source="$1"
    for _ald_file in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
                     "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_ald_file" ] || continue
        cmp -s "$_ald_source" "$_ald_file" 2>/dev/null && return 0
    done
    return 1
}

_app_library_copy_one() {
    _al_source="$1"
    [ -f "$_al_source" ] || return 1
    _app_library_find_duplicate "$_al_source" && return 0
    _al_name=$(_app_library_safe_name "$_al_source")
    _al_ext=${_al_name##*.}; _al_stem=${_al_name%.*}; _al_target="$USER_FONTS_DIR/$_al_name"; _al_index=2
    while [ -e "$_al_target" ]; do
        cmp -s "$_al_source" "$_al_target" 2>/dev/null && return 0
        _al_name="${_al_stem}-${_al_index}.${_al_ext}"; _al_target="$USER_FONTS_DIR/$_al_name"; _al_index=$((_al_index + 1))
    done
    cp -f "$_al_source" "$_al_target" 2>/dev/null || return 1
    chmod 0644 "$_al_target" 2>/dev/null || true
    return 0
}

app_prepare_font_library() {
    _apf_mode="${1:-}"
    _apf_marker="$CONFIG_DIR/app_library_compat.done"
    mkdir -p "$USER_FONTS_DIR" "$CONFIG_DIR" 2>/dev/null || return 1
    if [ "$_apf_mode" != refresh ] && [ -f "$_apf_marker" ]; then return 0; fi
    chmod 0775 "$LUOSHU_PUBLIC_DIR" "$USER_FONTS_DIR" 2>/dev/null || true
    find "$USER_FONTS_DIR" -maxdepth 1 -type f -name '.app-import-*' -delete 2>/dev/null || true

    if [ -d "$LEGACY_FONTS_DIR" ] && [ "$LEGACY_FONTS_DIR" != "$USER_FONTS_DIR" ]; then
        while IFS= read -r _apf_file; do
            _app_library_copy_one "$_apf_file" || true
        done <<EOF_LEGACY_FONTS
$(find "$LEGACY_FONTS_DIR" -maxdepth 4 -type f \( -iname '*.ttf' -o -iname '*.otf' -o -iname '*.ttc' \) 2>/dev/null)
EOF_LEGACY_FONTS
    fi

    while IFS= read -r _apf_nested; do
        [ -f "$_apf_nested" ] || continue
        _app_library_copy_one "$_apf_nested" || true
    done <<EOF_NESTED_FONTS
$(find "$USER_FONTS_DIR" -mindepth 2 -maxdepth 4 -type f \( -iname '*.ttf' -o -iname '*.otf' -o -iname '*.ttc' \) 2>/dev/null)
EOF_NESTED_FONTS

    rm -f "$MODULE_DIR/config/webui_font_list.json" "$MODULE_DIR/config/webui_font_list.key" "$MODULE_DIR/config/app_font_index.json" "$MODULE_DIR/config/app_font_index.key" 2>/dev/null || true
    date +%s >"$_apf_marker" 2>/dev/null || touch "$_apf_marker" 2>/dev/null || true
    return 0
}
