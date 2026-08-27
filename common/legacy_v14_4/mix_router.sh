#!/system/bin/sh
# Current App -> pre-reset v14.4 composite-core router.
# UI/API stay on v4; composite generation, weighted/auto engines and final physical mapping use v14.
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
PAYLOAD="$REALMOD/.luoshu-payload"
LOG_FILE="$REALMOD/logs/fontswitch.log"

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

setup_runtime() {
    mkdir -p "$RUNTIME/common" "$REALMOD/config" "$REALMOD/cache" "$REALMOD/logs" "$PAYLOAD" 2>/dev/null || return 1
    force_link "$REALMOD/config" "$RUNTIME/config" || return 1
    force_link "$REALMOD/cache" "$RUNTIME/cache" || return 1
    force_link "$REALMOD/logs" "$RUNTIME/logs" || return 1
    force_link "$PAYLOAD" "$RUNTIME/.luoshu-payload" || return 1
    force_link "$REALMOD/module.prop" "$RUNTIME/module.prop" || return 1

    for _part in system system_ext product vendor odm oem my_product my_engineering my_company my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust hw_product; do
        mkdir -p "$PAYLOAD/$_part" 2>/dev/null || true
        force_link "$PAYLOAD/$_part" "$RUNTIME/$_part" || return 1
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

    cat >"$RUNTIME/common/mount_compat.sh" <<'EOF'
#!/system/bin/sh
# v14 compatibility runtime: partition paths already resolve directly into .luoshu-payload.
set +e
EOF
    chmod 0755 "$RUNTIME/common/mount_compat.sh" 2>/dev/null || true
    return 0
}

mark_mix_mode_if_success() {
    _out="$1"
    printf '%s\n' "$_out" | grep -q '"state":"success"' || return 0
    _tmp="$REALMOD/config/font_runtime_legacy_v14_4.conf.tmp.$$"
    {
        printf 'enabled=true\ncore=v14.4.0\nfont=mix\npipeline=legacy-v14-composite\ntime=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } >"$_tmp" 2>/dev/null && mv -f "$_tmp" "$REALMOD/config/font_runtime_legacy_v14_4.conf" 2>/dev/null || true
    chmod 0600 "$REALMOD/config/font_runtime_legacy_v14_4.conf" 2>/dev/null || true
}

setup_runtime || {
    printf '{"status":"error","message":"无法准备 v14.4 复合字体兼容运行时"}\n'
    exit 1
}
export LUOSHU_REAL_MODDIR="$REALMOD"
export MODDIR="$RUNTIME"
export MODULE_DIR="$RUNTIME"

case "${1:-config}" in
    reconcile)
        printf '{"status":"ok"}\n'
        ;;
    status)
        _out="$(sh "$RUNTIME/common/v14_mix.sh" "$@" 2>&1)"
        _rc=$?
        printf '%s\n' "$_out"
        mark_mix_mode_if_success "$_out"
        exit "$_rc"
        ;;
    start|config|recover)
        exec sh "$RUNTIME/common/v14_mix.sh" "$@"
        ;;
    *)
        exec sh "$RUNTIME/common/v14_mix.sh" "$@"
        ;;
esac
