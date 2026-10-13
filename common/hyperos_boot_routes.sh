#!/system/bin/sh
# Early-boot HyperOS routes for the v4 runtime.
#
# The legacy physical route (legacy_v14_4/hyperos_full_coverage.sh) already
# runs the optional theme takeover and the MiSansVF_Overlay -> theme_webview
# route before zygote. The v4 route execs the frozen core and never reaches
# that code, so HyperOS default sans-serif Latin/digits stayed on stock Roboto
# for v4 users. common/util_functions.sh calls this from its post-fs-data hook
# for the v4 route only (no legacy marker). Both helpers are journalled per
# boot, read-only binds of the active payload, and fail closed.
set +e

_lhbr_is_hyperos() {
    [ "${IS_HYPEROS:-false}" = true ] && return 0
    _lhbr_mios=$(getprop ro.mi.os.version.name 2>/dev/null | tr -d '\r\n')
    _lhbr_miui=$(getprop ro.miui.ui.version.name 2>/dev/null | tr -d '\r\n')
    [ -n "$_lhbr_mios$_lhbr_miui" ]
}

luoshu_hyperos_boot_routes_ensure() {
    _lhbr_module="${LUOSHU_REAL_MODDIR:-${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}}"
    [ -f "$_lhbr_module/module.prop" ] || return 0
    # The legacy runtime handles its own routes from the payload hook.
    [ ! -f "$_lhbr_module/config/font_runtime_legacy_v14_4.conf" ] || return 0
    _lhbr_is_hyperos || return 0
    if [ -f "$_lhbr_module/common/hyperos_theme_takeover.sh" ]; then
        ( LUOSHU_REAL_MODDIR="$_lhbr_module"
          . "$_lhbr_module/common/hyperos_theme_takeover.sh"
          luoshu_hyperos_theme_takeover_ensure ) >/dev/null 2>&1 || true
    fi
    [ ! -f "$_lhbr_module/config/hyperos-webview-route.disable" ] || return 0
    [ -L "${LUOSHU_WEBVIEW_ROUTE_ALIAS:-/system/fonts/MiSansVF_Overlay.ttf}" ] || return 0
    [ -f "$_lhbr_module/common/hyperos_webview_route.sh" ] || return 0
    ( LUOSHU_REAL_MODDIR="$_lhbr_module"
      . "$_lhbr_module/common/hyperos_webview_route.sh"
      luoshu_hyperos_webview_route_ensure ) >/dev/null 2>&1 || true
    return 0
}
