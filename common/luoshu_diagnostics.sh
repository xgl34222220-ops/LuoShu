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
_diag_exec "$EXPORTER" --moddir "$MODDIR" --output "$_diag_out"
