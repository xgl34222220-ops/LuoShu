#!/system/bin/sh
# 洛书 fs-verity 工具入口：只给模块自有的 /data/fonts 替换字体开启并测量 fs-verity。
# 移植自 字域 Ziyu v1.4.8 common/font_verity.sh（作者 酷安@柔性体，GPL-3.0-only）。
# 也会经 /proc/1/root 从其他 mount namespace 调用，因此只用相对 $0 的路径。
# 退出码：0 成功，1 失败，3 内核/文件系统不支持 fs-verity（调用方必须放弃该受保护目标）。
_fv_mod="${0%/*}/.."
_fv_root="$_fv_mod/common/python"
if [ -n "${LUOSHU_FONT_VERITY_PYTHON:-}" ]; then
    exec "$LUOSHU_FONT_VERITY_PYTHON" "$_fv_mod/common/font_verity.py" "$@"
fi
PYTHONHOME="$_fv_root" PYTHONPATH="$_fv_root/lib/python3.14:$_fv_root/lib/python3.14/site-packages" \
LD_LIBRARY_PATH="$_fv_root/lib:$_fv_root/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    exec "$_fv_root/bin/luoshu-python" "$_fv_mod/common/font_verity.py" "$@"
