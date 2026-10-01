#!/system/bin/sh
# Composite workers own fallback. Universal preparation must never invoke a second
# legacy worker or write into the compatibility runtime's current payload.
set +e
MODDIR="${LUOSHU_REAL_MODDIR:-${MODDIR:-}}"
[ -f "$MODDIR/module.prop" ] || exit 1
REQUEST="${LUOSHU_MIX_REQUEST_ID:-}"
[ -n "$REQUEST" ] || exit 1
PYROOT="$MODDIR/common/python"
_um_python() {
    if [ -n "${LUOSHU_PYTHON:-}" ]; then "$LUOSHU_PYTHON" "$@"; return $?; fi
    PYTHONHOME="$PYROOT" PYTHONPATH="$MODDIR/common:$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" \
        LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$PYROOT/bin/luoshu-python" "$@"
}
_um_fail() {
    mkdir -p "$MODDIR/config" 2>/dev/null || true
    printf 'state=fallback\nfont=mix\ndecision=legacy\nreason=%s\nrequestId=%s\n' "$1" "$REQUEST" \
        > "$MODDIR/config/universal-font-cutover.conf.tmp.$$" && \
        mv -f "$MODDIR/config/universal-font-cutover.conf.tmp.$$" "$MODDIR/config/universal-font-cutover.conf"
}
export LUOSHU_SWITCH_PROGRESS_FILE="$MODDIR/config/universal-mixed-progress.conf"
export LUOSHU_UNIVERSAL_MIX_STRICT=1
printf 'requestId=%s\nstate=running\npercent=78\nmessage=正在检查组合字体源\nupdated=%s\n' "$REQUEST" "$(date +%s)" > "$LUOSHU_SWITCH_PROGRESS_FILE"
_um_root=$(_um_python "$MODDIR/common/universal_mixed_font.py" --module "$MODDIR" \
    --request "$REQUEST" --mode "$1" --source "$2") || { _um_fail mixed-source-freeze-failed; exit 1; }
# Keep one completed/failed request trace without unbounded log growth. Rotation
# happens only after the freezer has accepted this request's generation.
_um_trace="$MODDIR/config/universal-compile-trace.jsonl"
if [ -s "$_um_trace" ]; then
    mv -f "$_um_trace" "${_um_trace%.jsonl}.previous.jsonl" 2>/dev/null || true
fi
# Validate revisions and current dynamic generation, not merely file presence.
if ! MODDIR="$MODDIR" sh "$MODDIR/common/font_topology_snapshot.sh" ensure >/dev/null 2>&1; then
    _um_fail topology-upgrade-or-refresh-required
    exit 1
fi
unset LUOSHU_MIX_SELECTION_FILE LUOSHU_FIXED_XML_MIX
# Only this accepted fixed-composite request selects the new representation.
# Ordinary fonts and the real variable multiweight path retain their contracts.
if [ "$1" = fixed ]; then
    export LUOSHU_MIX_SELECTION_FILE="$_um_root/source.json"
    export LUOSHU_FIXED_XML_MIX=1
    export LUOSHU_ROUTE_BRIDGE="$MODDIR/common/fixed_static_xml_router.sh"
fi
MODDIR="$MODDIR" MODULE_DIR="$MODDIR" CONFIG_DIR="$MODDIR/config" \
    LUOSHU_PUBLIC_DIR="$_um_root" LUOSHU_SWITCH_ACTIVE_LABEL=mix \
    sh "$MODDIR/common/universal_font_cutover.sh" prepare-mixed LuoShuMix

_um_rc=$?
if [ "$_um_rc" -ne 0 ]; then
    printf 'requestId=%s\nstate=fallback\npercent=82\nmessage=通用引擎条件未满足，正在生成兼容负载\nupdated=%s\n' "$REQUEST" "$(date +%s)" > "$LUOSHU_SWITCH_PROGRESS_FILE"
fi
# Compilation has copied all accepted artifacts into a self-contained deployment.
# Keep diagnostic provenance, but do not accumulate nine CJK masters on each try.
case "$_um_root" in
    "$MODDIR"/cache/universal-mixed-sources/*)
        if [ "$_um_rc" -ne 0 ]; then rm -rf "$_um_root/fonts" 2>/dev/null || true; fi
        ;;
esac
# Old source roots are no longer inputs to the single current LuoShuMix plan.
# Retain three recent attempts for diagnosis; live/retired deployments own bytes.
_um_count=0
for _um_old in $(ls -dt "$MODDIR/cache/universal-mixed-sources/"* 2>/dev/null); do
    [ -d "$_um_old" ] || continue
    _um_count=$((_um_count + 1))
    [ "$_um_count" -gt 3 ] && [ "$_um_old" != "$_um_root" ] || continue
    rm -rf "$_um_old" 2>/dev/null || true
done
exit "$_um_rc"
