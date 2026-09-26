#!/system/bin/sh
# Follow dynamic routes discovered from actual system font symlinks.
# Keep aliases and original targets intact; mount validated isolated views only
# in consumer namespaces, maintained by the existing provider watcher.
set +e

MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
. "$MODDIR/common/google_font_provider_bridge.sh"
DFR_BASE="$MODDIR/config/dynamic-font-routes"
DFR_INVENTORY="$MODDIR/config/device_font_inventory.json"
DFR_CATALOG="$DFR_BASE/routes.tsv"
DFR_CATALOG_STAMP="$DFR_BASE/inventory.stamp"
DFR_DATA_ROOT="${LUOSHU_DYNAMIC_DATA_ROOT:-/data}"
DFR_CR=$(printf '\r')

_dfr_select() {
    DFR_KEY="$1"; DFR_ALIAS="$2"; DFR_RECORDED_TARGET="$3"
    DFR_TARGET="$DFR_RECORDED_TARGET"
    DFR_CACHE="$DFR_BASE/$DFR_KEY"
    DFR_STATE="$DFR_CACHE/state.conf"
    DFR_MOUNTS="$DFR_CACHE/namespaces.conf"
}

_dfr_catalog() {
    [ -s "$DFR_INVENTORY" ] || return 2
    _dfr_inventory_stamp=$(_dfr_stamp "$DFR_INVENTORY") || return 1
    [ -s "$DFR_CATALOG_STAMP" ] && [ -f "$DFR_CATALOG" ] && \
        [ "$(cat "$DFR_CATALOG_STAMP")" = "$_dfr_inventory_stamp" ] && return 0
    mkdir -p "$DFR_BASE" "$MODDIR/logs" || return 1
    _dfr_catalog_tmp="$DFR_BASE/.routes.$$"
    _dfr_saved_patcher=$PATCHER
    PATCHER="$MODDIR/common/dynamic_font_route_patch.py"
    _gfp_python --inventory "$DFR_INVENTORY" > "$_dfr_catalog_tmp" 2>> "$LOG"
    _dfr_catalog_rc=$?
    PATCHER=$_dfr_saved_patcher
    [ "$_dfr_catalog_rc" -eq 0 ] || { rm -f "$_dfr_catalog_tmp"; return 1; }
    # A concurrent refresh cannot certify rows derived from the older inventory.
    [ "$(_dfr_stamp "$DFR_INVENTORY")" = "$_dfr_inventory_stamp" ] || { rm -f "$_dfr_catalog_tmp"; return 1; }
    mv -f "$_dfr_catalog_tmp" "$DFR_CATALOG" || return 1
    printf '%s\n' "$_dfr_inventory_stamp" > "$DFR_CATALOG_STAMP.tmp.$$" && \
        mv -f "$DFR_CATALOG_STAMP.tmp.$$" "$DFR_CATALOG_STAMP"
}

_dfr_active() {
    [ "$(_gfp_active_font)" != default ] || return 1
    [ -L "$DFR_ALIAS" ] || return 1
    _dfr_resolved=$(readlink -f "$DFR_ALIAS" 2>/dev/null) || return 1
    case "$_dfr_resolved" in
        "$DFR_DATA_ROOT"/*) ;;
        *) return 1 ;;
    esac
    case "$_dfr_resolved" in
        "$MODDIR"/*|*'|'*|*'
'*|*"$DFR_CR"*|*'	'*) return 1 ;;
    esac
    # The validator checks font bytes and text capabilities; framework targets
    # are not required to use a particular filename suffix.
    DFR_TARGET=$_dfr_resolved
    [ ! -L "$DFR_TARGET" ] && [ -f "$DFR_TARGET" ] && [ -s "$DFR_TARGET" ]
}

_dfr_source() {
    # Only the boot-activated payload is authoritative. A pending selection
    # must not change Chrome before its system font generation is activated.
    _dfr_fonts="$MODDIR/.luoshu-payload/system/fonts"
    for _dfr_candidate in \
        "$_dfr_fonts/.luoshu-font-store/mix-composite.font" \
        "$_dfr_fonts/.luoshu-font-store/regular.font" \
        "$_dfr_fonts/.luoshu-font-store/compact-regular.font" \
        "$_dfr_fonts/.luoshu-font-store/variable.font"; do
        _gfp_valid_font "$_dfr_candidate" && { printf '%s\n' "$_dfr_candidate"; return 0; }
    done
    return 1
}

_dfr_stamp() {
    stat -L -c '%d:%i:%s:%y:%z' "$1" 2>/dev/null
}

_dfr_identity() {
    # Cache unlink/chcon can change ctime without changing a mounted inode.
    stat -L -c '%d:%i:%s' "$1" 2>/dev/null
}

_dfr_pids() {
    _gfp_unique_namespace_pids
}

_dfr_fingerprint() {
    _dfr_active || { printf 'dynamic-font:inactive\n'; return 0; }
    _dfr_donor=$(_dfr_source) || { printf 'dynamic-font:source-pending\n'; return 0; }
    _dfr_proc="${LUOSHU_PROC_ROOT:-/proc}"
    {
        printf 'dynamic-font:v1|%s|%s|%s\n' "$_dfr_donor" "$DFR_ALIAS" "$DFR_TARGET"
        _dfr_stamp "$_dfr_donor"
        _dfr_stamp "${_dfr_donor%/*}"
        _dfr_stamp "$DFR_TARGET"
        _dfr_stamp "$DFR_ALIAS"
        _dfr_stamp "${DFR_ALIAS%/*}"
        _dfr_stamp "${DFR_TARGET%/*}"
        for _dfr_pid in $(_dfr_pids); do
            printf 'pid|%s|' "$_dfr_pid"
            readlink "$_dfr_proc/$_dfr_pid/ns/mnt" 2>/dev/null || true
            _dfr_stamp "$_dfr_proc/$_dfr_pid/root$DFR_TARGET"
        done
    } | _gfp_hash_text
}

_dfr_prepare() {
    _dfr_donor=$(_dfr_source) || return 2
    _dfr_source_stamp="$(_dfr_stamp "$_dfr_donor"):$(_dfr_stamp "${_dfr_donor%/*}")"
    _dfr_target_stamp=$(_dfr_stamp "$DFR_TARGET")
    [ -n "$_dfr_source_stamp" ] && [ -n "$_dfr_target_stamp" ] || return 1
    mkdir -p "$DFR_CACHE" "$MODDIR/logs" 2>/dev/null || return 1
    _dfr_old_source=; _dfr_old_target=; _dfr_old_clone=
    if [ -s "$DFR_STATE" ]; then
        IFS='|' read -r _dfr_old_source _dfr_old_target _dfr_old_clone < "$DFR_STATE"
        case "$_dfr_old_clone" in "$DFR_CACHE/"*.ttf) ;; *) _dfr_old_clone= ;; esac
        if [ "$_dfr_source_stamp" = "$_dfr_old_source" ] && [ -s "$_dfr_old_clone" ]; then
            if [ "$_dfr_target_stamp" = "$_dfr_old_target" ] || \
               [ "$_dfr_target_stamp" = "$(_dfr_stamp "$_dfr_old_clone")" ]; then
                DFR_CLONE=$_dfr_old_clone
                return 0
            fi
        fi
    fi
    _dfr_key=$(printf 'dynamic-view-v1|%s|%s|%s|%s' "$DFR_TARGET" "$_dfr_donor" "$_dfr_source_stamp" "$_dfr_target_stamp" | _gfp_hash_text)
    DFR_CLONE="$DFR_CACHE/$_dfr_key.ttf"
    if ! _gfp_valid_font "$DFR_CLONE"; then
        _dfr_saved_patcher=$PATCHER
        PATCHER="$MODDIR/common/dynamic_font_route_patch.py"
        _gfp_python --module "$MODDIR" --alias "$DFR_ALIAS" --target "$DFR_TARGET" --output "$DFR_CLONE" >> "$LOG" 2>&1
        _dfr_rc=$?
        PATCHER=$_dfr_saved_patcher
        [ "$_dfr_rc" -ne 2 ] || return 2
        [ "$_dfr_rc" -eq 0 ] && _gfp_valid_font "$DFR_CLONE" || return 1
    fi
    if command -v chcon >/dev/null 2>&1; then
        chcon --reference="$DFR_TARGET" "$DFR_CLONE" 2>/dev/null || true
    fi
    printf '%s|%s|%s\n' "$_dfr_source_stamp" "$_dfr_target_stamp" "$DFR_CLONE" > "${DFR_STATE}.tmp.$$" || return 1
    mv -f "${DFR_STATE}.tmp.$$" "$DFR_STATE" || return 1
    chmod 0600 "$DFR_STATE" 2>/dev/null || true
    # Kernel binds retain old inodes. Keep one new view and one previous view
    # while a failed namespace repair is retried; never accumulate selections.
    for _dfr_cached in "$DFR_CACHE"/*.ttf; do
        [ "$_dfr_cached" = "$DFR_CLONE" ] || [ "$_dfr_cached" = "$_dfr_old_clone" ] || rm -f "$_dfr_cached"
    done
}

_dfr_owned_identity() {
    [ -s "$DFR_MOUNTS" ] || return 1
    awk -F '|' -v inode="$1" -v target="$2" -v legacy="$DFR_RECORDED_TARGET" \
        '$2 == inode && (NF == 4 ? $4 : legacy) == target {found=1} END {exit !found}' "$DFR_MOUNTS"
}

_dfr_clear_owned_pid() {
    _dfr_clear_pid="$1"
    _dfr_clear_target="${2:-$DFR_TARGET}"
    _dfr_clear_round=0
    # Multiple old layers are possible after an interrupted earlier attempt.
    # Never pop a foreign layer; retain the journal if a layer cannot be removed.
    while [ "$_dfr_clear_round" -lt 64 ]; do
        _dfr_clear_id=$(_dfr_identity "${LUOSHU_PROC_ROOT:-/proc}/$_dfr_clear_pid/root$_dfr_clear_target")
        [ -n "$_dfr_clear_id" ] || return 0
        _dfr_owned_identity "$_dfr_clear_id" "$_dfr_clear_target" || return 0
        _gfp_unmount_in_pid "$_dfr_clear_pid" "$_dfr_clear_target" || return 1
        _dfr_clear_round=$((_dfr_clear_round + 1))
    done
    return 1
}

_dfr_mount_pid() {
    # The system may change a route after preparation. Do not attach the old
    # contract to another target generation. The watcher will retry its new view.
    [ "$(readlink -f "$DFR_ALIAS" 2>/dev/null)" = "$DFR_TARGET" ] || return 1
    _dfr_mount_pid_value="$1"
    _dfr_mount_ns=$(readlink "${LUOSHU_PROC_ROOT:-/proc}/$_dfr_mount_pid_value/ns/mnt" 2>/dev/null)
    _dfr_mount_id=$(_dfr_identity "${LUOSHU_PROC_ROOT:-/proc}/$_dfr_mount_pid_value/root$DFR_TARGET")
    _dfr_mount_previous=$_dfr_mount_id
    _dfr_mount_changed=0
    # Prepare the journal before mounting, and commit each namespace promptly.
    # A later failed namespace must not erase successful ownership records.
    _dfr_mount_row="${DFR_MOUNTS}.row.$$"
    if [ -s "$DFR_MOUNTS" ]; then
        awk -F '|' -v ns="$_dfr_mount_ns" -v target="$DFR_TARGET" -v legacy="$DFR_RECORDED_TARGET" \
            '!($1 == ns && (NF == 4 ? $4 : legacy) == target)' "$DFR_MOUNTS" > "$_dfr_mount_row" || return 1
    else
        : > "$_dfr_mount_row" || return 1
    fi
    if [ -n "$_dfr_mount_id" ] && [ -s "$DFR_MOUNTS" ] && awk -F '|' -v inode="$_dfr_mount_id" -v clone="$DFR_CLONE" -v target="$DFR_TARGET" -v legacy="$DFR_RECORDED_TARGET" \
        '$2 == inode && $3 == clone && (NF == 4 ? $4 : legacy) == target {found=1} END {exit !found}' "$DFR_MOUNTS"; then
        _gfp_mount_mode=already
    else
        _dfr_clear_owned_pid "$_dfr_mount_pid_value" || { rm -f "$_dfr_mount_row"; return 1; }
        _gfp_mount_in_pid "$_dfr_mount_pid_value" "$DFR_CLONE" "$DFR_TARGET" 1 || { rm -f "$_dfr_mount_row"; return 1; }
        [ "$_gfp_mount_mode" = already ] || _dfr_mount_changed=1
        _dfr_mount_id=$(_dfr_identity "${LUOSHU_PROC_ROOT:-/proc}/$_dfr_mount_pid_value/root$DFR_TARGET")
    fi
    _dfr_mount_saved=0
    if [ -n "$_dfr_mount_ns" ] && [ -n "$_dfr_mount_id" ]; then
        printf '%s|%s|%s|%s\n' "$_dfr_mount_ns" "$_dfr_mount_id" "$DFR_CLONE" "$DFR_TARGET" >> "$_dfr_mount_row" && \
            mv -f "$_dfr_mount_row" "$DFR_MOUNTS" && _dfr_mount_saved=1
    fi
    rm -f "$_dfr_mount_row"
    if [ "$_dfr_mount_saved" != 1 ]; then
        if [ "$_dfr_mount_changed" = 1 ] && [ "$(_dfr_identity "${LUOSHU_PROC_ROOT:-/proc}/$_dfr_mount_pid_value/root$DFR_TARGET")" = "$_dfr_mount_id" ]; then
            _gfp_unmount_in_pid "$_dfr_mount_pid_value" "$DFR_TARGET" || true
        fi
        return 1
    fi
    chmod 0600 "$DFR_MOUNTS" 2>/dev/null || true
    [ "$_dfr_mount_changed" != 1 ] || _gfp_queue_all_consumers "${_dfr_mount_previous%:*}"
    return 0
}

_dfr_apply_internal() {
    _gfp_consumer_pids_loaded=
    _gfp_queued_identities=
    if ! _dfr_active; then
        _dfr_restore || return 1
        return 2
    fi
    # A router rebuilt as a regular file changes the destination. Release the
    # previous destination by its recorded path before applying the new route.
    if [ -s "$DFR_MOUNTS" ]; then
        _dfr_retired=$(awk -F '|' -v current="$DFR_TARGET" -v legacy="$DFR_RECORDED_TARGET" '{target=(NF == 4 ? $4 : legacy); if (target != current && !seen[target]++) print target}' "$DFR_MOUNTS")
        while IFS= read -r _dfr_retired_target; do
            [ -n "$_dfr_retired_target" ] || continue
            for _dfr_retired_pid in $(_dfr_pids); do
                _dfr_clear_owned_pid "$_dfr_retired_pid" "$_dfr_retired_target" || return 1
            done
        done <<EOF
$_dfr_retired
EOF
    fi
    _dfr_prepare
    _dfr_prepare_rc=$?
    if [ "$_dfr_prepare_rc" -eq 2 ]; then
        _dfr_restore_internal || return 1
        return 2
    fi
    [ "$_dfr_prepare_rc" -eq 0 ] || return "$_dfr_prepare_rc"
    # Keep the original dynamic inode from prepare even when a shared namespace
    # already exposes our clone; old Chrome FDs can still refer to that inode.
    _dfr_original_stamp=$(awk -F '|' 'NR == 1 {print $2}' "$DFR_STATE" 2>/dev/null)
    _dfr_original_identity=$(printf '%s\n' "$_dfr_original_stamp" | awk -F ':' 'NF >= 2 {print $1 ":" $2}')
    _dfr_current_identity=$(_gfp_identity "$DFR_CLONE")
    [ "$_dfr_original_identity" = "${_dfr_current_identity%:*}" ] || _gfp_queue_all_consumers "$_dfr_original_identity"
    _dfr_ok=0; _dfr_failed=0
    _dfr_proc="${LUOSHU_PROC_ROOT:-/proc}"
    _dfr_journal="${DFR_MOUNTS}.tmp.$$"
    : > "$_dfr_journal" || return 1
    : > "${_dfr_journal}.live" || return 1
    : > "${_dfr_journal}.handled" || return 1
    for _dfr_pid in $(_dfr_pids); do
        _dfr_ns=$(readlink "$_dfr_proc/$_dfr_pid/ns/mnt" 2>/dev/null)
        [ -z "$_dfr_ns" ] || printf '%s\n' "$_dfr_ns" >> "${_dfr_journal}.live"
        if _dfr_mount_pid "$_dfr_pid"; then
            _dfr_ok=$((_dfr_ok + 1))
            _dfr_ns=$(readlink "$_dfr_proc/$_dfr_pid/ns/mnt" 2>/dev/null)
            _dfr_view=$(_dfr_identity "$_dfr_proc/$_dfr_pid/root$DFR_TARGET")
            [ -z "$_dfr_ns" ] || [ -z "$_dfr_view" ] || printf '%s|%s|%s|%s\n' "$_dfr_ns" "$_dfr_view" "$DFR_CLONE" "$DFR_TARGET" >> "$_dfr_journal"
            [ -z "$_dfr_ns" ] || printf '%s\n' "$_dfr_ns" >> "${_dfr_journal}.handled"
        else
            _dfr_failed=$((_dfr_failed + 1))
        fi
    done
    # Keep previous successful binds when one process disappears or a retry
    # fails. The journal also identifies temporary staging inodes after unlink.
    if [ -s "$DFR_MOUNTS" ]; then
        awk -F '|' 'FILENAME == ARGV[1] {live[$1]=1; next}
                    FILENAME == ARGV[2] {handled[$1]=1; next}
                    $1 in live && !($1 in handled)' \
            "${_dfr_journal}.live" "${_dfr_journal}.handled" "$DFR_MOUNTS" >> "$_dfr_journal"
    fi
    _dfr_journal_rc=0
    awk -F '|' 'NF >= 3 && !seen[$1 FS $2 FS $4]++' "$_dfr_journal" > "${DFR_MOUNTS}.new.$$" && \
        mv -f "${DFR_MOUNTS}.new.$$" "$DFR_MOUNTS" || _dfr_journal_rc=1
    rm -f "$_dfr_journal" "${_dfr_journal}.live" "${_dfr_journal}.handled" "${DFR_MOUNTS}.new.$$"
    _gfp_log "Inventory dynamic font view：mounted=$_dfr_ok failed=$_dfr_failed; framework symlinks preserved"
    [ "$_dfr_ok" -gt 0 ] && [ "$_dfr_failed" -eq 0 ] && [ "$_dfr_journal_rc" -eq 0 ]
}

_dfr_restore_internal() {
    [ -s "$DFR_MOUNTS" ] || { rm -f "$DFR_STATE"; return 0; }
    # Mount ownership is checked by inode before unmounting; never detach a
    # replacement installed by the ROM/theme manager or another module.
    _dfr_proc="${LUOSHU_PROC_ROOT:-/proc}"
    _dfr_restore_failed=0
    _dfr_restore_targets=$(awk -F '|' -v legacy="$DFR_RECORDED_TARGET" '{target=(NF == 4 ? $4 : legacy); if (!seen[target]++) print target}' "$DFR_MOUNTS")
    _dfr_restore_pids=$(_dfr_pids)
    while IFS= read -r _dfr_restore_target; do
        [ -n "$_dfr_restore_target" ] || continue
        for _dfr_pid in $_dfr_restore_pids; do
            _dfr_clear_owned_pid "$_dfr_pid" "$_dfr_restore_target" || _dfr_restore_failed=1
        done
    done <<EOF
$_dfr_restore_targets
EOF
    [ "$_dfr_restore_failed" -eq 0 ] || return 1
    rm -f "$DFR_STATE" "$DFR_MOUNTS" 2>/dev/null || true
}

_dfr_apply() { _gfp_locked _dfr_apply_internal; }
_dfr_restore() { _gfp_locked _dfr_restore_internal; }

# Removed inventory routes still own mounts until their journals are restored.
# Enumerate journals as well as current rows, so an inventory refresh cannot
# orphan a view in Chrome or a newly inherited namespace.
_dfr_restore_all_internal() {
    _dfr_restore_all_rc=0
    for _dfr_journal in "$DFR_BASE"/*/namespaces.conf; do
        [ -s "$_dfr_journal" ] || continue
        _dfr_directory=${_dfr_journal%/*}
        _dfr_select "${_dfr_directory##*/}" '' ''
        _dfr_restore_internal || _dfr_restore_all_rc=1
    done
    return "$_dfr_restore_all_rc"
}

_dfr_apply_all_internal() {
    if [ "$(_gfp_active_font)" = default ]; then
        _dfr_restore_all_internal || return 1
        return 2
    fi
    _dfr_catalog
    _dfr_catalog_status=$?
    if [ "$_dfr_catalog_status" -eq 2 ]; then
        _dfr_restore_all_internal || return 1
        return 2
    fi
    [ "$_dfr_catalog_status" -eq 0 ] || return 1
    _dfr_all_failed=0; _dfr_all_applied=0
    for _dfr_journal in "$DFR_BASE"/*/namespaces.conf; do
        [ -s "$_dfr_journal" ] || continue
        _dfr_directory=${_dfr_journal%/*}
        _dfr_retired_key=${_dfr_directory##*/}
        awk -F '|' -v key="$_dfr_retired_key" '$1 == key {found=1} END {exit !found}' "$DFR_CATALOG" && continue
        _dfr_select "$_dfr_retired_key" '' ''
        _dfr_restore_internal || _dfr_all_failed=1
    done
    while IFS='|' read -r _dfr_row_key _dfr_row_alias _dfr_row_target; do
        [ -n "$_dfr_row_key" ] || continue
        _dfr_select "$_dfr_row_key" "$_dfr_row_alias" "$_dfr_row_target"
        _dfr_apply_internal
        case "$?" in 0) _dfr_all_applied=1 ;; 2) ;; *) _dfr_all_failed=1 ;; esac
    done < "$DFR_CATALOG"
    [ "$_dfr_all_failed" -eq 0 ] || return 1
    [ "$_dfr_all_applied" -eq 1 ] && return 0
    return 2
}

_dfr_fingerprint_all() {
    [ "$(_gfp_active_font)" != default ] || { printf 'dynamic-fonts:default\n'; return 0; }
    _dfr_catalog
    _dfr_catalog_status=$?
    [ "$_dfr_catalog_status" -ne 2 ] || { printf 'dynamic-fonts:no-inventory\n'; return 0; }
    [ "$_dfr_catalog_status" -eq 0 ] || return 1
    {
        _dfr_stamp "$DFR_INVENTORY"
        _dfr_stamp "$MODDIR/.luoshu-payload"
        while IFS='|' read -r _dfr_row_key _dfr_row_alias _dfr_row_target; do
            [ -n "$_dfr_row_key" ] || continue
            _dfr_select "$_dfr_row_key" "$_dfr_row_alias" "$_dfr_row_target"
            _dfr_fingerprint
        done < "$DFR_CATALOG"
    } | _gfp_hash_text
}

if [ "${0##*/}" = dynamic_font_route_bridge.sh ]; then
    case "${1:-apply}" in
        fingerprint) _gfp_locked _dfr_fingerprint_all ;;
        apply) _gfp_locked _dfr_apply_all_internal ;;
        restore) _gfp_locked _dfr_restore_all_internal ;;
        *) exit 2 ;;
    esac
fi
