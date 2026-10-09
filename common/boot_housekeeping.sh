#!/system/bin/sh
# LuoShu post-boot cost control and on-disk housekeeping.
#
# Only used after the font mount has already been confirmed. Nothing here reads,
# writes or decides anything about the mounted payload: it lowers the priority of
# the remaining maintenance, lets the device settle after sys.boot_completed,
# computes cheap "inputs unchanged" keys, and keeps LuoShu's own files under
# /data/adb bounded (log size/count caps and stale pid-suffixed temp files).
#
# Sourced by service.sh; can also be run directly: boot_housekeeping.sh housekeep

# Lower the scheduling and I/O priority of the calling process tree. Children
# inherit both. Every tool is optional; failure is harmless.
luoshu_boot_lower_priority() {
    _lbp_pid="${1:-}"
    if [ -z "$_lbp_pid" ]; then
        # $$ is the parent shell inside a ( ... ) subshell; ask a child for its PPID.
        _lbp_pid=$(sh -c 'echo "$PPID"' 2>/dev/null)
    fi
    case "$_lbp_pid" in ''|*[!0-9]*) return 0 ;; esac
    renice -n 10 -p "$_lbp_pid" >/dev/null 2>&1 || \
        busybox renice -n 10 -p "$_lbp_pid" >/dev/null 2>&1 || true
    ionice -c 3 -p "$_lbp_pid" >/dev/null 2>&1 || \
        ionice -c 2 -n 7 -p "$_lbp_pid" >/dev/null 2>&1 || \
        busybox ionice -c 3 -p "$_lbp_pid" >/dev/null 2>&1 || true
    return 0
}

# Sleep once after sys.boot_completed so deferred maintenance does not compete
# with launcher/SystemUI/app start-up. Bounded 0..120 s, default 25 s.
luoshu_boot_settle() {
    _lbs_delay="${LUOSHU_BOOT_SETTLE_SECONDS:-25}"
    case "$_lbs_delay" in ''|*[!0-9]*) _lbs_delay=25 ;; esac
    [ "$_lbs_delay" -le 120 ] 2>/dev/null || _lbs_delay=120
    [ "$_lbs_delay" -gt 0 ] 2>/dev/null || return 0
    sleep "$_lbs_delay"
}

# Print a short digest of stdin. Empty output means "no key" (caller must not skip).
luoshu_boot_digest() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum 2>/dev/null | awk '{print $1}'
    elif command -v busybox >/dev/null 2>&1; then
        busybox sha256sum 2>/dev/null | awk '{print $1}'
    else
        cksum 2>/dev/null | awk '{print $1 "-" $2}'
    fi
}

# Key for the native font-list prewarm. It covers everything the cached
# native_font_index.json depends on: module version, active selection and the
# name/size/mtime of every file in the public font folder. If the folder cannot
# be listed (e.g. user storage still locked) no key is produced, so the caller
# falls back to the original unconditional prewarm.
luoshu_native_index_boot_key() {
    _lnk_moddir="$1"
    _lnk_active="$2"
    _lnk_fonts="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts"
    [ -d "$_lnk_fonts" ] || return 1
    _lnk_listing=$(ls -lnA --full-time "$_lnk_fonts" 2>/dev/null) || return 1
    _lnk_version=$(sed -n 's/^versionCode=//p' "$_lnk_moddir/module.prop" 2>/dev/null | head -n1)
    _lnk_key=$({
        printf 'native-index-boot-v1\n'
        printf 'version=%s\n' "$_lnk_version"
        printf 'active=%s\n' "$_lnk_active"
        printf '%s\n' "$_lnk_listing"
    } | luoshu_boot_digest)
    [ -n "$_lnk_key" ] || return 1
    printf '%s\n' "$_lnk_key"
}

# True when the prewarm can be skipped: same key as the last successful run and
# a valid index is still on disk.
luoshu_native_index_boot_fresh() {
    _lnf_moddir="$1"
    _lnf_key="$2"
    [ -n "$_lnf_key" ] || return 1
    [ -s "$_lnf_moddir/config/native_font_index.json" ] || return 1
    grep -q '"status":"ok"' "$_lnf_moddir/config/native_font_index.json" 2>/dev/null || return 1
    [ "$(cat "$_lnf_moddir/config/native_font_index.boot-key" 2>/dev/null)" = "$_lnf_key" ]
}

luoshu_native_index_boot_record() {
    _lnr_moddir="$1"
    _lnr_key="$2"
    [ -n "$_lnr_key" ] || return 0
    printf '%s\n' "$_lnr_key" > "$_lnr_moddir/config/native_font_index.boot-key.tmp.$$" 2>/dev/null && \
        mv -f "$_lnr_moddir/config/native_font_index.boot-key.tmp.$$" \
            "$_lnr_moddir/config/native_font_index.boot-key" 2>/dev/null || \
        rm -f "$_lnr_moddir/config/native_font_index.boot-key.tmp.$$" 2>/dev/null
    return 0
}

# Keep one log file bounded: above the byte cap keep only the newest lines.
luoshu_log_cap_file() {
    _lcf_file="$1"
    _lcf_max="${2:-524288}"
    _lcf_keep="${3:-1500}"
    [ -f "$_lcf_file" ] && [ ! -L "$_lcf_file" ] || return 0
    _lcf_size=$(wc -c < "$_lcf_file" 2>/dev/null | tr -d '[:space:]')
    case "$_lcf_size" in ''|*[!0-9]*) return 0 ;; esac
    [ "$_lcf_size" -gt "$_lcf_max" ] || return 0
    tail -n "$_lcf_keep" "$_lcf_file" > "$_lcf_file.trim.$$" 2>/dev/null && \
        mv -f "$_lcf_file.trim.$$" "$_lcf_file" 2>/dev/null || rm -f "$_lcf_file.trim.$$" 2>/dev/null
    return 0
}

# Remove regular files older than N minutes matching a glob inside one directory
# (non-recursive, never follows symlinks).
luoshu_prune_stale() {
    _lps_dir="$1"
    _lps_name="$2"
    _lps_minutes="${3:-1440}"
    [ -d "$_lps_dir" ] && [ ! -L "$_lps_dir" ] || return 0
    find "$_lps_dir" -maxdepth 1 -type f -name "$_lps_name" -mmin +"$_lps_minutes" \
        -exec rm -f {} + 2>/dev/null || true
}

# Cap the number of files in a log directory; oldest rotated/extra files go first.
luoshu_log_cap_count() {
    _lcc_dir="$1"
    _lcc_max="${2:-40}"
    [ -d "$_lcc_dir" ] && [ ! -L "$_lcc_dir" ] || return 0
    _lcc_count=$(find "$_lcc_dir" -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d '[:space:]')
    case "$_lcc_count" in ''|*[!0-9]*) return 0 ;; esac
    [ "$_lcc_count" -gt "$_lcc_max" ] || return 0
    _lcc_excess=$((_lcc_count - _lcc_max))
    # Oldest first by mtime. ls -t lists newest first; take the tail.
    ls -1t "$_lcc_dir" 2>/dev/null | tail -n "$_lcc_excess" | while IFS= read -r _lcc_name; do
        [ -n "$_lcc_name" ] || continue
        [ -f "$_lcc_dir/$_lcc_name" ] && [ ! -L "$_lcc_dir/$_lcc_name" ] || continue
        rm -f "$_lcc_dir/$_lcc_name" 2>/dev/null || true
    done
}

# Bound everything LuoShu itself appends to under /data/adb. Never touches the
# active payload, mount state, inventories or any lock/stage directory.
luoshu_boot_real_dir() {
    # config/ and logs/ are compatibility links into .luoshu-state after the
    # runtime-paths migration; operate on the real directory, never a link.
    if [ -d "$1/.luoshu-state/$2" ] && [ ! -L "$1/.luoshu-state/$2" ]; then
        printf '%s\n' "$1/.luoshu-state/$2"
    elif [ -d "$1/$2" ] && [ ! -L "$1/$2" ]; then
        printf '%s\n' "$1/$2"
    fi
}

luoshu_boot_housekeep() {
    _lbh_moddir="$1"
    [ -d "$_lbh_moddir" ] || return 0
    _lbh_logdir=$(luoshu_boot_real_dir "$_lbh_moddir" logs)
    if [ -n "$_lbh_logdir" ]; then
        for _lbh_log in "$_lbh_logdir"/*; do
            [ -f "$_lbh_log" ] || continue
            luoshu_log_cap_file "$_lbh_log" 524288 1500
        done
        luoshu_prune_stale "$_lbh_logdir" '*.trim.*' 1440
        luoshu_log_cap_count "$_lbh_logdir" 40
    fi
    # pid-suffixed scratch files from interrupted writers (".tmp.<pid>",
    # fingerprint/manifest scratch). Only files older than a day are removed.
    _lbh_config=$(luoshu_boot_real_dir "$_lbh_moddir" config)
    if [ -n "$_lbh_config" ]; then
        luoshu_prune_stale "$_lbh_config" '*.tmp.*' 1440
        luoshu_prune_stale "$_lbh_config" '.font-fingerprint.*' 1440
        luoshu_prune_stale "$_lbh_config" '.native-font-manifest.*' 1440
        luoshu_prune_stale "$_lbh_config" '.native-font-families.*' 1440
    fi
    luoshu_prune_stale "$_lbh_moddir" 'module.prop.tmp.*' 1440
    return 0
}

if [ "${0##*/}" = "boot_housekeeping.sh" ]; then
    MODDIR="${MODDIR:-$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)}"
    case "${1:-housekeep}" in
        housekeep) luoshu_boot_housekeep "$MODDIR" ;;
        *) echo "Usage: $0 housekeep" >&2; exit 2 ;;
    esac
fi
