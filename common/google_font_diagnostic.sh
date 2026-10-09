#!/system/bin/sh
# Read-only, one-shot collection. Do not initialize/migrate runtime or undo paths.
set -eu
HERE=$(CDPATH= cd -P -- "$(dirname -- "$0")" && pwd)
MODDIR="${MODDIR:-${MODULE_DIR:-${HERE%/*}}}"
export MODDIR
PYROOT="$HERE/python"
if [ ! -x "$PYROOT/bin/luoshu-python" ]; then
    printf '%s\n' '{"status":"error","message":"Google 字体诊断运行环境缺失。"}'
    exit 1
fi
export PYTHONHOME="$PYROOT"
export PYTHONPATH="$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages"
export PYTHONDONTWRITEBYTECODE=1
export LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$PYROOT/bin/luoshu-python" "$HERE/google_font_diagnostic.py" "$@"
