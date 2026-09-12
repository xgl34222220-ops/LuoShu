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
HTF_ALIAS="${LUOSHU_THEME_FONT_ALIAS:-/system/fonts/MiSansVF_Overlay.ttf}"
HTF_ROUTER="${LUOSHU_THEME_FONT_ROUTER:-/data/system/fonts/theme_webview/Roboto-Regular.ttf}"

_htf_active() {
    [ "$(_gfp_active_font)" != default ] || return 1
    [ -L "$HTF_ALIAS" ] && [ "$(readlink "$HTF_ALIAS" 2>/dev/null)" = "$HTF_ROUTER" ] || return 1
    [ -L "$HTF_ROUTER" ] && [ "$(readlink "$HTF_ROUTER" 2>/dev/null)" = "$HTF_TARGET" ] || return 1
    # Never follow a theme file onward into an unrelated path.
    # Empty-font themes can legitimately have a tiny SFNT. Let the patcher's
    # table parser validate it; a provider-cache size threshold is not valid here.
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
    stat -L -c '%d:%i:%s:%Y:%Z' "$1" 2>/dev/null
}

_htf_identity() {
    # Cache unlink/chcon can change ctime without changing a mounted inode.
    stat -L -c '%d:%i:%s' "$1" 2>/dev/null
}

_htf_pids() {
    # Reuse one batched /proc scan and the provider's Chrome/Google/zygote set.
    # Never address PID 1 or system_server; inherited zygote views cover new apps.
    _htf_proc="${LUOSHU_PROC_ROOT:-/proc}"
    _gfp_namespace_pids | while IFS= read -r _htf_pid; do
        [ "$_htf_pid" != 1 ] || continue
        _htf_ns=$(readlink "$_htf_proc/$_htf_pid/ns/mnt" 2>/dev/null)
        [ -n "$_htf_ns" ] && printf '%s|%s\n' "$_htf_ns" "$_htf_pid"
    done | awk -F '|' '!seen[$1]++ {print $2}'
}

_htf_fingerprint() {
    _htf_active || { printf 'theme-font:inactive\n'; return 0; }
    _htf_donor=$(_htf_source) || { printf 'theme-font:source-pending\n'; return 0; }
    _htf_proc="${LUOSHU_PROC_ROOT:-/proc}"
    {
        printf 'theme-font:v1|%s|%s\n' "$_htf_donor" "$HTF_TARGET"
        _htf_stamp "$_htf_donor"
        _htf_stamp "$HTF_TARGET"
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
    _htf_key=$(printf 'theme-view-v1|%s|%s|%s' "$_htf_donor" "$_htf_source_stamp" "$_htf_target_stamp" | _gfp_hash_text)
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
    awk -F '|' -v ns="$1" -v inode="$2" '$1 == ns && $2 == inode {found=1} END {exit !found}' "$HTF_MOUNTS"
}

_htf_clear_owned_pid() {
    _htf_clear_pid="$1"
    _htf_clear_ns=$(readlink "${LUOSHU_PROC_ROOT:-/proc}/$_htf_clear_pid/ns/mnt" 2>/dev/null)
    _htf_clear_round=0
    # Multiple old layers are possible after an interrupted earlier attempt.
    # Never pop a foreign layer; retain the journal if a layer cannot be removed.
    while [ "$_htf_clear_round" -lt 64 ]; do
        _htf_clear_id=$(_htf_identity "${LUOSHU_PROC_ROOT:-/proc}/$_htf_clear_pid/root$HTF_TARGET")
        [ -n "$_htf_clear_id" ] || return 0
        _htf_owned_identity "$_htf_clear_ns" "$_htf_clear_id" || return 0
        _gfp_unmount_in_pid "$_htf_clear_pid" "$HTF_TARGET" || return 1
        _htf_clear_round=$((_htf_clear_round + 1))
    done
    return 1
}

_htf_mount_pid() {
    _htf_mount_pid_value="$1"
    _htf_mount_ns=$(readlink "${LUOSHU_PROC_ROOT:-/proc}/$_htf_mount_pid_value/ns/mnt" 2>/dev/null)
    _htf_mount_id=$(_htf_identity "${LUOSHU_PROC_ROOT:-/proc}/$_htf_mount_pid_value/root$HTF_TARGET")
    if [ -s "$HTF_MOUNTS" ] && grep -Fxq "$_htf_mount_ns|$_htf_mount_id|$HTF_CLONE" "$HTF_MOUNTS"; then
        return 0
    fi
    # Replacing the top layer rather than stacking makes restore reversible.
    _htf_clear_owned_pid "$_htf_mount_pid_value" || return 1
    _gfp_mount_in_pid "$_htf_mount_pid_value" "$HTF_CLONE" "$HTF_TARGET" 1
}

_htf_apply() {
    if ! _htf_active; then
        _htf_restore || return 1
        return 2
    fi
    _htf_prepare || return $?
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
            [ -z "$_htf_ns" ] || [ -z "$_htf_view" ] || printf '%s|%s|%s\n' "$_htf_ns" "$_htf_view" "$HTF_CLONE" >> "$_htf_journal"
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
    awk -F '|' 'NF == 3 && !seen[$1 FS $2]++' "$_htf_journal" > "${HTF_MOUNTS}.new.$$" && \
        mv -f "${HTF_MOUNTS}.new.$$" "$HTF_MOUNTS" || _htf_journal_rc=1
    rm -f "$_htf_journal" "${_htf_journal}.live" "${_htf_journal}.handled" "${HTF_MOUNTS}.new.$$"
    _gfp_log "HyperOS theme view：mounted=$_htf_ok failed=$_htf_failed; framework symlinks preserved"
    [ "$_htf_ok" -gt 0 ] && [ "$_htf_failed" -eq 0 ] && [ "$_htf_journal_rc" -eq 0 ]
}

_htf_restore() {
    [ -s "$HTF_MOUNTS" ] || { rm -f "$HTF_STATE"; return 0; }
    # Mount ownership is checked by inode before unmounting; never detach a
    # replacement installed by the ROM/theme manager or another module.
    _htf_proc="${LUOSHU_PROC_ROOT:-/proc}"
    _htf_restore_failed=0
    for _htf_pid in $(_htf_pids); do
        _htf_clear_owned_pid "$_htf_pid" || _htf_restore_failed=1
    done
    [ "$_htf_restore_failed" -eq 0 ] || return 1
    rm -f "$HTF_STATE" "$HTF_MOUNTS" 2>/dev/null || true
}

if [ "${0##*/}" = hyperos_theme_font_bridge.sh ]; then
    case "${1:-apply}" in
        fingerprint) _htf_fingerprint ;;
        apply) _htf_apply ;;
        restore) _htf_restore ;;
        *) exit 2 ;;
    esac
fi
