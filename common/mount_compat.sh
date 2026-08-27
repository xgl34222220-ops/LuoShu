#!/system/bin/sh
# LuoShu mount compatibility loader.
# The v2.2.7 implementation remains in mount_compat_base.sh; this loader always
# applies the non-invasive self-mount compatibility and final engine policy afterwards.
# hyperos_global.sh remains loaded by the base implementation.
set +e

_lmcl_module="${MODULE_DIR:-${MODDIR:-}}"
if [ -z "$_lmcl_module" ]; then
    _lmcl_module=$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)
fi
[ -n "$_lmcl_module" ] || _lmcl_module=/data/adb/modules/LuoShu
_lmcl_base="$_lmcl_module/common/mount_compat_base.sh"
_lmcl_fallback="$_lmcl_module/common/mount_self_fallback.sh"
_lmcl_policy="$_lmcl_module/common/mount_compat_policy.sh"
_lmcl_private_policy="$_lmcl_module/common/private_mount_policy.sh"
_lmcl_atomic="$_lmcl_module/common/mount_self_atomic.sh"
_lmcl_font_runtime="$_lmcl_module/common/font_runtime_policy.sh"
_lmcl_font_cleanup="$_lmcl_module/common/font_runtime_cleanup.sh"
_lmcl_font_mount="$_lmcl_module/common/font_runtime_mount.sh"
_lmcl_google_provider="$_lmcl_module/common/google_font_provider_service.sh"

# When invoked as a CLI, source the base in a child shell whose $0 is not
# mount_compat.sh so the legacy CLI footer cannot run before the overrides.
if [ "${0##*/}" = mount_compat.sh ]; then
    _lmcl_command="${1:-status}"
    _lmcl_argument="${2:-}"
    MODDIR="$_lmcl_module" MODULE_DIR="$_lmcl_module" \
    sh -c '
        . "$1" || exit 1
        [ ! -f "$2" ] || . "$2"
        [ ! -f "$3" ] || . "$3"
        [ ! -f "$4" ] || . "$4"
        [ ! -f "$5" ] || . "$5"
        [ ! -f "$6" ] || . "$6"
        [ ! -f "$7" ] || . "$7"
        [ ! -f "$8" ] || . "$8"
        case "$9" in
            status)
                luoshu_mount_status_json
                printf "\n"
                ;;
            detect)
                printf "engine=%s\n" "$(luoshu_detect_mount_engine)"
                printf "backend=%s\n" "$(luoshu_mount_backend)"
                printf "warning=%s\n" "$(luoshu_mount_detection_warning)"
                ;;
            verify)
                luoshu_mount_verify_active "${10}"
                ;;
            *)
                printf "usage: %s {status|detect|verify [font]}\n" "$0" >&2
                exit 2
                ;;
        esac
    ' sh "$_lmcl_base" "$_lmcl_fallback" "$_lmcl_policy" "$_lmcl_private_policy" \
        "$_lmcl_atomic" "$_lmcl_font_runtime" "$_lmcl_font_cleanup" "$_lmcl_font_mount" \
        "$_lmcl_command" "$_lmcl_argument"
    exit $?
fi

[ -f "$_lmcl_base" ] && . "$_lmcl_base"
[ -f "$_lmcl_fallback" ] && . "$_lmcl_fallback"
[ -f "$_lmcl_policy" ] && . "$_lmcl_policy"
[ -f "$_lmcl_private_policy" ] && . "$_lmcl_private_policy"
[ -f "$_lmcl_atomic" ] && . "$_lmcl_atomic"
[ -f "$_lmcl_font_runtime" ] && . "$_lmcl_font_runtime"
[ -f "$_lmcl_font_cleanup" ] && . "$_lmcl_font_cleanup"
[ -f "$_lmcl_font_mount" ] && . "$_lmcl_font_mount"

# Play Store, Google surfaces, Chrome and WebView can open downloadable Latin fonts directly,
# outside Android fonts.xml. Launch the provider bridge only from service.sh; it waits
# for boot completion and applies read-only binds in each consumer mount namespace.
if [ "${0##*/}" = service.sh ] && [ -f "$_lmcl_google_provider" ]; then
    (
        MODDIR="$_lmcl_module" MODULE_DIR="$_lmcl_module" \
            sh "$_lmcl_google_provider" boot >/dev/null 2>&1
    ) &
fi

unset _lmcl_module _lmcl_base _lmcl_fallback _lmcl_policy _lmcl_private_policy \
    _lmcl_atomic _lmcl_font_runtime _lmcl_font_cleanup _lmcl_font_mount \
    _lmcl_google_provider \
    _lmcl_command _lmcl_argument
