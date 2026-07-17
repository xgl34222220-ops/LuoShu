#!/system/bin/sh
# 洛书 v14.1：设备字体能力与模块持久化状态。
set +e
MODDIR="${MODDIR:-/data/adb/modules/LuoShu}"
json_escape(){ printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '; }
ROM=generic; ROM_NAME='通用 Android'; DIGIT=false; CJK=true; LATIN=true
if [ -n "$(getprop ro.mi.os.version.name 2>/dev/null)" ] || [ -n "$(getprop ro.miui.ui.version.name 2>/dev/null)" ]; then ROM=hyperos; ROM_NAME='HyperOS / MIUI'; DIGIT=true
elif [ -n "$(getprop ro.build.version.oplusrom 2>/dev/null)" ] || [ -n "$(getprop ro.build.version.opporom 2>/dev/null)" ]; then ROM=coloros; ROM_NAME='ColorOS / OxygenOS / realme UI'; DIGIT=true
fi
ROOT='Root'; APATCH=false
if command -v apd >/dev/null 2>&1 || [ -d /data/adb/ap ] || [ -d /data/adb/apatch ]; then ROOT=APatch; APATCH=true
elif command -v ksud >/dev/null 2>&1 || [ -d /data/adb/ksu ]; then
    _info="$(ksud -V 2>/dev/null || ksud --version 2>/dev/null || true)"; case "$_info $(getprop ro.build.version.incremental 2>/dev/null)" in *SukiSU*|*sukisu*|*SUKISU*) ROOT='SukiSU Ultra' ;; *) ROOT=KernelSU ;; esac
elif command -v magisk >/dev/null 2>&1 || [ -d /data/adb/magisk ]; then ROOT=Magisk
fi
MOUNT='原生模块挂载'; [ -d /data/adb/modules/mountify ] && [ ! -f /data/adb/modules/mountify/disable ] && [ ! -f /data/adb/modules/mountify/remove ] && MOUNT=Mountify
PERSIST=true; PERSIST_MESSAGE='模块目录正常'
[ -f "$MODDIR/module.prop" ] || { PERSIST=false; PERSIST_MESSAGE='模块目录缺少 module.prop'; }
[ -f "$MODDIR/remove" ] && { PERSIST=false; PERSIST_MESSAGE='检测到 remove 标记，重启会卸载模块'; }
[ -f "$MODDIR/disable" ] && PERSIST_MESSAGE='模块当前已禁用'
GMS=false; XWEB=false
command -v pm >/dev/null 2>&1 && pm path com.google.android.gms >/dev/null 2>&1 && GMS=true
command -v pm >/dev/null 2>&1 && pm path com.tencent.mm >/dev/null 2>&1 && XWEB=true
printf '{"status":"ok","data":{"rom":"%s","romName":"%s","root":"%s","mount":"%s","apatch":%s,"persistent":%s,"persistentMessage":"%s","cjkIndependent":%s,"latinIndependent":%s,"digitIndependent":%s,"gms":%s,"xweb":%s}}\n' \
 "$(json_escape "$ROM")" "$(json_escape "$ROM_NAME")" "$(json_escape "$ROOT")" "$(json_escape "$MOUNT")" "$APATCH" "$PERSIST" "$(json_escape "$PERSIST_MESSAGE")" "$CJK" "$LATIN" "$DIGIT" "$GMS" "$XWEB"
