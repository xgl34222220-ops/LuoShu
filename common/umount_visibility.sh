#!/system/bin/sh
# Read-only umount visibility facts for the coverage export (umountVisibility).
#
#   facts    key=value lines: root manager + version, KernelSU kernel_umount /
#            webview_zygote_umount, Magisk Zygisk/DenyList switches, installed
#            Zygisk implementations (ZygiskNext / ReZygisk / NeoZygisk), modules
#            that manage kernel_umount, dmesg umount counters, preload companion.
#
# Nothing here changes a setting, a mount or a module: only `ksud feature get`,
# `ksud debug version`, `-V/-v` version queries, `magisk --sqlite "SELECT ..."`,
# `dmesg` (read) and module.prop reads. common/umount_visibility.py turns these
# facts plus /proc/<pid>/mountinfo into the report section.
set +e

UV_MODULES="${LUOSHU_UMOUNT_MODULES_DIR:-/data/adb/modules}"
UV_PRELOAD_ID="${LUOSHU_UMOUNT_PRELOAD_ID:-LuoShuFontPreload}"

_uv_clean() {
    # One line, no separators that would break key=value, bounded length.
    printf '%s' "$1" | tr '\r\n\t|=' '     ' | sed 's/[^A-Za-z0-9 ._+()/:-]//g; s/  */ /g; s/^ //; s/ $//' | cut -c1-80
}

_uv_timeout() {
    if command -v timeout >/dev/null 2>&1; then
        timeout 5 "$@"
    else
        "$@"
    fi
}

_uv_bin() {
    for _uv_c in "$@"; do
        case "$_uv_c" in
            /*) [ -x "$_uv_c" ] && { printf '%s\n' "$_uv_c"; return 0; } ;;
            *) command -v "$_uv_c" 2>/dev/null && return 0 ;;
        esac
    done
    return 1
}

# kernel_umount / webview_zygote_umount through `ksud feature get <name>`:
# "Value: N" -> N; "... is not supported by kernel" -> unsupported.
_uv_ksu_feature() {
    _uv_out=$(_uv_timeout "$1" feature get "$2" 2>&1)
    case "$_uv_out" in
        *"not supported"*) printf 'unsupported\n'; return 0 ;;
    esac
    _uv_val=$(printf '%s\n' "$_uv_out" | sed -n 's/^Value:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -n1)
    printf '%s\n' "${_uv_val:-unknown}"
}

_uv_magisk_setting() {
    _uv_out=$(_uv_timeout "$1" --sqlite "SELECT value FROM settings WHERE key='$2'" 2>/dev/null)
    _uv_rc=$?
    _uv_val=$(printf '%s\n' "$_uv_out" | sed -n 's/^value=\([0-9][0-9]*\).*/\1/p' | head -n1)
    # Magisk keeps defaults out of the table (zygisk/denylist default off).
    [ -z "$_uv_val" ] && [ "$_uv_rc" -eq 0 ] && _uv_val=default
    printf '%s\n' "${_uv_val:-unknown}"
}

_uv_prop() {
    sed -n "s/^$2=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r'
}

_uv_module_state() {
    if [ -f "$1/remove" ]; then printf 'remove\n'
    elif [ -f "$1/disable" ]; then printf 'disabled\n'
    else printf 'enabled\n'
    fi
}

uv_facts() {
    printf 'schema=luoshu-umount-facts-v1\n'
    _uv_ksud=$(_uv_bin ksud /data/adb/ksud)
    _uv_apd=$(_uv_bin apd /data/adb/apd)
    _uv_magisk=$(_uv_bin magisk /data/adb/magisk/magisk64 /data/adb/magisk/magisk32)

    _uv_manager=unknown
    if [ -n "$_uv_apd" ] || [ -d /data/adb/ap ]; then
        _uv_manager=APatch
    elif [ -n "$_uv_ksud" ] || [ -d /data/adb/ksu ]; then
        _uv_manager=KernelSU
    elif [ -n "$_uv_magisk" ] || [ -d /data/adb/magisk ]; then
        _uv_manager=Magisk
    fi
    printf 'manager=%s\n' "$_uv_manager"

    if [ -n "$_uv_ksud" ]; then
        _uv_v=$(_uv_timeout "$_uv_ksud" -V 2>/dev/null | head -n1)
        printf 'ksudVersion=%s\n' "$(_uv_clean "$_uv_v")"
        _uv_kv=$(_uv_timeout "$_uv_ksud" debug version 2>/dev/null | sed -n 's/.*Kernel Version:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -n1)
        printf 'ksuKernelVersion=%s\n' "${_uv_kv:-unknown}"
        printf 'kernelUmount=%s\n' "$(_uv_ksu_feature "$_uv_ksud" kernel_umount)"
        printf 'webviewZygoteUmount=%s\n' "$(_uv_ksu_feature "$_uv_ksud" webview_zygote_umount)"
    fi
    if [ -n "$_uv_apd" ]; then
        _uv_v=$(_uv_timeout "$_uv_apd" -V 2>/dev/null | head -n1)
        printf 'apdVersion=%s\n' "$(_uv_clean "$_uv_v")"
    fi
    if [ -n "$_uv_magisk" ]; then
        _uv_v=$(_uv_timeout "$_uv_magisk" -v 2>/dev/null | head -n1)
        _uv_vc=$(_uv_timeout "$_uv_magisk" -V 2>/dev/null | head -n1)
        printf 'magiskVersion=%s\n' "$(_uv_clean "$_uv_v ${_uv_vc}")"
        printf 'magiskZygisk=%s\n' "$(_uv_magisk_setting "$_uv_magisk" zygisk)"
        printf 'magiskDenylist=%s\n' "$(_uv_magisk_setting "$_uv_magisk" denylist)"
    fi

    # Zygisk implementations and mount hiders. NeoZygisk and ZygiskNext both use
    # the module id zygisksu, so the name decides.
    _uv_managed=''
    for _uv_dir in "$UV_MODULES"/*; do
        [ -f "$_uv_dir/module.prop" ] || continue
        _uv_id=$(_uv_prop "$_uv_dir/module.prop" id)
        [ -n "$_uv_id" ] || _uv_id=${_uv_dir##*/}
        _uv_name=$(_uv_prop "$_uv_dir/module.prop" name)
        _uv_ver=$(_uv_prop "$_uv_dir/module.prop" version)
        _uv_features=$(_uv_prop "$_uv_dir/module.prop" managedFeatures)
        _uv_state=$(_uv_module_state "$_uv_dir")
        case ",$_uv_features," in
            *,kernel_umount,*) [ "$_uv_state" = enabled ] && _uv_managed="$_uv_managed $(_uv_clean "$_uv_id")" ;;
        esac
        case "$_uv_id" in
            zygisksu|zygisk_next|zygisknext|zygisk-next|rezygisk|neozygisk|zygisk_neozygisk)
                printf 'zygiskModule=%s|%s|%s|%s\n' "$(_uv_clean "$_uv_id")" "$(_uv_clean "$_uv_name")" \
                    "$(_uv_clean "$_uv_ver")" "$_uv_state"
                ;;
            zygisk_shamiko|shamiko|zygisk-assistant|zygisk_assistant)
                printf 'hiderModule=%s|%s|%s|%s\n' "$(_uv_clean "$_uv_id")" "$(_uv_clean "$_uv_name")" \
                    "$(_uv_clean "$_uv_ver")" "$_uv_state"
                ;;
        esac
    done
    printf 'kernelUmountManagedBy=%s\n' "$(printf '%s' "$_uv_managed" | sed 's/^ //')"

    if [ -d "$UV_MODULES/$UV_PRELOAD_ID" ]; then
        printf 'preloadModule=%s\n' "$(_uv_module_state "$UV_MODULES/$UV_PRELOAD_ID")"
    else
        printf 'preloadModule=absent\n'
    fi

    # KernelSU logs one "handle umount for uid" per unmounted zygote child and one
    # "unmounting: <path>" per mount point (kernel_umount.c). Counts only.
    _uv_dmesg=$(_uv_timeout dmesg 2>/dev/null)
    if [ -n "$_uv_dmesg" ]; then
        printf 'dmesgReadable=1\n'
        printf 'dmesgUmountUid=%s\n' "$(printf '%s\n' "$_uv_dmesg" | grep -c 'handle umount for uid')"
        printf 'dmesgUmountFonts=%s\n' "$(printf '%s\n' "$_uv_dmesg" | grep 'unmounting:' | grep -c 'font')"
    else
        printf 'dmesgReadable=0\n'
    fi
}

case "${1:-facts}" in
    facts) uv_facts ;;
    *) printf 'error=unknown-command\n' ;;
esac
exit 0
