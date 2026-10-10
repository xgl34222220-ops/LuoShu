#!/system/bin/sh
# 洛书：在 Root 管理器中显示简洁的当前字体状态。
# module.prop 的“当前字体”只描述用户实际选择/挂载结果，不承担设备可信验证 UI。
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
    else
        MODDIR="/data/adb/modules/LuoShu"
    fi
fi

PROP="$MODDIR/module.prop"
ACTIVE="${1:-}"
[ -n "$ACTIVE" ] || ACTIVE=$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
[ -n "$ACTIVE" ] || ACTIVE="default"

case "$ACTIVE" in
    default) DISPLAY="系统默认字体" ;;
    mix)
        CJK=$(sed -n 's/^cjk=//p' "$MODDIR/config/font_mix.conf" 2>/dev/null | head -n1 | tr -d '\r\n')
        LATIN=$(sed -n 's/^latin=//p' "$MODDIR/config/font_mix.conf" 2>/dev/null | head -n1 | tr -d '\r\n')
        DIGIT=$(sed -n 's/^digit=//p' "$MODDIR/config/font_mix.conf" 2>/dev/null | head -n1 | tr -d '\r\n')
        if [ -n "$CJK$LATIN$DIGIT" ]; then
            DISPLAY="组合：${CJK:-默认} / ${LATIN:-默认} / ${DIGIT:-默认}"
        else
            DISPLAY="组合字体"
        fi
        ;;
    *) DISPLAY=$(printf '%s' "$ACTIVE" | tr '\r\n' '  ') ;;
esac

EFFECTIVE_DISPLAY="$DISPLAY"
if [ "$ACTIVE" != default ]; then
    VERIFY="$MODDIR/config/device-font-load-verification.conf"
    VERIFY_STATE=$(sed -n 's/^state=//p' "$VERIFY" 2>/dev/null | head -n1)
    MOUNT_STATE=$(sed -n 's/^state=//p' "$MODDIR/config/self-mount.conf" 2>/dev/null | head -n1)

    # Root 管理器这里显示的是“当前字体”，不是验收页面。旧逻辑在字体已经肉眼生效时
    # 仍会因为 v4 验证文件缺失/模式不同而长期写“待验证”，造成错误状态。现在只在
    # 明确等待重启或明确失败时附加状态；其余情况直接显示当前字体。
    if [ -f "$MODDIR/config/text_reboot_required.conf" ]; then
        EFFECTIVE_DISPLAY="已配置：$DISPLAY（等待重启）"
    elif [ "$MOUNT_STATE" = failed ] || [ "$VERIFY_STATE" = failed ]; then
        EFFECTIVE_DISPLAY="系统默认字体（$DISPLAY 未生效）"
    else
        EFFECTIVE_DISPLAY="$DISPLAY"
    fi
fi

# System OTA: compare the ROM build with the one recorded at the last successful
# apply and, when it changed, request the existing stock rescan/validation.
if [ -f "$MODDIR/common/system_ota_guard.sh" ]; then
    . "$MODDIR/common/system_ota_guard.sh"
    luoshu_system_ota_check "$MODDIR" "$ACTIVE" \
        "$(sed -n 's/^state=//p' "$MODDIR/config/self-mount.conf" 2>/dev/null | head -n1)" || true
fi

DESCRIPTION="Android 全局字体管理，当前字体：$EFFECTIVE_DISPLAY"

# KernelSU: publish the status through the documented module config key
# override.description (https://kernelsu.org/guide/module-config.html) instead
# of rewriting module.prop. Magisk/APatch, or a ksud without module config,
# keep the module.prop path below unchanged.
luoshu_status_ksud() {
    [ "${KSU:-}" = true ] || return 1
    [ -z "${APATCH:-}" ] && [ ! -d /data/adb/ap ] && [ ! -d /data/adb/apatch ] || return 1
    for _lsk in "${LUOSHU_KSUD:-}" /data/adb/ksud "$(command -v ksud 2>/dev/null)"; do
        [ -n "$_lsk" ] && [ -x "$_lsk" ] || continue
        KSU_MODULE="$KSU_ID" "$_lsk" module config list >/dev/null 2>&1 || return 1
        printf '%s\n' "$_lsk"
        return 0
    done
    return 1
}
KSU_ID="${KSU_MODULE:-$(sed -n 's/^id=//p' "$PROP" 2>/dev/null | head -n1 | tr -d '\r\n')}"
[ -n "$KSU_ID" ] || KSU_ID=LuoShu
if KSUD=$(luoshu_status_ksud); then
    if [ "$(KSU_MODULE="$KSU_ID" "$KSUD" module config get override.description 2>/dev/null)" = "$DESCRIPTION" ] || \
       KSU_MODULE="$KSU_ID" "$KSUD" module config set override.description "$DESCRIPTION" >/dev/null 2>&1; then
        printf '%s\n' "$DESCRIPTION"
        exit 0
    fi
fi

[ -f "$PROP" ] || exit 0
# Unchanged status: do not rewrite module.prop (avoids a flash write and a
# root-manager module rescan on every boot).
if [ "$(sed -n 's/^description=//p' "$PROP" 2>/dev/null | head -n1)" = "$DESCRIPTION" ]; then
    printf '%s\n' "$DESCRIPTION"
    exit 0
fi
TMP="$PROP.tmp.$$"
awk -v description="$DESCRIPTION" '
BEGIN { replaced=0 }
/^description=/ { print "description=" description; replaced=1; next }
{ print }
END { if (!replaced) print "description=" description }
' "$PROP" > "$TMP" 2>/dev/null && mv -f "$TMP" "$PROP" 2>/dev/null
chmod 0644 "$PROP" 2>/dev/null || true
printf '%s\n' "$DESCRIPTION"
exit 0
