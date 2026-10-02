#!/system/bin/sh
# Explicit App preflight or a child inside the existing finite switch scope.
set -eu
MODDIR="${MODDIR:-$(CDPATH= cd -- "${0%/*}/.." && pwd)}"
export MODDIR
PYROOT="$MODDIR/common/python"
if [ ! -e /system/bin/sh ]; then
    PYBIN="${LUOSHU_TASK_PYTHON:-$(command -v python3)}"
else
    PYBIN="$PYROOT/bin/luoshu-python"
    export PYTHONHOME="$PYROOT"
    export PYTHONPATH="$MODDIR/common:$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages"
    export LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
case "${1:-}" in
    request)
        exec "$PYBIN" "$MODDIR/common/font_request_scope.py" \
            --scope-dir "$MODDIR/config/font-requests" --timeout 29 -- \
            "$PYBIN" "$MODDIR/common/font_switch_input.py" preflight "${2:-}"
        ;;
    preflight|run)
        exec "$PYBIN" "$MODDIR/common/font_switch_input.py" "$@"
        ;;
    *) exit 2 ;;
esac
