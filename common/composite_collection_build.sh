#!/system/bin/sh
# Compile the composite into a collection with the device's own face count.
# A child of the existing finite mix scope, never a detached/resident job.
# Usage: composite_collection_build.sh SOURCE STOCK_TARGET OUTPUT
set -eu
REALMOD="${LUOSHU_REAL_MODDIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
_ccb_python="${LUOSHU_TASK_SCOPE_PYTHON:-}"
if [ -z "$_ccb_python" ]; then
    _ccb_root="$REALMOD/common/python"
    _ccb_python="$_ccb_root/bin/luoshu-python"
    [ -x "$_ccb_python" ] || chmod 0755 "$_ccb_python" 2>/dev/null || true
    [ -x "$_ccb_python" ] || { echo '[MIX] 缺少内置 Python，无法编译字体集合' >&2; exit 1; }
    export PYTHONHOME="$_ccb_root"
    export PYTHONPATH="$REALMOD/common:$_ccb_root/lib/python3.14:$_ccb_root/lib/python3.14/site-packages"
    export LD_LIBRARY_PATH="$_ccb_root/lib:$_ccb_root/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
_ccb_log="${LUOSHU_LOG_DIR:-$REALMOD/logs}"
mkdir -p "$_ccb_log" 2>/dev/null || true
exec "$_ccb_python" "$REALMOD/common/composite_collection_build.py" \
    --module "$REALMOD" --source "$1" --target "$2" --output "$3" \
    --request "${LUOSHU_MIX_REQUEST_ID:?}" >> "$_ccb_log/fontswitch.log" 2>&1
