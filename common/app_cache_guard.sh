#!/system/bin/sh
# Exact user-0 app cache isolation. Compare canonical paths to literal package
# roots, never to a resolved base which could itself be an escaping symlink.
_luocache_realpath() {
    _lc_candidate="$1"; _lc_suffix=''
    while :; do
        _lc_resolved=''
        if command -v readlink >/dev/null 2>&1; then
            _lc_resolved=$(readlink -f "$_lc_candidate" 2>/dev/null)
        elif command -v busybox >/dev/null 2>&1; then
            _lc_resolved=$(busybox readlink -f "$_lc_candidate" 2>/dev/null)
        fi
        if [ -n "$_lc_resolved" ]; then
            printf '%s%s\n' "$_lc_resolved" "$_lc_suffix"
            return 0
        fi
        # A dangling link is not a missing output directory we may create.
        [ ! -L "$_lc_candidate" ] || return 1
        [ "$_lc_candidate" != / ] || return 1
        _lc_suffix="/${_lc_candidate##*/}$_lc_suffix"
        _lc_candidate=${_lc_candidate%/*}
        [ -n "$_lc_candidate" ] || _lc_candidate=/
    done
}

luoshu_app_cache_guard() {
    _lc_input="$1"; _lc_purpose="${2:-preview}"
    LUOSHU_TRUSTED_CACHE_PATH=''
    case "$_lc_input" in
        *'/../'*|*/..|*'/./'*|*/.|*'//'*) return 1 ;;
    esac
    case "$_lc_input" in
        /data/user/0/*) _lc_tail=${_lc_input#/data/user/0/} ;;
        /data/data/*) _lc_tail=${_lc_input#/data/data/} ;;
        *) return 1 ;;
    esac
    _lc_package=${_lc_tail%%/*}
    case "$_lc_package" in
        io.github.xgl34222220.luoshu|io.github.xgl34222220.luoshu.debug|io.github.xgl34222220.luoshu.audit) ;;
        *) return 1 ;;
    esac
    case "$_lc_purpose" in
        preview) _lc_relative=cache ;;
        native_import|font_archive) _lc_relative="cache/$_lc_purpose" ;;
        *) return 1 ;;
    esac
    case "$_lc_tail" in "$_lc_package/$_lc_relative/"?*) ;; *) return 1 ;; esac
    _lc_canonical=$(_luocache_realpath "$_lc_input") || return 1
    case "$_lc_canonical" in
        "/data/user/0/$_lc_package/$_lc_relative/"?*|"/data/data/$_lc_package/$_lc_relative/"?*) ;;
        *) return 1 ;;
    esac
    LUOSHU_TRUSTED_CACHE_PATH="$_lc_canonical"
    return 0
}
