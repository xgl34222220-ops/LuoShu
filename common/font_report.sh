#!/system/bin/sh
# LuoShu v13.4 Beta2 Hotfix6 - 设备与字体基础检测报告
set +e
MODDIR="${MODDIR:-/data/adb/modules/LuoShu}"
[ -f "$MODDIR/common/font_check.sh" ] && . "$MODDIR/common/font_check.sh"
FONT="$1"
OUT="${2:-/sdcard/LuoShu/reports/LuoShu_Font_Report_$(date +%Y%m%d_%H%M%S).txt}"
mkdir -p "${OUT%/*}" 2>/dev/null || true
{
    echo "LuoShu Font Report v13.4 Beta2 Hotfix6"
    echo "Generated: $(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)"
    echo "Device: $(getprop ro.product.manufacturer 2>/dev/null) $(getprop ro.product.model 2>/dev/null)"
    echo "Android: $(getprop ro.build.version.release 2>/dev/null) (SDK $(getprop ro.build.version.sdk 2>/dev/null))"
    echo "ROM: ColorOS=$(getprop ro.build.version.oplusrom 2>/dev/null) HyperOS=$(getprop ro.mi.os.version.name 2>/dev/null)"
    echo "Root: Magisk=${MAGISK_VER:-} KernelSU=${KSU_VER:-}"
    echo "Active text: $(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null)"
    echo "Active Emoji: $(head -n1 "$MODDIR/config/active_emoji.conf" 2>/dev/null)"
    echo "Font weight desired: $(sed -n 's/^weight=//p' "$MODDIR/config/font_weight.conf" 2>/dev/null | head -n1)"
    echo "Font weight adjustment: $(settings get secure font_weight_adjustment 2>/dev/null)"
    echo "Text reboot pending: $([ -f "$MODDIR/config/text_reboot_required.conf" ] && echo yes || echo no)"
    echo "Emoji reboot pending: $([ -f "$MODDIR/config/emoji_reboot_required.conf" ] && echo yes || echo no)"
    echo "Hybrid marker: $([ -f "$MODDIR/magic" ] && echo magic || echo missing)"
    echo "Native scanner: $([ -x "$MODDIR/bin/luoshud" ] && echo available-arm64 || echo unavailable)"
    echo "Meta mount error: $([ -e "$MODDIR/mount.error" ] && echo present || echo clear)"
    echo "Public text dir: /sdcard/LuoShu/fonts"
    echo "Public Emoji dir: /sdcard/LuoShu/emoji"
    echo
    echo "Storage (/data):"
    df -h /data 2>/dev/null || true
    echo
    echo "Inodes (/data):"
    df -i /data 2>/dev/null || true
    echo
    echo "Mount count: $(wc -l < /proc/mounts 2>/dev/null || echo unknown)"
    echo "LuoShu mounts:"
    grep -i 'LuoShu\|/system/fonts\|/data/fonts' /proc/mounts 2>/dev/null | tail -n 80 || true
    echo
    echo "Known stale path check:"
    if [ -e /data/adb/modules/com.omarea.vtools ]; then
        echo "/data/adb/modules/com.omarea.vtools exists"
    else
        echo "/data/adb/modules/com.omarea.vtools missing (remove stale Hybrid Mount record if it is still referenced)"
    fi
    echo
    echo "File: $FONT"
    if [ -f "$FONT" ]; then
        if type font_validate >/dev/null 2>&1 && font_validate "$FONT" text; then
            echo "Validation: PASS"
            echo "Real format: $FONT_CHECK_FORMAT"
            echo "Bytes: $FONT_CHECK_SIZE"
            echo "Variable: $FONT_CHECK_VARIABLE"
            echo "Color tables: $FONT_CHECK_COLOR"
            [ -n "$FONT_CHECK_WARNING" ] && echo "Warning: $FONT_CHECK_WARNING"
        else
            echo "Validation: FAIL"
            echo "Reason: ${FONT_CHECK_ERROR:-checker unavailable}"
        fi
    else
        echo "Validation: MISSING"
    fi
    echo
    echo "Bridge status:"
    grep -E 'GMS-BRIDGE|XWEB-BRIDGE' "$MODDIR/logs/fontswitch.log" 2>/dev/null | tail -n 12 || true
    echo
    echo "Recent log:"
    tail -n 100 "$MODDIR/logs/fontswitch.log" 2>/dev/null
    echo
    echo "Note: WebUI font details provide deeper cmap sampling. App-bundled fonts cannot be replaced by a system font module."
} > "$OUT"
chmod 0644 "$OUT" 2>/dev/null || true
echo "$OUT"
