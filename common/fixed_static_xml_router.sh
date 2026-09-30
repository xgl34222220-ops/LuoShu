#!/system/bin/sh
# Explicit fixed-selection route bridge. Does not publish or mount a payload.
MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
CONFIG_DIR="${CONFIG_DIR:-$MODDIR/config}"
LEGACY="$MODDIR/common/minimal_xml_router.sh"
PYROOT="$MODDIR/common/python"
_fsr_python() {
    if [ -n "${LUOSHU_PYTHON:-}" ]; then "$LUOSHU_PYTHON" "$@"; return $?; fi
    PYTHONHOME="$PYROOT" PYTHONPATH="$MODDIR/common:$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" \
      LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
      "$PYROOT/bin/luoshu-python" "$@"
}
case "${1:-build}" in
    path) exec sh "$LEGACY" path "${2:-}" ;;
    build|refresh)
        result=$(sh "$LEGACY" build "${2:-}" 2>&1); status=$?
        if [ "$status" -ne 0 ]; then printf '%s\n' "$result"; exit "$status"; fi
        route=$(sh "$LEGACY" path "${2:-}") || exit 1
        plan=$(sh "$MODDIR/common/universal_font_plan.sh" path "${2:-}") || exit 1
        _fsr_python "$MODDIR/common/fixed_static_xml_router.py" --font-plan "$plan" --base-route "$route" --output "$route"
        ;;
    validate)
        route=$(sh "$LEGACY" path "${2:-}") || exit 1
        plan=$(sh "$MODDIR/common/universal_font_plan.sh" path "${2:-}") || exit 1
        _fsr_python "$MODDIR/common/fixed_static_xml_router.py" --font-plan "$plan" --validate "$route"
        ;;
    *) exit 2 ;;
esac
