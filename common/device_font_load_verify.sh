#!/system/bin/sh
# Full visible-byte verification is explicit/post-boot; normal status checks
# reuse only evidence bound to the current boot, selection and output manifest.
set +e

_dfload_module() {
    printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
}

_dfload_run() {
    _dfload_module_dir="$(_dfload_module)"
    _dfload_python_root="$_dfload_module_dir/common/python"
    _dfload_python="$_dfload_python_root/bin/luoshu-python"
    _dfload_helper="$_dfload_module_dir/common/physical_font_load_verify.py"
    if [ -x "$_dfload_python" ] && [ -f "$_dfload_helper" ]; then
        PYTHONHOME="$_dfload_python_root" \
        PYTHONPATH="$_dfload_module_dir/common:$_dfload_python_root/lib/python3.14:$_dfload_python_root/lib/python3.14/site-packages" \
        LD_LIBRARY_PATH="$_dfload_python_root/lib:$_dfload_python_root/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
            "$_dfload_python" "$_dfload_helper" --module "$_dfload_module_dir" "$1"
        return $?
    fi
    # A missing runtime is not proof of failure or success. Retain all payloads.
    _dfload_active=$(head -n1 "$_dfload_module_dir/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    mkdir -p "$_dfload_module_dir/config" 2>/dev/null || return 2
    {
        printf 'state=pending\nmode=physical-evidence\nreason=verifier-unavailable\n'
        printf 'activeFont=%s\n' "${_dfload_active:-default}"
    } > "$_dfload_module_dir/config/device-font-load-verification.conf.tmp.$$" && \
        mv -f "$_dfload_module_dir/config/device-font-load-verification.conf.tmp.$$" \
            "$_dfload_module_dir/config/device-font-load-verification.conf"
    return 2
}

device_font_load_status() { _dfload_run status; }
device_font_load_verify() { _dfload_run verify; }

if [ "${0##*/}" = device_font_load_verify.sh ]; then
    case "${1:-status}" in
        status|auto) device_font_load_status ;;
        verify|deep) device_font_load_verify ;;
        *) printf 'usage: %s {status|verify}\n' "$0" >&2; exit 2 ;;
    esac
fi
