#!/system/bin/sh
# Both switch paths discard old text trees immediately after staging. Copy only
# the retained payload entries, so a rejected hard link cannot copy gigabytes of
# old font aliases just to delete them again. The live tree is always read-only.

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

# Use the scanner's partition manifest for BOTH direct switching and mixing.
# Names are data, never commands/paths. Keep this policy in sync with the private
# mount layer; regressions compare the two rather than adding OEM brand lists.
luoshu_payload_partition_safe() {
    case "$1" in
        ''|*[!A-Za-z0-9_]*|[0-9]*|_*) return 1 ;;
        data|proc|sys|dev|mnt|storage|sdcard|apex|metadata|cache|tmp|config|acct|linkerconfig|debug_ramdisk|vendor_dlkm|odm_dlkm|system_dlkm) return 1 ;;
    esac
    return 0
}

luoshu_payload_partitions() (
    _lpp_module="${1:-${REALMOD:-${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}}}"
    _lpp_base='system system_ext product vendor odm oem my_product my_engineering my_company my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust hw_product'
    printf '%s\n' "$_lpp_base"
    _lpp_manifest="$_lpp_module/config/device_font_partitions.conf"
    [ -f "$_lpp_manifest" ] || return 0
    _lpp_seen=" $_lpp_base "
    while IFS= read -r _lpp_part || [ -n "$_lpp_part" ]; do
        luoshu_payload_partition_safe "$_lpp_part" || continue
        case "$_lpp_seen" in *" $_lpp_part "*) continue ;; esac
        printf '%s\n' "$_lpp_part"
        _lpp_seen="$_lpp_seen$_lpp_part "
    done < "$_lpp_manifest"
)

luoshu_payload_nested_font_roots() (
    _lpnfr_module="${1:-${REALMOD:-${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}}}"
    _lpnfr_manifest="$_lpnfr_module/config/device_font_roots.conf"
    [ -f "$_lpnfr_manifest" ] || return 0
    while IFS='|' read -r _lpnfr_part _lpnfr_rel _lpnfr_key || \
          [ -n "$_lpnfr_part$_lpnfr_rel$_lpnfr_key" ]; do
        luoshu_payload_partition_safe "$_lpnfr_part" || continue
        case "$_lpnfr_rel" in ''|/*|*'..'*|fonts|etc) continue ;; esac
        case "/$_lpnfr_rel/" in *"/./"*|*"//"*) continue ;; esac
        printf '%s|%s\n' "$_lpnfr_part" "$_lpnfr_rel"
    done < "$_lpnfr_manifest"
)

luoshu_clone_payload_etc() (
    _lcet_source="$1"; _lcet_dest="$2"
    mkdir -p "$_lcet_dest" 2>/dev/null || return 1
    for _lcet_entry in "$_lcet_source"/* "$_lcet_source"/.[!.]* "$_lcet_source"/..?*; do
        [ -e "$_lcet_entry" ] || [ -L "$_lcet_entry" ] || continue
        _lcet_name=${_lcet_entry##*/}
        # Do not carry a generated font configuration across generations, even
        # in partitions that the mix caller's historical cleanup list omits.
        case "$_lcet_name" in
            fonts*.xml|font_fallback*.xml|font_customization*.xml)
                if [ -f "$_lcet_entry" ] && grep -a -qE 'LuoShuSlot-|LuoShu(Mono)?-|luoshu' "$_lcet_entry"; then
                    continue
                fi
                ;;
        esac
        luoshu_clone_payload_entry "$_lcet_entry" "$_lcet_dest/$_lcet_name" || return 1
    done
)

luoshu_clone_payload_metadata() (
    _lcpm_source="$1"; _lcpm_dest="$2"
    [ -d "$_lcpm_source" ] && [ "$_lcpm_source" != "$_lcpm_dest" ] || return 1
    _lcpm_partitions=" $(luoshu_payload_partitions | tr '\n' ' ') "
    mkdir -p "$_lcpm_dest" 2>/dev/null || return 1
    for _lcpm_entry in "$_lcpm_source"/* "$_lcpm_source"/.[!.]* "$_lcpm_source"/..?*; do
        [ -e "$_lcpm_entry" ] || [ -L "$_lcpm_entry" ] || continue
        _lcpm_name=${_lcpm_entry##*/}
        case "$_lcpm_name" in
            .luoshu-metrics-report.json|.luoshu-coverage-preserved.tsv|.luoshu-coverage-remediation.conf) continue ;;
        esac
        case "$_lcpm_partitions" in
            *" $_lcpm_name "*)
                if [ -d "$_lcpm_entry" ]; then
                    mkdir -p "$_lcpm_dest/$_lcpm_name" 2>/dev/null || return 1
                    for _lcpm_child in "$_lcpm_entry"/* "$_lcpm_entry"/.[!.]* "$_lcpm_entry"/..?*; do
                        [ -e "$_lcpm_child" ] || [ -L "$_lcpm_child" ] || continue
                        _lcpm_base=${_lcpm_child##*/}
                        [ "$_lcpm_base" != fonts ] || continue
                        if [ "$_lcpm_base" = etc ] && [ -d "$_lcpm_child" ]; then
                            luoshu_clone_payload_etc "$_lcpm_child" "$_lcpm_dest/$_lcpm_name/etc" || return 1
                        else
                            luoshu_clone_payload_entry "$_lcpm_child" "$_lcpm_dest/$_lcpm_name/$_lcpm_base" || return 1
                        fi
                    done
                    continue
                fi
                ;;
        esac
        luoshu_clone_payload_entry "$_lcpm_entry" "$_lcpm_dest/$_lcpm_name" || return 1
    done

    # Nested OEM font roots are text payload too. They may sit below an
    # otherwise retained directory (for example product/vivo/fonts), so remove
    # only the scanner-declared font root after cloning and preserve siblings.
    while IFS='|' read -r _lcpm_part _lcpm_rel; do
        [ -n "$_lcpm_part" ] && [ -n "$_lcpm_rel" ] || continue
        rm -rf "$_lcpm_dest/$_lcpm_part/$_lcpm_rel" 2>/dev/null || return 1
    done <<EOF_LUOSHU_NESTED_FONT_ROOTS
$(luoshu_payload_nested_font_roots)
EOF_LUOSHU_NESTED_FONT_ROOTS
    return 0
)
