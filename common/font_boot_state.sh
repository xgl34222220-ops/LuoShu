#!/system/bin/sh
# One-reboot font transaction marker and late-boot convergence helpers.
set +e

_lfbs_module() {
    printf '%s\n' "${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
}

_lfbs_value() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

_lfbs_boot_id() {
    if [ -n "${LUOSHU_TEST_BOOT_ID:-}" ]; then
        printf '%s\n' "$LUOSHU_TEST_BOOT_ID"
        return
    fi
    if type luoshu_current_boot_id >/dev/null 2>&1; then
        luoshu_current_boot_id
        return
    fi
    _lfbs_id=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')
    [ -n "$_lfbs_id" ] || _lfbs_id=$(getprop ro.runtime.firstboot 2>/dev/null | tr -d '\r\n')
    [ -n "$_lfbs_id" ] || _lfbs_id=unknown
    printf '%s\n' "$_lfbs_id"
}

luoshu_text_reboot_mark() {
    _lfbs_font="${1:-default}"
    _lfbs_module_dir="$(_lfbs_module)"
    _lfbs_marker="$_lfbs_module_dir/config/text_reboot_required.conf"
    _lfbs_temp="${_lfbs_marker}.tmp.$$"
    mkdir -p "${_lfbs_marker%/*}" 2>/dev/null || return 1
    {
        printf 'font=%s\n' "$_lfbs_font"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
        printf 'bootId=%s\n' "$(_lfbs_boot_id)"
    } > "$_lfbs_temp" 2>/dev/null || return 1
    mv -f "$_lfbs_temp" "$_lfbs_marker" 2>/dev/null || return 1
    chmod 0644 "$_lfbs_marker" 2>/dev/null || true
}

# A successful foreground commit is newer than an update/dynamic-config migration
# marker. Recover only that narrow stale-marker case.
luoshu_font_rebuild_marker_reconcile() {
    _lfbs_module_dir="$(_lfbs_module)"
    _lfbs_config="$_lfbs_module_dir/config"
    _lfbs_pending="$_lfbs_config/font-payload-rebuild-pending.conf"
    [ -s "$_lfbs_pending" ] || return 0
    _lfbs_active=$(head -n1 "$_lfbs_config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    _lfbs_pending_font=$(_lfbs_value "$_lfbs_pending" font)
    _lfbs_pending_time=$(_lfbs_value "$_lfbs_pending" time)
    _lfbs_boot="$_lfbs_config/font-payload-boot.conf"
    _lfbs_boot_font=$(_lfbs_value "$_lfbs_boot" font)
    _lfbs_boot_time=$(_lfbs_value "$_lfbs_boot" time)
    _lfbs_boot_state=$(_lfbs_value "$_lfbs_boot" state)
    _lfbs_schema=$(_lfbs_value "$_lfbs_config/font-payload-schema.conf" schema)
    case "$_lfbs_pending_time:$_lfbs_boot_time" in *[!0-9:]*|:*) return 2 ;; esac
    case "$_lfbs_boot_state" in prepared|booting|confirmed) ;; *) return 2 ;; esac
    [ -n "$_lfbs_active" ] && [ "$_lfbs_active" != default ] || return 2
    [ "$_lfbs_pending_font" = "$_lfbs_active" ] && [ "$_lfbs_boot_font" = "$_lfbs_active" ] || return 2
    [ "$_lfbs_schema" = "${LUOSHU_PAYLOAD_SCHEMA_CURRENT:-device-template-v2-baseline-v10-latin-coverage-v1}" ] || return 2
    [ "$_lfbs_boot_time" -ge "$_lfbs_pending_time" ] 2>/dev/null || return 2
    [ -s "$_lfbs_config/font-payload-manifest.conf" ] || return 2
    rm -f "$_lfbs_pending" "$_lfbs_config/font-payload-reapply-notified.conf" 2>/dev/null || true
    return 0
}

_lfbs_confirm_boot_file() {
    _lfbs_module_dir="$(_lfbs_module)"
    _lfbs_config="$_lfbs_module_dir/config"
    _lfbs_boot="$_lfbs_config/font-payload-boot.conf"
    _lfbs_state=$(_lfbs_value "$_lfbs_boot" state)
    [ "$_lfbs_state" = booting ] || return 0
    _lfbs_font=$(_lfbs_value "$_lfbs_boot" font)
    _lfbs_generation=$(_lfbs_value "$_lfbs_boot" generation)
    _lfbs_temp="${_lfbs_boot}.tmp.$$"
    {
        printf 'state=confirmed\n'
        printf 'font=%s\n' "${_lfbs_font:-unknown}"
        [ -z "$_lfbs_generation" ] || printf 'generation=%s\n' "$_lfbs_generation"
        printf 'bootId=%s\n' "$(_lfbs_boot_id)"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_lfbs_temp" 2>/dev/null || return 1
    mv -f "$_lfbs_temp" "$_lfbs_boot" 2>/dev/null || return 1
    chmod 0644 "$_lfbs_boot" 2>/dev/null || true
}

luoshu_text_reboot_reconcile() {
    _lfbs_module_dir="$(_lfbs_module)"
    _lfbs_config="$_lfbs_module_dir/config"
    _lfbs_marker="$_lfbs_config/text_reboot_required.conf"
    [ -s "$_lfbs_marker" ] || return 0
    _lfbs_marker_boot=$(_lfbs_value "$_lfbs_marker" bootId)
    _lfbs_current_boot=$(_lfbs_boot_id)
    # Never clear a marker using the previous font that is still mounted in this boot.
    [ -n "$_lfbs_marker_boot" ] && [ "$_lfbs_marker_boot" = "$_lfbs_current_boot" ] && return 2

    luoshu_font_rebuild_marker_reconcile >/dev/null 2>&1 || true
    _lfbs_boot_state=$(_lfbs_value "$_lfbs_config/font-payload-boot.conf" state)
    case "$_lfbs_boot_state" in booting|confirmed) ;; *) return 2 ;; esac
    _lfbs_verify="$_lfbs_module_dir/common/device_font_load_verify.sh"
    [ -f "$_lfbs_verify" ] || return 2
    MODDIR="$_lfbs_module_dir" MODULE_DIR="$_lfbs_module_dir" sh "$_lfbs_verify" verify >/dev/null 2>&1
    _lfbs_verify_state=$(_lfbs_value "$_lfbs_config/device-font-load-verification.conf" state)
    case "$_lfbs_verify_state" in verified|not-applicable) ;; *) return 2 ;; esac
    _lfbs_confirm_boot_file || return 1
    rm -f "$_lfbs_marker" "$_lfbs_config/font-mount-verify-failures" \
        "$_lfbs_config/font-boot-inconclusive.conf" 2>/dev/null || true
    return 0
}

# mix 模式只需要覆盖真实 UI 常用槽。v10 曾把 ColorOS 所有可发现字体文件都塞进
# 前台复合负载，导致 payload 数量暴涨，94% 的完整负载校验遍历大量重复硬链接。
# 这里仅在 font_mix.sh 进程内收敛到已知文本槽；普通单字体链路仍保留完整设备发现。
_lfbs_mix_coloros_files() {
    printf '%s\n' 'SysSans-Hans-Regular.ttf SysSans-Hans-Bold.ttf SysSans-Hans-Medium.ttf SysSans-Hans-Light.ttf SysSans-Hant-Regular.ttf SysSans-Hant-Bold.ttf SysSans-Hant-Medium.ttf SysSans-Hant-Light.ttf SysFont-Hans-Regular.ttf SysFont-Hans-Bold.ttf SysFont-Hans-Medium.ttf SysFont-Hans-Light.ttf SysFont-Hant-Regular.ttf SysFont-Hant-Bold.ttf SysFont-Hant-Medium.ttf SysFont-Hant-Light.ttf SysFont-Static-Regular.ttf SysFont-Static-Bold.ttf SysFont-Static-Medium.ttf SysFont-Static-Light.ttf SysFont-Regular.ttf SysFont-Bold.ttf SysFont-Medium.ttf SysFont-Light.ttf SysFont-Thin.ttf SysFont-Black.ttf SysSans-En-Regular.ttf SysSans-En-Bold.ttf SysSans-En-Medium.ttf SysSans-En-Light.ttf SysSans-En-Thin.ttf SysSans-En-Black.ttf Opposans-Hans-Regular.ttf Opposans-Hans-Bold.ttf Opposans-Hans-Medium.ttf Opposans-Hans-Light.ttf Opposans-En-Regular.ttf Opposans-En-Bold.ttf Opposans-En-Medium.ttf Opposans-En-Light.ttf OPSans-En-Regular.ttf OplusSans-Regular.ttf OplusSans-Medium.ttf OplusSans-Bold.ttf OppoSans-Regular.ttf OppoSans-Medium.ttf OppoSans-Bold.ttf GoogleSansText-Thin.ttf GoogleSansText-ExtraLight.ttf GoogleSansText-Light.ttf GoogleSansText-Regular.ttf GoogleSansText-Medium.ttf GoogleSansText-SemiBold.ttf GoogleSansText-Bold.ttf GoogleSansText-ExtraBold.ttf GoogleSansText-Black.ttf GoogleSansText-VF.ttf GoogleSansTextVF.ttf GoogleSans-Thin.ttf GoogleSans-ExtraLight.ttf GoogleSans-Light.ttf GoogleSans-Regular.ttf GoogleSans-Medium.ttf GoogleSans-SemiBold.ttf GoogleSans-Bold.ttf GoogleSans-ExtraBold.ttf GoogleSans-Black.ttf GoogleSans-VF.ttf GoogleSansFlex-Regular.ttf GoogleSansDisplay-Regular.ttf GoogleSansDisplay-Medium.ttf GoogleSansDisplay-SemiBold.ttf GoogleSansDisplay-Bold.ttf GoogleSans18pt-Regular.ttf GoogleSans18pt-Medium.ttf GoogleSans18pt-SemiBold.ttf GoogleSans18pt-Bold.ttf GoogleSansText18pt-Regular.ttf GoogleSansText18pt-Medium.ttf GoogleSansText18pt-SemiBold.ttf GoogleSansText18pt-Bold.ttf ProductSans-Regular.ttf ProductSans-Medium.ttf ProductSans-Bold.ttf Roboto-Thin.ttf Roboto-ExtraLight.ttf Roboto-Light.ttf Roboto-Regular.ttf Roboto-Medium.ttf Roboto-SemiBold.ttf Roboto-Bold.ttf Roboto-ExtraBold.ttf Roboto-Black.ttf RobotoFlex-Regular.ttf RobotoStatic-Regular.ttf NotoSans-Regular.ttf NotoSans-Medium.ttf NotoSans-SemiBold.ttf NotoSans-Bold.ttf SourceSansPro-Regular.ttf SourceSansPro-SemiBold.ttf SourceSansPro-Bold.ttf DINCondensedBold.ttf DINPro-Regular.ttf DINPro-Medium.ttf DINPro-Bold.ttf OPPODIN-Regular.ttf OPPODIN-Medium.ttf OPPODIN-Bold.ttf OPPODINCondensed-Regular.ttf OPPODINCondensed-Medium.ttf OPPODINCondensed-Bold.ttf'
}

if [ "${0##*/}" = font_mix.sh ]; then
    get_all_coloros_files() {
        _lfbs_mix_coloros_files
    }
    get_all_coloros_names() {
        for _lfbs_file in $(_lfbs_mix_coloros_files); do
            printf '%s\n' "${_lfbs_file%.*}"
        done
    }
fi

if [ "${0##*/}" = font_boot_state.sh ]; then
    case "${1:-reconcile}" in
        mark) luoshu_text_reboot_mark "${2:-default}" ;;
        reconcile) luoshu_text_reboot_reconcile ;;
        reconcile-rebuild) luoshu_font_rebuild_marker_reconcile ;;
        *) echo 'Usage: font_boot_state.sh {mark FONT|reconcile|reconcile-rebuild}' >&2; exit 2 ;;
    esac
fi
