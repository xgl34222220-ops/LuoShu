#!/system/bin/sh
# 洛书 v14.1 - 设备、APatch 持久化与字体诊断报告
set +e
MODDIR="${MODDIR:-/data/adb/modules/LuoShu}"
[ -f "$MODDIR/common/font_check.sh" ] && . "$MODDIR/common/font_check.sh"
FONT="$1"
OUT="${2:-/sdcard/LuoShu/reports/LuoShu_Font_Report_$(date +%Y%m%d_%H%M%S).txt}"
mkdir -p "${OUT%/*}" 2>/dev/null || true
ROOT_MANAGER="Root"
if command -v apd >/dev/null 2>&1 || [ -d /data/adb/ap ] || [ -d /data/adb/apatch ]; then ROOT_MANAGER="APatch"
elif command -v ksud >/dev/null 2>&1 || [ -d /data/adb/ksu ]; then
    _info="$(ksud -V 2>/dev/null || ksud --version 2>/dev/null || true)"; case "$_info $(getprop ro.build.version.incremental 2>/dev/null)" in *SukiSU*|*sukisu*|*SUKISU*) ROOT_MANAGER="SukiSU Ultra" ;; *) ROOT_MANAGER="KernelSU" ;; esac
elif command -v magisk >/dev/null 2>&1 || [ -d /data/adb/magisk ]; then ROOT_MANAGER="Magisk"; fi
MOUNT_ENV="原生模块挂载"
[ -d /data/adb/modules/mountify ] && [ ! -f /data/adb/modules/mountify/disable ] && [ ! -f /data/adb/modules/mountify/remove ] && MOUNT_ENV="Mountify"
PERSISTENCE="normal"
[ -f "$MODDIR/remove" ] && PERSISTENCE="remove marker present"
[ -f "$MODDIR/disable" ] && PERSISTENCE="disabled"
[ -f "$MODDIR/module.prop" ] || PERSISTENCE="module.prop missing"
CAPABILITY=""
[ -f "$MODDIR/common/device_capabilities.sh" ] && CAPABILITY=$(MODDIR="$MODDIR" sh "$MODDIR/common/device_capabilities.sh" 2>/dev/null)
{
    echo "LuoShu Font Report v14.1"
    echo "Generated: $(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)"
    echo "Device: $(getprop ro.product.manufacturer 2>/dev/null) $(getprop ro.product.model 2>/dev/null)"
    echo "Android: $(getprop ro.build.version.release 2>/dev/null) (SDK $(getprop ro.build.version.sdk 2>/dev/null))"
    echo "ROM: ColorOS=$(getprop ro.build.version.oplusrom 2>/dev/null) HyperOS=$(getprop ro.mi.os.version.name 2>/dev/null)"
    echo "Root manager: $ROOT_MANAGER"
    echo "Mount environment: $MOUNT_ENV"
    echo "Module directory: $MODDIR"
    echo "Module persistence: $PERSISTENCE"
    echo "Install environment: $(tr '\n' ' ' < "$MODDIR/config/install_environment.conf" 2>/dev/null)"
    echo "Capability JSON: $CAPABILITY"
    echo "Active font: $(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null)"
    echo "Font mix: $(tr '\n' ' ' < "$MODDIR/config/font_mix.conf" 2>/dev/null)"
    echo "Font weight desired: $(sed -n 's/^weight=//p' "$MODDIR/config/font_weight.conf" 2>/dev/null | head -n1)"
    echo "Font weight adjustment: $(settings get secure font_weight_adjustment 2>/dev/null)"
    echo "Text reboot pending: $([ -f "$MODDIR/config/text_reboot_required.conf" ] && echo yes || echo no)"
    echo "Transaction directories: $(find "$MODDIR/.font-transaction" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)"
    echo "Public font dir: /sdcard/LuoShu/fonts"
    echo
    echo "Storage (/data):"; df -h /data 2>/dev/null || true
    echo; echo "Inodes (/data):"; df -i /data 2>/dev/null || true
    echo; echo "Mount count: $(wc -l < /proc/mounts 2>/dev/null || echo unknown)"
    echo "LuoShu mounts:"; grep -i 'LuoShu\|/system/fonts\|/data/fonts' /proc/mounts 2>/dev/null | tail -n 80 || true
    echo; echo "File: $FONT"
    if [ -f "$FONT" ]; then
        if type font_validate >/dev/null 2>&1 && font_validate "$FONT" text; then
            echo "Validation: PASS"; echo "Real format: $FONT_CHECK_FORMAT"; echo "Bytes: $FONT_CHECK_SIZE"; echo "Variable: $FONT_CHECK_VARIABLE"
            [ -n "$FONT_CHECK_WARNING" ] && echo "Warning: $FONT_CHECK_WARNING"
        else echo "Validation: FAIL"; echo "Reason: ${FONT_CHECK_ERROR:-checker unavailable}"; fi
    else echo "Validation: MISSING"; fi
    echo; echo "Bridge status:"; grep -E 'GMS-BRIDGE|XWEB-BRIDGE' "$MODDIR/logs/fontswitch.log" 2>/dev/null | tail -n 12 || true
    echo; echo "Recent log:"; tail -n 120 "$MODDIR/logs/fontswitch.log" 2>/dev/null || true
    echo; echo "Note: 洛书 v14.1 不管理 Emoji；应用内置字体无法由系统字体模块替换。"
} > "$OUT"
chmod 0644 "$OUT" 2>/dev/null || true
echo "$OUT"
