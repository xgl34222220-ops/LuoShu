#!/system/bin/sh
# LuoShu self-mount backend.
# Uses the same read-only lower-layer model as KernelSU's reference meta-overlayfs:
# module content first, captured stock tree last, and source name KSU for unified cleanup.
set +e

luoshu_self_mount_stage_for_manager() {
    case "${1:-unknown}" in
        APatch|KernelSU|KernelSU*|SukiSU|SukiSU*)
            printf 'post-mount\n'
            ;;
        *)
            # Magisk does not provide a module post-mount hook. Unknown legacy
            # managers retain the existing early path for compatibility.
            printf 'post-fs-data\n'
            ;;
    esac
}

# Only remove an empty mount point. An unsuccessful unmount must never turn
# stock-view cleanup into recursive deletion of the still-visible original tree.
_luoshu_prepare_lower_mountpoint() (
    point="$1"
    _luoshu_umount_cmd "$point" >/dev/null 2>&1 || true
    if [ -e "$point" ]; then rmdir "$point" 2>/dev/null || exit 1; fi
    mkdir -p "$point" 2>/dev/null
)

_luoshu_bind_private_lower() (
    source="$1";point="$2"
    # Register our empty prepared mount point before a cancellable mount call.
    if [ -n "${_lsme_mount_list:-}" ]; then
        printf '%s\n' "$point" >> "$_lsme_mount_list" || exit 1
    fi
    if ! _luoshu_mount_cmd -o bind "$source" "$point" >/dev/null 2>&1 ||
       ! _luoshu_mount_cmd -o private none "$point" >/dev/null 2>&1; then
        _luoshu_umount_cmd "$point" >/dev/null 2>&1 || true
        rmdir "$point" 2>/dev/null || true
        exit 1
    fi
)

_luoshu_memory_tree_inventory() (
    root="$1"; output="$2"
    find "$root" -print > "$output.paths" 2>/dev/null || exit 1
    : > "$output" || exit 1
    while IFS= read -r path; do
        [ "$path" != "$root" ] || continue
        [ ! -L "$path" ] || exit 1
        rel="${path#"$root"/}"
        if [ -f "$path" ]; then printf 'f|%s\n' "$rel"
        elif [ -d "$path" ]; then printf 'd|%s\n' "$rel"
        else exit 1
        fi
    done < "$output.paths" > "$output.unsorted" || exit 1
    sort "$output.unsorted" > "$output" || exit 1
)

# Some Android /data filesystems advertise casefold support; OverlayFS rejects
# every lower on that filesystem. For a sealed Universal transaction only, use
# an owned, bounded tmpfs copy. No source bytes or filesystem flags are changed.
_luoshu_overlay_memory_layer() (
    source="$1"; point="$2"; state="$3"
    [ "${LUOSHU_REQUIRED_PAYLOAD_FILES:-0}" = 1 ] || exit 1
    [ -n "${_lsme_mount_list:-}" ] || exit 1
    # Record the complete tree, including directories; no links/special files.
    inventory="$state/memory-inventory.$$"
    trap 'rm -f "$inventory" "$inventory.paths" "$inventory.unsorted" "$inventory.after" "$inventory.after.paths" "$inventory.after.unsorted" "$inventory.copy" "$inventory.copy.paths" "$inventory.copy.unsorted"' EXIT
    _luoshu_memory_tree_inventory "$source" "$inventory" || exit 1
    kb=$(du -sk "$source" 2>/dev/null | awk '{print $1}')
    case "$kb" in ''|*[!0-9]*) exit 1 ;; esac
    capacity=$((kb + kb / 8 + 1024))
    used=$(cat "$state/memory-layer-kb" 2>/dev/null || echo 0)
    case "$used" in ''|*[!0-9]*) exit 1 ;; esac
    total=$((used + capacity))
    available=$(awk '/^MemAvailable:/{print $2;exit}' /proc/meminfo)
    case "$available" in ''|*[!0-9]*) exit 1 ;; esac
    [ "$total" -le 262144 ] && [ "$total" -le $((available / 8)) ] || exit 1
    # Reject a nonempty/still-mounted prior view instead of removing its files.
    if [ -e "$point" ]; then rmdir "$point" 2>/dev/null || exit 1; fi
    mkdir -p "$point" || exit 1
    printf '%s\n' "$point" >> "$_lsme_mount_list" || exit 1
    printf '%s\n' "$total" > "$state/memory-layer-kb" || exit 1
    _luoshu_mount_cmd -t tmpfs -o "size=${capacity}k,mode=0755,nosuid,nodev,noexec" luoshu-layer "$point" >/dev/null 2>&1 || exit 1
    _luoshu_mount_cmd -o private none "$point" >/dev/null 2>&1 || exit 1
    cp -R "$source/." "$point/" 2>/dev/null || exit 1
    _luoshu_memory_tree_inventory "$source" "$inventory.after" || exit 1
    _luoshu_memory_tree_inventory "$point" "$inventory.copy" || exit 1
    cmp -s "$inventory" "$inventory.after" && cmp -s "$inventory" "$inventory.copy" || exit 1
    _luoshu_atomic_tree_visible "$source" "$point" overlay || exit 1
    _luoshu_mount_cmd -o remount,ro,nosuid,nodev,noexec luoshu-layer "$point" >/dev/null 2>&1 || exit 1
    awk -v p="$point" '$5==p && $6 ~ /(^|,)ro(,|$)/ {ok=1} END{exit !ok}' /proc/self/mountinfo
)

# Persist the exact attempted overlay before mount(2), so cancellation between
# kernel success and the ordinary journal append still has a recoverable owner.
_luoshu_overlay_try() (
    source="$1";lower="$2";target="$3";key="$4";state="$5"
    mkdir -p "$state/overlay-intents" || exit 1
    intent="$state/overlay-intents/$key"
    [ ! -e "$intent" ] || exit 1
    baseline=$(_luoshu_visible_mount_id "$target") || exit 1
    printf '%s|%s|%s|%s\n' "$source" "$lower" "$target" "$baseline" > "$intent.tmp.$$" || exit 1
    mv "$intent.tmp.$$" "$intent" || exit 1
    if _luoshu_mount_cmd -t overlay KSU -o "ro,lowerdir=$source:$lower" "$target" >/dev/null 2>&1; then
        owned=$(_luoshu_visible_mount_id "$target") || exit 1
        [ "$owned" != "$baseline" ] || exit 1
        printf '%s|%s|%s|%s|%s\n' "$source" "$lower" "$target" "$baseline" "$owned" > "$intent.tmp.$$" || exit 1
        mv "$intent.tmp.$$" "$intent" || exit 1
        printf '%s\n' "$target" >> "$_lsme_mount_list" || exit 1
        # Keep baseline/owner evidence for normal rollback too. The original
        # target may itself be a mounted ROM directory.
        exit 0
    fi
    current=$(_luoshu_visible_mount_id "$target")
    [ "$current" != "$baseline" ] || rm -f "$intent"
    exit 1
)

_luoshu_overlay_mount_dir() {
    _lsomb_source="$1"
    _lsomb_target="$2"
    _lsomb_key="$3"
    _lsomb_state=$(_luoshu_self_state_root)
    _lsomb_lower="$_lsomb_state/lower/$_lsomb_key"

    [ -d "$_lsomb_source" ] && [ -d "$_lsomb_target" ] || return 1
    _luoshu_prepare_lower_mountpoint "$_lsomb_lower" || return 1
    _luoshu_bind_private_lower "$_lsomb_target" "$_lsomb_lower" || return 1

    # No upperdir/workdir is needed: LuoShu only needs a merged read-only boot view.
    # Changes made by the App are intentionally picked up after the requested reboot.
    if _luoshu_overlay_try "$_lsomb_source" "$_lsomb_lower" "$_lsomb_target" "$_lsomb_key" "$_lsomb_state"; then
        return 0
    fi

    _lsomb_memory="$_lsomb_state/memory-layers/$_lsomb_key"
    if _luoshu_overlay_memory_layer "$_lsomb_source" "$_lsomb_memory" "$_lsomb_state" &&
       _luoshu_overlay_try "$_lsomb_memory" "$_lsomb_lower" "$_lsomb_target" "$_lsomb_key" "$_lsomb_state"; then
        return 0
    fi

    _luoshu_umount_cmd "$_lsomb_lower" >/dev/null 2>&1 || true
    rmdir "$_lsomb_lower" 2>/dev/null || true
    return 1
}

# OverlayFS is not available on every KernelSU/HyperOS combination. The atomic
# runtime then falls back to per-file bind mounts, but the stock directory must
# still remain reachable for later inventory scans and stock-metric alignment.
# Capture it before installing any file binds and detach its propagation so the
# later child mounts cannot leak back into this stock view.
_luoshu_capture_lower_dir() {
    _lscld_target="$1"
    _lscld_key="$2"
    _lscld_state=$(_luoshu_self_state_root)
    _lscld_lower="$_lscld_state/lower/$_lscld_key"

    [ -d "$_lscld_target" ] || return 1
    _luoshu_prepare_lower_mountpoint "$_lscld_lower" || return 1
    _luoshu_bind_private_lower "$_lscld_target" "$_lscld_lower"
}
