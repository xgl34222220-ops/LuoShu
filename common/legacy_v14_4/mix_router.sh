#!/system/bin/sh
# Current App -> v14.4 composite-core compatibility router.
# Composite generation is isolated from the payload mounted by the current boot.
# The compatibility runtime writes into .luoshu-mix-stage; a successful task is then
# committed as the real module's .luoshu-payload-next for atomic activation next boot.
set +e

REALMOD="${MODDIR:-}"
if [ -z "$REALMOD" ]; then
    if [ -f "${0%/*}/../../module.prop" ]; then
        REALMOD="$(CDPATH= cd -- "${0%/*}/../.." 2>/dev/null && pwd)"
    else
        REALMOD="/data/adb/modules/LuoShu"
    fi
fi
LEGACY="$REALMOD/common/legacy_v14_4"
RUNTIME="$REALMOD/.legacy-v14-runtime"
LIVE_PAYLOAD="$REALMOD/.luoshu-payload"
MIX_STAGE="$REALMOD/.luoshu-mix-stage"
NEXT_PAYLOAD="$REALMOD/.luoshu-payload-next"
NEXT_STATE="$REALMOD/config/font-payload-next.conf"
MIX_STAGE_STATE="$REALMOD/config/mix-stage-next.conf"
ACTIVE_CONF="$REALMOD/config/active_font.conf"
LEGACY_MODE="$REALMOD/config/font_runtime_legacy_v14_4.conf"
REBOOT_CONF="$REALMOD/config/text_reboot_required.conf"
LOG_FILE="$REALMOD/logs/fontswitch.log"

read_value() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

force_link() {
    _target="$1"; _link="$2"
    if [ -L "$_link" ]; then
        ln -sfn "$_target" "$_link" 2>/dev/null || return 1
    elif [ -e "$_link" ]; then
        rm -rf "$_link" 2>/dev/null || return 1
        ln -s "$_target" "$_link" 2>/dev/null || return 1
    else
        ln -s "$_target" "$_link" 2>/dev/null || return 1
    fi
}

prepare_mix_stage() {
    mkdir -p "$REALMOD/config" "$REALMOD/cache" "$REALMOD/logs" 2>/dev/null || return 1
    rm -rf "$MIX_STAGE" 2>/dev/null || true
    mkdir -p "$MIX_STAGE" 2>/dev/null || return 1
    if [ -d "$LIVE_PAYLOAD" ]; then
        cp -al "$LIVE_PAYLOAD/." "$MIX_STAGE/" 2>/dev/null || \
            cp -af "$LIVE_PAYLOAD/." "$MIX_STAGE/" 2>/dev/null || \
            cp -rfp "$LIVE_PAYLOAD/." "$MIX_STAGE/" 2>/dev/null || return 1
    fi

    _previous=$(head -n1 "$ACTIVE_CONF" 2>/dev/null | tr -d '\r\n')
    [ -n "$_previous" ] || _previous=default
    _previous_legacy=false
    [ -f "$LEGACY_MODE" ] && _previous_legacy=true
    {
        printf 'previousFont=%s\n' "$_previous"
        printf 'previousLegacy=%s\n' "$_previous_legacy"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "${MIX_STAGE_STATE}.tmp.$$" 2>/dev/null && \
        mv -f "${MIX_STAGE_STATE}.tmp.$$" "$MIX_STAGE_STATE" 2>/dev/null || return 1
    chmod 0644 "$MIX_STAGE_STATE" 2>/dev/null || true
    return 0
}

stage_has_fonts() {
    [ -d "$MIX_STAGE" ] || return 1
    find "$MIX_STAGE" -type f \( -iname '*.ttf' -o -iname '*.otf' -o -iname '*.ttc' \) \
        -print -quit 2>/dev/null | grep -q .
}

complete_hyperos_stage() {
    _helper="$REALMOD/common/hyperos_stage_complete.sh"
    [ -f "$_helper" ] || return 0
    if [ -e /system/fonts/MiSansVF.ttf ] || [ -n "$(getprop ro.mi.os.version.name 2>/dev/null)" ] || \
       [ -n "$(getprop ro.miui.ui.version.name 2>/dev/null)" ]; then
        LUOSHU_REAL_MODDIR="$REALMOD" sh "$_helper" "$MIX_STAGE" >> "$LOG_FILE" 2>&1 || true
    fi
}

write_next_state() {
    _previous=$(read_value "$MIX_STAGE_STATE" previousFont)
    _previous_legacy=$(read_value "$MIX_STAGE_STATE" previousLegacy)
    [ -n "$_previous" ] || _previous=default
    [ "$_previous_legacy" = true ] || _previous_legacy=false
    _tmp="${NEXT_STATE}.tmp.$$"
    {
        printf 'state=prepared\n'
        printf 'font=mix\n'
        printf 'previousFont=%s\n' "$_previous"
        printf 'previousLegacy=%s\n' "$_previous_legacy"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_tmp" 2>/dev/null || return 1
    mv -f "$_tmp" "$NEXT_STATE" 2>/dev/null || return 1
    chmod 0644 "$NEXT_STATE" 2>/dev/null || true

    printf 'mix\n' > "$ACTIVE_CONF" 2>/dev/null || return 1
    chmod 0644 "$ACTIVE_CONF" 2>/dev/null || true
    _boot_id=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')
    {
        printf 'font=mix\n'
        printf 'reason=next-boot-payload-prepared\n'
        printf 'bootId=%s\n' "$_boot_id"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$REBOOT_CONF" 2>/dev/null || true
    chmod 0644 "$REBOOT_CONF" 2>/dev/null || true
    return 0
}

commit_mix_stage_if_needed() {
    # Auto-multiweight may already have gone through font_switch_safe.sh. In that
    # case the real next payload is authoritative; discard this compatibility clone.
    if [ -d "$NEXT_PAYLOAD" ] && [ -s "$NEXT_STATE" ]; then
        _next_font=$(read_value "$NEXT_STATE" font)
        if [ "$_next_font" = mix ]; then
            rm -rf "$MIX_STAGE" 2>/dev/null || true
            rm -f "$MIX_STAGE_STATE" 2>/dev/null || true
            return 0
        fi
    fi

    stage_has_fonts || return 1
    complete_hyperos_stage
    rm -rf "$NEXT_PAYLOAD" 2>/dev/null || true
    mv "$MIX_STAGE" "$NEXT_PAYLOAD" 2>/dev/null || return 1
    if ! write_next_state; then
        mv "$NEXT_PAYLOAD" "$MIX_STAGE" 2>/dev/null || true
        return 1
    fi
    rm -f "$MIX_STAGE_STATE" 2>/dev/null || true
    printf '[%s] legacy composite staged for next boot: mix\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" >> "$LOG_FILE" 2>/dev/null || true
    return 0
}

write_legacy_mix_mode() {
    _tmp="$REALMOD/config/font_runtime_legacy_v14_4.conf.tmp.$$"
    {
        printf 'enabled=true\ncore=v14.4.0\nfont=mix\npipeline=atomic-next-boot-composite\ntime=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } >"$_tmp" 2>/dev/null && mv -f "$_tmp" "$REALMOD/config/font_runtime_legacy_v14_4.conf" 2>/dev/null || true
    chmod 0600 "$REALMOD/config/font_runtime_legacy_v14_4.conf" 2>/dev/null || true
}

finalize_mix_stage() {
    if ! commit_mix_stage_if_needed; then
        printf '{"status":"error","message":"复合字体已生成但下一启动负载提交失败"}\n'
        return 1
    fi
    write_legacy_mix_mode
    printf '{"status":"ok","data":{"font":"mix","rebootRequired":true,"pipeline":"atomic-next-boot-composite"}}\n'
    return 0
}

setup_runtime() {
    _payload="$1"
    mkdir -p "$RUNTIME/common" "$REALMOD/config" "$REALMOD/cache" "$REALMOD/logs" "$_payload" 2>/dev/null || return 1
    force_link "$REALMOD/config" "$RUNTIME/config" || return 1
    force_link "$REALMOD/cache" "$RUNTIME/cache" || return 1
    force_link "$REALMOD/logs" "$RUNTIME/logs" || return 1
    force_link "$_payload" "$RUNTIME/.luoshu-payload" || return 1
    force_link "$REALMOD/module.prop" "$RUNTIME/module.prop" || return 1

    for _part in system system_ext product vendor odm oem my_product my_engineering my_company my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust hw_product; do
        mkdir -p "$_payload/$_part" 2>/dev/null || true
        force_link "$_payload/$_part" "$RUNTIME/$_part" || return 1
    done

    force_link "$LEGACY/v14_mix.sh" "$RUNTIME/common/v14_mix.sh" || return 1
    force_link "$LEGACY/v142_weighted_mix.sh" "$RUNTIME/common/v142_weighted_mix.sh" || return 1
    force_link "$LEGACY/v143_auto_multiweight_mix.sh" "$RUNTIME/common/v143_auto_multiweight_mix.sh" || return 1
    force_link "$LEGACY/font_mix_runtime.sh" "$RUNTIME/common/font_mix.sh" || return 1
    force_link "$LEGACY/font_mix_engine.sh" "$RUNTIME/common/font_mix_engine.sh" || return 1
    force_link "$LEGACY/font_instance.py" "$RUNTIME/common/font_instance.py" || return 1
    force_link "$LEGACY/composite_font.py" "$RUNTIME/common/composite_font.py" || return 1
    force_link "$LEGACY/luoshu_composite.sh" "$RUNTIME/common/luoshu_composite.sh" || return 1
    force_link "$LEGACY/mix_weight_mode.sh" "$RUNTIME/common/mix_weight_mode.sh" || return 1
    force_link "$LEGACY/font_role_check.sh" "$RUNTIME/common/font_role_check.sh" || return 1
    force_link "$LEGACY/font_role_check.py" "$RUNTIME/common/font_role_check.py" || return 1
    force_link "$LEGACY/util_functions.sh" "$RUNTIME/common/util_functions.sh" || return 1
    force_link "$LEGACY/font_check.sh" "$RUNTIME/common/font_check.sh" || return 1
    force_link "$LEGACY/rom_adapters.sh" "$RUNTIME/common/rom_adapters.sh" || return 1
    force_link "$REALMOD/common/python" "$RUNTIME/common/python" || return 1
    force_link "$REALMOD/common/font_manager.sh" "$RUNTIME/common/font_manager.sh" || return 1
    force_link "$REALMOD/common/legacy_v14_4_switch.sh" "$RUNTIME/common/legacy_v14_4_switch.sh" || return 1
    force_link "$REALMOD/common/font_switch_lock.sh" "$RUNTIME/common/font_switch_lock.sh" || return 1
    force_link "$LEGACY" "$RUNTIME/common/legacy_v14_4" || return 1
    force_link "$REALMOD/common/module_status.sh" "$RUNTIME/common/module_status.sh" || true
    force_link "$REALMOD/common/hyperos_stage_complete.sh" "$RUNTIME/common/hyperos_stage_complete.sh" || true

    cat >"$RUNTIME/common/mount_compat.sh" <<'EOF'
#!/system/bin/sh
# Compatibility runtime: partition paths resolve into an isolated staging payload.
set +e
EOF
    chmod 0755 "$RUNTIME/common/mount_compat.sh" 2>/dev/null || true
    return 0
}

mark_mix_mode_if_success() {
    _out="$1"
    printf '%s\n' "$_out" | grep -q '"state":"success"' || return 0
    finalize_mix_stage >/dev/null 2>&1 || return 1
    return 0
}

_cmd="${1:-config}"
if [ "$_cmd" = finalize ]; then
    finalize_mix_stage
    exit $?
fi
case "$_cmd" in
    start)
        prepare_mix_stage || {
            printf '{"status":"error","message":"无法创建复合字体下一启动暂存负载"}\n'
            exit 1
        }
        _payload="$MIX_STAGE"
        ;;
    status|config|recover|reconcile)
        if [ -d "$MIX_STAGE" ]; then _payload="$MIX_STAGE"; else _payload="$LIVE_PAYLOAD"; fi
        ;;
    *)
        if [ -d "$MIX_STAGE" ]; then _payload="$MIX_STAGE"; else _payload="$LIVE_PAYLOAD"; fi
        ;;
esac

setup_runtime "$_payload" || {
    printf '{"status":"error","message":"无法准备 v14.4 复合字体兼容运行时"}\n'
    [ "$_cmd" != start ] || { rm -rf "$MIX_STAGE" 2>/dev/null || true; rm -f "$MIX_STAGE_STATE" 2>/dev/null || true; }
    exit 1
}
export LUOSHU_REAL_MODDIR="$REALMOD"
export MODDIR="$RUNTIME"
export MODULE_DIR="$RUNTIME"

case "$_cmd" in
    reconcile)
        printf '{"status":"ok"}\n'
        ;;
    status)
        _out="$(sh "$RUNTIME/common/v14_mix.sh" "$@" 2>&1)"
        _rc=$?
        if ! mark_mix_mode_if_success "$_out"; then
            printf '{"status":"error","message":"复合字体已生成但下一启动负载提交失败"}\n'
            exit 1
        fi
        printf '%s\n' "$_out"
        exit "$_rc"
        ;;
    start)
        _out="$(sh "$RUNTIME/common/v14_mix.sh" "$@" 2>&1)"
        _rc=$?
        printf '%s\n' "$_out"
        if [ "$_rc" -ne 0 ] || ! printf '%s\n' "$_out" | grep -q '"status":"ok"'; then
            rm -rf "$MIX_STAGE" 2>/dev/null || true
            rm -f "$MIX_STAGE_STATE" 2>/dev/null || true
        fi
        exit "$_rc"
        ;;
    recover)
        _out="$(sh "$RUNTIME/common/v14_mix.sh" "$@" 2>&1)"
        _rc=$?
        rm -rf "$MIX_STAGE" 2>/dev/null || true
        rm -f "$MIX_STAGE_STATE" 2>/dev/null || true
        printf '%s\n' "$_out"
        exit "$_rc"
        ;;
    config)
        exec sh "$RUNTIME/common/v14_mix.sh" "$@"
        ;;
    *)
        exec sh "$RUNTIME/common/v14_mix.sh" "$@"
        ;;
esac
