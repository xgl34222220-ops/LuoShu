#!/system/bin/sh
# 洛书 v14.1 测试版 3：按需字体预览缓存与存储明细。
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
    else
        MODDIR="/data/adb/modules/LuoShu"
    fi
fi
MODULE_DIR="$MODDIR"
CONFIG_DIR="$MODDIR/config"
USER_FONTS_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts"
WEBROOT_NAME=$(sed -n 's/^webroot=//p' "$MODDIR/module.prop" 2>/dev/null | head -n1 | tr -d '\r\n')
[ -n "$WEBROOT_NAME" ] || WEBROOT_NAME=webroot
ACTIVE_WEBROOT="$MODDIR/$WEBROOT_NAME"
PREVIEW_DIR="$ACTIVE_WEBROOT/fonts"
MANIFEST="$CONFIG_DIR/preview_cache.conf"
MAX_FAMILIES=3

[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
if ! type detect_font_family >/dev/null 2>&1; then
    detect_font_family(){ _n="${1%.*}"; printf '%s\n' "${_n%-*}"; }
fi
if ! type detect_font_weight >/dev/null 2>&1; then
    detect_font_weight(){ case "$1" in *[Bb]old*) echo bold;; *[Mm]edium*) echo medium;; *[Ll]ight*) echo light;; *[Tt]hin*) echo thin;; *) echo regular;; esac; }
fi

json_escape(){ printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '; }
file_bytes(){ _v=$(wc -c < "$1" 2>/dev/null | tr -d '[:space:]'); case "$_v" in ''|*[!0-9]*) _v=0;; esac; printf '%s' "$_v"; }
fmt_bytes(){
    _n="$1"; case "$_n" in ''|*[!0-9]*) _n=0;; esac
    if [ "$_n" -ge 1073741824 ] 2>/dev/null; then printf '%d.%d GB' $((_n/1073741824)) $(((_n%1073741824)/107374182));
    elif [ "$_n" -ge 1048576 ] 2>/dev/null; then printf '%d.%d MB' $((_n/1048576)) $(((_n%1048576)/104857));
    elif [ "$_n" -ge 1024 ] 2>/dev/null; then printf '%d KB' $((_n/1024)); else printf '%d B' "$_n"; fi
}
family_key(){ printf '%s' "$1" | cksum 2>/dev/null | awk '{print $1}'; }
find_family_main(){
    _want="$1"; _preferred="$2"
    if [ -f "$_preferred" ] && [ "$(detect_font_family "$(basename "$_preferred")")" = "$_want" ]; then printf '%s\n' "$_preferred"; return 0; fi
    _fallback=""
    for _f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
              "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_f" ] || continue
        [ "$(detect_font_family "$(basename "$_f")")" = "$_want" ] || continue
        _w=$(detect_font_weight "$(basename "$_f")")
        [ "$_w" = regular ] && { printf '%s\n' "$_f"; return 0; }
        [ -n "$_fallback" ] || _fallback="$_f"
    done
    [ -n "$_fallback" ] && { printf '%s\n' "$_fallback"; return 0; }
    return 1
}

cleanup_legacy(){
    mkdir -p "$PREVIEW_DIR" "$CONFIG_DIR" 2>/dev/null || true
    for _old_root in webroot webroot_v141; do
        [ "$MODDIR/$_old_root" = "$ACTIVE_WEBROOT" ] && continue
        rm -rf "$MODDIR/$_old_root/fonts" 2>/dev/null || true
    done
    rm -rf "$PREVIEW_DIR/.tmp" 2>/dev/null || true
}

remove_key_files(){
    _key="$1"
    for _f in "$PREVIEW_DIR/${_key}--"*; do [ -e "$_f" ] && rm -f "$_f" 2>/dev/null || true; done
}

prune_manifest(){
    [ -s "$MANIFEST" ] || return 0
    _tmp="$MANIFEST.tmp.$$"
    sort -t'|' -k3,3nr "$MANIFEST" 2>/dev/null | awk -F'|' '!seen[$1]++' > "$_tmp" 2>/dev/null || cp -f "$MANIFEST" "$_tmp"
    _keep="$MANIFEST.keep.$$"; : > "$_keep"
    _i=0
    while IFS='|' read -r _key _family _time _main; do
        [ -n "$_key" ] || continue
        _i=$((_i+1))
        if [ "$_i" -le "$MAX_FAMILIES" ]; then
            printf '%s|%s|%s|%s\n' "$_key" "$_family" "$_time" "$_main" >> "$_keep"
        else
            remove_key_files "$_key"
        fi
    done < "$_tmp"
    mv -f "$_keep" "$MANIFEST" 2>/dev/null || true
    rm -f "$_tmp" 2>/dev/null || true
}

prepare_family(){
    _family="$1"; _preferred="$2"
    [ -n "$_family" ] || { printf '{"status":"error","message":"未指定字体"}\n'; return 1; }
    cleanup_legacy
    _main=$(find_family_main "$_family" "$_preferred")
    [ -f "$_main" ] || { printf '{"status":"error","message":"找不到字体文件"}\n'; return 1; }
    _key=$(family_key "$_family"); [ -n "$_key" ] || _key=font
    remove_key_files "$_key"
    _variants=""; _main_url=""; _main_name=""
    for _src in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
                "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_src" ] || continue
        [ "$(detect_font_family "$(basename "$_src")")" = "$_family" ] || continue
        _base=$(basename "$_src")
        _dest_name="${_key}--${_base}"
        _dest="$PREVIEW_DIR/$_dest_name"
        cp -f "$_src" "$_dest.tmp.$$" 2>/dev/null && mv -f "$_dest.tmp.$$" "$_dest" 2>/dev/null || { rm -f "$_dest.tmp.$$"; continue; }
        chmod 0644 "$_dest" 2>/dev/null || true
        _role=$(detect_font_weight "$_base")
        [ -n "$_variants" ] && _variants="$_variants,"
        _variants="$_variants\"$(json_escape "$_role")\":\"./fonts/$(json_escape "$_dest_name")\""
        if [ "$_src" = "$_main" ] || [ -z "$_main_url" ]; then _main_url="./fonts/$_dest_name"; _main_name="$_dest_name"; fi
    done
    [ -n "$_main_url" ] || { printf '{"status":"error","message":"预览缓存生成失败"}\n'; return 1; }
    _now=$(date +%s)
    _tmp="$MANIFEST.tmp.$$"
    { [ ! -f "$MANIFEST" ] || awk -F'|' -v k="$_key" '$1!=k' "$MANIFEST"; printf '%s|%s|%s|%s\n' "$_key" "$_family" "$_now" "$_main_name"; } > "$_tmp"
    mv -f "$_tmp" "$MANIFEST" 2>/dev/null || true
    PC_RESULT_FAMILY="$_family"; PC_RESULT_MAIN="$_main"; PC_RESULT_URL="$_main_url"; PC_RESULT_VARIANTS="$_variants"; PC_RESULT_BYTES=$(file_bytes "$_main")
    prune_manifest
    printf '{"status":"ok","data":{"family":"%s","source":"%s","file":"%s","variants":{%s},"bytes":%s}}\n' \
        "$(json_escape "$PC_RESULT_FAMILY")" "$(json_escape "$PC_RESULT_MAIN")" "$(json_escape "$PC_RESULT_URL")" "$PC_RESULT_VARIANTS" "$PC_RESULT_BYTES"
}

sum_apparent(){
    _root="$1"; _sum=0
    [ -d "$_root" ] || { echo 0; return; }
    find "$_root" -type f 2>/dev/null | while IFS= read -r _f; do printf '%s\n' "$(file_bytes "$_f")"; done | awk '{s+=$1} END{printf "%.0f\n",s+0}'
}
du_bytes(){ _k=$(du -sk "$1" 2>/dev/null | awk 'NR==1{print $1}'); case "$_k" in ''|*[!0-9]*) _k=0;; esac; echo $((_k*1024)); }
storage_json(){
    cleanup_legacy
    _actual=$(du_bytes "$MODDIR")
    _apparent=$(sum_apparent "$MODDIR")
    _font=$(du_bytes "$MODDIR/system/fonts")
    _preview=$(du_bytes "$PREVIEW_DIR")
    _logs=$(du_bytes "$MODDIR/logs")
    _txn=$(du_bytes "$MODDIR/.font-transaction")
    _secondary=$(( $(du_bytes "$MODDIR/system_ext/fonts") + $(du_bytes "$MODDIR/product/fonts") ))
    _legacy=$(du_bytes "$MODDIR/webroot/fonts")
    printf '{"status":"ok","data":{"actualBytes":%s,"actual":"%s","apparentBytes":%s,"apparent":"%s","fontBytes":%s,"font":"%s","previewBytes":%s,"preview":"%s","secondaryBytes":%s,"secondary":"%s","logsBytes":%s,"logs":"%s","transactionBytes":%s,"transaction":"%s","legacyPreviewBytes":%s,"legacyPreview":"%s"}}\n' \
        "$_actual" "$(fmt_bytes "$_actual")" "$_apparent" "$(fmt_bytes "$_apparent")" "$_font" "$(fmt_bytes "$_font")" "$_preview" "$(fmt_bytes "$_preview")" "$_secondary" "$(fmt_bytes "$_secondary")" "$_logs" "$(fmt_bytes "$_logs")" "$_txn" "$(fmt_bytes "$_txn")" "$_legacy" "$(fmt_bytes "$_legacy")"
}

case "${1:-cleanup}" in
    prepare) prepare_family "$2" "$3" ;;
    prune) cleanup_legacy; prune_manifest; printf '{"status":"ok"}\n' ;;
    cleanup) cleanup_legacy; rm -rf "$PREVIEW_DIR" 2>/dev/null || true; mkdir -p "$PREVIEW_DIR"; rm -f "$MANIFEST"; printf '{"status":"ok"}\n' ;;
    storage) storage_json ;;
    *) printf '{"status":"error","message":"未知预览缓存命令"}\n' ;;
esac
exit 0
