#!/system/bin/sh
# Root 管理器“操作”按钮：安装或更新模块内置的洛书 App。

MODDIR="${0%/*}"
APK="$MODDIR/bundled/LuoShu-App.apk"
LOG="$MODDIR/logs/app-install.log"

mkdir -p "$MODDIR/logs" 2>/dev/null || true

print_line() {
    if type ui_print >/dev/null 2>&1; then
        ui_print "$1"
    else
        echo "$1"
    fi
}

if [ ! -s "$APK" ]; then
    print_line "未找到模块内置的洛书 App。"
    print_line "请重新下载带 App 的完整模块包。"
    exit 1
fi

if ! command -v pm >/dev/null 2>&1; then
    print_line "当前环境无法调用 Android 包管理器。"
    exit 1
fi

print_line "正在安装洛书 App…"
_result="$(pm install -r -d --user 0 "$APK" 2>&1)"
_code=$?
printf '%s\n' "$_result" > "$LOG" 2>/dev/null || true

if [ "$_code" -eq 0 ] && printf '%s' "$_result" | grep -q 'Success'; then
    print_line "洛书 App 已安装或更新。"
    exit 0
fi

print_line "App 安装失败，详情已写入："
print_line "$LOG"
print_line "若提示签名不一致，请先卸载旧测试版 App 后重试。"
exit 1
