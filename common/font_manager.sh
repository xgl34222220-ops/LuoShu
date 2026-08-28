#!/system/bin/sh
# LuoShu native App font-manager router.
# Inventory, preview, delete and weight actions stay on the current manager.
# Final font apply uses the isolated safe physical switch core, which builds the
# next-boot payload off-line and never rewrites the source tree mounted by this boot.
# Source-check compatibility markers owned by font_manager_v4.sh: native-v3 manifest-fast
# The current inventory contract remains config/native_font_index.json.
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
    else
        MODDIR="/data/adb/modules/LuoShu"
    fi
fi
LUOSHU_PUBLIC_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}"
CURRENT_MANAGER="$MODDIR/common/font_manager_v4.sh"
SAFE_SWITCH="$MODDIR/common/legacy_v14_4/font_switch_safe.sh"
LEGACY_SWITCH="$MODDIR/common/legacy_v14_4_switch.sh"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"
STOCK_SCANNER="$MODDIR/common/font_inventory.py"
STOCK_INVENTORY="$MODDIR/config/device_font_inventory.json"
export MODDIR LUOSHU_PUBLIC_DIR

json_escape_router() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

stock_scan_available() {
    [ -x "$PYBIN" ] && [ -f "$STOCK_SCANNER" ] && [ -f "$MODDIR/common/font_check.sh" ]
}

stock_scan_json() {
    if ! stock_scan_available; then
        printf '{"status":"error","message":"%s"}\n' "$(json_escape_router '原厂字体扫描组件不完整')"
        return 1
    fi
    mkdir -p "$MODDIR/config" "$MODDIR/logs" 2>/dev/null || true
    _stock_out=$(
        PYTHONHOME="$PYROOT" \
        PYTHONPATH="$MODDIR/common:$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" \
        LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
            "$PYBIN" "$STOCK_SCANNER" \
                --scan --force \
                --overlay-module "$MODDIR" \
                --font-check "$MODDIR/common/font_check.sh" \
                --output "$STOCK_INVENTORY" 2>&1
    )
    _stock_rc=$?
    _stock_last=$(printf '%s\n' "$_stock_out" | tail -n1)
    if [ "$_stock_rc" -eq 0 ] && [ -s "$STOCK_INVENTORY" ]; then
        printf '%s\n' "$_stock_last"
        return 0
    fi
    _stock_message=$(printf '%s\n' "$_stock_last" | sed -n 's/^.*"message"[[:space:]]*:[[:space:]]*"\([^"]*\)".*$/\1/p')
    [ -n "$_stock_message" ] || _stock_message="$_stock_out"
    [ -n "$_stock_message" ] || _stock_message='原厂字体扫描失败'
    printf '{"status":"error","message":"%s"}\n' "$(json_escape_router "$_stock_message")"
    return 1
}

if [ "${1:-}" = action ] && [ "${2:-}" = switch ]; then
    # The legacy composite runtime creates a temporary family (LuoShuAutoMix etc.)
    # only as a source container. It must never become the persisted active font.
    # Keep the user-visible/runtime identity as `mix`, while the safe switch still
    # resolves and validates the temporary source family normally.
    if [ -n "${LUOSHU_REAL_MODDIR:-}" ]; then
        case "$MODDIR" in
            */.legacy-v14-runtime)
                LUOSHU_SWITCH_ACTIVE_LABEL="${LUOSHU_SWITCH_ACTIVE_LABEL:-mix}"
                export LUOSHU_SWITCH_ACTIVE_LABEL
                ;;
        esac
    fi
    if [ -f "$SAFE_SWITCH" ]; then
        exec sh "$SAFE_SWITCH" "$@"
    fi
    if [ -f "$LEGACY_SWITCH" ]; then
        exec sh "$LEGACY_SWITCH" "$@"
    fi
    printf '{"status":"error","message":"%s"}\n' "$(json_escape_router '缺少字体切换核心')"
    exit 1
fi

if [ "${1:-}" = action ] && [ "${2:-}" = stock_scan ]; then
    stock_scan_json
    exit $?
fi

if [ ! -f "$CURRENT_MANAGER" ]; then
    printf '{"status":"error","message":"%s"}\n' "$(json_escape_router '缺少当前字体管理后端')"
    exit 1
fi

# Keep the existing fast user-font index, but report the stock scanner as available
# whenever its real runtime dependencies are present. Older v4 code hard-coded
# nativeAvailable=false even though the stock scanner was packaged and usable.
case "${1:-}:${2:-}" in
    action:list|list:*)
        if stock_scan_available; then
            _manager_out=$(sh "$CURRENT_MANAGER" "$@")
            _manager_rc=$?
            printf '%s\n' "$_manager_out" | sed 's/"nativeAvailable":false/"nativeAvailable":true/g'
            exit "$_manager_rc"
        fi
        ;;
esac
exec sh "$CURRENT_MANAGER" "$@"
