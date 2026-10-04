#!/system/bin/sh
# A child of the existing finite mix scope, never a detached/resident job.
set -eu
REALMOD="${LUOSHU_REAL_MODDIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
. "$REALMOD/common/background_task.sh"
luoshu_task_runtime || exit 1
if [ "$_ltr_bundled" = 1 ]; then
    export PYTHONHOME="$_ltr_root"
    export PYTHONPATH="$REALMOD/common:$_ltr_root/lib/python3.14:$_ltr_root/lib/python3.14/site-packages"
    export LD_LIBRARY_PATH="$_ltr_root/lib:$_ltr_root/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
mkdir -p "$REALMOD/logs"
exec "$_ltr_python" "$REALMOD/common/composite_collection_build.py" \
    --module "$REALMOD" --source "$1" --target "$2" --output "$3" \
    --request "${LUOSHU_MIX_REQUEST_ID:?}" >> "$REALMOD/logs/fontswitch.log" 2>&1
