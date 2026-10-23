#!/system/bin/sh
# LuoShu fs-verity wrapper for protected updatable fonts (/data/fonts).
#
# Source this file and call:
#   luoshu_font_verity enable|measure|compare ARGS...
#   luoshu_font_protected_path PATH   -> true when PATH lies under the protected root
# The one-line output and exit codes are those of common/font_verity.py
# (0 ok, 3 unsupported, 4 verity off, 5 mismatch, 1 error).
# LUOSHU_FONT_VERITY_PYTHON overrides the interpreter (tests, host tools).

LUOSHU_FONT_VERITY_ROOT="${LUOSHU_FONT_VERITY_ROOT:-${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}}"
LUOSHU_PROTECTED_FONT_ROOT="${LUOSHU_PROTECTED_FONT_ROOT:-/data/fonts}"

luoshu_font_protected_path() {
    _lfv_root="${LUOSHU_PROTECTED_FONT_ROOT%/}"
    [ -n "$_lfv_root" ] || return 1
    case "$1" in "$_lfv_root"/*) return 0 ;; esac
    return 1
}

luoshu_font_verity() {
    _lfv_script="$LUOSHU_FONT_VERITY_ROOT/common/font_verity.py"
    [ -f "$_lfv_script" ] || { printf 'error:helper-missing\n'; return 1; }
    _lfv_pyroot="$LUOSHU_FONT_VERITY_ROOT/common/python"
    _lfv_python="${LUOSHU_FONT_VERITY_PYTHON:-${LUOSHU_GOOGLE_FONT_PYTHON:-$_lfv_pyroot/bin/luoshu-python}}"
    if [ "$_lfv_python" = "$_lfv_pyroot/bin/luoshu-python" ]; then
        [ -x "$_lfv_python" ] || { printf 'error:python-missing\n'; return 1; }
        PYTHONHOME="$_lfv_pyroot" \
        PYTHONPATH="$_lfv_pyroot/lib/python3.14:$_lfv_pyroot/lib/python3.14/site-packages" \
        LD_LIBRARY_PATH="$_lfv_pyroot/lib:$_lfv_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
            "$_lfv_python" "$_lfv_script" "$@"
    else
        "$_lfv_python" "$_lfv_script" "$@"
    fi
}

if [ "${0##*/}" = font_verity.sh ]; then
    luoshu_font_verity "$@"
fi
