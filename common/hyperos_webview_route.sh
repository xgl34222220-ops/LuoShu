#!/system/bin/sh
# HyperOS default sans-serif route: /system/fonts/MiSansVF_Overlay.ttf is a ROM
# symlink to /data/system/fonts/theme_webview/Roboto-Regular.ttf. Early in boot
# that /data file is a plain copy of the ROM Roboto, so system_server (and
# therefore every app's shared system font map) reads Latin/digits from stock
# Roboto there and only falls back to the replaced MiSans for Han.
#
# When the theme engine has a font component applied, the framework instead
# leaves theme_webview as a symlink to /data/system/theme/fonts/Roboto-Regular.ttf
# (SymlinkUtils.doProcessSymlink, theme branch) and system_server maps that file.
# The chain is resolved (bounded) and only that exact final file is accepted,
# and only when it is still a Roboto-family Latin file (small, named Roboto);
# a theme-store font with another name or CJK-sized file is skipped and logged.
#
# The later boot-completed theme bridge cannot fix this: system_server has
# already loaded its font map. This helper runs before zygote, from the legacy
# HyperOS payload hook, and only when the route file is byte-identical to the
# visible ROM Roboto, or is the theme engine's Roboto described above (never a
# user-picked theme-store font). It binds a private copy of the
# active payload's processed Roboto-Regular.ttf over the route, read-only, for
# this boot only. Nothing on /data is rewritten; restore unmounts only the
# inode recorded in this boot's journal.
set +e

_lwr_module() {
    printf '%s\n' "${LUOSHU_REAL_MODDIR:-${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}}"
}

_lwr_init() {
    LWR_MODULE=$(_lwr_module)
    LWR_ALIAS="${LUOSHU_WEBVIEW_ROUTE_ALIAS:-/system/fonts/MiSansVF_Overlay.ttf}"
    LWR_ROUTER="${LUOSHU_WEBVIEW_ROUTE_ROUTER:-/data/system/fonts/theme_webview/Roboto-Regular.ttf}"
    LWR_STOCK="${LUOSHU_WEBVIEW_ROUTE_STOCK:-/system/fonts/Roboto-Regular.ttf}"
    LWR_THEME_TARGET="${LUOSHU_WEBVIEW_ROUTE_THEME_TARGET:-/data/system/theme/fonts/Roboto-Regular.ttf}"
    # Roboto variants are ~1-2 MiB; theme-store CJK fonts are far larger.
    LWR_THEME_MAX_BYTES="${LUOSHU_WEBVIEW_ROUTE_THEME_MAX_BYTES:-4194304}"
    LWR_MOUNTINFO="${LUOSHU_WEBVIEW_ROUTE_MOUNTINFO:-/proc/self/mountinfo}"
    LWR_BOOT_ID_FILE="${LUOSHU_WEBVIEW_ROUTE_BOOT_ID:-/proc/sys/kernel/random/boot_id}"
    LWR_PAYLOAD="${LUOSHU_WEBVIEW_ROUTE_PAYLOAD:-$LWR_MODULE/.luoshu-payload/system/fonts/Roboto-Regular.ttf}"
    LWR_CACHE="$LWR_MODULE/config/hyperos-webview-route"
    LWR_JOURNAL="$LWR_MODULE/config/hyperos-webview-route.conf"
    LWR_LOCK="$LWR_MODULE/config/.hyperos-webview-route.lock"
    LWR_LOG="$LWR_MODULE/logs/fontswitch.log"
    # The router reference is the exact ROM symlink text proven on K80/dali.
    LWR_EXPECTED_LINK=/data/system/fonts/theme_webview/Roboto-Regular.ttf
    [ -z "${LUOSHU_WEBVIEW_ROUTE_ROUTER:-}" ] || LWR_EXPECTED_LINK="$LWR_ROUTER"
}

_lwr_log() {
    mkdir -p "${LWR_LOG%/*}" 2>/dev/null || return 0
    printf '[%s] [WEBVIEW-ROUTE] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" "$*" \
        >> "$LWR_LOG" 2>/dev/null || true
}

_lwr_boot_id() {
    tr -d '\r\n' < "$LWR_BOOT_ID_FILE" 2>/dev/null
}

_lwr_identity() {
    stat -L -c '%d:%i' "$1" 2>/dev/null
}

_lwr_single_font() {
    [ -f "$1" ] && [ -s "$1" ] || return 1
    _lwr_magic=$(dd if="$1" bs=4 count=1 2>/dev/null | od -An -tx1 2>/dev/null | tr -d ' \n')
    case "$_lwr_magic" in 00010000|4f54544f|74727565) return 0 ;; esac
    return 1
}

_lwr_active_font() {
    _lwr_active=$(head -n1 "$LWR_MODULE/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_lwr_active" ] || _lwr_active=default
    printf '%s\n' "$_lwr_active"
}

_lwr_is_mountpoint() {
    # mountinfo field 5 is the mount point; fonts paths contain no escapes.
    awk -v target="$1" '$5 == target {found=1} END {exit !found}' "$LWR_MOUNTINFO" 2>/dev/null
}

# Follow router symlinks (bounded, relative-aware) to the file actually read.
_lwr_resolve_final() {
    _lwr_res=$1
    _lwr_res_depth=0
    while [ -L "$_lwr_res" ]; do
        [ "$_lwr_res_depth" -lt 4 ] || return 1
        _lwr_res_next=$(readlink "$_lwr_res" 2>/dev/null) || return 1
        [ -n "$_lwr_res_next" ] || return 1
        case "$_lwr_res_next" in
            /*) _lwr_res=$_lwr_res_next ;;
            *) _lwr_res="${_lwr_res%/*}/$_lwr_res_next" ;;
        esac
        _lwr_res_depth=$((_lwr_res_depth + 1))
    done
    printf '%s\n' "$_lwr_res"
}

# The theme engine's Roboto (byte copy of ROM Roboto, or a Roboto-named Latin
# file) may be covered while a LuoShu font is active; a user theme font not.
_lwr_theme_is_roboto() {
    cmp -s "$1" "$LWR_STOCK" 2>/dev/null && return 0
    _lwr_t_size=$(stat -L -c '%s' "$1" 2>/dev/null)
    [ -n "$_lwr_t_size" ] && [ "$_lwr_t_size" -le "$LWR_THEME_MAX_BYTES" ] || return 1
    tr -d '\000' < "$1" 2>/dev/null | tr -c 'A-Za-z' '\n' 2>/dev/null | grep -q 'Roboto'
}

_lwr_sha() {
    sha256sum "$1" 2>/dev/null | awk '{print $1}'
}

_lwr_lock() {
    mkdir -p "$LWR_MODULE/config" 2>/dev/null || return 1
    _lwr_lock_round=0
    while ! mkdir "$LWR_LOCK" 2>/dev/null; do
        _lwr_lock_owner=$(cat "$LWR_LOCK/pid" 2>/dev/null)
        if [ -n "$_lwr_lock_owner" ] && ! kill -0 "$_lwr_lock_owner" 2>/dev/null; then
            rm -rf "$LWR_LOCK" 2>/dev/null || true
            continue
        fi
        _lwr_lock_round=$((_lwr_lock_round + 1))
        [ "$_lwr_lock_round" -lt 50 ] || return 1
        sleep 0.1 2>/dev/null || sleep 1
    done
    printf '%s\n' "$$" > "$LWR_LOCK/pid" 2>/dev/null || true
    return 0
}

_lwr_unlock() {
    rm -rf "$LWR_LOCK" 2>/dev/null || true
}

# Journal: boot_id|bound-target|clone|clone-identity. bound-target is the final
# file of the router chain (the router itself, or the theme engine's Roboto).
_lwr_owned_now() {
    [ -s "$LWR_JOURNAL" ] || return 1
    IFS='|' read -r _lwr_j_boot _lwr_j_target _lwr_j_clone _lwr_j_id < "$LWR_JOURNAL" || return 1
    [ "$_lwr_j_boot" = "$(_lwr_boot_id)" ] || return 1
    case "$_lwr_j_target" in "$LWR_ROUTER"|"$LWR_THEME_TARGET") ;; *) return 1 ;; esac
    _lwr_j_final=$(_lwr_resolve_final "$LWR_ROUTER") || return 1
    [ "$_lwr_j_final" = "$_lwr_j_target" ] || \
        [ "$(_lwr_identity "$_lwr_j_final")" = "$(_lwr_identity "$_lwr_j_target")" ] || return 1
    case "$_lwr_j_clone" in "$LWR_CACHE/"*.ttf) ;; *) return 1 ;; esac
    [ -n "$_lwr_j_id" ] && [ "$(_lwr_identity "$_lwr_j_target")" = "$_lwr_j_id" ] || return 1
    _lwr_is_mountpoint "$_lwr_j_target"
}

_lwr_clear_stale() {
    # A journal from an earlier boot never refers to a live mount.
    [ -s "$LWR_JOURNAL" ] || return 0
    IFS='|' read -r _lwr_s_boot _lwr_s_rest < "$LWR_JOURNAL" || _lwr_s_boot=
    if [ "$_lwr_s_boot" != "$(_lwr_boot_id)" ]; then
        rm -f "$LWR_JOURNAL" 2>/dev/null || true
        rm -rf "$LWR_CACHE" 2>/dev/null || true
    fi
}

_lwr_ensure_internal() {
    _lwr_clear_stale
    if [ "$(_lwr_active_font)" = default ] || [ -f "$LWR_MODULE/disable" ] || [ -f "$LWR_MODULE/remove" ]; then
        _lwr_restore_internal
        return 2
    fi
    if _lwr_owned_now; then
        _lwr_log "already bound target=$_lwr_j_target"
        return 0
    fi
    # Only the proven ROM route; any other link text is left to the framework.
    [ -L "$LWR_ALIAS" ] || return 2
    [ "$(readlink "$LWR_ALIAS" 2>/dev/null)" = "$LWR_EXPECTED_LINK" ] || return 2
    _lwr_target=$(_lwr_resolve_final "$LWR_ROUTER") || {
        _lwr_log 'skip router-chain-too-deep-or-broken'
        return 2
    }
    # A relative ROM link may spell the theme path differently; match by inode.
    if [ "$_lwr_target" != "$LWR_ROUTER" ] && [ "$_lwr_target" != "$LWR_THEME_TARGET" ] && \
       [ ! -L "$LWR_THEME_TARGET" ] && [ -n "$(_lwr_identity "$LWR_THEME_TARGET")" ] && \
       [ "$(_lwr_identity "$_lwr_target")" = "$(_lwr_identity "$LWR_THEME_TARGET")" ]; then
        _lwr_target=$LWR_THEME_TARGET
    fi
    _lwr_single_font "$LWR_STOCK" || return 2
    case "$_lwr_target" in
        "$LWR_ROUTER")
            _lwr_single_font "$LWR_ROUTER" || { _lwr_log 'skip router-missing-or-not-font'; return 2; }
            # The plain router must be a byte copy of ROM Roboto.
            if ! cmp -s "$LWR_ROUTER" "$LWR_STOCK" 2>/dev/null; then
                _lwr_log 'skip router-not-stock-copy (theme or other font kept)'
                return 2
            fi
            ;;
        "$LWR_THEME_TARGET")
            [ ! -L "$_lwr_target" ] || return 2
            _lwr_single_font "$_lwr_target" || { _lwr_log "skip theme-target-missing-or-not-font target=$_lwr_target"; return 2; }
            if ! _lwr_theme_is_roboto "$_lwr_target"; then
                _lwr_log "skip theme-font-is-user-theme (not Roboto) target=$_lwr_target size=$(stat -L -c '%s' "$_lwr_target" 2>/dev/null) sha256=$(_lwr_sha "$_lwr_target")"
                return 2
            fi
            ;;
        *)
            _lwr_log "skip router-target-not-accepted target=$_lwr_target"
            return 2
            ;;
    esac
    if _lwr_is_mountpoint "$_lwr_target"; then
        _lwr_log "skip target-already-mounted-by-other target=$_lwr_target"
        return 2
    fi
    _lwr_single_font "$LWR_PAYLOAD" || { _lwr_log 'skip payload-roboto-missing'; return 2; }
    if cmp -s "$LWR_PAYLOAD" "$_lwr_target" 2>/dev/null; then
        return 2
    fi
    [ "$_lwr_target" = "$LWR_ROUTER" ] || \
        _lwr_log "theme engine Roboto accepted target=$_lwr_target sha256=$(_lwr_sha "$_lwr_target")"
    mkdir -p "$LWR_CACHE" 2>/dev/null || return 1
    _lwr_clone="$LWR_CACHE/route.ttf"
    _lwr_tmp="$LWR_CACHE/.route.$$.tmp"
    rm -f "$_lwr_tmp" 2>/dev/null || true
    cp -f "$LWR_PAYLOAD" "$_lwr_tmp" 2>/dev/null || { rm -f "$_lwr_tmp"; return 1; }
    cmp -s "$LWR_PAYLOAD" "$_lwr_tmp" 2>/dev/null || { rm -f "$_lwr_tmp"; return 1; }
    chmod 0644 "$_lwr_tmp" 2>/dev/null || true
    if command -v chcon >/dev/null 2>&1; then
        chcon --reference="$_lwr_target" "$_lwr_tmp" 2>/dev/null || true
    fi
    mv -f "$_lwr_tmp" "$_lwr_clone" || { rm -f "$_lwr_tmp"; return 1; }
    _lwr_clone_id=$(_lwr_identity "$_lwr_clone")
    [ -n "$_lwr_clone_id" ] || return 1
    # Journal before mounting so an interrupted run can still be undone.
    printf '%s|%s|%s|%s\n' "$(_lwr_boot_id)" "$_lwr_target" "$_lwr_clone" "$_lwr_clone_id" \
        > "$LWR_JOURNAL.tmp.$$" && mv -f "$LWR_JOURNAL.tmp.$$" "$LWR_JOURNAL" || return 1
    chmod 0600 "$LWR_JOURNAL" 2>/dev/null || true
    if ! mount --bind "$_lwr_clone" "$_lwr_target" 2>/dev/null && \
       ! mount -o bind "$_lwr_clone" "$_lwr_target" 2>/dev/null; then
        rm -f "$LWR_JOURNAL" 2>/dev/null || true
        _lwr_log 'bind failed; route left unchanged'
        return 1
    fi
    # Read-only so a later init/theme copy cannot write into LuoShu's clone.
    mount -o remount,bind,ro "$_lwr_target" 2>/dev/null || \
        mount -o bind,remount,ro "$_lwr_target" 2>/dev/null || true
    if [ "$(_lwr_identity "$_lwr_target")" != "$_lwr_clone_id" ]; then
        _lwr_log 'bind verify failed'
        return 1
    fi
    _lwr_log "bound payload Roboto over route target=$_lwr_target router=$LWR_ROUTER"
    return 0
}

_lwr_restore_internal() {
    [ -s "$LWR_JOURNAL" ] || { rm -rf "$LWR_CACHE" 2>/dev/null || true; return 0; }
    IFS='|' read -r _lwr_r_boot _lwr_r_router _lwr_r_clone _lwr_r_id < "$LWR_JOURNAL"
    # Only the two accepted route files are ever unmounted from a journal.
    case "$_lwr_r_router" in "$LWR_ROUTER"|"$LWR_THEME_TARGET") ;; *) _lwr_r_router= ;; esac
    if [ "$_lwr_r_boot" = "$(_lwr_boot_id)" ] && [ -n "$_lwr_r_router" ] && [ -n "$_lwr_r_id" ]; then
        _lwr_r_round=0
        # Pop only layers whose visible inode is LuoShu's recorded clone.
        while [ "$_lwr_r_round" -lt 8 ] && \
              [ "$(_lwr_identity "$_lwr_r_router")" = "$_lwr_r_id" ] && \
              _lwr_is_mountpoint "$_lwr_r_router"; do
            umount "$_lwr_r_router" 2>/dev/null || { _lwr_log 'restore unmount failed; journal kept'; return 1; }
            _lwr_r_round=$((_lwr_r_round + 1))
        done
        [ "$(_lwr_identity "$_lwr_r_router")" != "$_lwr_r_id" ] || { _lwr_log 'restore incomplete; journal kept'; return 1; }
        # A foreign layer on top may still hide ours; never pop it, keep the journal.
        if [ "$_lwr_r_round" -eq 0 ] && _lwr_is_mountpoint "$_lwr_r_router"; then
            _lwr_log 'restore deferred: foreign layer above route; journal kept'
            return 1
        fi
        [ "$_lwr_r_round" -eq 0 ] || _lwr_log "restored stock route router=$_lwr_r_router"
    fi
    rm -f "$LWR_JOURNAL" 2>/dev/null || true
    rm -rf "$LWR_CACHE" 2>/dev/null || true
    return 0
}

luoshu_hyperos_webview_route_ensure() {
    _lwr_init
    _lwr_lock || return 1
    _lwr_ensure_internal
    _lwr_rc=$?
    _lwr_unlock
    return "$_lwr_rc"
}

luoshu_hyperos_webview_route_restore() {
    _lwr_init
    _lwr_lock || return 1
    _lwr_restore_internal
    _lwr_rc=$?
    _lwr_unlock
    return "$_lwr_rc"
}

# True when this boot's early bind currently owns the router file.
luoshu_hyperos_webview_route_owned() {
    _lwr_init
    _lwr_owned_now
}

if [ "${0##*/}" = hyperos_webview_route.sh ]; then
    case "${1:-ensure}" in
        ensure) luoshu_hyperos_webview_route_ensure ;;
        restore) luoshu_hyperos_webview_route_restore ;;
        owned) luoshu_hyperos_webview_route_owned ;;
        *) exit 2 ;;
    esac
fi
