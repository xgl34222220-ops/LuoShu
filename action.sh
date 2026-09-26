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

open_bundled_app() {
    _package=$(sed -n 's/^package=//p' "$MODDIR/bundled/app.prop" 2>/dev/null | head -n1)
    case "$_package" in
        io.github.xgl34222220.luoshu|io.github.xgl34222220.luoshu.debug|io.github.xgl34222220.luoshu.preview) ;;
        *) print_line "App 包名无效，未启动。"; return 1 ;;
    esac
    if command -v am >/dev/null 2>&1; then
        am start -n "$_package/io.github.xgl34222220.luoshu.MainActivity" >/dev/null 2>&1 && return 0
    fi
    if [ "$_package" = io.github.xgl34222220.luoshu.preview ]; then
        print_line "请从桌面打开“洛书测试版”。"
    else
        print_line "请从桌面打开洛书 App。"
    fi
}

if [ ! -s "$APK" ]; then
    print_line "未找到模块内置的洛书 App。"
    print_line "请重新下载并刷入完整的洛书模块包。"
    exit 1
fi

if [ ! -f "$HELPER" ]; then
    print_line "模块内置 App 安装器缺失。"
    print_line "请重新刷入洛书模块包。"
    exit 1
fi

print_line "正在检查洛书 App 版本…"
_result=$(MODDIR="$MODDIR" APP_INSTALL_LOG="$LOG" sh "$HELPER" manual 2>/dev/null)
_code=$?
case "$_result" in
    installed)
        rm -f "$MODDIR/config/app_install_manual" 2>/dev/null || true
        if grep -qx 'package=io.github.xgl34222220.luoshu.preview' "$MODDIR/bundled/app.prop" 2>/dev/null; then
            print_line "洛书测试版已安装或更新。"
        else
            print_line "洛书 App 已安装或更新，原有数据和界面设置已保留。"
        fi
        open_bundled_app
        exit 0
        ;;
    already-current)
        rm -f "$MODDIR/config/app_install_manual" 2>/dev/null || true
        print_line "洛书 App 已是模块内置的当前版本。"
        open_bundled_app
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
        print_line "若提示签名不一致，请保留旧 App 并检查安装包版本。"
        print_line "错误代码：$_code"
        exit 1
        ;;
esac
