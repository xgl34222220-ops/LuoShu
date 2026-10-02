#!/system/bin/sh
# App composite entry: delegate before loading any runtime or scanning fonts.
set +e
MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
    else
        MODDIR=/data/adb/modules/LuoShu
    fi
fi
export MODDIR
LEGACY_V14_MIX="$MODDIR/common/legacy_v14_4/mix_router.sh"
case "${1:-config}" in
    start|config|status|recover|reconcile)
        if [ -f "$LEGACY_V14_MIX" ]; then
            if [ -f "$MODDIR/common/background_task.sh" ]; then
                . "$MODDIR/common/background_task.sh"
                if [ "${1:-config}" = start ]; then
                    # Admission precedes stage creation: concurrent App requests
                    # must never replace the first worker's queued record/stage.
                    luoshu_task_helper submit "$MODDIR/config" -- sh "$LEGACY_V14_MIX" "$@"
                    exit $?
                fi
                if [ "${1:-config}" = recover ]; then
                    for _fmc_name in axes_worker auto_multiweight_worker mix_worker; do
                        luoshu_stop_task_pid "$MODDIR/config/$_fmc_name.pid" || exit 1
                    done
                fi
            fi
            exec sh "$LEGACY_V14_MIX" "$@"
        fi
        printf '{"status":"error","message":"缺少字体组合核心，请重新安装当前版本模块"}\n'
        exit 1
        ;;
    *) printf '{"status":"error","message":"未知组合命令"}\n'; exit 2 ;;
esac
