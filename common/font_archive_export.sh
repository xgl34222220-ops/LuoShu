#!/system/bin/sh
# 洛书字体归档只读导出桥：将指定 Family 的真实字体文件复制到 App 私有缓存。
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
    else
        MODDIR="/data/adb/modules/LuoShu"
    fi
fi
USER_FONTS_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts"
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

fail() {
    printf '{"status":"error","message":"%s"}\n' "$(json_escape "$1")"
    exit 0
}

family="${1:-}"
dest="${2:-}"
[ -n "$family" ] || fail "未指定字体 Family"
[ -n "$dest" ] || fail "未指定归档缓存目录"

case "$dest" in
    *'/../'*|*/..|../*) fail "归档缓存路径无效" ;;
    /data/user/0/io.github.xgl34222220.luoshu/cache/font_archive/*|\
    /data/data/io.github.xgl34222220.luoshu/cache/font_archive/*|\
    /data/user/0/io.github.xgl34222220.luoshu.debug/cache/font_archive/*|\
    /data/data/io.github.xgl34222220.luoshu.debug/cache/font_archive/*) ;;
    *) fail "归档目标目录不受信任" ;;
esac

[ -d "$USER_FONTS_DIR" ] || fail "字体库目录不存在"
rm -rf "$dest" 2>/dev/null || fail "无法清理归档缓存"
mkdir -p "$dest" 2>/dev/null || fail "无法创建归档缓存"
chmod 0700 "$dest" 2>/dev/null || true

count=0
total=0
for file in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
            "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
    [ -f "$file" ] || continue
    [ -L "$file" ] && continue
    if type detect_font_family >/dev/null 2>&1; then
        detected="$(detect_font_family "$(basename "$file")")"
    else
        detected="$(basename "$file")"
        detected="${detected%.*}"
        detected="${detected%-Regular}"
    fi
    [ "$detected" = "$family" ] || continue

    count=$((count + 1))
    [ "$count" -le 128 ] 2>/dev/null || { rm -rf "$dest" 2>/dev/null; fail "单个 Family 超过 128 个字体文件限制"; }
    bytes="$(wc -c < "$file" 2>/dev/null | tr -d '[:space:]')"
    case "$bytes" in ''|*[!0-9]*) bytes=0 ;; esac
    [ "$bytes" -gt 0 ] 2>/dev/null || { rm -rf "$dest" 2>/dev/null; fail "字体文件为空或无法读取"; }
    total=$((total + bytes))
    [ "$total" -le 1073741824 ] 2>/dev/null || { rm -rf "$dest" 2>/dev/null; fail "单个 Family 归档超过 1 GB 限制"; }

    ext="${file##*.}"
    ext="$(printf '%s' "$ext" | tr '[:upper:]' '[:lower:]')"
    target="$dest/$(printf '%03d' "$count").$ext"
    cp -f "$file" "$target" 2>/dev/null || { rm -rf "$dest" 2>/dev/null; fail "复制字体文件失败"; }
    chmod 0644 "$target" 2>/dev/null || true
done

[ "$count" -gt 0 ] 2>/dev/null || { rm -rf "$dest" 2>/dev/null; fail "找不到指定 Family 的字体文件"; }
printf '{"status":"ok","data":{"family":"%s","count":%s,"bytes":%s}}\n' \
    "$(json_escape "$family")" "$count" "$total"
exit 0
