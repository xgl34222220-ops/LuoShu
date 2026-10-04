#!/system/bin/sh
# LuoShu engine diagnostic bundle: read-only for fonts, writes one zip under the public directory.
set +e

MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
PUBLIC_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"
EXPORTER="$MODDIR/common/luoshu_diagnostics.py"

_diag_exec() {
    if [ -n "${LUOSHU_PYTHON:-}" ]; then
        "$LUOSHU_PYTHON" "$@"
        return $?
    fi
    [ -x "$PYBIN" ] || return 127
    PYTHONHOME="$PYROOT" \
    PYTHONPATH="$MODDIR/common:$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$PYBIN" "$@"
}

[ -f "$EXPORTER" ] || { printf '{"status":"error","message":"诊断包组件不可用"}\n'; exit 1; }
_diag_model=$(getprop ro.product.model 2>/dev/null | tr -c 'A-Za-z0-9._-' '_' | cut -c1-32)
_diag_stamp=$(date +%Y%m%d-%H%M%S 2>/dev/null || echo now)
_diag_out="$PUBLIC_DIR/diagnostics/LuoShu-engine-${_diag_model:-device}-$_diag_stamp.zip"
# Default: lite bundle (fonts hollowed to the glyphs the engine inspects). "full" ships fonts whole.
mkdir -p "$MODDIR/logs" 2>/dev/null || true
_diag_log="$MODDIR/logs/diagnostics.log"
if [ "${1:-}" = full ]; then
    _diag_result=$(_diag_exec "$EXPORTER" --moddir "$MODDIR" --output "${_diag_out%.zip}-full.zip" --full 2>>"$_diag_log")
else
    _diag_result=$(_diag_exec "$EXPORTER" --moddir "$MODDIR" --output "$_diag_out" 2>>"$_diag_log")
fi
_diag_rc=$?
if printf '%s' "$_diag_result" | grep -q '"status"'; then
    printf '%s\n' "$_diag_result"
else
    # The interpreter died before reporting (missing runtime, killed, out of memory).
    printf '{"status":"error","message":"诊断包生成中断（代码 %s），详情见 logs/diagnostics.log"}\n' "$_diag_rc"
fi
exit "$_diag_rc"
