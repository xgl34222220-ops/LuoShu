#!/system/bin/sh
# Optional HyperOS theme-store font takeover (default OFF).
#
# When a theme-store font is applied, HyperOS's ThemeFontManager and the
# MiSansVF_Overlay -> theme_webview route read /data/system/theme/fonts/*, and
# LuoShu's early route bind deliberately skips a user theme font. Users then see
# "LuoShu only changed some places". Detection is always available (the App
# shows a strong hint); the takeover itself only runs when
# config/hyperos_theme_takeover.conf contains an exact "enabled=1" line.
#
# Takeover: before zygote, every regular single-font file in the theme fonts
# directory (not only Roboto-Regular.ttf) is covered with a private, read-only
# bind of the active LuoShu payload font of the nearest weight. Nothing on /data
# is rewritten. Exactly like hyperos_webview_route.sh, every bind is journalled
# with this boot's id and the clone inode, and restore pops only layers whose
# visible inode is LuoShu's recorded clone. A journal from an earlier boot never
# refers to a live mount and is discarded.
set +e

_lht_module() {
    printf '%s\n' "${LUOSHU_REAL_MODDIR:-${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}}"
}

_lht_init() {
    LHT_MODULE=$(_lht_module)
    LHT_DIR="${LUOSHU_THEME_TAKEOVER_DIR:-/data/system/theme/fonts}"
    LHT_CONF="${LUOSHU_THEME_TAKEOVER_CONF:-$LHT_MODULE/config/hyperos_theme_takeover.conf}"
    LHT_CACHE="$LHT_MODULE/config/hyperos-theme-takeover"
    LHT_JOURNAL="$LHT_MODULE/config/hyperos-theme-takeover.journal"
    LHT_LOCK="$LHT_MODULE/config/.hyperos-theme-takeover.lock"
    LHT_LOG="$LHT_MODULE/logs/fontswitch.log"
    LHT_MOUNTINFO="${LUOSHU_THEME_TAKEOVER_MOUNTINFO:-/proc/self/mountinfo}"
    LHT_BOOT_ID_FILE="${LUOSHU_THEME_TAKEOVER_BOOT_ID:-/proc/sys/kernel/random/boot_id}"
    LHT_FONTS="${LUOSHU_THEME_TAKEOVER_PAYLOAD_FONTS:-$LHT_MODULE/.luoshu-payload/system/fonts}"
    # Same threshold as hyperos_webview_route.sh: the ROM "default theme" leaves
    # an ~8.9 KiB near-glyphless sfnt; real theme fonts are far larger.
    LHT_PLACEHOLDER_MAX_BYTES="${LUOSHU_THEME_TAKEOVER_PLACEHOLDER_MAX_BYTES:-65536}"
    LHT_MAX_FILES=32
    LHT_STOCK_DIR="${LUOSHU_THEME_TAKEOVER_STOCK_DIR:-/system/fonts}"
    LHT_ROBOTO_MAX_BYTES="${LUOSHU_THEME_TAKEOVER_ROBOTO_MAX_BYTES:-4194304}"
}

_lht_log() {
    mkdir -p "${LHT_LOG%/*}" 2>/dev/null || return 0
    printf '[%s] [THEME-TAKEOVER] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" "$*" \
        >> "$LHT_LOG" 2>/dev/null || true
}

_lht_boot_id() { tr -d '\r\n' < "$LHT_BOOT_ID_FILE" 2>/dev/null; }
_lht_identity() { stat -L -c '%d:%i' "$1" 2>/dev/null; }
_lht_size() { stat -L -c '%s' "$1" 2>/dev/null; }

_lht_magic() {
    dd if="$1" bs=4 count=1 2>/dev/null | od -An -tx1 2>/dev/null | tr -d ' \n'
}

_lht_single_font() {
    [ -f "$1" ] && [ -s "$1" ] || return 1
    case "$(_lht_magic "$1")" in 00010000|4f54544f|74727565) return 0 ;; esac
    return 1
}

_lht_is_mountpoint() {
    awk -v target="$1" '$5 == target {found=1} END {exit !found}' "$LHT_MOUNTINFO" 2>/dev/null
}

lht_enabled() {
    grep -qx 'enabled=1' "$LHT_CONF" 2>/dev/null
}

_lht_active_font() {
    _lht_active=$(head -n1 "$LHT_MODULE/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    printf '%s\n' "${_lht_active:-default}"
}

# Regular, non-symlink font files directly in the theme fonts directory.
_lht_theme_files() {
    [ -d "$LHT_DIR" ] || return 0
    _lht_n=0
    for _lht_f in "$LHT_DIR"/*; do
        [ -f "$_lht_f" ] && [ ! -L "$_lht_f" ] || continue
        case "${_lht_f##*/}" in *.ttf|*.otf|*.TTF|*.OTF|*.ttc|*.TTC) ;; *) continue ;; esac
        _lht_n=$((_lht_n + 1))
        [ "$_lht_n" -le "$LHT_MAX_FILES" ] || break
        printf '%s\n' "$_lht_f"
    done
}

# dev:ino of LuoShu's own files on theme paths (webview-route clone, provider
# theme views): seeing one through the theme dir is not a theme-store font.
_lht_luoshu_ids() {
    _lht_boot=$(_lht_boot_id)
    if [ -s "$LHT_MODULE/config/hyperos-webview-route.conf" ]; then
        awk -F'|' -v b="$_lht_boot" '$1 == b && $4 != "" {print $4}' \
            "$LHT_MODULE/config/hyperos-webview-route.conf" 2>/dev/null
    fi
    if [ -s "$LHT_MODULE/config/hyperos-theme-font-namespaces.conf" ]; then
        awk -F'|' '$2 != "" {n=split($2, p, ":"); if (n >= 2) print p[1] ":" p[2]}' \
            "$LHT_MODULE/config/hyperos-theme-font-namespaces.conf" 2>/dev/null
    fi
    for _lht_c in "$LHT_MODULE/config/hyperos-webview-route"/*.ttf \
                  "$LHT_MODULE/config/hyperos-theme-font"/*.ttf; do
        [ -f "$_lht_c" ] && _lht_identity "$_lht_c"
    done
}

_lht_same_as_any() {
    _lht_sa_file="$1"; shift
    _lht_sa_size=$(_lht_size "$_lht_sa_file")
    for _lht_sa_c in "$@"; do
        [ -f "$_lht_sa_c" ] || continue
        [ "$(_lht_size "$_lht_sa_c")" = "$_lht_sa_size" ] || continue
        cmp -s "$_lht_sa_file" "$_lht_sa_c" 2>/dev/null && return 0
    done
    return 1
}

# user | placeholder | luoshu | stock; only "user" is a theme-store font. A
# file the takeover owns stays "user" (it binds only over theme-store fonts).
_lht_classify() {
    _lht_cf="$1"
    if _lht_journal_has "$_lht_cf" && lht_owned "$_lht_cf"; then
        printf 'user\n'; return 0
    fi
    _lht_cf_id=$(_lht_identity "$_lht_cf")
    if [ -n "$_lht_cf_id" ] && printf '%s\n' "$LHT_LUOSHU_IDS" | grep -qxF "$_lht_cf_id"; then
        printf 'luoshu\n'; return 0
    fi
    _lht_cf_sz=$(_lht_size "$_lht_cf"); case "$_lht_cf_sz" in ''|*[!0-9]*) _lht_cf_sz=0 ;; esac
    if [ "$_lht_cf_sz" -le "$LHT_PLACEHOLDER_MAX_BYTES" ]; then
        printf 'placeholder\n'; return 0
    fi
    if _lht_same_as_any "$_lht_cf" "$LHT_STOCK_DIR/Roboto-Regular.ttf" "$LHT_STOCK_DIR/${_lht_cf##*/}" \
        "$LHT_STOCK_DIR/MiSansVF.ttf"; then
        printf 'stock\n'; return 0
    fi
    # shellcheck disable=SC2046
    if _lht_same_as_any "$_lht_cf" $(for _lht_p in "$LHT_FONTS"/.luoshu-font-store/*.font "$LHT_FONTS"/*.ttf \
        "$LHT_MODULE/config/hyperos-theme-takeover"/*; do [ -f "$_lht_p" ] && printf '%s\n' "$_lht_p"; done); then
        printf 'luoshu\n'; return 0
    fi
    # Theme engine's own Roboto (as hyperos_webview_route.sh accepts it).
    if [ "$_lht_cf_sz" -le "$LHT_ROBOTO_MAX_BYTES" ] && \
       tr -d '\000' < "$_lht_cf" 2>/dev/null | tr -c 'A-Za-z' '\n' 2>/dev/null | grep -qx 'Roboto[A-Za-z]*'; then
        printf 'stock\n'; return 0
    fi
    printf 'user\n'
}

# state: none | placeholder | user-theme. Prints key=value lines.
lht_detect() {
    _lht_files=0; _lht_user=0; _lht_bytes=0; _lht_names=''; _lht_user_names=''; _lht_own=0
    LHT_LUOSHU_IDS=$(_lht_luoshu_ids)
    while IFS= read -r _lht_f; do
        [ -n "$_lht_f" ] || continue
        _lht_files=$((_lht_files + 1))
        _lht_sz=$(_lht_size "$_lht_f"); case "$_lht_sz" in ''|*[!0-9]*) _lht_sz=0 ;; esac
        _lht_bytes=$((_lht_bytes + _lht_sz))
        case "$(_lht_classify "$_lht_f")" in
            user)
                _lht_user=$((_lht_user + 1))
                _lht_user_names="${_lht_user_names:+$_lht_user_names;}${_lht_f##*/}"
                ;;
            luoshu) _lht_own=$((_lht_own + 1)) ;;
        esac
        _lht_names="${_lht_names:+$_lht_names;}${_lht_f##*/}"
    done <<EOF_LHT_FILES
$(_lht_theme_files)
EOF_LHT_FILES
    if [ "$_lht_user" -gt 0 ]; then _lht_state=user-theme; _lht_names=$_lht_user_names
    elif [ "$_lht_files" -gt 0 ]; then _lht_state=placeholder
    else _lht_state=none
    fi
    printf 'state=%s\nfiles=%s\nuserFiles=%s\nluoshuFiles=%s\nbytes=%s\nnames=%s\n' \
        "$_lht_state" "$_lht_files" "$_lht_user" "$_lht_own" "$_lht_bytes" "$_lht_names"
}

_lht_weight_for() {
    _lht_l=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
    case "$_lht_l" in
        *extrabold*|*extra-bold*) printf '800\n' ;; *semibold*|*semi-bold*|*demibold*) printf '600\n' ;;
        *extralight*|*extra-light*|*ultralight*) printf '200\n' ;; *medium*) printf '500\n' ;;
        *black*|*heavy*) printf '900\n' ;; *bold*) printf '700\n' ;; *light*) printf '300\n' ;;
        *thin*) printf '100\n' ;; *) printf '400\n' ;;
    esac
}

# The active payload's font for one weight; only the boot-activated payload.
_lht_source_for() {
    _lht_w=$(_lht_weight_for "$1")
    for _lht_c in \
        "$LHT_FONTS/.luoshu-font-store/wght-$_lht_w.font" \
        "$LHT_FONTS/LuoShu-$_lht_w.ttf" \
        "$LHT_FONTS/$_lht_w.ttf" \
        "$LHT_FONTS/.luoshu-font-store/mix-composite.font" \
        "$LHT_FONTS/.luoshu-font-store/regular.font" \
        "$LHT_FONTS/.luoshu-font-store/compact-regular.font" \
        "$LHT_FONTS/Roboto-Regular.ttf" \
        "$LHT_FONTS/MiSansVF.ttf" \
        "$LHT_FONTS/400.ttf"; do
        _lht_single_font "$_lht_c" && { printf '%s\n' "$_lht_c"; return 0; }
    done
    return 1
}

_lht_lock() {
    mkdir -p "$LHT_MODULE/config" 2>/dev/null || return 1
    _lht_round=0
    while ! mkdir "$LHT_LOCK" 2>/dev/null; do
        _lht_owner=$(cat "$LHT_LOCK/pid" 2>/dev/null)
        if [ -n "$_lht_owner" ] && ! kill -0 "$_lht_owner" 2>/dev/null; then
            rm -rf "$LHT_LOCK" 2>/dev/null || true
            continue
        fi
        _lht_round=$((_lht_round + 1))
        [ "$_lht_round" -lt 50 ] || return 1
        sleep 0.1 2>/dev/null || sleep 1
    done
    printf '%s\n' "$$" > "$LHT_LOCK/pid" 2>/dev/null || true
}

_lht_unlock() { rm -rf "$LHT_LOCK" 2>/dev/null || true; }

_lht_clear_stale() {
    [ -s "$LHT_JOURNAL" ] || return 0
    IFS='|' read -r _lht_s_boot _lht_s_rest < "$LHT_JOURNAL" || _lht_s_boot=
    if [ "$_lht_s_boot" != "$(_lht_boot_id)" ]; then
        rm -f "$LHT_JOURNAL" 2>/dev/null || true
        rm -rf "$LHT_CACHE" 2>/dev/null || true
    fi
}

# Journal line: boot_id|target|clone|clone-identity
_lht_journal_has() {
    [ -s "$LHT_JOURNAL" ] || return 1
    awk -F'|' -v t="$1" '$2 == t {found=1} END {exit !found}' "$LHT_JOURNAL" 2>/dev/null
}

lht_owned() {
    _lht_target="$1"
    [ -s "$LHT_JOURNAL" ] || return 1
    _lht_boot=$(_lht_boot_id)
    while IFS='|' read -r _lht_j_boot _lht_j_target _lht_j_clone _lht_j_id; do
        [ "$_lht_j_boot" = "$_lht_boot" ] || continue
        [ -z "$_lht_target" ] || [ "$_lht_j_target" = "$_lht_target" ] || continue
        [ "$(_lht_identity "$_lht_j_target")" = "$_lht_j_id" ] || continue
        _lht_is_mountpoint "$_lht_j_target" && return 0
    done < "$LHT_JOURNAL"
    return 1
}

_lht_bind_one() {
    _lht_target="$1"
    _lht_name=${_lht_target##*/}
    case "$_lht_name" in */*|''|.*) return 1 ;; esac
    if ! _lht_single_font "$_lht_target"; then
        _lht_log "skip not-single-font target=$_lht_target (collections keep the theme font)"
        return 2
    fi
    if _lht_journal_has "$_lht_target" && lht_owned "$_lht_target"; then
        return 0
    fi
    if _lht_is_mountpoint "$_lht_target"; then
        _lht_log "skip target-already-mounted-by-other target=$_lht_target"
        return 2
    fi
    _lht_src=$(_lht_source_for "$_lht_name") || { _lht_log 'skip payload-font-missing'; return 2; }
    mkdir -p "$LHT_CACHE" 2>/dev/null || return 1
    _lht_clone="$LHT_CACHE/$_lht_name"
    _lht_tmp="$LHT_CACHE/.$_lht_name.$$.tmp"
    rm -f "$_lht_tmp" 2>/dev/null || true
    cp -f "$_lht_src" "$_lht_tmp" 2>/dev/null && cmp -s "$_lht_src" "$_lht_tmp" 2>/dev/null || {
        rm -f "$_lht_tmp"; return 1; }
    chmod 0644 "$_lht_tmp" 2>/dev/null || true
    command -v chcon >/dev/null 2>&1 && chcon --reference="$_lht_target" "$_lht_tmp" 2>/dev/null
    mv -f "$_lht_tmp" "$_lht_clone" || { rm -f "$_lht_tmp"; return 1; }
    _lht_clone_id=$(_lht_identity "$_lht_clone")
    [ -n "$_lht_clone_id" ] || return 1
    # Journal before mounting so an interrupted run can still be undone.
    printf '%s|%s|%s|%s\n' "$(_lht_boot_id)" "$_lht_target" "$_lht_clone" "$_lht_clone_id" \
        >> "$LHT_JOURNAL" || return 1
    chmod 0600 "$LHT_JOURNAL" 2>/dev/null || true
    if ! mount --bind "$_lht_clone" "$_lht_target" 2>/dev/null && \
       ! mount -o bind "$_lht_clone" "$_lht_target" 2>/dev/null; then
        _lht_log "bind failed target=$_lht_target"
        return 1
    fi
    mount -o remount,bind,ro "$_lht_target" 2>/dev/null || \
        mount -o bind,remount,ro "$_lht_target" 2>/dev/null || true
    if [ "$(_lht_identity "$_lht_target")" != "$_lht_clone_id" ]; then
        _lht_log "bind verify failed target=$_lht_target"
        return 1
    fi
    _lht_log "bound payload font over theme font target=$_lht_target source=${_lht_src##*/}"
    return 0
}

_lht_restore_internal() {
    [ -s "$LHT_JOURNAL" ] || { rm -rf "$LHT_CACHE" 2>/dev/null || true; return 0; }
    _lht_boot=$(_lht_boot_id)
    _lht_failed=0
    while IFS='|' read -r _lht_r_boot _lht_r_target _lht_r_clone _lht_r_id; do
        [ "$_lht_r_boot" = "$_lht_boot" ] && [ -n "$_lht_r_id" ] || continue
        case "$_lht_r_target" in "$LHT_DIR"/*) ;; *) continue ;; esac
        _lht_round=0
        while [ "$_lht_round" -lt 8 ] && [ "$(_lht_identity "$_lht_r_target")" = "$_lht_r_id" ] && \
              _lht_is_mountpoint "$_lht_r_target"; do
            umount "$_lht_r_target" 2>/dev/null || break
            _lht_round=$((_lht_round + 1))
        done
        if [ "$(_lht_identity "$_lht_r_target")" = "$_lht_r_id" ]; then
            _lht_failed=1
            _lht_log "restore incomplete target=$_lht_r_target; journal kept"
            continue
        fi
        [ "$_lht_round" -eq 0 ] || _lht_log "restored theme font target=$_lht_r_target"
    done < "$LHT_JOURNAL"
    [ "$_lht_failed" -eq 0 ] || return 1
    rm -f "$LHT_JOURNAL" 2>/dev/null || true
    rm -rf "$LHT_CACHE" 2>/dev/null || true
    return 0
}

_lht_ensure_internal() {
    _lht_clear_stale
    if ! lht_enabled || [ "$(_lht_active_font)" = default ] || \
       [ -f "$LHT_MODULE/disable" ] || [ -f "$LHT_MODULE/remove" ]; then
        _lht_restore_internal
        return 2
    fi
    eval "$(lht_detect | sed -n 's/^state=/_lht_state=/p')"
    if [ "$_lht_state" != user-theme ]; then
        _lht_restore_internal
        return 2
    fi
    _lht_bound=0; _lht_rc_all=2
    while IFS= read -r _lht_f; do
        [ -n "$_lht_f" ] || continue
        _lht_bind_one "$_lht_f"
        case $? in 0) _lht_bound=$((_lht_bound + 1)); _lht_rc_all=0 ;; 1) _lht_rc_all=1 ;; esac
    done <<EOF_LHT_BIND
$(_lht_theme_files)
EOF_LHT_BIND
    _lht_log "takeover result bound=$_lht_bound dir=$LHT_DIR"
    [ "$_lht_bound" -gt 0 ] && return 0
    return "$_lht_rc_all"
}

luoshu_hyperos_theme_takeover_ensure() {
    _lht_init
    _lht_lock || return 1
    _lht_ensure_internal
    _lht_rc=$?
    _lht_unlock
    return "$_lht_rc"
}

luoshu_hyperos_theme_takeover_restore() {
    _lht_init
    _lht_lock || return 1
    _lht_restore_internal
    _lht_rc=$?
    _lht_unlock
    return "$_lht_rc"
}

# key=value status for the App: detection plus setting and current ownership.
luoshu_hyperos_theme_takeover_status() {
    _lht_init
    lht_detect
    if lht_enabled; then printf 'takeover=1\n'; else printf 'takeover=0\n'; fi
    if lht_owned ''; then printf 'owned=1\n'; else printf 'owned=0\n'; fi
}

if [ "${0##*/}" = hyperos_theme_takeover.sh ]; then
    case "${1:-status}" in
        ensure) luoshu_hyperos_theme_takeover_ensure ;;
        restore) luoshu_hyperos_theme_takeover_restore ;;
        status) luoshu_hyperos_theme_takeover_status ;;
        owned) _lht_init; lht_owned "${2:-}" ;;
        *) exit 2 ;;
    esac
fi
