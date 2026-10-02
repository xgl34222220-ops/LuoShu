#!/system/bin/sh
# Direct CLI inventory or one finite App-owned synchronous request. No mount work.
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
        ACTION="${2:-}"; TIMEOUT="${3:-60}"
        case "$ACTION" in cached|preview|scan|refresh|fingerprint) ;; *) exit 2 ;; esac
        exec "$PYBIN" "$MODDIR/common/font_request_scope.py" \
            --scope-dir "$MODDIR/config/font-requests" --timeout "$TIMEOUT" -- \
            "$PYBIN" "$MODDIR/common/font_inventory_batch.py" "$ACTION"
        ;;
    cached|preview|scan|refresh|fingerprint)
        exec "$PYBIN" "$MODDIR/common/font_inventory_batch.py" "$1"
        ;;
    *) printf '%s\n' '{"status":"error","message":"未知字体库存请求"}'; exit 2 ;;
esac
