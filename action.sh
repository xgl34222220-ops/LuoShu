#!/system/bin/sh
# Root 管理器“操作”按钮：检查并安装或更新模块内置的洛书 App。

MODDIR="${0%/*}"
APK="$MODDIR/bundled/LuoShu-App.apk"
HELPER="$MODDIR/common/app_installer.sh"
LOG="$MODDIR/logs/app-install.log"

mkdir -p "$MODDIR/logs" "$MODDIR/config" 2>/dev/null || true

print_line() {
    if type ui_print >/dev/null 2>&1; then
        ui_print "$1"
    else
        echo "$1"
    fi
}

if [ ! -s "$APK" ]; then
    print_line "未找到模块内置的洛书 App。"
    print_line "请重新下载带 App 的 Full 模块包。"
    exit 1
fi

if [ ! -f "$HELPER" ]; then
    print_line "模块内置 App 安装器缺失。"
    print_line "请重新刷入完整模块包。"
    exit 1
fi

print_line "正在检查洛书 App 版本…"
_result=$(MODDIR="$MODDIR" APP_INSTALL_LOG="$LOG" sh "$HELPER" manual 2>/dev/null)
_code=$?
case "$_result" in
    installed)
        rm -f "$MODDIR/config/app_install_manual" 2>/dev/null || true
        print_line "洛书 App 已安装或更新，原有数据和界面设置已保留。"
        exit 0
        ;;
    already-current)
        rm -f "$MODDIR/config/app_install_manual" 2>/dev/null || true
        print_line "洛书 App 已是模块内置的当前版本。"
        exit 0
        ;;
    deferred)
        print_line "当前环境无法调用 Android 包管理器。"
        print_line "请在系统启动完成后再次点击模块“操作”按钮。"
        exit 1
        ;;
    *)
        print_line "App 安装或更新失败，详情已写入："
        print_line "$LOG"
        print_line "若提示签名不一致，请先卸载旧测试版 App 后重试。"
        print_line "错误代码：$_code"
        exit 1
        ;;
esac
