#!/system/bin/sh
# Align the legacy ColorOS staging result in one Python process before commit.
set -eu

PAYLOAD_ROOT="${1:-}"
[ -n "$PAYLOAD_ROOT" ] || exit 2
REALMOD="${LUOSHU_REAL_MODDIR:-}"
if [ -z "$REALMOD" ]; then
    _self_dir=$(CDPATH= cd -- "${0%/*}" 2>/dev/null && pwd)
    REALMOD=$(CDPATH= cd -- "$_self_dir/.." 2>/dev/null && pwd)
fi
[ -f "$REALMOD/module.prop" ] || exit 2
_pyroot="$REALMOD/common/python"
_python="$_pyroot/bin/luoshu-python"
[ -x "$_python" ] || { echo 'ColorOS 字体处理运行时不可用' >&2; exit 1; }
PYTHONHOME="$_pyroot" \
PYTHONPATH="$REALMOD/common:$_pyroot/lib/python3.14:$_pyroot/lib/python3.14/site-packages" \
LD_LIBRARY_PATH="$_pyroot/lib:$_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    exec "$_python" "$REALMOD/common/coloros_metrics_batch.py" "$REALMOD" "$PAYLOAD_ROOT"
