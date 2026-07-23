#!/system/bin/sh
# LuoShu v2.2 dynamic FontManagerService config guard.
# Loaded after device_font_payload_runtime.sh and overrides only the dynamic view stage.
set +e

_dfpr_mark_dynamic_rebuild() {
    _dfpr_reason="${1:-dynamic-config-changed}"
    _dfpr_module_dir="$(_dfpr_module)"
    _dfpr_config="$_dfpr_module_dir/config"
    _dfpr_pending="$_dfpr_config/font-payload-rebuild-pending.conf"
    _dfpr_active=$(head -n1 "$_dfpr_config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_dfpr_active" ] || _dfpr_active=default
    [ "$_dfpr_active" != default ] || return 0
    mkdir -p "$_dfpr_config" 2>/dev/null || return 1
    _dfpr_pending_tmp="${_dfpr_pending}.tmp.$$"
    {
        printf 'state=pending\n'
        printf 'font=%s\n' "$_dfpr_active"
        printf 'reason=%s\n' "$_dfpr_reason"
        printf 'oldSchema=%s\n' "$(sed -n 's/^schema=//p' "$_dfpr_config/font-payload-schema.conf" 2>/dev/null | head -n1)"
        printf 'newSchema=%s\n' "${LUOSHU_PAYLOAD_SCHEMA_CURRENT:-device-template-v1-baseline-v7-mono-v6}"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_dfpr_pending_tmp" 2>/dev/null || return 1
    mv -f "$_dfpr_pending_tmp" "$_dfpr_pending" 2>/dev/null || return 1
    chmod 0600 "$_dfpr_pending" 2>/dev/null || true
    return 0
}

# Prepare a private sanitized config only when the real FontManagerService document is
# readable. Missing/changed targets remove stale state instead of carrying it forward.
_dfpr_prepare_dynamic_state() {
    _dfpr_overlay="$1"
    _dfpr_manifest_tmp="$2"
    _dfpr_module_dir="$(_dfpr_module)"
    _dfpr_dynamic_source="$_dfpr_overlay/dynamic/data-fonts-config.xml"
    _dfpr_dynamic_dest="$_dfpr_module_dir/system/etc/.luoshu-data-fonts-config.xml"
    _dfpr_dynamic_state="$_dfpr_module_dir/config/device-font-dynamic-mount.conf"
    _dfpr_dynamic_target="${LUOSHU_DATA_FONTS_CONFIG_TARGET:-/data/fonts/config/config.xml}"
    if [ ! -s "$_dfpr_dynamic_source" ] || [ ! -s "$_dfpr_dynamic_target" ]; then
        rm -f "$_dfpr_dynamic_dest" "$_dfpr_dynamic_state" 2>/dev/null || true
        return 2
    fi
    _dfpr_link_or_copy "$_dfpr_dynamic_source" "$_dfpr_dynamic_dest" || return 1
    chmod 0600 "$_dfpr_dynamic_dest" 2>/dev/null || true
    if command -v chcon >/dev/null 2>&1; then
        chcon --reference="$_dfpr_dynamic_target" "$_dfpr_dynamic_dest" 2>/dev/null || true
    elif command -v toybox >/dev/null 2>&1; then
        toybox chcon --reference="$_dfpr_dynamic_target" "$_dfpr_dynamic_dest" 2>/dev/null || true
    fi
    _dfpr_target_hash="$(_dfpr_hash "$_dfpr_dynamic_target")"
    _dfpr_source_hash="$(_dfpr_hash "$_dfpr_dynamic_dest")"
    [ -n "$_dfpr_target_hash" ] && [ -n "$_dfpr_source_hash" ] || return 1
    _dfpr_state_tmp="${_dfpr_dynamic_state}.tmp.$$"
    {
        printf 'state=prepared\n'
        printf 'source=system/etc/.luoshu-data-fonts-config.xml\n'
        printf 'target=%s\n' "$_dfpr_dynamic_target"
        printf 'targetSha256=%s\n' "$_dfpr_target_hash"
        printf 'sourceSha256=%s\n' "$_dfpr_source_hash"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_dfpr_state_tmp" 2>/dev/null || return 1
    mv -f "$_dfpr_state_tmp" "$_dfpr_dynamic_state" 2>/dev/null || return 1
    chmod 0600 "$_dfpr_dynamic_state" 2>/dev/null || true
    _dfpr_bytes="$(_dfpr_size "$_dfpr_dynamic_dest")"
    printf 'file|system/etc/.luoshu-data-fonts-config.xml|%s|%s\n' "$_dfpr_source_hash" "$_dfpr_bytes" >> "$_dfpr_manifest_tmp"
    return 0
}

_dfpr_dynamic_mount_is_readonly() {
    _dfpr_mount_target="$1"
    awk -v path="$_dfpr_mount_target" '
        $5 == path && $6 ~ /(^|,)ro(,|$)/ { found=1 }
        END { exit !found }
    ' /proc/self/mountinfo 2>/dev/null
}

device_font_dynamic_mount_apply() {
    _dfpr_module_dir="$(_dfpr_module)"
    _dfpr_state="$_dfpr_module_dir/config/device-font-dynamic-mount.conf"
    [ -s "$_dfpr_state" ] || return 2
    _dfpr_source_rel=$(sed -n 's/^source=//p' "$_dfpr_state" 2>/dev/null | head -n1)
    _dfpr_target=$(sed -n 's/^target=//p' "$_dfpr_state" 2>/dev/null | head -n1)
    _dfpr_target_hash=$(sed -n 's/^targetSha256=//p' "$_dfpr_state" 2>/dev/null | head -n1)
    _dfpr_source_hash=$(sed -n 's/^sourceSha256=//p' "$_dfpr_state" 2>/dev/null | head -n1)
    case "$_dfpr_source_rel" in system/etc/.luoshu-data-fonts-config.xml) ;; *) return 1 ;; esac
    [ "$_dfpr_target" = "${LUOSHU_DATA_FONTS_CONFIG_TARGET:-/data/fonts/config/config.xml}" ] || return 1
    _dfpr_source="$_dfpr_module_dir/$_dfpr_source_rel"
    [ -s "$_dfpr_source" ] && [ -s "$_dfpr_target" ] || return 2
    [ "$(_dfpr_hash "$_dfpr_source")" = "$_dfpr_source_hash" ] || return 1
    if [ "$(_dfpr_hash "$_dfpr_target")" != "$_dfpr_target_hash" ]; then
        _dfpr_mark_dynamic_rebuild dynamic-config-changed >/dev/null 2>&1 || true
        _dfpr_log WARN '动态字体配置已被系统更新，已登记后台重建并保留 ROM 原配置'
        return 2
    fi
    _dfpr_dynamic_mount_is_readonly "$_dfpr_target" && return 0
    mount -o bind "$_dfpr_source" "$_dfpr_target" 2>/dev/null || \
        mount --bind "$_dfpr_source" "$_dfpr_target" 2>/dev/null || {
            _dfpr_log WARN '动态字体配置只读视图挂载失败，保留 ROM 原配置'
            return 2
        }
    if ! mount -o remount,bind,ro "$_dfpr_target" 2>/dev/null && \
       ! mount -o bind,remount,ro "$_dfpr_target" 2>/dev/null && \
       ! mount -o remount,ro,bind "$_dfpr_target" 2>/dev/null; then
        umount "$_dfpr_target" 2>/dev/null || true
        _dfpr_log WARN '动态字体配置无法切换为只读 bind，已撤销挂载'
        return 2
    fi
    if _dfpr_dynamic_mount_is_readonly "$_dfpr_target"; then
        _dfpr_log INFO '动态字体配置只读视图已在 FontManagerService 初始化前挂载'
        return 0
    fi
    umount "$_dfpr_target" 2>/dev/null || true
    _dfpr_log WARN '动态字体配置只读验证失败，已撤销并保留 ROM 原配置'
    return 2
}
