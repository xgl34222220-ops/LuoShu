#!/system/bin/sh
set -eu
MODDIR="${MODDIR:-$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)}"
RUNTIME="$MODDIR/common/python"
PYBIN="$RUNTIME/bin/luoshu-python"
[ -x "$PYBIN" ] || { echo '{"status":"error","message":"复合字体运行时缺失"}' >&2; exit 20; }
case "$(uname -m 2>/dev/null || true)" in aarch64|arm64) ;; *) echo '{"status":"error","message":"完整复合字体引擎仅支持 ARM64"}' >&2; exit 21 ;; esac
export PYTHONHOME="$RUNTIME"
export PYTHONPATH="$RUNTIME/lib/python3.14:$RUNTIME/lib/python3.14/site-packages"
export LD_LIBRARY_PATH="$RUNTIME/lib:$RUNTIME/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export TMPDIR="${TMPDIR:-$MODDIR/cache/tmp}"
mkdir -p "$TMPDIR" 2>/dev/null || true
if [ "${1:-}" = "--self-test" ]; then
    exec "$PYBIN" -c 'import fontTools; print("ok")'
fi
exec "$PYBIN" "$MODDIR/common/composite_font.py" "$@"
