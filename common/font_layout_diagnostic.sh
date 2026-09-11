#!/system/bin/sh
# One read-only Python invocation; the collector enforces a total time budget.
MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
fi
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"
[ -x "$PYBIN" ] && [ -f "$MODDIR/common/font_layout_diagnostic.py" ] || {
    printf '%s\n' 'font-layout-diagnostic-runtime-unavailable' >&2
    exit 1
}
export PYTHONHOME="$PYROOT"
export PYTHONPATH="$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages"
export LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$PYBIN" "$MODDIR/common/font_layout_diagnostic.py" --module "$MODDIR" "$@"
