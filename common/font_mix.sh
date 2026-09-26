#!/system/bin/sh
# Public compatibility entry. Composite sources and inventory mapping share one
# isolated next-boot transaction; this entry never writes the live font tree.
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
MIX_ROUTER="$MODDIR/common/legacy_v14_4/mix_router.sh"
[ -f "$MIX_ROUTER" ] || {
    printf '{"status":"error","message":"缺少字体组合核心，请重新安装当前版本模块"}\n'
    exit 1
}
case "${1:-config}" in
    start|config|recover|reconcile) exec sh "$MIX_ROUTER" "$@" ;;
    status)
        # The old no-argument status API returned the selected configuration.
        if [ -z "${2:-}" ]; then exec sh "$MIX_ROUTER" config; fi
        exec sh "$MIX_ROUTER" "$@"
        ;;
    worker)
        # Compatibility for the updater's synchronous worker interface. Start a
        # normal isolated task and wait for its real next-boot commit result.
        _saved=''
        for _candidate in "$MODDIR/config/axes_mix.conf" "$MODDIR/config/font_mix.conf"; do
            [ -s "$_candidate" ] || continue
            [ "$(sed -n 's/^cjk=//p' "$_candidate" | head -n1)" = "${3:-}" ] || continue
            [ "$(sed -n 's/^latin=//p' "$_candidate" | head -n1)" = "${4:-}" ] || continue
            [ "$(sed -n 's/^digit=//p' "$_candidate" | head -n1)" = "${5:-}" ] || continue
            _saved="$_candidate"; break
        done
        _cjk_axes="${7:-}"; _latin_axes="${8:-}"; _digit_axes="${9:-}"
        _cjk_mode="${10:-}"; _latin_mode="${11:-}"; _digit_mode="${12:-}"
        if [ -n "$_saved" ]; then
            [ -n "$_cjk_axes" ] || _cjk_axes=$(sed -n 's/^cjkAxes=//p' "$_saved" | head -n1)
            [ -n "$_latin_axes" ] || _latin_axes=$(sed -n 's/^latinAxes=//p' "$_saved" | head -n1)
            [ -n "$_digit_axes" ] || _digit_axes=$(sed -n 's/^digitAxes=//p' "$_saved" | head -n1)
            [ -n "$_cjk_mode" ] || _cjk_mode=$(sed -n 's/^cjkMode=//p' "$_saved" | head -n1)
            [ -n "$_latin_mode" ] || _latin_mode=$(sed -n 's/^latinMode=//p' "$_saved" | head -n1)
            [ -n "$_digit_mode" ] || _digit_mode=$(sed -n 's/^digitMode=//p' "$_saved" | head -n1)
        fi
        _result=$(sh "$MIX_ROUTER" start "${3:-}" "${4:-}" "${5:-}" \
            "${_cjk_axes:-wght=400}" "${_latin_axes:-wght=400}" "${_digit_axes:-wght=400}" \
            "${_cjk_mode:-infer}" "${_latin_mode:-infer}" "${_digit_mode:-infer}" 2>&1)
        printf '%s\n' "$_result"
        _task=$(printf '%s\n' "$_result" | sed -n 's/^.*"task":"\([^"]*\)".*$/\1/p' | tail -n1)
        [ -n "$_task" ] || exit 1
        _loops=0
        while [ "$_loops" -lt 480 ]; do
            _result=$(sh "$MIX_ROUTER" status "$_task" 2>&1)
            case "$_result" in
                *'"state":"success"'*) printf '%s\n' "$_result"; exit 0 ;;
                *'"state":"failed"'*|*'"status":"error"'*) printf '%s\n' "$_result"; exit 1 ;;
            esac
            sleep 2
            _loops=$((_loops + 1))
        done
        printf '{"status":"error","message":"等待组合任务完成超时"}\n'
        exit 1
        ;;
    *) printf '{"status":"error","message":"未知组合命令"}\n'; exit 2 ;;
esac
