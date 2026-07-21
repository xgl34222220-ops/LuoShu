#!/system/bin/sh
# 洛书字体运行时探测入口。使用模块内置 Python，避免 Toybox find/unzip 兼容差异。
set +e

MODDIR="${MODDIR:-${0%/*}/..}"
REPORT="${LUOSHU_FONT_PROBE_REPORT:-$MODDIR/logs/font-runtime-probe.txt}"
PYROOT="$MODDIR/common/python"
PYTHON="$PYROOT/bin/luoshu-python"
SCRIPT="$MODDIR/common/font_runtime_probe.py"

mkdir -p "${REPORT%/*}" 2>/dev/null || true

if [ -x "$PYTHON" ] && [ -f "$SCRIPT" ]; then
    MODDIR="$MODDIR" \
    LUOSHU_FONT_PROBE_REPORT="$REPORT" \
    PYTHONHOME="$PYROOT" \
    PYTHONPATH="$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$PYTHON" "$SCRIPT" >/dev/null 2>&1
    _code=$?
    if [ "$_code" -eq 0 ] && [ -s "$REPORT" ]; then
        printf '%s\n' "$REPORT"
        exit 0
    fi
fi

# 极端情况下内置 Python 无法启动，至少保留可定位原因的最小报告。
{
    printf '# LuoShu font runtime probe fallback\n'
    printf 'time=%s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)"
    printf 'python=%s executable=%s script=%s\n' "$PYTHON" "$([ -x "$PYTHON" ] && echo true || echo false)" "$([ -f "$SCRIPT" ] && echo true || echo false)"
    printf 'model=%s\n' "$(getprop ro.product.model 2>/dev/null)"
    printf 'device=%s\n' "$(getprop ro.product.device 2>/dev/null)"
    printf 'hyperos=%s\n' "$(getprop ro.mi.os.version.name 2>/dev/null)"
    printf '\n# Directory listing\n'
    for _dir in /system/fonts /product/fonts /system_ext/fonts "$MODDIR/system/fonts" "$MODDIR/product/fonts" "$MODDIR/system_ext/fonts"; do
        [ -d "$_dir" ] || continue
        printf '[%s]\n' "$_dir"
        ls -la "$_dir" 2>/dev/null | head -n 500
    done
} > "$REPORT" 2>&1
chmod 0644 "$REPORT" 2>/dev/null || true
printf '%s\n' "$REPORT"
