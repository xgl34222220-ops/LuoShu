#!/system/bin/sh
# LuoShu next-boot payload activation.
# Foreground font switching only prepares .luoshu-payload-next. This helper runs
# before LuoShu self-mount, so the payload used by the previous boot is never
# renamed, deleted or rewritten while Android is still rendering from it.
set +e

luoshu_next_boot_module() {
    printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
}

luoshu_next_boot_value() {
    _lnbv_file="$1"
    _lnbv_key="$2"
    sed -n "s/^${_lnbv_key}=//p" "$_lnbv_file" 2>/dev/null | head -n1 | tr -d '\r\n'
}

luoshu_next_boot_log() {
    _lnbl_module=$(luoshu_next_boot_module)
    mkdir -p "$_lnbl_module/logs" 2>/dev/null || true
    printf '[%s] [NEXT-BOOT] %s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$*" \
        >> "$_lnbl_module/logs/fontswitch.log" 2>/dev/null || true
}

luoshu_next_boot_write_mode() {
    _lnbwm_module="$1"
    _lnbwm_font="$2"
    _lnbwm_mode="$_lnbwm_module/config/font_runtime_legacy_v14_4.conf"
    _lnbwm_schema="$_lnbwm_module/config/font-payload-schema.conf"
    if [ "$_lnbwm_font" = default ]; then
        rm -f "$_lnbwm_mode" "$_lnbwm_schema" 2>/dev/null || true
        return 0
    fi
    _lnbwm_tmp="${_lnbwm_mode}.tmp.$$"
    {
        printf 'enabled=true\n'
        printf 'core=physical-safe-v1\n'
        printf 'font=%s\n' "$_lnbwm_font"
        printf 'pipeline=atomic-next-boot\n'
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_lnbwm_tmp" 2>/dev/null && mv -f "$_lnbwm_tmp" "$_lnbwm_mode" 2>/dev/null || return 1
    chmod 0600 "$_lnbwm_mode" 2>/dev/null || true
    printf 'schema=legacy-physical-safe-v1\n' > "$_lnbwm_schema" 2>/dev/null || true
    chmod 0644 "$_lnbwm_schema" 2>/dev/null || true
    return 0
}

luoshu_next_boot_restore_selection() {
    _lnbrs_module="$1"
    _lnbrs_previous="$2"
    _lnbrs_previous_legacy="$3"
    [ -n "$_lnbrs_previous" ] || _lnbrs_previous=default
    printf '%s\n' "$_lnbrs_previous" > "$_lnbrs_module/config/active_font.conf" 2>/dev/null || true
    chmod 0644 "$_lnbrs_module/config/active_font.conf" 2>/dev/null || true
    if [ "$_lnbrs_previous_legacy" = true ] && [ "$_lnbrs_previous" != default ]; then
        luoshu_next_boot_write_mode "$_lnbrs_module" "$_lnbrs_previous" >/dev/null 2>&1 || true
    else
        rm -f "$_lnbrs_module/config/font_runtime_legacy_v14_4.conf" 2>/dev/null || true
    fi
}

luoshu_next_boot_activate() {
    _lnba_module=$(luoshu_next_boot_module)
    _lnba_live="$_lnba_module/.luoshu-payload"
    _lnba_next="$_lnba_module/.luoshu-payload-next"
    _lnba_state="$_lnba_module/config/font-payload-next.conf"
    _lnba_activated="$_lnba_module/config/font-payload-activated.conf"
    [ -d "$_lnba_next" ] && [ -s "$_lnba_state" ] || return 2

    _lnba_font=$(luoshu_next_boot_value "$_lnba_state" font)
    _lnba_previous=$(luoshu_next_boot_value "$_lnba_state" previousFont)
    _lnba_previous_legacy=$(luoshu_next_boot_value "$_lnba_state" previousLegacy)
    [ -n "$_lnba_font" ] || return 1
    [ -n "$_lnba_previous" ] || _lnba_previous=default
    [ "$_lnba_previous_legacy" = true ] || _lnba_previous_legacy=false

    _lnba_retired_root="$_lnba_module/.luoshu-retired"
    _lnba_boot=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')
    [ -n "$_lnba_boot" ] || _lnba_boot="$(date +%s 2>/dev/null || echo 0)-$$"
    _lnba_retired="$_lnba_retired_root/payload-${_lnba_boot}"
    mkdir -p "$_lnba_retired_root" "$_lnba_module/config" 2>/dev/null || return 1
    rm -rf "$_lnba_retired" 2>/dev/null || true

    if [ -d "$_lnba_live" ]; then
        mv "$_lnba_live" "$_lnba_retired" 2>/dev/null || {
            luoshu_next_boot_log "cannot retire previous payload; keeping previous selection=$_lnba_previous"
            luoshu_next_boot_restore_selection "$_lnba_module" "$_lnba_previous" "$_lnba_previous_legacy"
            return 1
        }
    fi

    if ! mv "$_lnba_next" "$_lnba_live" 2>/dev/null; then
        [ ! -d "$_lnba_retired" ] || mv "$_lnba_retired" "$_lnba_live" 2>/dev/null || true
        luoshu_next_boot_restore_selection "$_lnba_module" "$_lnba_previous" "$_lnba_previous_legacy"
        luoshu_next_boot_log "next payload activation failed; previous payload restored"
        return 1
    fi

    chmod 0755 "$_lnba_live" 2>/dev/null || true
    if ! luoshu_next_boot_write_mode "$_lnba_module" "$_lnba_font"; then
        rm -rf "$_lnba_live" 2>/dev/null || true
        [ ! -d "$_lnba_retired" ] || mv "$_lnba_retired" "$_lnba_live" 2>/dev/null || true
        luoshu_next_boot_restore_selection "$_lnba_module" "$_lnba_previous" "$_lnba_previous_legacy"
        luoshu_next_boot_log "runtime mode commit failed; previous payload restored"
        return 1
    fi

    printf '%s\n' "$_lnba_font" > "$_lnba_module/config/active_font.conf" 2>/dev/null || true
    chmod 0644 "$_lnba_module/config/active_font.conf" 2>/dev/null || true
    {
        printf 'font=%s\n' "$_lnba_font"
        printf 'previousFont=%s\n' "$_lnba_previous"
        printf 'previousLegacy=%s\n' "$_lnba_previous_legacy"
        printf 'retired=%s\n' "$_lnba_retired"
        printf 'bootId=%s\n' "$_lnba_boot"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "${_lnba_activated}.tmp.$$" 2>/dev/null && \
        mv -f "${_lnba_activated}.tmp.$$" "$_lnba_activated" 2>/dev/null || true
    chmod 0644 "$_lnba_activated" 2>/dev/null || true
    rm -f "$_lnba_state" 2>/dev/null || true

    if [ "$_lnba_font" = default ]; then
        # No LuoShu font source will be mounted this boot, so the retired custom
        # payload can be reclaimed immediately before Android finishes starting.
        rm -rf "$_lnba_retired" 2>/dev/null || true
        rm -f "$_lnba_activated" 2>/dev/null || true
    fi
    luoshu_next_boot_log "activated payload for $_lnba_font; previous=$_lnba_previous"
    return 0
}