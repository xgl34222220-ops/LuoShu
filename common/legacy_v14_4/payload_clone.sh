#!/system/bin/sh
# Both switch paths discard old text trees immediately after staging. Copy only
# the retained payload entries, so a rejected hard link cannot copy gigabytes of
# old font aliases just to delete them again. The live tree is always read-only.

luoshu_clone_payload_partitions() {
    printf '%s\n' 'system system_ext product vendor odm oem my_product my_engineering my_company my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust hw_product'
    _lcpp_module="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
    _lcpp_manifest="$_lcpp_module/config/device_font_partitions.conf"
    [ -f "$_lcpp_manifest" ] || return 0
    while IFS= read -r _lcpp_part; do
        case "$_lcpp_part" in ''|*[!A-Za-z0-9_]*|[0-9]*|_* ) continue ;; esac
        printf '%s\n' "$_lcpp_part"
    done < "$_lcpp_manifest"
}

luoshu_clone_payload_is_partition() {
    _lcpp_wanted="$1"
    for _lcpp_part in $(luoshu_clone_payload_partitions); do
        [ "$_lcpp_part" = "$_lcpp_wanted" ] && return 0
    done
    return 1
}

luoshu_clone_payload_entry() {
    _lcpe_source="$1"; _lcpe_dest="$2"
    if cp -al "$_lcpe_source" "$_lcpe_dest" 2>/dev/null; then
        return 0
    fi
    rm -rf "$_lcpe_dest" 2>/dev/null || return 1
    cp -R "$_lcpe_source" "$_lcpe_dest" 2>/dev/null || return 1
    if [ -d "$_lcpe_dest" ] && [ ! -L "$_lcpe_dest" ]; then
        find "$_lcpe_dest" -type d -exec chmod 0755 {} + 2>/dev/null || true
        find "$_lcpe_dest" -type f -exec chmod 0644 {} + 2>/dev/null || true
    elif [ ! -L "$_lcpe_dest" ]; then
        chmod 0644 "$_lcpe_dest" 2>/dev/null || true
    fi
}

luoshu_clone_payload_metadata() {
    _lcpm_source="$1"; _lcpm_dest="$2"
    [ -d "$_lcpm_source" ] && [ "$_lcpm_source" != "$_lcpm_dest" ] || return 1
    mkdir -p "$_lcpm_dest" 2>/dev/null || return 1
    for _lcpm_entry in "$_lcpm_source"/* "$_lcpm_source"/.[!.]* "$_lcpm_source"/..?*; do
        [ -e "$_lcpm_entry" ] || [ -L "$_lcpm_entry" ] || continue
        _lcpm_name=${_lcpm_entry##*/}
        [ "$_lcpm_name" != .luoshu-metrics-report.json ] || continue
        if luoshu_clone_payload_is_partition "$_lcpm_name" && [ -d "$_lcpm_entry" ]; then
            mkdir -p "$_lcpm_dest/$_lcpm_name" 2>/dev/null || return 1
            for _lcpm_child in "$_lcpm_entry"/* "$_lcpm_entry"/.[!.]* "$_lcpm_entry"/..?*; do
                [ -e "$_lcpm_child" ] || [ -L "$_lcpm_child" ] || continue
                _lcpm_base=${_lcpm_child##*/}
                # Font trees are rebuilt from the selected source. Never clone old
                # font aliases, including scanner-discovered OEM partitions.
                [ "$_lcpm_base" != fonts ] || continue
                luoshu_clone_payload_entry "$_lcpm_child" "$_lcpm_dest/$_lcpm_name/$_lcpm_base" || return 1
            done
            continue
        fi
        luoshu_clone_payload_entry "$_lcpm_entry" "$_lcpm_dest/$_lcpm_name" || return 1
    done
    return 0
}
