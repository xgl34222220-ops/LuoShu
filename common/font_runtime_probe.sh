#!/system/bin/sh
# 洛书字体运行时探测：收集当前机型实际字体配置、GMS 提供器和目标 App 内置字体。
set +e

MODDIR="${MODDIR:-${0%/*}/..}"
REPORT="${LUOSHU_FONT_PROBE_REPORT:-$MODDIR/logs/font-runtime-probe.txt}"
PM_BIN="${LUOSHU_PM:-pm}"
CMD_BIN="${LUOSHU_CMD:-cmd}"

mkdir -p "${REPORT%/*}" 2>/dev/null || true

_prop() {
    printf '%s=%s\n' "$1" "$(getprop "$1" 2>/dev/null)"
}

_list_users() {
    {
        "$CMD_BIN" user list 2>/dev/null | sed -n 's/.*UserInfo{\([0-9][0-9]*\):.*/\1/p'
        for _dir in /data/user/[0-9]*; do [ -d "$_dir" ] && basename "$_dir"; done
        printf '0\n'
    } | awk '/^[0-9]+$/ && !seen[$0]++ { print $0 }'
}

_component_state() {
    "$PM_BIN" get-component-enabled-setting --user "$1" "$2" 2>/dev/null | tail -n1 | tr -d '\r'
}

_dump_font_dir() {
    _dir="$1"
    [ -d "$_dir" ] || return 0
    printf '\n[%s]\n' "$_dir"
    find "$_dir" -maxdepth 1 -type f \( -iname '*.ttf' -o -iname '*.otf' -o -iname '*.ttc' \) \
        -printf '%f|%s\n' 2>/dev/null | sort
}

_dump_config() {
    _file="$1"
    [ -f "$_file" ] || return 0
    printf '\n[%s]\n' "$_file"
    sed -nE 's/.*<font[^>]*weight="?([0-9]+)"?[^>]*>([^<]+)<.*/weight=\1 file=\2/p; s/.*<family[^>]*name="([^"]+)".*/family=\1/p; s/.*<alias[^>]*name="([^"]+)"[^>]*to="([^"]+)".*/alias=\1 to=\2/p' "$_file" 2>/dev/null | head -n 800
}

_dump_apk_fonts() {
    _pkg="$1"
    printf '\n[%s APK fonts]\n' "$_pkg"
    _found=0
    "$PM_BIN" path "$_pkg" 2>/dev/null | sed 's/^package://' | while IFS= read -r _apk; do
        [ -f "$_apk" ] || continue
        printf 'apk=%s\n' "$_apk"
        if command -v unzip >/dev/null 2>&1; then
            unzip -Z1 "$_apk" 2>/dev/null | grep -Ei '(^|/)(res/font|assets?/fonts?|fonts?)/|\.(ttf|otf|ttc)$' | head -n 300
        fi
        _found=1
    done
    [ "$_found" -eq 1 ] 2>/dev/null || true
}

{
    printf '# LuoShu font runtime probe\n'
    printf 'time=%s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)"
    for _key in \
        ro.product.manufacturer ro.product.brand ro.product.model ro.product.device \
        ro.build.version.release ro.build.version.sdk ro.build.display.id \
        ro.mi.os.version.name ro.miui.ui.version.code; do
        _prop "$_key"
    done

    printf '\n# GMS downloadable font provider\n'
    printf 'gmsPath=%s\n' "$($PM_BIN path com.google.android.gms 2>/dev/null | tr '\n' ',')"
    for _user in $(_list_users); do
        printf 'user=%s provider=%s updater=%s\n' \
            "$_user" \
            "$(_component_state "$_user" 'com.google.android.gms/com.google.android.gms.fonts.provider.FontsProvider')" \
            "$(_component_state "$_user" 'com.google.android.gms/com.google.android.gms.fonts.update.UpdateSchedulerService')"
    done

    printf '\n# Font configuration\n'
    for _xml in \
        /system/etc/fonts.xml /system/etc/font_fallback.xml \
        /product/etc/fonts_customization.xml /product/etc/fonts.xml \
        /system_ext/etc/fonts_customization.xml /system_ext/etc/fonts.xml \
        /vendor/etc/fonts_customization.xml /vendor/etc/fonts.xml \
        /my_product/etc/fonts_customization.xml /my_product/etc/fonts.xml; do
        _dump_config "$_xml"
    done

    printf '\n# Physical font files\n'
    for _dir in /system/fonts /product/fonts /system_ext/fonts /vendor/fonts /my_product/fonts /data/fonts/files /data/system/theme/fonts; do
        _dump_font_dir "$_dir"
    done

    _dump_apk_fonts com.android.vending
    _dump_apk_fonts com.android.deskclock
    _dump_apk_fonts com.miui.clock
} > "$REPORT" 2>&1

chmod 0644 "$REPORT" 2>/dev/null || true
printf '%s\n' "$REPORT"
