#!/system/bin/sh
# 洛书字体库轻量指纹与缓存辅助。
# 只读取文件名、大小和修改时间，不解析字体轮廓，可用于 App 后台快速判断是否需要重建索引。

font_library_fingerprint_value() {
    _font_dir="${USER_FONTS_DIR:-/sdcard/LuoShu/fonts}"
    _config_dir="${CONFIG_DIR:-/data/adb/modules/LuoShu/config}"
    mkdir -p "$_config_dir" 2>/dev/null || true
    _tmp="$_config_dir/.font-fingerprint.$$"
    : > "$_tmp" 2>/dev/null || return 1
    _count=0
    _bytes=0

    for _font_file in "$_font_dir"/*.ttf "$_font_dir"/*.otf "$_font_dir"/*.ttc \
        "$_font_dir"/*.TTF "$_font_dir"/*.OTF "$_font_dir"/*.TTC; do
        [ -f "$_font_file" ] || continue
        _name=$(basename "$_font_file" 2>/dev/null)
        case "$_name" in SysFont*|SysSans*) continue ;; esac
        _size=$(stat -c %s "$_font_file" 2>/dev/null)
        _mtime=$(stat -c '%Y:%y' "$_font_file" 2>/dev/null)
        case "$_size" in ''|*[!0-9]*) _size=0 ;; esac
        [ -n "$_mtime" ] || _mtime=0
        printf '%s|%s|%s\n' "$_name" "$_size" "$_mtime" >> "$_tmp"
        _count=$((_count + 1))
        _bytes=$((_bytes + _size))
    done

    LC_ALL=C sort -o "$_tmp" "$_tmp" 2>/dev/null || true
    if command -v sha256sum >/dev/null 2>&1; then
        _digest=$(sha256sum "$_tmp" 2>/dev/null | awk '{print $1}')
    elif command -v busybox >/dev/null 2>&1; then
        _digest=$(busybox sha256sum "$_tmp" 2>/dev/null | awk '{print $1}')
    else
        _digest=$(cksum "$_tmp" 2>/dev/null | awk '{print $1 "-" $2}')
    fi
    rm -f "$_tmp" 2>/dev/null || true
    [ -n "$_digest" ] || _digest="empty"
    printf 'v3:%s:%s:%s\n' "$_digest" "$_count" "$_bytes"
}

font_library_fingerprint_json() {
    _fingerprint=$(font_library_fingerprint_value)
    _current="default"
    [ -f "${ACTIVE_FONT_CONF:-}" ] && _current=$(head -n1 "$ACTIVE_FONT_CONF" 2>/dev/null | tr -d '\r\n')
    [ -n "$_current" ] || _current="default"
    _count=$(printf '%s' "$_fingerprint" | awk -F: '{print $(NF-1)}')
    _bytes=$(printf '%s' "$_fingerprint" | awk -F: '{print $NF}')
    case "$_count" in ''|*[!0-9]*) _count=0 ;; esac
    case "$_bytes" in ''|*[!0-9]*) _bytes=0 ;; esac
    printf '{"status":"ok","data":{"fingerprint":"%s","current":"%s","count":%s,"bytes":%s}}\n' \
        "$(json_escape "$_fingerprint")" "$(json_escape "$_current")" "$_count" "$_bytes"
}

# font_manager.sh 在 rom_adapters.sh 之后加载本文件，因此这里接入 HyperOS 增强层，
# 让直接应用字体使用真实分区映射与原厂度量外壳。
_hyperos_helper="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}/common/hyperos_global.sh"
[ -f "$_hyperos_helper" ] && . "$_hyperos_helper"
_font_config_partitions="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}/common/font_config_partitions.sh"
[ -f "$_font_config_partitions" ] && . "$_font_config_partitions"

# 直接执行时提供给原生 App 使用；被 font_manager.sh source 时只定义函数。
if [ "${0##*/}" = "font_library_cache.sh" ]; then
    MODDIR="${MODDIR:-$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)}"
    USER_FONTS_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts"
    CONFIG_DIR="$MODDIR/config"
    ACTIVE_FONT_CONF="$CONFIG_DIR/active_font.conf"
    json_escape() {
        printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
    }

    # v2.2 的逐设备模板在完整开机后的索引预热阶段异步采集。
    # 它只读取 ROM XML/字体，不阻塞当前 App 字体列表，也不改写任何系统文件。
    _device_template="$MODDIR/common/device_font_template.sh"
    if [ -f "$_device_template" ] && [ "${1:-fingerprint}" = value ]; then
        (MODDIR="$MODDIR" sh "$_device_template" ensure >/dev/null 2>&1) &
    fi

    case "${1:-fingerprint}" in
        fingerprint) font_library_fingerprint_json ;;
        value) font_library_fingerprint_value ;;
        *) printf '{"status":"error","message":"未知字体索引命令"}\n' ;;
    esac
fi
