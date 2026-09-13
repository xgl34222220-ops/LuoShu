#!/system/bin/sh
# Explicit UI action only. Never enable on install or boot.
set -eu
HERE=${0%/*}
PYROOT="$HERE/python"
case "${1:-status}" in status|enable|restore|restore-owned) ;; *)
    printf '%s\n' '{"status":"error","message":"不支持的 Google 字体操作。"}'; exit 2;;
esac
if [ "$(id -u)" != 0 ]; then
    printf '%s\n' '{"status":"error","message":"请在 Root 管理器中为洛书授予 Root 权限。"}'; exit 1
fi
if [ ! -x "$PYROOT/bin/luoshu-python" ]; then
    printf '%s\n' '{"status":"error","message":"模块运行环境缺失，请安装配套模块并完整重启。"}'; exit 1
fi
export PYTHONHOME="$PYROOT"
export PYTHONPATH="$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages"
export LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$PYROOT/bin/luoshu-python" "$HERE/google_font_fallback.py" "$@"
