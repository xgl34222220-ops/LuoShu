#!/system/bin/sh
# LuoShu self-mount backend.
# Uses the same read-only lower-layer model as KernelSU's reference meta-overlayfs:
# module content first, captured stock tree last, and source name KSU for unified cleanup.
set +e

luoshu_self_mount_stage_for_manager() {
    case "${1:-unknown}" in
        APatch|KernelSU|KernelSU*|SukiSU|SukiSU*)
            printf 'post-mount\n'
            ;;
        *)
            # Magisk does not provide a module post-mount hook. Unknown legacy
            # managers retain the existing early path for compatibility.
            printf 'post-fs-data\n'
            ;;
    esac
}

# ColorOS/OxygenOS devices in the OPlus family are especially sensitive to a second
# directory-level OverlayFS being stacked over /system/fonts after the root manager
# has already prepared its own module view. On affected Android 16 builds this can
# leave zygote/font services reading an inconsistent tree and cause a black-screen
# boot loop. Keep the safer per-file bind fallback for the core font tree.
_luoshu_oplus_font_bind_only() {
    case "${LUOSHU_OPLUS_FONT_BIND_ONLY:-auto}" in
        1|true|yes) return 0 ;;
        0|false|no) return 1 ;;
    esac
    command -v getprop >/dev/null 2>&1 || return 1
    _lsob_oplus=$(getprop ro.build.version.oplusrom 2>/dev/null)
    [ -n "$_lsob_oplus" ] && return 0
    _lsob_oplus=$(getprop ro.oplus.version 2>/dev/null)
    [ -n "$_lsob_oplus" ] && return 0
    _lsob_brand=$(getprop ro.product.brand 2>/dev/null | tr '[:upper:]' '[:lower:]')
    case "$_lsob_brand" in
        oneplus|oppo|realme) return 0 ;;
    esac
    _lsob_manufacturer=$(getprop ro.product.manufacturer 2>/dev/null | tr '[:upper:]' '[:lower:]')
    case "$_lsob_manufacturer" in
        oneplus|oppo|realme) return 0 ;;
    esac
    return 1
}

_luoshu_overlay_mount_dir() {
    _lsomb_source="$1"
    _lsomb_target="$2"
    _lsomb_key="$3"
    _lsomb_state=$(_luoshu_self_state_root)
    _lsomb_lower="$_lsomb_state/lower/$_lsomb_key"

    [ -d "$_lsomb_source" ] && [ -d "$_lsomb_target" ] || return 1

    if [ "$_lsomb_key" = system-fonts ]; then
        # v3.2.2 had an effective "already visible" escape hatch. v3.2.3 removed
        # it while consolidating the atomic path, allowing a second self-overlay to
        # be stacked on devices where KernelSU/SukiSU already exposed this payload.
        if type _luoshu_system_probe_visible >/dev/null 2>&1 && _luoshu_system_probe_visible; then
            _luoshu_self_log '检测到当前字体负载已由系统挂载提供，跳过 /system/fonts 二次 OverlayFS'
            return 0
        fi
        if _luoshu_oplus_font_bind_only; then
            _luoshu_self_log 'OPlus/ColorOS 安全模式：禁止整目录 /system/fonts OverlayFS，改用逐文件 bind'
            return 1
        fi
    fi

    _luoshu_umount_cmd "$_lsomb_lower" >/dev/null 2>&1 || true
    rm -rf "$_lsomb_lower" 2>/dev/null || true
    mkdir -p "$_lsomb_lower" 2>/dev/null || return 1

    # Keep a stable reference to the currently visible stock/metamodule tree before
    # placing LuoShu's own layer on the same target.
    _luoshu_mount_cmd -o bind "$_lsomb_target" "$_lsomb_lower" >/dev/null 2>&1 || return 1

    # No upperdir/workdir is needed: LuoShu only needs a merged read-only boot view.
    # Changes made by the App are intentionally picked up after the requested reboot.
    if _luoshu_mount_cmd -t overlay KSU \
        -o "lowerdir=$_lsomb_source:$_lsomb_lower" \
        "$_lsomb_target" >/dev/null 2>&1; then
        # self_mount_ensure appends the visible target too. Recording the captured
        # lower first guarantees reverse-order uninstall: target, then lower bind.
        if [ -n "${_lsme_mount_list:-}" ]; then
            printf '%s\n' "$_lsomb_lower" >> "$_lsme_mount_list" 2>/dev/null || true
        fi
        return 0
    fi

    _luoshu_umount_cmd "$_lsomb_lower" >/dev/null 2>&1 || true
    rm -rf "$_lsomb_lower" 2>/dev/null || true
    return 1
}
