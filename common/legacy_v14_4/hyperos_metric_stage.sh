#!/system/bin/sh
# HyperOS staged metric alignment for the safe next-boot payload path.
# Never touches the payload mounted by the current boot.
set +e

_lhms_module_dir() {
    printf '%s\n' "${LUOSHU_REAL_MODDIR:-${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}}"
}

_lhms_role_for_target() {
    _lhms_lower=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
    case "$_lhms_lower" in
        *mono*) printf 'mono\n' ;;
        *clock*|clockopia.ttf) printf 'clock\n' ;;
        *) printf 'ui\n' ;;
    esac
}

_lhms_source_key() {
    _lhms_source="$1"
    if command -v stat >/dev/null 2>&1; then
        _lhms_key=$(stat -c '%d-%i-%s-%Y' "$_lhms_source" 2>/dev/null)
    elif command -v toybox >/dev/null 2>&1; then
        _lhms_key=$(toybox stat -c '%d-%i-%s-%Y' "$_lhms_source" 2>/dev/null)
    else
        _lhms_key=''
    fi
    if [ -z "$_lhms_key" ]; then
        _lhms_key=$(basename "$_lhms_source" | tr -c 'A-Za-z0-9._-' '_')
    fi
    printf '%s\n' "$_lhms_key" | tr -c 'A-Za-z0-9._-' '_'
}

_lhms_stock_for_target() {
    _lhms_name="$1"
    _lhms_state="${LUOSHU_SELF_MOUNT_STATE_ROOT:-/data/adb/luoshu/self-mount}"
    for _lhms_part in system system_ext product mi_ext vendor odm oem my_product hw_product cust; do
        for _lhms_candidate in \
            "$_lhms_state/lower/${_lhms_part}-fonts/$_lhms_name" \
            "/debug_ramdisk/.magisk/mirror/${_lhms_part}/fonts/$_lhms_name" \
            "/sbin/.magisk/mirror/${_lhms_part}/fonts/$_lhms_name" \
            "/data/adb/magisk/mirror/${_lhms_part}/fonts/$_lhms_name"; do
            [ -s "$_lhms_candidate" ] || continue
            printf '%s\n' "$_lhms_candidate"
            return 0
        done
    done
    return 1
}

_lhms_python_align() {
    _lhms_source="$1"; _lhms_output="$2"; _lhms_role="$3"; _lhms_stock="$4"
    _lhms_module="$(_lhms_module_dir)"
    _lhms_pyroot="$_lhms_module/common/python"
    _lhms_python="$_lhms_pyroot/bin/luoshu-python"
    _lhms_helper="$_lhms_module/common/legacy_v14_4/hyperos_metric_align.py"
    _lhms_inventory="$_lhms_module/config/device_font_inventory.json"
    [ -x "$_lhms_python" ] && [ -f "$_lhms_helper" ] || return 1

    set -- --source "$_lhms_source" --output "$_lhms_output" --role "$_lhms_role" --inventory "$_lhms_inventory"
    [ -n "$_lhms_stock" ] && set -- "$@" --stock "$_lhms_stock"
    PYTHONHOME="$_lhms_pyroot" \
    PYTHONPATH="$_lhms_module/common:$_lhms_module/common/legacy_v14_4:$_lhms_pyroot/lib/python3.14:$_lhms_pyroot/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$_lhms_pyroot/lib:$_lhms_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$_lhms_python" "$_lhms_helper" "$@" >/dev/null 2>&1
}

# Usage: luoshu_hyperos_stage_metric_anchor SOURCE TARGET_NAME STAGE_FONT_DIR
# Prints an aligned font path on success. UI fonts share one normalized cache per source;
# clock/mono fonts keep a target-specific cache because their stock contracts differ.
luoshu_hyperos_stage_metric_anchor() {
    _lhms_source="$1"; _lhms_target="$2"; _lhms_stage_fonts="$3"
    [ -s "$_lhms_source" ] && [ -n "$_lhms_target" ] && [ -d "$_lhms_stage_fonts" ] || return 1
    _lhms_role=$(_lhms_role_for_target "$_lhms_target")
    _lhms_key=$(_lhms_source_key "$_lhms_source")
    _lhms_store="$_lhms_stage_fonts/.luoshu-font-store"
    mkdir -p "$_lhms_store" 2>/dev/null || return 1

    if [ "$_lhms_role" = ui ]; then
        _lhms_output="$_lhms_store/hyperos-ui-${_lhms_key}.font"
        _lhms_stock=''
    else
        _lhms_safe_target=$(printf '%s' "$_lhms_target" | tr -c 'A-Za-z0-9._-' '_')
        _lhms_output="$_lhms_store/hyperos-${_lhms_role}-${_lhms_safe_target}-${_lhms_key}.font"
        _lhms_stock=$(_lhms_stock_for_target "$_lhms_target" 2>/dev/null || true)
    fi

    if [ -s "$_lhms_output" ]; then
        printf '%s\n' "$_lhms_output"
        return 0
    fi
    rm -f "$_lhms_output" 2>/dev/null || true
    if _lhms_python_align "$_lhms_source" "$_lhms_output" "$_lhms_role" "$_lhms_stock" && [ -s "$_lhms_output" ]; then
        chmod 0644 "$_lhms_output" 2>/dev/null || true
        printf '%s\n' "$_lhms_output"
        return 0
    fi
    rm -f "$_lhms_output" 2>/dev/null || true
    return 1
}
