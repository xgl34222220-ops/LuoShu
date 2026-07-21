#!/system/bin/sh
# LuoShu meta-module / OverlayFS compatibility layer.
# Synchronization runs only after an App-side payload transaction has validated successfully.
set +e

LUOSHU_MOUNT_MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
LUOSHU_MOUNT_LOG="${LUOSHU_MOUNT_LOG:-$LUOSHU_MOUNT_MODDIR/logs/mount_compat.log}"
LUOSHU_MOUNT_LOCK="$LUOSHU_MOUNT_MODDIR/.mount_compat.lock"
LUOSHU_MOUNT_TIMEOUT="${LUOSHU_MOUNT_TIMEOUT:-120}"

luoshu_mount_log() {
    _lml_msg="$1"
    mkdir -p "${LUOSHU_MOUNT_LOG%/*}" 2>/dev/null || true
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$_lml_msg" >> "$LUOSHU_MOUNT_LOG" 2>/dev/null || true
}

luoshu_module_id() {
    _lmi_id=$(sed -n 's/^id=//p' "$LUOSHU_MOUNT_MODDIR/module.prop" 2>/dev/null | head -n1 | tr -d '\r\n')
    [ -n "$_lmi_id" ] || _lmi_id=$(basename "$LUOSHU_MOUNT_MODDIR")
    printf '%s\n' "$_lmi_id"
}

luoshu_payload_partitions() {
    printf '%s\n' 'system system_ext product vendor odm oem my_product my_engineering my_company my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust'
}

luoshu_detect_root_manager() {
    if [ -d /data/adb/ap ] || [ -d /data/adb/apatch ]; then
        printf 'APatch\n'
    elif [ -d /data/adb/ksu ]; then
        if [ -e /data/adb/ksu/.ksud ] || [ -d /data/adb/ksu/bin ]; then printf 'KernelSU\n'; else printf 'KernelSU-compatible\n'; fi
    elif [ -d /data/adb/magisk ] || [ -x /data/adb/magisk/magisk ]; then
        printf 'Magisk\n'
    else
        printf 'unknown\n'
    fi
}

luoshu_detect_mount_engine() {
    _ldme_id=$(luoshu_module_id)
    if [ -n "${LUOSHU_META_TEST_ROOT:-}" ]; then
        printf 'test-meta\n'
    elif [ -n "${MODULE_CONTENT_DIR:-}" ]; then
        printf 'external-content-dir\n'
    elif [ -d "/data/adb/metamodule/mnt/$_ldme_id" ] || \
         [ -d "/data/adb/modules/meta-overlay/mnt/$_ldme_id" ] || \
         [ -d "/data/adb/modules/meta-overlayfs/mnt/$_ldme_id" ]; then
        printf 'meta-overlayfs\n'
    elif [ -d /data/adb/mountify ] || [ -d /data/adb/modules/Mountify ]; then
        printf 'mountify\n'
    elif [ -e /data/adb/modules/.hybrid_mount ] || [ -d /data/adb/modules/HybridMount ]; then
        printf 'hybrid-mount\n'
    elif [ -f "$LUOSHU_MOUNT_MODDIR/magic" ]; then
        printf 'magic-mount\n'
    else
        printf 'native-module-mount\n'
    fi
}

luoshu_root_candidate() {
    _lrc_base="$1"
    _lrc_id="$2"
    [ -n "$_lrc_base" ] || return 0
    case "$_lrc_base" in
        */"$_lrc_id") printf '%s\n' "$_lrc_base" ;;
        *) printf '%s/%s\n' "${_lrc_base%/}" "$_lrc_id" ;;
    esac
}

# Output the content roots actually consumed by meta-mount engines, one module root per line.
luoshu_meta_content_roots() {
    _lmcr_id=$(luoshu_module_id)
    _lmcr_seen=''
    _lmcr_candidates=''

    if [ -n "${LUOSHU_META_TEST_ROOT:-}" ]; then
        luoshu_root_candidate "$LUOSHU_META_TEST_ROOT" "$_lmcr_id"
        return 0
    fi

    for _lmcr_base in \
        "${MODULE_CONTENT_DIR:-}" \
        /data/adb/metamodule/mnt \
        /data/adb/metamodule/modules \
        /data/adb/modules/.metamodule/mnt \
        /data/adb/modules/meta-overlay/mnt \
        /data/adb/modules/meta-overlayfs/mnt \
        /data/adb/mountify/mnt \
        /data/adb/modules/Mountify/mnt \
        /data/adb/modules/HybridMount/mnt \
        /data/adb/ksu/metamodule/mnt \
        /data/adb/ap/metamodule/mnt; do
        [ -n "$_lmcr_base" ] || continue
        _lmcr_candidate=$(luoshu_root_candidate "$_lmcr_base" "$_lmcr_id")
        _lmcr_candidates="$_lmcr_candidates $_lmcr_candidate"
    done

    # New meta modules frequently move their staging root. Discover only paths that clearly belong to
    # a mount/meta engine; never mirror into arbitrary directories named after the module.
    if command -v find >/dev/null 2>&1 && [ -d /data/adb ]; then
        for _lmcr_candidate in $(find /data/adb -maxdepth 6 -type d -name "$_lmcr_id" 2>/dev/null); do
            case "$_lmcr_candidate" in
                */mnt/"$_lmcr_id"|*/metamodule/*/"$_lmcr_id"|*/meta-overlay*/*/"$_lmcr_id"|*/mountify/*/"$_lmcr_id"|*/HybridMount/*/"$_lmcr_id")
                    _lmcr_candidates="$_lmcr_candidates $_lmcr_candidate"
                    ;;
            esac
        done
    fi

    for _lmcr_root in $_lmcr_candidates; do
        [ -n "$_lmcr_root" ] || continue
        [ "$_lmcr_root" != "$LUOSHU_MOUNT_MODDIR" ] || continue
        case " $_lmcr_seen " in *" $_lmcr_root "*) continue ;; esac
        _lmcr_seen="$_lmcr_seen $_lmcr_root"
        _lmcr_parent=${_lmcr_root%/*}
        [ -d "$_lmcr_root" ] || [ -d "$_lmcr_parent" ] || continue
        [ -w "$_lmcr_root" ] || [ -w "$_lmcr_parent" ] || continue
        printf '%s\n' "$_lmcr_root"
    done
}

luoshu_mount_lock_acquire() {
    if [ -f "$LUOSHU_MOUNT_LOCK" ]; then
        _lmla_pid=$(cat "$LUOSHU_MOUNT_LOCK" 2>/dev/null)
        if [ -n "$_lmla_pid" ] && kill -0 "$_lmla_pid" 2>/dev/null; then
            luoshu_mount_log "拒绝并发元模块同步：pid=$_lmla_pid"
            return 1
        fi
        rm -f "$LUOSHU_MOUNT_LOCK" 2>/dev/null || true
    fi
    printf '%s\n' "$$" > "$LUOSHU_MOUNT_LOCK" 2>/dev/null || return 1
    return 0
}

luoshu_mount_lock_release() {
    rm -f "$LUOSHU_MOUNT_LOCK" 2>/dev/null || true
}

luoshu_tree_fingerprint() {
    _ltf_root="$1"
    [ -d "$_ltf_root" ] || { printf 'absent\n'; return 0; }
    _ltf_tmp="${TMPDIR:-/data/local/tmp}/.luoshu-fingerprint.$$"
    rm -f "$_ltf_tmp" 2>/dev/null || true
    find "$_ltf_root" -type f 2>/dev/null | sort | while IFS= read -r _ltf_file; do
        _ltf_rel=${_ltf_file#$_ltf_root/}
        _ltf_sum=$(cksum "$_ltf_file" 2>/dev/null | awk '{print $1 ":" $2}')
        printf '%s|%s\n' "$_ltf_rel" "$_ltf_sum"
    done > "$_ltf_tmp" 2>/dev/null
    if command -v cksum >/dev/null 2>&1; then
        cksum "$_ltf_tmp" 2>/dev/null | awk '{print $1 ":" $2}'
    else
        wc -c < "$_ltf_tmp" 2>/dev/null
    fi
    rm -f "$_ltf_tmp" 2>/dev/null || true
}

luoshu_copy_tree_bounded() {
    _lctb_src="$1"
    _lctb_dst="$2"
    if command -v timeout >/dev/null 2>&1; then
        timeout "$LUOSHU_MOUNT_TIMEOUT" cp -af "$_lctb_src" "$_lctb_dst" 2>/dev/null && return 0
    elif command -v toybox >/dev/null 2>&1 && toybox timeout --help >/dev/null 2>&1; then
        toybox timeout "$LUOSHU_MOUNT_TIMEOUT" cp -af "$_lctb_src" "$_lctb_dst" 2>/dev/null && return 0
    else
        cp -af "$_lctb_src" "$_lctb_dst" 2>/dev/null && return 0
    fi
    rm -rf "$_lctb_dst" 2>/dev/null || true
    mkdir -p "$_lctb_dst" 2>/dev/null || return 1
    if command -v timeout >/dev/null 2>&1; then
        timeout "$LUOSHU_MOUNT_TIMEOUT" cp -rfp "$_lctb_src/." "$_lctb_dst/" 2>/dev/null
    elif command -v toybox >/dev/null 2>&1 && toybox timeout --help >/dev/null 2>&1; then
        toybox timeout "$LUOSHU_MOUNT_TIMEOUT" cp -rfp "$_lctb_src/." "$_lctb_dst/" 2>/dev/null
    else
        cp -rfp "$_lctb_src/." "$_lctb_dst/" 2>/dev/null
    fi
}

luoshu_copy_partition_atomic() {
    _lcpa_src="$1"
    _lcpa_dst="$2"
    _lcpa_fingerprint="$3"
    _lcpa_parent=${_lcpa_dst%/*}
    _lcpa_name=${_lcpa_dst##*/}
    _lcpa_tmp="$_lcpa_parent/.${_lcpa_name}.luoshu.$$"
    _lcpa_backup="$_lcpa_parent/.${_lcpa_name}.luoshu-backup.$$"

    mkdir -p "$_lcpa_parent" 2>/dev/null || return 1
    rm -rf "$_lcpa_tmp" "$_lcpa_backup" 2>/dev/null || true
    luoshu_copy_tree_bounded "$_lcpa_src" "$_lcpa_tmp" || { rm -rf "$_lcpa_tmp"; return 1; }
    printf '%s\n' "$_lcpa_fingerprint" > "$_lcpa_tmp/.luoshu-part-fingerprint" 2>/dev/null || { rm -rf "$_lcpa_tmp"; return 1; }
    chmod -R u=rwX,go=rX "$_lcpa_tmp" 2>/dev/null || true

    if [ -e "$_lcpa_dst" ]; then
        mv "$_lcpa_dst" "$_lcpa_backup" 2>/dev/null || { rm -rf "$_lcpa_tmp"; return 1; }
    fi
    if mv "$_lcpa_tmp" "$_lcpa_dst" 2>/dev/null; then
        rm -rf "$_lcpa_backup" 2>/dev/null || true
        return 0
    fi
    rm -rf "$_lcpa_dst" 2>/dev/null || true
    [ ! -e "$_lcpa_backup" ] || mv "$_lcpa_backup" "$_lcpa_dst" 2>/dev/null || true
    rm -rf "$_lcpa_tmp" 2>/dev/null || true
    return 1
}

luoshu_sync_mount_payload() {
    _lsmp_engine=$(luoshu_detect_mount_engine)
    _lsmp_manager=$(luoshu_detect_root_manager)
    _lsmp_roots=''
    _lsmp_synced=0
    _lsmp_skipped=0
    _lsmp_failed=0

    luoshu_mount_lock_acquire || return 1
    trap 'luoshu_mount_lock_release' EXIT HUP INT TERM

    for _lsmp_root in $(luoshu_meta_content_roots); do
        [ -n "$_lsmp_root" ] || continue
        _lsmp_roots="${_lsmp_roots}${_lsmp_roots:+,}$_lsmp_root"
        mkdir -p "$_lsmp_root" 2>/dev/null || { _lsmp_failed=$((_lsmp_failed + 1)); continue; }
        for _lsmp_part in $(luoshu_payload_partitions); do
            _lsmp_src="$LUOSHU_MOUNT_MODDIR/$_lsmp_part"
            _lsmp_dst="$_lsmp_root/$_lsmp_part"
            if [ -d "$_lsmp_src" ]; then
                _lsmp_fp=$(luoshu_tree_fingerprint "$_lsmp_src")
                _lsmp_old=$(cat "$_lsmp_dst/.luoshu-part-fingerprint" 2>/dev/null)
                if [ -n "$_lsmp_fp" ] && [ "$_lsmp_fp" = "$_lsmp_old" ]; then
                    _lsmp_skipped=$((_lsmp_skipped + 1))
                    continue
                fi
                if luoshu_copy_partition_atomic "$_lsmp_src" "$_lsmp_dst" "$_lsmp_fp"; then
                    _lsmp_synced=$((_lsmp_synced + 1))
                else
                    _lsmp_failed=$((_lsmp_failed + 1))
                fi
            else
                rm -rf "$_lsmp_dst" 2>/dev/null || _lsmp_failed=$((_lsmp_failed + 1))
            fi
        done
        printf 'source=%s\ntime=%s\n' "$LUOSHU_MOUNT_MODDIR" "$(date +%s)" > "$_lsmp_root/.luoshu-payload" 2>/dev/null || true
    done

    mkdir -p "$LUOSHU_MOUNT_MODDIR/config" 2>/dev/null || true
    {
        printf 'manager=%s\n' "$_lsmp_manager"
        printf 'engine=%s\n' "$_lsmp_engine"
        printf 'roots=%s\n' "$_lsmp_roots"
        printf 'synced=%s\n' "$_lsmp_synced"
        printf 'skipped=%s\n' "$_lsmp_skipped"
        printf 'failed=%s\n' "$_lsmp_failed"
        printf 'time=%s\n' "$(date +%s)"
    } > "$LUOSHU_MOUNT_MODDIR/config/mount_compat.conf.tmp.$$" 2>/dev/null || true
    mv -f "$LUOSHU_MOUNT_MODDIR/config/mount_compat.conf.tmp.$$" "$LUOSHU_MOUNT_MODDIR/config/mount_compat.conf" 2>/dev/null || true

    luoshu_mount_lock_release
    trap - EXIT HUP INT TERM
    if [ "$_lsmp_failed" -gt 0 ]; then
        luoshu_mount_log "元模块同步失败并保持旧负载：manager=$_lsmp_manager engine=$_lsmp_engine roots=$_lsmp_roots synced=$_lsmp_synced skipped=$_lsmp_skipped failed=$_lsmp_failed"
        return 1
    fi
    if [ -n "$_lsmp_roots" ]; then
        luoshu_mount_log "元模块同步完成：manager=$_lsmp_manager engine=$_lsmp_engine roots=$_lsmp_roots synced=$_lsmp_synced skipped=$_lsmp_skipped"
    else
        luoshu_mount_log "当前挂载引擎直接读取模块目录，无需镜像：manager=$_lsmp_manager engine=$_lsmp_engine"
    fi
    return 0
}

luoshu_mount_status_json() {
    _lmsj_engine=$(luoshu_detect_mount_engine)
    _lmsj_manager=$(luoshu_detect_root_manager)
    _lmsj_roots=''
    for _lmsj_root in $(luoshu_meta_content_roots); do _lmsj_roots="${_lmsj_roots}${_lmsj_roots:+,}$_lmsj_root"; done
    _lmsj_conf="$LUOSHU_MOUNT_MODDIR/config/mount_compat.conf"
    _lmsj_synced=$(sed -n 's/^synced=//p' "$_lmsj_conf" 2>/dev/null | head -n1)
    _lmsj_skipped=$(sed -n 's/^skipped=//p' "$_lmsj_conf" 2>/dev/null | head -n1)
    _lmsj_failed=$(sed -n 's/^failed=//p' "$_lmsj_conf" 2>/dev/null | head -n1)
    _lmsj_time=$(sed -n 's/^time=//p' "$_lmsj_conf" 2>/dev/null | head -n1)
    printf '{"manager":"%s","engine":"%s","roots":"%s","synced":%s,"skipped":%s,"failed":%s,"time":%s}' \
        "$_lmsj_manager" "$_lmsj_engine" "$_lmsj_roots" "${_lmsj_synced:-0}" "${_lmsj_skipped:-0}" "${_lmsj_failed:-0}" "${_lmsj_time:-0}"
}

# Keep enhanced ROM mapping and partition discovery in every caller that sources mount_compat.sh.
_luoshu_hyperos_helper="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}/common/hyperos_global.sh"
[ -f "$_luoshu_hyperos_helper" ] && . "$_luoshu_hyperos_helper"
_luoshu_font_config_partitions="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}/common/font_config_partitions.sh"
[ -f "$_luoshu_font_config_partitions" ] && . "$_luoshu_font_config_partitions"
