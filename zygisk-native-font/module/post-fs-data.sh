#!/system/bin/sh
# 在 zygote 启动前把用户开关与名单编译成 runtime/config.bin（带本次 boot_id）。
# 任何一步失败都删掉 config.bin：模块读不到配置就只做跳过，不改变任何进程。
MODDIR=${0%/*}
DATA_DIR=/data/adb/luoshu_native_font
MAIN_MODULE=/data/adb/modules/LuoShu
OUT="$MODDIR/runtime/config.bin"
LOG="$MODDIR/runtime/config.log"

case "$(getprop ro.product.cpu.abi)" in
  arm64-v8a) ABI=arm64-v8a ;;
  armeabi-v7a|armeabi) ABI=armeabi-v7a ;;
  x86_64) ABI=x86_64 ;;
  x86) ABI=x86 ;;
  *) ABI=arm64-v8a ;;
esac
TOOL="$MODDIR/bin/$ABI/lsnf-config"

mkdir -p "$MODDIR/runtime"
rm -f "$OUT"

enabled=0
[ -f "$DATA_DIR/enabled" ] && enabled=1
# 主模块不在或被禁用/待删除时整体关闭。
if [ ! -d "$MAIN_MODULE" ] || [ -f "$MAIN_MODULE/disable" ] || [ -f "$MAIN_MODULE/remove" ]; then
  enabled=0
fi
verbose=0
[ -f "$DATA_DIR/verbose" ] && verbose=1

set -- build --out "$OUT" --enabled "$enabled" --verbose "$verbose" --exclude "$MODDIR/defaults/exclude.list"
[ -f "$DATA_DIR/exclude.list" ] && set -- "$@" --exclude "$DATA_DIR/exclude.list"
[ -f "$DATA_DIR/force.list" ] && set -- "$@" --force "$DATA_DIR/force.list"

if "$TOOL" "$@" > "$LOG" 2>&1; then
  chmod 0644 "$OUT"
else
  rm -f "$OUT"
fi
exit 0
