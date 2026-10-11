#!/system/bin/sh
# Bounded top-level JSON "message" reader (see json_error_message.py).
# Usage: luoshu_json_error_message FILE   or   ... | luoshu_json_error_message -
# Infrequent failure paths only; progress polling never starts Python.
luoshu_json_error_message() (
    # The legacy mix runtime is a link farm; the real module always has both
    # the helper and the bundled interpreter.
    _ljem_mod=''
    for _ljem_base in "${MODDIR:-}" "${LUOSHU_REAL_MODDIR:-}"; do
        [ -n "$_ljem_base" ] && [ -f "$_ljem_base/common/json_error_message.py" ] || continue
        _ljem_mod="$_ljem_base"; break
    done
    [ -n "$_ljem_mod" ] || return 1
    _ljem_program="$_ljem_mod/common/json_error_message.py"
    # Host tests reuse the existing task-scope interpreter override.
    _ljem_python="${LUOSHU_JSON_MESSAGE_PYTHON:-${LUOSHU_TASK_SCOPE_PYTHON:-}}"
    if [ -z "$_ljem_python" ]; then
        _ljem_root="$_ljem_mod/common/python"
        _ljem_python="$_ljem_root/bin/luoshu-python"
        [ -x "$_ljem_python" ] || return 1
        export PYTHONHOME="$_ljem_root"
        export PYTHONPATH="$_ljem_root/lib/python3.14:$_ljem_root/lib/python3.14/site-packages"
        export LD_LIBRARY_PATH="$_ljem_root/lib:$_ljem_root/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    fi
    exec "$_ljem_python" "$_ljem_program" "$@"
)
