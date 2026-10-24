#!/system/bin/sh
# 洛书 Native 字体伴随模块安装脚本。不挂载任何文件（skip_mount），不触碰主模块。
SKIPUNZIP=0
DATA_DIR=/data/adb/luoshu_native_font

case "$ARCH" in
  arm64) ABI=arm64-v8a ;;
  arm) ABI=armeabi-v7a ;;
  x64) ABI=x86_64 ;;
  x86) ABI=x86 ;;
  *) abort "! 不支持的架构：$ARCH" ;;
esac

[ -f "$MODPATH/zygisk/$ABI.so" ] || abort "! 缺少 zygisk/$ABI.so"
[ -x "$MODPATH/bin/$ABI/lsnf-config" ] || chmod 0755 "$MODPATH/bin/$ABI/lsnf-config"

ui_print "- 洛书 Native 字体（实验）N3：App 自带字体 → 洛书正文字体"
ui_print "-   Java 层替换 Font\$Builder.nBuild（Android 12–17 / API 31–37）"
ui_print "-   图标、等宽、彩色字体保留；洛书主模块字体未验证生效时自动让出"
ui_print "- 需要 Zygisk（Magisk 内置 Zygisk / ZygiskNext / ReZygisk）"
ui_print "- 默认关闭。开启：touch $DATA_DIR/enabled 后重启"
ui_print "-   单独关闭 Java 层替换：touch $DATA_DIR/java_font.off"
ui_print "-   查看日志：touch $DATA_DIR/verbose，然后 logcat -s LuoShuNativeFont"

mkdir -p "$DATA_DIR"
[ -f "$DATA_DIR/exclude.list" ] || cp "$MODPATH/defaults/exclude.list" "$DATA_DIR/exclude.list"
[ -f "$DATA_DIR/force.list" ] || : > "$DATA_DIR/force.list"
mkdir -p "$MODPATH/runtime"
touch "$MODPATH/skip_mount"

set_perm_recursive "$MODPATH" 0 0 0755 0644
set_perm_recursive "$MODPATH/bin" 0 0 0755 0755
set_perm_recursive "$DATA_DIR" 0 0 0700 0600
