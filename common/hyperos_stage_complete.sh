#!/system/bin/sh
# Complete a staged LuoShu payload with the same HyperOS physical UI targets used by
# the current mapper. This helper never writes the live payload; callers pass an
# isolated next-boot/staging root.
set +e

PAYLOAD_ROOT="${1:-${LUOSHU_HYPEROS_STAGE_ROOT:-}}"
[ -n "$PAYLOAD_ROOT" ] || exit 2

REALMOD="${LUOSHU_REAL_MODDIR:-}"
if [ -z "$REALMOD" ]; then
    _self_dir=$(CDPATH= cd -- "${0%/*}" 2>/dev/null && pwd)
    REALMOD=$(CDPATH= cd -- "$_self_dir/.." 2>/dev/null && pwd)
fi
[ -f "$REALMOD/module.prop" ] || exit 2

MODULE_DIR="$REALMOD"
MODDIR="$REALMOD"
USER_FONTS_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts"
export MODULE_DIR MODDIR USER_FONTS_DIR

[ -f "$REALMOD/common/util_functions.sh" ] && . "$REALMOD/common/util_functions.sh"
[ -f "$REALMOD/common/rom_adapters.sh" ] && . "$REALMOD/common/rom_adapters.sh"
[ -f "$REALMOD/common/hyperos_global.sh" ] && . "$REALMOD/common/hyperos_global.sh"
[ -f "$REALMOD/common/legacy_v14_4/hyperos_full_coverage.sh" ] && \
    . "$REALMOD/common/legacy_v14_4/hyperos_full_coverage.sh"

type _hyperos_core_files >/dev/null 2>&1 || exit 2
type _hyperos_weight_files >/dev/null 2>&1 || exit 2
type _hyperos_upright_ui_files >/dev/null 2>&1 || exit 2
type _hyperos_clock_ui_files >/dev/null 2>&1 || exit 2

# HyperOS 4 / Android 15+ moves variable-font configuration toward
# font_fallback.xml. Prefer the trusted inventory's exact current-ROM UI graph:
# this catches new OEM filenames without replacing every language fallback file,
# and avoids rewriting 100+ unrelated physical fonts on each switch.
_pyroot="$REALMOD/common/python"
_python="$_pyroot/bin/luoshu-python"
[ -x "$_python" ] || { echo 'HyperOS 字体处理运行时不可用' >&2; exit 1; }

if [ -s "$REALMOD/config/device_font_inventory.json" ]; then
    PYTHONHOME="$_pyroot" \
    PYTHONPATH="$REALMOD/common:$_pyroot/lib/python3.14:$_pyroot/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$_pyroot/lib:$_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        exec "$_python" "$REALMOD/common/hyperos_metrics_batch.py" \
            "$REALMOD" "$PAYLOAD_ROOT" --inventory-ui
fi

# Old installs without a trusted inventory keep the narrow legacy path. They do
# not receive speculative HyperOS 4 coverage until stock scanning has completed.
_targets=$({
    _hyperos_core_files
    _hyperos_weight_files
    _hyperos_upright_ui_files
    _hyperos_clock_ui_files
} | tr ' ' '\n' | awk 'NF && !seen[$0]++')
PYTHONHOME="$_pyroot" \
PYTHONPATH="$REALMOD/common:$_pyroot/lib/python3.14:$_pyroot/lib/python3.14/site-packages" \
LD_LIBRARY_PATH="$_pyroot/lib:$_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    exec "$_python" "$REALMOD/common/hyperos_metrics_batch.py" "$REALMOD" "$PAYLOAD_ROOT" <<EOF_TARGETS
$_targets
EOF_TARGETS
