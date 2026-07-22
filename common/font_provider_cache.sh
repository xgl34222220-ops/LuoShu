#!/system/bin/sh
# LuoShu downloadable-fonts provider cache hijack.
#
# Play 商店、Gmail 等 Google 系应用不读 /system 或 /product 下的字体文件，
# 而是通过 GMS 的 Fonts Provider（Downloadable Fonts）加载字体，
# 缓存落在 /data/fonts/files/（按内容哈希命名）。系统分区的文件替换对它们无效。
# 本脚本把已归一化的用户字体同步进该缓存，并 force-stop 相关进程使其重新加载。
set +e

LUOSHU_PROVIDER_DIR="${LUOSHU_PROVIDER_DIR:-/data/fonts/files}"
LUOSHU_PROVIDER_BACKUP_SUFFIX=".luoshu-bak"

luoshu_provider_log() {
    _lpl_msg="$1"
    _lpl_mod="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
    mkdir -p "$_lpl_mod/logs" 2>/dev/null || true
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$_lpl_msg" >> "$_lpl_mod/logs/provider_cache.log" 2>/dev/null || true
}

# 尽力识别 downloadable emoji 字体（如 NotoColorEmoji 的 provider 下载副本），
# 它们绝不能被文字字体替换，否则使用 downloadable emoji 的应用会变方块。
# 识别不了（无 Python 环境）时按文字字体处理——Play 商店链路本来就没有 emoji 缓存。
_luoshu_provider_family_is_emoji() {
    _lpie_file="$1"
    _lpie_mod="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
    _lpie_py="$_lpie_mod/common/python/bin/luoshu-python"
    [ -x "$_lpie_py" ] || return 1
    _lpie_pyroot="$_lpie_mod/common/python"
    _lpie_kind=$(PYTHONHOME="$_lpie_pyroot" \
        PYTHONPATH="$_lpie_pyroot/lib/python3.14:$_lpie_pyroot/lib/python3.14/site-packages" \
        LD_LIBRARY_PATH="$_lpie_pyroot/lib:$_lpie_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$_lpie_py" - "$_lpie_file" <<'PY_LUOSHU_EMOJI_PROBE' 2>/dev/null
import sys
from fontTools.ttLib import TTFont, TTCollection
try:
    src = sys.argv[1]
    with open(src, "rb") as fh:
        coll = fh.read(4) == b"ttcf"
    font = (TTCollection(src, lazy=True).fonts[0] if coll else TTFont(src, lazy=True))
    names = " ".join(r.toUnicode() for r in font["name"].names if r.nameID in (1, 4, 6, 16)).lower()
    print("emoji" if "emoji" in names else "text")
except Exception:
    print("unknown")
PY_LUOSHU_EMOJI_PROBE
)
    [ "$_lpie_kind" = "emoji" ]
}

# luoshu_provider_cache_sync <归一化后的字体文件>
# 备份原始缓存（仅首次），再把缓存内所有 ttf/otf 替换为用户字体。
luoshu_provider_cache_sync() {
    _lpcs_font="$1"
    [ -f "$_lpcs_font" ] || return 0
    [ -d "$LUOSHU_PROVIDER_DIR" ] || return 0

    _lpcs_count=0
    for _lpcs_f in "$LUOSHU_PROVIDER_DIR"/*; do
        [ -f "$_lpcs_f" ] || continue
        case "$_lpcs_f" in *"$LUOSHU_PROVIDER_BACKUP_SUFFIX") continue ;; esac
        # 只处理字体文件（magic: 00010000 / OTTO / ttcf）
        _lpcs_magic=$(dd if="$_lpcs_f" bs=4 count=1 2>/dev/null | od -An -tx1 2>/dev/null | tr -d ' \n')
        case "$_lpcs_magic" in
            00010000|4f54544f|74746366) ;;  # ttf / otf / ttc
            *) continue ;;
        esac
        if _luoshu_provider_family_is_emoji "$_lpcs_f"; then
            luoshu_provider_log "跳过 downloadable emoji 字体：${_lpcs_f##*/}"
            continue
        fi
        if [ ! -f "${_lpcs_f}${LUOSHU_PROVIDER_BACKUP_SUFFIX}" ]; then
            cp -f "$_lpcs_f" "${_lpcs_f}${LUOSHU_PROVIDER_BACKUP_SUFFIX}" 2>/dev/null || true
        fi
        if cp -f "$_lpcs_font" "$_lpcs_f" 2>/dev/null; then
            chmod 644 "$_lpcs_f" 2>/dev/null || true
            _lpcs_count=$((_lpcs_count + 1))
        fi
    done
    [ "$_lpcs_count" -gt 0 ] || return 0

    # 已缓存 Typeface 的进程不会重读文件，force-stop 让其下次启动走新缓存
    for _lpcs_pkg in com.android.vending com.google.android.gms; do
        am force-stop "$_lpcs_pkg" >/dev/null 2>&1 || true
    done
    luoshu_provider_log "已劫持 $_lpcs_count 个 provider 缓存字体并重启 GMS/Play"
    return 0
}

# luoshu_provider_cache_restore：恢复默认字体时还原原始缓存。
luoshu_provider_cache_restore() {
    [ -d "$LUOSHU_PROVIDER_DIR" ] || return 0
    _lpcr_count=0
    for _lpcr_bak in "$LUOSHU_PROVIDER_DIR"/*"$LUOSHU_PROVIDER_BACKUP_SUFFIX"; do
        [ -f "$_lpcr_bak" ] || continue
        _lpcr_orig="${_lpcr_bak%$LUOSHU_PROVIDER_BACKUP_SUFFIX}"
        if mv -f "$_lpcr_bak" "$_lpcr_orig" 2>/dev/null; then
            chmod 644 "$_lpcr_orig" 2>/dev/null || true
            _lpcr_count=$((_lpcr_count + 1))
        fi
    done
    if [ "$_lpcr_count" -gt 0 ]; then
        for _lpcr_pkg in com.android.vending com.google.android.gms; do
            am force-stop "$_lpcr_pkg" >/dev/null 2>&1 || true
        done
        luoshu_provider_log "已恢复 $_lpcr_count 个 provider 缓存字体"
    fi
    return 0
}
