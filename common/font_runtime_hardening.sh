#!/system/bin/sh
# LuoShu runtime mapping hardening.
# Loaded after rom_adapters/coloros_global/hyperos_global so the final dispatcher
# always combines ROM-specific physical slots with the device's discovered slots.
set +e

_luoshu_inventory_anchor_for_weight() {
    _lria_weight="$1"
    _lria_module="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
    _lria_store="$_lria_module/system/fonts/.luoshu-font-store"
    case "$_lria_weight" in
        100) _lria_role=thin ;;
        200) _lria_role=extralight ;;
        300|350) _lria_role=light ;;
        500) _lria_role=medium ;;
        600) _lria_role=semibold ;;
        700) _lria_role=bold ;;
        800) _lria_role=extrabold ;;
        900) _lria_role=black ;;
        *) _lria_role=regular; _lria_weight=400 ;;
    esac
    for _lria_candidate in \
        "$_lria_store/compact-wght-${_lria_weight}.font" \
        "$_lria_store/${_lria_role}.font" \
        "$_lria_store/compact-regular.font" \
        "$_lria_store/regular.font"; do
        [ -s "$_lria_candidate" ] && {
            printf '%s\n' "$_lria_candidate"
            return 0
        }
    done
    return 1
}

_luoshu_inventory_augment() {
    type _device_font_inventory_entries >/dev/null 2>&1 || return 2
    type _device_font_inventory_target >/dev/null 2>&1 || return 2
    type _font_alias >/dev/null 2>&1 || return 2
    _lria_entries=$(_device_font_inventory_entries) || return 2
    [ -n "$_lria_entries" ] || return 2
    _lria_tab=$(printf '\t')
    _lria_count=0
    _lria_bad=0
    while IFS="$_lria_tab" read -r _lria_logical _lria_name _lria_partition _lria_format _lria_weight _lria_style _lria_source; do
        [ -n "$_lria_logical" ] && [ -n "$_lria_name" ] || continue
        _lria_target=$(_device_font_inventory_target "$_lria_logical") || continue
        case "$_lria_target" in
            "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"/*/fonts/*) ;;
            *) continue ;;
        esac
        [ -f "$_lria_target" ] && {
            _lria_count=$((_lria_count + 1))
            continue
        }
        _lria_anchor=$(_luoshu_inventory_anchor_for_weight "${_lria_weight:-400}") || {
            _lria_bad=$((_lria_bad + 1))
            continue
        }
        mkdir -p "${_lria_target%/*}" 2>/dev/null || {
            _lria_bad=$((_lria_bad + 1))
            continue
        }
        if _font_alias "$_lria_anchor" "$_lria_target"; then
            _lria_count=$((_lria_count + 1))
        else
            _lria_bad=$((_lria_bad + 1))
        fi
    done <<EOF_LUOSHU_RUNTIME_INVENTORY
$_lria_entries
EOF_LUOSHU_RUNTIME_INVENTORY
    if [ "$_lria_count" -gt 0 ]; then
        LUOSHU_INVENTORY_TARGETS_MAPPED=1
        export LUOSHU_INVENTORY_TARGETS_MAPPED
        type _log_step >/dev/null 2>&1 && \
            _log_step "  已补齐 $_lria_count 个本机原厂字体槽位${_lria_bad:+，异常=$_lria_bad}"
        return 0
    fi
    return 2
}

# Final dispatcher.  The old inventory-first path could return after mapping a
# few XML-visible shells and skip MiSans/OPlus physical slots entirely.  ROM
# mapping now runs first; inventory only adds paths discovered on this device.
apply_font_by_rom() {
    _lrh_src="$1"
    _lrh_dest="$2"
    _lrh_mode="${3:-full}"
    _lrh_family="${4:-}"
    [ -n "$_lrh_family" ] || _lrh_family=$(detect_font_family "$(basename "$_lrh_src")")

    _lrh_base_rc=1
    if [ "${IS_HYPEROS:-false}" = true ]; then
        copy_as_hyperos "$_lrh_src" "$_lrh_dest" "$_lrh_mode" "$_lrh_family"
        _lrh_base_rc=$?
    elif [ "${IS_COLOROS:-false}" = true ]; then
        copy_as_coloros "$_lrh_src" "$_lrh_dest" "$_lrh_mode" "$_lrh_family"
        _lrh_base_rc=$?
    else
        copy_as_generic "$_lrh_src" "$_lrh_dest" "$_lrh_mode"
        _lrh_base_rc=$?
    fi

    _luoshu_inventory_augment
    _lrh_inventory_rc=$?
    if [ "$_lrh_base_rc" -ne 0 ] && [ "$_lrh_inventory_rc" -ne 0 ]; then
        type _log_step >/dev/null 2>&1 && \
            _log_step '  ROM 物理槽与设备清单均未生成可用字体目标'
        return 1
    fi

    # HyperOS uses hidden/direct physical slots and intentionally keeps the ROM
    # XML metric shell.  Other ROMs may safely add the generated XML view.
    if [ "${IS_HYPEROS:-false}" != true ] && \
       type font_config_enable_for_payload >/dev/null 2>&1; then
        font_config_enable_for_payload "$_lrh_family" || \
            type _log_step >/dev/null 2>&1 && \
            _log_step '  设备没有可安全启用的字体 XML，继续使用文件槽映射'
    fi
    return 0
}
