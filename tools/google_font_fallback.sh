#!/system/bin/sh
# Optional maintenance tool; no automatic enable, boot hook, or font files.
set -eu
PYROOT=/data/adb/modules/LuoShu/common/python
[ "$(id -u)" = 0 ] || { echo '需要 Root。' >&2; exit 1; }
[ -x "$PYROOT/bin/luoshu-python" ] || { echo '请保留已安装的洛书模块运行环境，先恢复开关再卸载模块。' >&2; exit 1; }
export PYTHONHOME="$PYROOT"
export PYTHONPATH="$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages"
export LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$PYROOT/bin/luoshu-python" "${0%/*}/google_font_fallback.py" "$@"
