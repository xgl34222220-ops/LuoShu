#!/system/bin/sh
# 在 zygote 启动前把用户开关与名单编译成 runtime/config.bin（带本次 boot_id）。
# 任何一步失败都删掉 config.bin：模块读不到配置就只做跳过，不改变任何进程。
MODDIR=${0%/*}
DATA_DIR=/data/adb/luoshu_native_font
MAIN_MODULE=/data/adb/modules/LuoShu
OUT="$MODDIR/runtime/config.bin"
FACES="$MODDIR/runtime/faces.bin"
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
: > "$LOG.faces"
rm -f "$OUT" "$FACES"

enabled=0
[ -f "$DATA_DIR/enabled" ] && enabled=1
# 主模块不在或被禁用/待删除时整体关闭。
if [ ! -d "$MAIN_MODULE" ] || [ -f "$MAIN_MODULE/disable" ] || [ -f "$MAIN_MODULE/remove" ]; then
  enabled=0
fi
verbose=0
[ -f "$DATA_DIR/verbose" ] && verbose=1
# Feature 1（App 自带字体 → 洛书正文字体）：总开关打开时默认随之开启，java_font.off 单独关闭。
java_font=1
[ -f "$DATA_DIR/java_font.off" ] && java_font=0
allow_newer=0
[ -f "$DATA_DIR/allow_newer_api" ] && allow_newer=1

conf_value() {
  sed -n "s/^$2=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

# 洛书当前应用且已验证的正文字体（主模块 payload 里的 LuoShu-NNN.ttf）。只有主模块确认字体已生效
# （active_font 非 default、无待重启、加载验证 verified）才写 faces.bin；否则不写，Feature 1 不安装。
write_faces() {
  cfg="$MAIN_MODULE/config"
  active=$(head -n1 "$cfg/active_font.conf" 2>/dev/null | tr -d '\r\n')
  [ -n "$active" ] && [ "$active" != default ] || return 1
  [ ! -s "$cfg/text_reboot_required.conf" ] || return 1
  [ ! -s "$cfg/font-payload-rebuild-pending.conf" ] || return 1
  [ "$(conf_value "$cfg/device-font-load-verification.conf" state)" = verified ] || return 1
  [ "$(conf_value "$cfg/device-font-load-verification.conf" activeFont)" = "$active" ] || return 1
  case "$(conf_value "$cfg/device-font-load-verification.conf" mode)" in
    aligned|mount-verified|mount-confirmed) ;;
    *) return 1 ;;
  esac
  set --
  for f in "$MAIN_MODULE"/system/fonts/LuoShu-[1-9][0-9][0-9]*.ttf "$MAIN_MODULE"/system/fonts/LuoShu-[1-9][0-9][0-9]*.otf; do
    [ -f "$f" ] && set -- "$@" "$f"
  done
  [ "$#" -gt 0 ] || return 1
  "$TOOL" faces --out "$FACES" "$@"
}

if [ "$enabled" = 1 ] && [ "$java_font" = 1 ]; then
  if write_faces >> "$LOG.faces" 2>&1; then chmod 0644 "$FACES"; else rm -f "$FACES"; fi
fi

set -- build --out "$OUT" --enabled "$enabled" --verbose "$verbose" --java-font "$java_font" \
  --allow-newer-api "$allow_newer" --exclude "$MODDIR/defaults/exclude.list"
[ -f "$DATA_DIR/exclude.list" ] && set -- "$@" --exclude "$DATA_DIR/exclude.list"
[ -f "$DATA_DIR/force.list" ] && set -- "$@" --force "$DATA_DIR/force.list"

if "$TOOL" "$@" > "$LOG" 2>&1; then
  chmod 0644 "$OUT"
else
  rm -f "$OUT"
fi
exit 0
