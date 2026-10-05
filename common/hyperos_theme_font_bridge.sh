#!/system/bin/sh
# HyperOS routes Chrome/WebView through a framework-owned theme symlink.
# Keep that router intact; replace only its exact active theme file in consumer
# namespaces. Invoked by the existing provider watcher, with no extra daemon.
set +e

MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
. "$MODDIR/common/google_font_provider_bridge.sh"
HTF_CACHE="$MODDIR/config/hyperos-theme-font"
HTF_STATE="$MODDIR/config/hyperos-theme-font-mount.conf"
HTF_MOUNTS="$MODDIR/config/hyperos-theme-font-namespaces.conf"
HTF_TARGET="${LUOSHU_THEME_FONT_TARGET:-/data/system/theme/fonts/Roboto-Regular.ttf}"
HTF_THEME_TARGET="$HTF_TARGET"
HTF_ALIAS="${LUOSHU_THEME_FONT_ALIAS:-/system/fonts/MiSansVF_Overlay.ttf}"
HTF_ROUTER="${LUOSHU_THEME_FONT_ROUTER:-/data/system/fonts/theme_webview/Roboto-Regular.ttf}"

_htf_active() {
    [ "$(_gfp_active_font)" != default ] || return 1
    [ -L "$HTF_ALIAS" ] || return 1
    # HyperOS can rebuild theme_webview as a regular font or use relative links.
    # Compare resolved routes, not the spelling of readlink's immediate hop.
    # Only the two known framework paths are accepted; never follow arbitrary
    # user theme links into another module or outside the font router.
    _htf_resolved=$(readlink -f "$HTF_ALIAS" 2>/dev/null) || return 1
    _htf_router_resolved=$(readlink -f "$HTF_ROUTER" 2>/dev/null) || return 1
    [ "$_htf_resolved" = "$_htf_router_resolved" ] || return 1
    case "$_htf_resolved" in
        "$HTF_THEME_TARGET"|"$HTF_ROUTER") HTF_TARGET=$_htf_resolved ;;
        *) return 1 ;;
    esac
    [ ! -L "$HTF_TARGET" ] && [ -s "$HTF_TARGET" ]
}

_htf_source() {
    # Only the boot-activated payload is authoritative. A pending selection
    # must not change Chrome before its system font generation is activated.
    _htf_fonts="$MODDIR/.luoshu-payload/system/fonts"
    for _htf_candidate in \
        "$_htf_fonts/.luoshu-font-store/mix-composite.font" \
        "$_htf_fonts/.luoshu-font-store/regular.font" \
        "$_htf_fonts/.luoshu-font-store/compact-regular.font" \
        "$_htf_fonts/MiSansVF.ttf" "$_htf_fonts/400.ttf"; do
        _gfp_valid_font "$_htf_candidate" && { printf '%s\n' "$_htf_candidate"; return 0; }
    done
    return 1
}

_htf_stamp() {
    stat -L -c '%d:%i:%s:%y:%z' "$1" 2>/dev/null
}

_htf_identity() {
    # Cache unlink/chcon can change ctime without changing a mounted inode.
    stat -L -c '%d:%i:%s' "$1" 2>/dev/null
}

_htf_pids() {
    _gfp_unique_namespace_pids
}

_htf_fingerprint() {
    _htf_active || { printf 'theme-font:inactive\n'; return 0; }
    _htf_donor=$(_htf_source) || { printf 'theme-font:source-pending\n'; return 0; }
    _htf_proc="${LUOSHU_PROC_ROOT:-/proc}"
    {
        printf 'theme-font:v2|%s|%s\n' "$_htf_donor" "$HTF_TARGET"
        _htf_stamp "$_htf_donor"
        _htf_stamp "$HTF_TARGET"
        _htf_stamp "${HTF_ROUTER%/*}"
        _htf_stamp "${HTF_TARGET%/*}"
        for _htf_pid in $(_htf_pids); do
            printf 'pid|%s|' "$_htf_pid"
            readlink "$_htf_proc/$_htf_pid/ns/mnt" 2>/dev/null || true
            _htf_stamp "$_htf_proc/$_htf_pid/root$HTF_TARGET"
        done
    } | _gfp_hash_text
}

_htf_prepare() {
    _htf_donor=$(_htf_source) || return 2
    _htf_source_stamp=$(_htf_stamp "$_htf_donor")
    _htf_target_stamp=$(_htf_stamp "$HTF_TARGET")
    [ -n "$_htf_source_stamp" ] && [ -n "$_htf_target_stamp" ] || return 1
    mkdir -p "$HTF_CACHE" "$MODDIR/logs" 2>/dev/null || return 1
    _htf_old_source=; _htf_old_target=; _htf_old_clone=
    if [ -s "$HTF_STATE" ]; then
        IFS='|' read -r _htf_old_source _htf_old_target _htf_old_clone < "$HTF_STATE"
        case "$_htf_old_clone" in "$HTF_CACHE/"*.ttf) ;; *) _htf_old_clone= ;; esac
        if [ "$_htf_source_stamp" = "$_htf_old_source" ] && [ -s "$_htf_old_clone" ]; then
            if [ "$_htf_target_stamp" = "$_htf_old_target" ] || \
               [ "$_htf_target_stamp" = "$(_htf_stamp "$_htf_old_clone")" ]; then
                HTF_CLONE=$_htf_old_clone
                return 0
            fi
        fi
    fi
    _htf_key=$(printf 'theme-view-v2|%s|%s|%s' "$_htf_donor" "$_htf_source_stamp" "$_htf_target_stamp" | _gfp_hash_text)
    HTF_CLONE="$HTF_CACHE/$_htf_key.ttf"
    if ! _gfp_valid_font "$HTF_CLONE"; then
        _htf_saved_patcher=$PATCHER
        PATCHER="$MODDIR/common/hyperos_theme_font_patch.py"
        _gfp_python --source "$_htf_donor" --target "$HTF_TARGET" --output "$HTF_CLONE" >> "$LOG" 2>&1
        _htf_rc=$?
        PATCHER=$_htf_saved_patcher
        [ "$_htf_rc" -eq 0 ] && _gfp_valid_font "$HTF_CLONE" || return 1
    fi
    if command -v chcon >/dev/null 2>&1; then
        chcon --reference="$HTF_TARGET" "$HTF_CLONE" 2>/dev/null || true
    fi
    printf '%s|%s|%s\n' "$_htf_source_stamp" "$_htf_target_stamp" "$HTF_CLONE" > "${HTF_STATE}.tmp.$$" || return 1
    mv -f "${HTF_STATE}.tmp.$$" "$HTF_STATE" || return 1
    chmod 0600 "$HTF_STATE" 2>/dev/null || true
    # Kernel binds retain old inodes. Keep one new view and one previous view
    # while a failed namespace repair is retried; never accumulate selections.
    for _htf_cached in "$HTF_CACHE"/*.ttf; do
        [ "$_htf_cached" = "$HTF_CLONE" ] || [ "$_htf_cached" = "$_htf_old_clone" ] || rm -f "$_htf_cached"
    done
}

_htf_owned_identity() {
    [ -s "$HTF_MOUNTS" ] || return 1
    awk -F '|' -v inode="$1" -v target="$2" -v legacy="$HTF_THEME_TARGET" \
        '$2 == inode && (NF == 4 ? $4 : legacy) == target {found=1} END {exit !found}' "$HTF_MOUNTS"
}

_htf_clear_owned_pid() {
    _htf_clear_pid="$1"
    _htf_clear_target="${2:-$HTF_TARGET}"
    _htf_clear_round=0
    # Multiple old layers are possible after an interrupted earlier attempt.
    # Never pop a foreign layer; retain the journal if a layer cannot be removed.
    while [ "$_htf_clear_round" -lt 64 ]; do
        _htf_clear_id=$(_htf_identity "${LUOSHU_PROC_ROOT:-/proc}/$_htf_clear_pid/root$_htf_clear_target")
        [ -n "$_htf_clear_id" ] || return 0
        _htf_owned_identity "$_htf_clear_id" "$_htf_clear_target" || return 0
        _gfp_unmount_in_pid "$_htf_clear_pid" "$_htf_clear_target" || return 1
        _htf_clear_round=$((_htf_clear_round + 1))
    done
    return 1
}

_htf_mount_pid() {
    _htf_mount_pid_value="$1"
    _htf_mount_ns=$(readlink "${LUOSHU_PROC_ROOT:-/proc}/$_htf_mount_pid_value/ns/mnt" 2>/dev/null)
    _htf_mount_id=$(_htf_identity "${LUOSHU_PROC_ROOT:-/proc}/$_htf_mount_pid_value/root$HTF_TARGET")
    _htf_mount_previous=$_htf_mount_id
    _htf_mount_changed=0
    # Prepare the journal before mounting, and commit each namespace promptly.
    # A later failed namespace must not erase successful ownership records.
    _htf_mount_row="${HTF_MOUNTS}.row.$$"
    if [ -s "$HTF_MOUNTS" ]; then
        awk -F '|' -v ns="$_htf_mount_ns" -v target="$HTF_TARGET" -v legacy="$HTF_THEME_TARGET" \
            '!($1 == ns && (NF == 4 ? $4 : legacy) == target)' "$HTF_MOUNTS" > "$_htf_mount_row" || return 1
    else
        : > "$_htf_mount_row" || return 1
    fi
    if [ -n "$_htf_mount_id" ] && [ -s "$HTF_MOUNTS" ] && awk -F '|' -v inode="$_htf_mount_id" -v clone="$HTF_CLONE" -v target="$HTF_TARGET" -v legacy="$HTF_THEME_TARGET" \
        '$2 == inode && $3 == clone && (NF == 4 ? $4 : legacy) == target {found=1} END {exit !found}' "$HTF_MOUNTS"; then
        _gfp_mount_mode=already
    else
        _htf_clear_owned_pid "$_htf_mount_pid_value" || { rm -f "$_htf_mount_row"; return 1; }
        _gfp_mount_in_pid "$_htf_mount_pid_value" "$HTF_CLONE" "$HTF_TARGET" 1 || { rm -f "$_htf_mount_row"; return 1; }
        [ "$_gfp_mount_mode" = already ] || _htf_mount_changed=1
        _htf_mount_id=$(_htf_identity "${LUOSHU_PROC_ROOT:-/proc}/$_htf_mount_pid_value/root$HTF_TARGET")
    fi
    _htf_mount_saved=0
    if [ -n "$_htf_mount_ns" ] && [ -n "$_htf_mount_id" ]; then
        printf '%s|%s|%s|%s\n' "$_htf_mount_ns" "$_htf_mount_id" "$HTF_CLONE" "$HTF_TARGET" >> "$_htf_mount_row" && \
            mv -f "$_htf_mount_row" "$HTF_MOUNTS" && _htf_mount_saved=1
    fi
    rm -f "$_htf_mount_row"
    if [ "$_htf_mount_saved" != 1 ]; then
        if [ "$_htf_mount_changed" = 1 ] && [ "$(_htf_identity "${LUOSHU_PROC_ROOT:-/proc}/$_htf_mount_pid_value/root$HTF_TARGET")" = "$_htf_mount_id" ]; then
            _gfp_unmount_in_pid "$_htf_mount_pid_value" "$HTF_TARGET" || true
        fi
        return 1
    fi
    chmod 0600 "$HTF_MOUNTS" 2>/dev/null || true
    [ "$_htf_mount_changed" != 1 ] || _gfp_queue_all_consumers "${_htf_mount_previous%:*}"
    return 0
}

_htf_apply_internal() {
    _gfp_consumer_pids_loaded=
    _gfp_queued_identities=
    if ! _htf_active; then
        _htf_restore || return 1
        return 2
    fi
    # A router rebuilt as a regular file changes the destination. Release the
    # previous destination by its recorded path before applying the new route.
    if [ -s "$HTF_MOUNTS" ]; then
        _htf_retired=$(awk -F '|' -v current="$HTF_TARGET" -v legacy="$HTF_THEME_TARGET" '{target=(NF == 4 ? $4 : legacy); if (target != current && !seen[target]++) print target}' "$HTF_MOUNTS")
        while IFS= read -r _htf_retired_target; do
            [ -n "$_htf_retired_target" ] || continue
            for _htf_retired_pid in $(_htf_pids); do
                _htf_clear_owned_pid "$_htf_retired_pid" "$_htf_retired_target" || return 1
            done
        done <<EOF
$_htf_retired
EOF
    fi
    _htf_prepare || return $?
    # Keep the original theme inode from prepare even when a shared namespace
    # already exposes our clone; old Chrome FDs can still refer to that inode.
    _htf_original_stamp=$(awk -F '|' 'NR == 1 {print $2}' "$HTF_STATE" 2>/dev/null)
    _htf_original_identity=$(printf '%s\n' "$_htf_original_stamp" | awk -F ':' 'NF >= 2 {print $1 ":" $2}')
    _htf_current_identity=$(_gfp_identity "$HTF_CLONE")
    [ "$_htf_original_identity" = "${_htf_current_identity%:*}" ] || _gfp_queue_all_consumers "$_htf_original_identity"
    _htf_ok=0; _htf_failed=0
    _htf_proc="${LUOSHU_PROC_ROOT:-/proc}"
    _htf_journal="${HTF_MOUNTS}.tmp.$$"
    : > "$_htf_journal" || return 1
    : > "${_htf_journal}.live" || return 1
    : > "${_htf_journal}.handled" || return 1
    for _htf_pid in $(_htf_pids); do
        _htf_ns=$(readlink "$_htf_proc/$_htf_pid/ns/mnt" 2>/dev/null)
        [ -z "$_htf_ns" ] || printf '%s\n' "$_htf_ns" >> "${_htf_journal}.live"
        if _htf_mount_pid "$_htf_pid"; then
            _htf_ok=$((_htf_ok + 1))
            _htf_ns=$(readlink "$_htf_proc/$_htf_pid/ns/mnt" 2>/dev/null)
            _htf_view=$(_htf_identity "$_htf_proc/$_htf_pid/root$HTF_TARGET")
            [ -z "$_htf_ns" ] || [ -z "$_htf_view" ] || printf '%s|%s|%s|%s\n' "$_htf_ns" "$_htf_view" "$HTF_CLONE" "$HTF_TARGET" >> "$_htf_journal"
            [ -z "$_htf_ns" ] || printf '%s\n' "$_htf_ns" >> "${_htf_journal}.handled"
        else
            _htf_failed=$((_htf_failed + 1))
        fi
    done
    # Keep previous successful binds when one process disappears or a retry
    # fails. The journal also identifies temporary staging inodes after unlink.
    if [ -s "$HTF_MOUNTS" ]; then
        awk -F '|' 'FILENAME == ARGV[1] {live[$1]=1; next}
                    FILENAME == ARGV[2] {handled[$1]=1; next}
                    $1 in live && !($1 in handled)' \
            "${_htf_journal}.live" "${_htf_journal}.handled" "$HTF_MOUNTS" >> "$_htf_journal"
    fi
    _htf_journal_rc=0
    awk -F '|' 'NF >= 3 && !seen[$1 FS $2 FS $4]++' "$_htf_journal" > "${HTF_MOUNTS}.new.$$" && \
        mv -f "${HTF_MOUNTS}.new.$$" "$HTF_MOUNTS" || _htf_journal_rc=1
    rm -f "$_htf_journal" "${_htf_journal}.live" "${_htf_journal}.handled" "${HTF_MOUNTS}.new.$$"
    _gfp_log "HyperOS theme view：mounted=$_htf_ok failed=$_htf_failed; framework symlinks preserved"
    [ "$_htf_ok" -gt 0 ] && [ "$_htf_failed" -eq 0 ] && [ "$_htf_journal_rc" -eq 0 ]
}

_htf_restore_internal() {
    [ -s "$HTF_MOUNTS" ] || { rm -f "$HTF_STATE"; return 0; }
    # Mount ownership is checked by inode before unmounting; never detach a
    # replacement installed by the ROM/theme manager or another module.
    _htf_proc="${LUOSHU_PROC_ROOT:-/proc}"
    _htf_restore_failed=0
    _htf_restore_targets=$(awk -F '|' -v legacy="$HTF_THEME_TARGET" '{target=(NF == 4 ? $4 : legacy); if (!seen[target]++) print target}' "$HTF_MOUNTS")
    _htf_restore_pids=$(_htf_pids)
    while IFS= read -r _htf_restore_target; do
        [ -n "$_htf_restore_target" ] || continue
        for _htf_pid in $_htf_restore_pids; do
            _htf_clear_owned_pid "$_htf_pid" "$_htf_restore_target" || _htf_restore_failed=1
        done
    done <<EOF
$_htf_restore_targets
EOF
    [ "$_htf_restore_failed" -eq 0 ] || return 1
    rm -f "$HTF_STATE" "$HTF_MOUNTS" 2>/dev/null || true
}

_htf_apply() { _gfp_locked _htf_apply_internal; }
_htf_restore() { _gfp_locked _htf_restore_internal; }

if [ "${0##*/}" = hyperos_theme_font_bridge.sh ]; then
    case "${1:-apply}" in
        fingerprint) _htf_fingerprint ;;
        apply) _htf_apply ;;
        restore) _htf_restore ;;
        *) exit 2 ;;
    esac
fi
