#!/system/bin/sh
# LuoShu Google/GMS downloadable-font provider bridge.
#
# Android system XML and /data/fonts/config do not cover fonts opened directly from
# com.google.android.gms' private downloadable-font cache. This bridge never modifies
# those provider files: it builds identity-compatible clones inside the module and
# bind-mounts them read-only in zygote/GMS/Play mount namespaces.
set +e

MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
MODULE_DIR="$MODDIR"
PYROOT="$MODDIR/common/python"
PYTHON="${LUOSHU_GOOGLE_FONT_PYTHON:-$PYROOT/bin/luoshu-python}"
PATCHER="$MODDIR/common/google_font_provider_patch.py"
CACHE="$MODDIR/config/google-font-provider"
STATE="$MODDIR/config/google-font-provider-mounts.conf"
MOUNTS="$MODDIR/config/google-font-provider-namespaces.conf"
INSPECT_CACHE="$CACHE/inspected-targets-v1.conf"
REFRESH_QUEUE="$MODDIR/config/google-font-refresh-pending.conf"
LOG="$MODDIR/logs/google-font-provider.log"

# One writer owns all provider/theme journals and the deferred-refresh queue.
# The service's lifetime lock is separate: a manual apply/restore can safely
# coexist with the sleeping watcher without racing its next maintenance pass.
_gfp_locked() {
    if [ "${_gfp_lock_held:-0}" = 1 ]; then "$@"; return $?; fi
    if ! type luoshu_font_lock_acquire >/dev/null 2>&1 && [ -f "$MODDIR/common/font_switch_lock.sh" ]; then
        . "$MODDIR/common/font_switch_lock.sh"
    fi
    if type luoshu_font_lock_acquire >/dev/null 2>&1; then
        luoshu_font_lock_acquire "$MODDIR/.google-font-provider-bridge.lock" "$$" || return 1
        _gfp_lock_held=1
        case "${0##*/}" in
            google_font_provider_bridge.sh|hyperos_theme_font_bridge.sh)
                # Entry scripts own their traps. A killed apply must release
                # its lease before the service/installer attempts restore.
                trap '_gfp_release_lock' EXIT
                trap 'exit 129' HUP
                trap 'exit 130' INT
                trap 'exit 143' TERM
                ;;
        esac
    fi
    "$@"
    _gfp_locked_rc=$?
    if [ "${_gfp_lock_held:-0}" = 1 ]; then
        luoshu_font_lock_release "$MODDIR/.google-font-provider-bridge.lock" "$$" >/dev/null 2>&1 || true
        _gfp_lock_held=0
    fi
    return "$_gfp_locked_rc"
}

_gfp_release_lock() {
    [ "${_gfp_lock_held:-0}" = 1 ] || return 0
    luoshu_font_lock_release "$MODDIR/.google-font-provider-bridge.lock" "$$" >/dev/null 2>&1 || true
    _gfp_lock_held=0
}

_gfp_log() {
    mkdir -p "$MODDIR/logs" 2>/dev/null || true
    _gfp_log_bytes=$(stat -c '%s' "$LOG" 2>/dev/null)
    case "$_gfp_log_bytes" in ''|*[!0-9]*) _gfp_log_bytes=0 ;; esac
    # A persistent permission failure is retried throughout the boot lifetime.
    # Keep its history bounded instead of growing a permanent error log.
    [ "$_gfp_log_bytes" -lt 1048576 ] || mv -f "$LOG" "$LOG.1" 2>/dev/null || true
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$*" >> "$LOG" 2>/dev/null || true
}

_gfp_hash_raw() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" 2>/dev/null | awk '{print $1}'
    elif command -v busybox >/dev/null 2>&1; then
        busybox sha256sum "$1" 2>/dev/null | awk '{print $1}'
    else
        cksum "$1" 2>/dev/null | awk '{print $1 "-" $2}'
    fi
}

# Hash each immutable source once per repair, even when many downloaded weights
# use the same composite. This cache is discarded after this apply, never a
# persistent assumption that a file with an old pathname still has old bytes.
_gfp_hash() {
    _gfp_h_stamp=$(stat -L -c '%d:%i:%s:%y:%z' "$1" 2>/dev/null) || return 1
    if [ -n "${_gfp_hash_cache:-}" ]; then
        _gfp_h_value=$(awk -F '|' -v p="$1" -v s="$_gfp_h_stamp" '$1 == p && $2 == s {print $3; exit}' "$_gfp_hash_cache" 2>/dev/null)
        [ -z "$_gfp_h_value" ] || { printf '%s\n' "$_gfp_h_value"; return 0; }
    fi
    _gfp_h_value=$(_gfp_hash_raw "$1")
    [ -n "$_gfp_h_value" ] || return 1
    [ -z "${_gfp_hash_cache:-}" ] || printf '%s|%s|%s\n' "$1" "$_gfp_h_stamp" "$_gfp_h_value" >> "$_gfp_hash_cache"
    printf '%s\n' "$_gfp_h_value"
}

_gfp_hash_text() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum 2>/dev/null | awk '{print $1}'
    elif command -v busybox >/dev/null 2>&1; then
        busybox sha256sum 2>/dev/null | awk '{print $1}'
    else
        cksum 2>/dev/null | awk '{print $1 "-" $2}'
    fi
}

_gfp_size() {
    wc -c < "$1" 2>/dev/null | tr -d '[:space:]'
}

_gfp_valid_font() {
    [ -f "$1" ] || return 1
    _gfp_bytes=$(_gfp_size "$1")
    case "$_gfp_bytes" in ''|*[!0-9]*) return 1 ;; esac
    [ "$_gfp_bytes" -ge 1024 ]
}

_gfp_python() {
    [ -x "$PYTHON" ] && [ -f "$PATCHER" ] || return 1
    if [ "$PYTHON" = "$PYROOT/bin/luoshu-python" ]; then
        PYTHONHOME="$PYROOT" \
        PYTHONPATH="$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" \
        LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
            "$PYTHON" "$PATCHER" "$@"
    else
        "$PYTHON" "$PATCHER" "$@"
    fi
}

_gfp_active_font() {
    _gfp_active=$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_gfp_active" ] || _gfp_active=default
    printf '%s\n' "$_gfp_active"
}

_gfp_source_for_weight() {
    _gfp_requested="$1"
    case "$_gfp_requested" in
        100) _gfp_order='100 200 300 400 500 600 700 800 900' ;;
        200) _gfp_order='200 100 300 400 500 600 700 800 900' ;;
        300) _gfp_order='300 400 200 500 100 600 700 800 900' ;;
        500) _gfp_order='500 400 600 300 700 200 800 100 900' ;;
        600) _gfp_order='600 500 700 400 800 300 900 200 100' ;;
        700) _gfp_order='700 600 800 500 900 400 300 200 100' ;;
        800) _gfp_order='800 900 700 600 500 400 300 200 100' ;;
        900) _gfp_order='900 800 700 600 500 400 300 200 100' ;;
        *) _gfp_order='400 500 300 600 200 700 100 800 900' ;;
    esac
    # The active physical payload is authoritative after boot. The v4 source
    # cache can belong to a previous selection and must never override it.
    _gfp_live="$MODDIR/.luoshu-payload/system/fonts"
    if [ -d "$MODDIR/.luoshu-payload" ]; then
        for _gfp_w in $_gfp_order; do
            case "$_gfp_w" in
                100) _gfp_style=Thin ;; 200) _gfp_style=ExtraLight ;;
                300) _gfp_style=Light ;; 500) _gfp_style=Medium ;;
                600) _gfp_style=SemiBold ;; 700) _gfp_style=Bold ;;
                800) _gfp_style=ExtraBold ;; 900) _gfp_style=Black ;;
                *) _gfp_style=Regular ;;
            esac
            for _gfp_candidate in \
                "$_gfp_live/LuoShu-${_gfp_w}.ttf" \
                "$_gfp_live/${_gfp_w}.ttf" \
                "$_gfp_live/.luoshu-font-store/wght-${_gfp_w}.font" \
                "$_gfp_live/Roboto-${_gfp_style}.ttf" \
                "$_gfp_live/SysSans-En-${_gfp_style}.ttf" \
                "$_gfp_live/SysFont-${_gfp_style}.ttf"; do
                if _gfp_valid_font "$_gfp_candidate"; then
                    printf '%s\n' "$_gfp_candidate"
                    return 0
                fi
            done
        done
        for _gfp_candidate in \
            "$_gfp_live/.luoshu-font-store/mix-composite.font" \
            "$_gfp_live/.luoshu-font-store/regular.font" \
            "$_gfp_live/MiSansLatinVF.ttf" "$_gfp_live/MiSansVF.ttf"; do
            if _gfp_valid_font "$_gfp_candidate"; then
                printf '%s\n' "$_gfp_candidate"
                return 0
            fi
        done
        return 1
    fi
    for _gfp_w in $_gfp_order; do
        for _gfp_candidate in \
            "$MODDIR/config/device-font-sources/LuoShu-${_gfp_w}.ttf" \
            "$MODDIR/system/fonts/LuoShu-${_gfp_w}.ttf"; do
            if _gfp_valid_font "$_gfp_candidate"; then
                printf '%s\n' "$_gfp_candidate"
                return 0
            fi
        done
    done
    return 1
}

_gfp_targets() {
    if [ -n "${LUOSHU_GOOGLE_FONT_TARGETS:-}" ]; then
        printf '%s\n' "$LUOSHU_GOOGLE_FONT_TARGETS" | awk 'NF && !seen[$0]++'
        return 0
    fi
    _gfp_list="$CACHE/.targets.$$"
    : > "$_gfp_list" 2>/dev/null || return 1
    _gfp_seen_roots='|'
    for _gfp_root in \
        /data/data/com.google.android.gms/files/fonts \
        /data/user/*/com.google.android.gms/files/fonts \
        /data/user_de/*/com.google.android.gms/files/fonts \
        /data/data/com.android.vending/files/fonts \
        /data/user/*/com.android.vending/files/fonts \
        /data/user_de/*/com.android.vending/files/fonts; do
        [ -d "$_gfp_root" ] || continue
        _gfp_root=$(readlink -f "$_gfp_root" 2>/dev/null) || continue
        case "$_gfp_seen_roots" in *"|$_gfp_root|"*) continue ;; esac
        _gfp_seen_roots="$_gfp_seen_roots$_gfp_root|"
        # Cache filenames are not an API. The Python probe checks font headers
        # and a strict family allowlist, including opaque and extensionless files.
        find "$_gfp_root" -maxdepth 6 -type f -print 2>/dev/null >> "$_gfp_list"
    done
    if [ -d /data/fonts/files ]; then
        find /data/fonts/files -maxdepth 3 -type f -print 2>/dev/null >> "$_gfp_list"
    fi
    awk 'NF && !seen[$0]++' "$_gfp_list" 2>/dev/null
    rm -f "$_gfp_list" 2>/dev/null || true
}

# Watch metadata, not font contents. This is used after boot to detect lazy GMS
# downloads, atomic cache replacement and recreated/unmounted process views.
# Batch stat calls so an idle pass never starts Python or hashes large fonts.
_gfp_stat_files() {
    set --
    while IFS= read -r _gfp_stat_path; do
        [ -n "$_gfp_stat_path" ] || continue
        printf 'path|%s\n' "$_gfp_stat_path"
        set -- "$@" "$_gfp_stat_path"
        if [ "$#" -ge 100 ]; then
            stat -L -c '%n|%d|%i|%s|%y|%z' "$@" 2>/dev/null
            set --
        fi
    done
    [ "$#" -eq 0 ] || stat -L -c '%n|%d|%i|%s|%y|%z' "$@" 2>/dev/null
    return 0
}

_gfp_fingerprint() {
    mkdir -p "$CACHE" 2>/dev/null || return 1
    _gfp_fp_targets="$CACHE/.watch-targets.$$"
    _gfp_targets | LC_ALL=C sort -u > "$_gfp_fp_targets" || return 1
    _gfp_fp_proc="${LUOSHU_PROC_ROOT:-/proc}"
    {
        printf 'active|%s\n' "$(_gfp_active_font)"
        {
            printf '%s\n' "$MODDIR/config/active_font.conf" \
                "$MODDIR/.luoshu-payload" "$MODDIR/.luoshu-payload/system/fonts" \
                "$MODDIR/.luoshu-payload/system/fonts/.luoshu-font-store" \
                "$MODDIR/config/device-font-sources"
            cat "$_gfp_fp_targets"
            [ ! -s "$STATE" ] || awk -F '|' 'NF >= 2 {print $2}' "$STATE"
        } | _gfp_stat_files
        _gfp_fp_pids=
        [ ! -s "$_gfp_fp_targets" ] || _gfp_fp_pids=$(_gfp_namespace_pids)
        _gfp_fp_seen_ns='|'
        for _gfp_fp_pid in $_gfp_fp_pids; do
            _gfp_fp_ns=$(readlink "$_gfp_fp_proc/$_gfp_fp_pid/ns/mnt" 2>/dev/null) || continue
            # A new consumer can inherit an existing namespace but cache an old
            # provider FD. Namespace-only dedup hid that process permanently.
            printf 'process|%s|%s|%s\n' "$_gfp_fp_pid" "$(_gfp_process_start "$_gfp_fp_pid" 2>/dev/null)" "$_gfp_fp_ns"
            case "$_gfp_fp_seen_ns" in *"|$_gfp_fp_ns|"*) continue ;; esac
            _gfp_fp_seen_ns="$_gfp_fp_seen_ns$_gfp_fp_ns|"
            printf 'namespace|%s|%s\n' "$_gfp_fp_pid" "$_gfp_fp_ns"
            # stat through the process root observes its own bind, including
            # fallback staging files that were unlinked immediately after bind.
            while IFS= read -r _gfp_fp_target; do
                printf '%s/%s/root%s\n' "$_gfp_fp_proc" "$_gfp_fp_pid" "$_gfp_fp_target"
            done < "$_gfp_fp_targets" | _gfp_stat_files
        done
    } | LC_ALL=C sort | _gfp_hash_text
    _gfp_fp_rc=$?
    rm -f "$_gfp_fp_targets" 2>/dev/null || true
    return "$_gfp_fp_rc"
}

_gfp_build_clone() {
    _gfp_target="$1"
    _gfp_weight_value="$2"
    _gfp_source="$3"
    _gfp_source_hash=$(_gfp_hash "$_gfp_source")
    _gfp_target_hash=$(_gfp_hash "$_gfp_target")
    [ -n "$_gfp_source_hash" ] && [ -n "$_gfp_target_hash" ] || return 1
    # Some managers share our mount namespace with a target process. A later
    # pass may therefore see our own clone at the cache path. Keep its original
    # identity/cache key instead of generating clone-of-clone on every repair.
    if [ -s "$STATE" ]; then
        while IFS='|' read -r _gfp_old_target _gfp_old_clone _gfp_old_target_hash \
            _gfp_old_clone_hash _gfp_old_source_hash _gfp_old_weight _gfp_old_schema _gfp_old_identity; do
            [ "$_gfp_old_schema" = provider-v3 ] || continue
            [ "$_gfp_old_target" = "$_gfp_target" ] || continue
            [ "$_gfp_old_source_hash" = "$_gfp_source_hash" ] || continue
            [ "$_gfp_old_weight" = "$_gfp_weight_value" ] || continue
            case "$_gfp_old_clone" in "$CACHE/"*.ttf) ;; *) continue ;; esac
            [ "$_gfp_target_hash" = "$_gfp_old_target_hash" ] || \
                [ "$_gfp_target_hash" = "$_gfp_old_clone_hash" ] || continue
            _gfp_valid_font "$_gfp_old_clone" || continue
            [ "$(_gfp_hash "$_gfp_old_clone")" = "$_gfp_old_clone_hash" ] || continue
            printf '%s\n' "$_gfp_old_clone"
            return 0
        done < "$STATE"
    fi
    _gfp_key=$(printf 'provider-v3\n%s\n%s\n%s\n' "$_gfp_source_hash" "$_gfp_target_hash" "$_gfp_weight_value" | _gfp_hash_text)
    [ -n "$_gfp_key" ] || return 1
    _gfp_output="$CACHE/${_gfp_key}.ttf"
    if ! _gfp_valid_font "$_gfp_output"; then
        _gfp_tmp="${_gfp_output}.tmp.$$"
        rm -f "$_gfp_tmp" 2>/dev/null || true
        _gfp_result=$(_gfp_python --source "$_gfp_source" --target "$_gfp_target" --output "$_gfp_tmp" --weight "$_gfp_weight_value" 2>> "$LOG")
        _gfp_rc=$?
        if [ "$_gfp_rc" -ne 0 ] || ! _gfp_valid_font "$_gfp_tmp"; then
            rm -f "$_gfp_tmp" 2>/dev/null || true
            _gfp_log "跳过 provider 字体：target=$_gfp_target weight=$_gfp_weight_value result=$_gfp_result"
            return 2
        fi
        mv -f "$_gfp_tmp" "$_gfp_output" 2>/dev/null || return 1
        chmod 0644 "$_gfp_output" 2>/dev/null || true
    fi
    if command -v chcon >/dev/null 2>&1; then
        chcon --reference="$_gfp_target" "$_gfp_output" 2>/dev/null || \
            chcon u:object_r:system_file:s0 "$_gfp_output" 2>/dev/null || true
    elif command -v toybox >/dev/null 2>&1; then
        toybox chcon --reference="$_gfp_target" "$_gfp_output" 2>/dev/null || true
    fi
    printf '%s\n' "$_gfp_output"
    return 0
}

# The full /proc sweep used to run unconditionally and forked twice per process on the device --
# a `tr` and a `basename` for each of roughly a thousand entries, repeated on every retry. On a
# phone that is tens of thousands of process spawns in the first minute after boot, from a module
# whose only job is to swap fonts. pidof already answers the question in the normal case, so the
# sweep is now a fallback, and when it does run it forks once instead of once per process.
_gfp_namespace_pids() {
    _gfp_proc_root="${LUOSHU_PROC_ROOT:-/proc}"
    {
        # Named fast paths cover the common processes.
        for _gfp_pid in $(pidof zygote64 zygote zygote_secondary zygote64_32 zygote_ocomp 2>/dev/null); do
            printf '%s
' "$_gfp_pid"
        done
        for _gfp_pid in $(pidof com.android.vending com.android.chrome com.chrome.beta com.chrome.dev com.chrome.canary 2>/dev/null); do
            printf '%s
' "$_gfp_pid"
        done
        for _gfp_pid in $(pidof com.google.android.gms com.google.android.gms.persistent com.google.android.gms.unstable 2>/dev/null); do
            printf '%s
' "$_gfp_pid"
        done

        # Preserve the previous wildcard semantics for GMS subprocesses such as
        # com.google.android.gms:phenotype. This is one grep process for the whole proc tree, not
        # two child processes per PID. The result is merged with pidof rather than replacing it.
        grep -al -e '^zygote' -e '^com[.]android[.]vending' -e '^com[.]google[.]android[.]' \
            -e '^com[.]android[.]chrome' -e '^com[.]chrome[.]beta' -e '^com[.]chrome[.]dev' -e '^com[.]chrome[.]canary' \
            "$_gfp_proc_root"/[0-9]*/cmdline 2>/dev/null |
            while IFS= read -r _gfp_path; do
                [ -n "$_gfp_path" ] || continue
                _gfp_rest=${_gfp_path#"$_gfp_proc_root"/}
                _gfp_pid=${_gfp_rest%%/*}
                case "$_gfp_pid" in ''|*[!0-9]*) continue ;; esac
                printf '%s
' "$_gfp_pid"
            done
    } | awk '/^[0-9]+$/ && !seen[$0]++'
}

# Google apps commonly share a namespace with several renderers. Mount once per
# namespace; a newly isolated Chrome/Google process still produces a new entry.
_gfp_unique_namespace_pids() {
    _gfp_up_proc="${LUOSHU_PROC_ROOT:-/proc}"
    _gfp_namespace_pids | while IFS= read -r _gfp_up_pid; do
        [ "$_gfp_up_pid" != 1 ] || continue
        _gfp_up_ns=$(readlink "$_gfp_up_proc/$_gfp_up_pid/ns/mnt" 2>/dev/null)
        [ -z "$_gfp_up_ns" ] || printf '%s|%s\n' "$_gfp_up_ns" "$_gfp_up_pid"
    done | awk -F '|' '!seen[$1]++ {print $2}'
}

# A Chrome namespace restart must not launch FontTools to re-identify unchanged
# provider files. Cache both recognized fonts and irrelevant metadata by inode,
# size, mtime and ctime; build the cache transactionally only after parsing works.
_gfp_inspect_targets() {
    _gfp_ic_candidates="$1"; _gfp_ic_output="$2"
    _gfp_ic_stamps="$CACHE/.inspect-stamps.$$"
    _gfp_ic_pending="$CACHE/.inspect-pending.$$"
    _gfp_ic_parsed="$CACHE/.inspect-parsed.$$"
    _gfp_ic_next="$CACHE/.inspect-next.$$"
    _gfp_stat_files < "$_gfp_ic_candidates" | awk -F '|' 'NF == 6 {print}' > "$_gfp_ic_stamps"
    awk -F '|' 'FILENAME == ARGV[1] {old[$1]=$0; next}
        {split(old[$1], v, "|"); if (v[2] != $2 || v[3] != $3 || v[4] != $4 || v[5] != $5 || v[6] != $6) print $1}' \
        "$INSPECT_CACHE" "$_gfp_ic_stamps" > "$_gfp_ic_pending" 2>/dev/null
    # awk cannot open a missing first input; an absent cache means all files are new.
    [ -f "$INSPECT_CACHE" ] || cut -d '|' -f 1 "$_gfp_ic_stamps" > "$_gfp_ic_pending"
    : > "$_gfp_ic_parsed"
    if [ -s "$_gfp_ic_pending" ] && ! _gfp_python --inspect-targets "$_gfp_ic_pending" > "$_gfp_ic_parsed" 2>> "$LOG"; then
        rm -f "$_gfp_ic_stamps" "$_gfp_ic_pending" "$_gfp_ic_parsed" "$_gfp_ic_next"
        return 1
    fi
    # Explicit empty files make the first read safe without changing a previous cache.
    [ -f "$INSPECT_CACHE" ] || : > "$INSPECT_CACHE"
    awk -F '|' 'FILENAME == ARGV[1] {old[$1]=$7; next}
        FILENAME == ARGV[2] {pending[$1]=1; next}
        FILENAME == ARGV[3] {split($0, p, "\t"); parsed[p[1]]=p[2]; next}
        {weight=($1 in pending ? parsed[$1] : old[$1]); print $0 "|" (weight == "" ? "-" : weight)}' \
        "$INSPECT_CACHE" "$_gfp_ic_pending" "$_gfp_ic_parsed" "$_gfp_ic_stamps" > "$_gfp_ic_next" || return 1
    mv -f "$_gfp_ic_next" "$INSPECT_CACHE" || return 1
    awk -F '|' '$7 ~ /^[1-9]00$/ {print $1 "\t" $7}' "$INSPECT_CACHE" > "$_gfp_ic_output"
    rm -f "$_gfp_ic_stamps" "$_gfp_ic_pending" "$_gfp_ic_parsed"
}

# bind 的源必须由目标进程自己的 mount namespace 解析。
# 普通模块路径在目标 namespace 可见时直接 bind；如果 root 管理器隐藏了模块目录，
# 只通过 /proc/1/root 读取 clone 内容，并在目标 namespace 的 /data/local/tmp 创建
# 临时 staging 文件。真正执行 bind 的始终是目标 namespace 内解析出的普通路径，
# 避免把 /proc/1/root 对应的 foreign vfsmount 直接交给 __do_loopback()/check_mnt()。
_gfp_mount_in_pid() {
    _gfp_pid="$1"
    _gfp_source="$2"
    _gfp_target="$3"
    _gfp_regular_only="${4:-0}"
    _gfp_mount_detail=
    _gfp_mount_mode=
    [ -d "${LUOSHU_PROC_ROOT:-/proc}/$_gfp_pid/ns" ] || { _gfp_mount_detail=namespace-missing; return 1; }
    command -v nsenter >/dev/null 2>&1 || { _gfp_mount_detail=nsenter-missing; return 1; }
    _gfp_proc_source="/proc/1/root$_gfp_source"
    _gfp_stage_dir="${LUOSHU_GOOGLE_FONT_STAGE_DIR:-/data/local/tmp}"
    _gfp_ns_shell="${LUOSHU_GOOGLE_FONT_NS_SHELL:-/system/bin/sh}"
    _gfp_mount_detail=$(nsenter -t "$_gfp_pid" -m -- "$_gfp_ns_shell" -c '
        plain="$1"; proc_src="$2"; dst="$3"; stage_dir="$4"; owner_pid="$5"; regular_only="$6"
        if [ "$regular_only" = 1 ] && [ -L "$dst" ]; then
            printf "target-is-symlink"; exit 1
        fi
        [ -f "$dst" ] || { printf "target-missing"; exit 1; }

        one_line() {
            printf "%s" "$1" | tr "\r\n" "  " | cut -c1-240
        }

        bind_one() {
            src="$1"
            first=$(mount --bind "$src" "$dst" 2>&1)
            first_rc=$?
            if [ "$first_rc" -ne 0 ]; then
                second=$(mount -o bind "$src" "$dst" 2>&1)
                second_rc=$?
                if [ "$second_rc" -ne 0 ]; then
                    printf "%s | %s" "$(one_line "$first")" "$(one_line "$second")"
                    return 1
                fi
            fi
            mount -o remount,bind,ro "$dst" 2>/dev/null || \
                mount -o bind,remount,ro "$dst" 2>/dev/null || true
            return 0
        }

        plain_detail=source-not-visible
        if [ -f "$plain" ]; then
            if cmp -s "$plain" "$dst" 2>/dev/null; then
                printf "ok:already"
                exit 0
            fi
            plain_detail=$(bind_one "$plain")
            if [ $? -eq 0 ]; then
                printf "ok:plain"
                exit 0
            fi
            [ -n "$plain_detail" ] || plain_detail=bind-failed
        fi

        stage_detail=procroot-source-not-readable
        stage="${stage_dir%/}/.luoshu-provider-${owner_pid}-$$.ttf"
        rm -f "$stage" 2>/dev/null || true
        if [ -r "$proc_src" ]; then
            if mkdir -p "$stage_dir" 2>/dev/null && cat "$proc_src" > "$stage" 2>/dev/null; then
                chmod 0644 "$stage" 2>/dev/null || true
                if command -v chcon >/dev/null 2>&1; then
                    chcon --reference="$dst" "$stage" 2>/dev/null || true
                elif command -v toybox >/dev/null 2>&1; then
                    toybox chcon --reference="$dst" "$stage" 2>/dev/null || true
                fi
                if cmp -s "$stage" "$dst" 2>/dev/null; then
                    rm -f "$stage" 2>/dev/null || true
                    printf "ok:already"
                    exit 0
                fi
                stage_detail=$(bind_one "$stage")
                stage_rc=$?
                rm -f "$stage" 2>/dev/null || true
                if [ "$stage_rc" -eq 0 ]; then
                    printf "ok:staging"
                    exit 0
                fi
                [ -n "$stage_detail" ] || stage_detail=bind-failed
            else
                stage_detail=stage-copy-failed
                rm -f "$stage" 2>/dev/null || true
            fi
        fi
        printf "plain=%s; staging=%s" "$(one_line "$plain_detail")" "$(one_line "$stage_detail")"
        exit 1
    ' sh "$_gfp_source" "$_gfp_proc_source" "$_gfp_target" "$_gfp_stage_dir" "$_gfp_pid" "$_gfp_regular_only" 2>&1)
    _gfp_mount_rc=$?
    case "$_gfp_mount_detail" in
        ok:plain) _gfp_mount_mode=plain; _gfp_mount_detail=; return 0 ;;
        ok:staging) _gfp_mount_mode=staging; _gfp_mount_detail=; return 0 ;;
        ok:already) _gfp_mount_mode=already; _gfp_mount_detail=; return 0 ;;
    esac
    [ "$_gfp_mount_rc" -eq 0 ] && _gfp_mount_detail=unexpected-success-without-mode
    return 1
}

_gfp_unmount_in_pid() {
    _gfp_pid="$1"
    _gfp_target="$2"
    [ -d "${LUOSHU_PROC_ROOT:-/proc}/$_gfp_pid/ns" ] || return 1
    command -v nsenter >/dev/null 2>&1 || return 1
    nsenter -t "$_gfp_pid" -m -- umount "$_gfp_target" >/dev/null 2>&1
}

_gfp_process_start() {
    IFS= read -r _gfp_ps_stat < "${LUOSHU_PROC_ROOT:-/proc}/$1/stat" 2>/dev/null || return 1
    _gfp_ps_tail=${_gfp_ps_stat##*) }
    [ "$_gfp_ps_tail" != "$_gfp_ps_stat" ] || return 1
    set -- $_gfp_ps_tail
    [ "$#" -ge 20 ] || return 1
    shift 19
    case "$1" in ''|*[!0-9]*) return 1 ;; esac
    printf '%s\n' "$1"
}

_gfp_consumer_package() {
    _gfp_cp_name=$(tr '\000' '\n' < "${LUOSHU_PROC_ROOT:-/proc}/$1/cmdline" 2>/dev/null | head -n1)
    _gfp_cp_name=${_gfp_cp_name%%:*}
    case "$_gfp_cp_name" in
        com.google.android.gms|com.google.android.gms.*|com.google.android.webview) return 1 ;;
        com.android.chrome|com.chrome.beta|com.chrome.dev|com.chrome.canary|com.android.vending|com.google.android.*) ;;
        *) return 1 ;;
    esac
    case "$_gfp_cp_name" in *[!A-Za-z0-9_.]*) return 1 ;; esac
    printf '%s\n' "$_gfp_cp_name"
}

# Chromium caches opened ParcelFileDescriptors and dup()s them on later font
# requests. A replacement bind only affects future opens, not these old FDs.
# Remember only consumers whose view actually changed; never poll all app FDs.
_gfp_refresh_boot() {
    _gfp_rb_current=$(cat "${LUOSHU_PROC_ROOT:-/proc}/sys/kernel/random/boot_id" 2>/dev/null)
    [ -n "$_gfp_rb_current" ] || _gfp_rb_current=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null)
    [ -n "$_gfp_rb_current" ] || return 1
    if [ "$(cat "${REFRESH_QUEUE}.boot" 2>/dev/null)" != "$_gfp_rb_current" ]; then
        rm -f "$REFRESH_QUEUE"
        printf '%s\n' "$_gfp_rb_current" > "${REFRESH_QUEUE}.boot" || return 1
    fi
}

_gfp_queue_all_consumers() {
    _gfp_qac_identity="$1"
    [ -n "$_gfp_qac_identity" ] || return 0
    case "|${_gfp_queued_identities:-}" in *"|$_gfp_qac_identity|"*) return 0 ;; esac
    _gfp_queued_identities="${_gfp_queued_identities:-}$_gfp_qac_identity|"
    # Mount once per namespace, but stale FDs belong to individual processes.
    # A representative zygote/GMS PID must not hide its Chrome consumers.
    if [ -z "${_gfp_consumer_pids_loaded:-}" ]; then
        _gfp_consumer_pids=$(_gfp_namespace_pids)
        _gfp_consumer_pids_loaded=1
    fi
    for _gfp_qac_pid in $_gfp_consumer_pids; do
        _gfp_queue_refresh "$_gfp_qac_pid" "$_gfp_qac_identity"
    done
}

_gfp_queue_refresh() {
    _gfp_q_pid="$1"; _gfp_q_id="$2"
    case "$_gfp_q_id" in ''|*[!0-9:]*) return 0 ;; esac
    _gfp_refresh_boot || return 0
    _gfp_q_pkg=$(_gfp_consumer_package "$_gfp_q_pid") || return 0
    _gfp_q_start=$(_gfp_process_start "$_gfp_q_pid") || return 0
    _gfp_q_uid=$(awk '/^Uid:/ {print $2; exit}' "${LUOSHU_PROC_ROOT:-/proc}/$_gfp_q_pid/status" 2>/dev/null)
    case "$_gfp_q_uid" in ''|*[!0-9]*) return 0 ;; esac
    [ "$_gfp_q_uid" -ge 10000 ] || return 0
    _gfp_q_user=$((_gfp_q_uid / 100000))
    _gfp_q_device=${_gfp_q_id%:*}; _gfp_q_inode=${_gfp_q_id#*:}
    _gfp_q_map=$(printf '%x:%x:%s' "$(( (_gfp_q_device >> 8 & 4095) | (_gfp_q_device >> 32 & 4294963200) ))" \
        "$(( (_gfp_q_device & 255) | (_gfp_q_device >> 12 & 4294967040) ))" "$_gfp_q_inode")
    _gfp_q_row="$_gfp_q_pid|$_gfp_q_start|$_gfp_q_pkg|$_gfp_q_user|$_gfp_q_id"
    if [ -s "$REFRESH_QUEUE" ] && awk -F '|' -v row="$_gfp_q_row" '$1 FS $2 FS $3 FS $4 FS $5 == row {found=1} END {exit !found}' "$REFRESH_QUEUE"; then
        return 0
    fi
    printf '%s|0|%s\n' "$_gfp_q_row" "$_gfp_q_map" >> "$REFRESH_QUEUE"
    chmod 0600 "$REFRESH_QUEUE" 2>/dev/null || true
}

_gfp_refresh_internal() {
    [ -s "$REFRESH_QUEUE" ] || return 0
    _gfp_refresh_boot || return 1
    [ -s "$REFRESH_QUEUE" ] || return 0
    [ "$(_gfp_active_font)" != default ] && [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || {
        rm -f "$REFRESH_QUEUE" "${REFRESH_QUEUE}.boot"; return 0;
    }
    _gfp_r_proc="${LUOSHU_PROC_ROOT:-/proc}"
    _gfp_r_groups="${REFRESH_QUEUE}.groups.$$"
    _gfp_r_open="${REFRESH_QUEUE}.open.$$"
    _gfp_r_keep="${REFRESH_QUEUE}.keep.$$"
    _gfp_r_next="${REFRESH_QUEUE}.next.$$"
    awk -F '|' 'NF == 7 && !seen[$1 FS $2 FS $3 FS $4]++ {print $1 FS $2 FS $3 FS $4 FS $6}' "$REFRESH_QUEUE" > "$_gfp_r_groups" || return 1
    : > "$_gfp_r_next" || return 1
    _gfp_r_now=$(date +%s 2>/dev/null)
    case "$_gfp_r_now" in ''|*[!0-9]*) _gfp_r_now=0 ;; esac
    _gfp_r_calls=0
    while IFS='|' read -r _gfp_r_pid _gfp_r_start _gfp_r_pkg _gfp_r_user _gfp_r_last; do
        [ "$(_gfp_process_start "$_gfp_r_pid")" = "$_gfp_r_start" ] || continue
        [ "$(_gfp_consumer_package "$_gfp_r_pid")" = "$_gfp_r_pkg" ] || continue
        case "$_gfp_r_user:$_gfp_r_last" in *[!0-9:]*) continue ;; esac
        # All stat calls are in one batch; maps also cover a closed FD whose
        # font remains mmap'ed. Matching both device and inode prevents an
        # unrelated descriptor on another filesystem from triggering a refresh.
        stat -L -c '%d:%i' "$_gfp_r_proc/$_gfp_r_pid/fd/"* > "$_gfp_r_open" 2>/dev/null || true
        awk '$5 ~ /^[0-9]+$/ && $5 != 0 {split($4,d,":"); sub(/^0+/,"",d[1]); sub(/^0+/,"",d[2]);
            print "map|" (d[1] == "" ? "0" : d[1]) ":" (d[2] == "" ? "0" : d[2]) ":" $5}' \
            "$_gfp_r_proc/$_gfp_r_pid/maps" >> "$_gfp_r_open" 2>/dev/null || true
        awk -F '|' -v pid="$_gfp_r_pid" -v start="$_gfp_r_start" \
            'FILENAME == ARGV[1] {opened[$0]=1; next} $1 == pid && $2 == start && (opened[$5] || opened["map|" $7])' \
            "$_gfp_r_open" "$REFRESH_QUEUE" > "$_gfp_r_keep"
        [ -s "$_gfp_r_keep" ] || continue
        if [ "$_gfp_r_calls" -lt 4 ] && [ $((_gfp_r_now - _gfp_r_last)) -ge 60 ] && command -v timeout >/dev/null 2>&1; then
            # ActivityManager killBackgroundProcesses skips foreground/visible
            # processes. Never force-stop an app, GMS, zygote or system_server.
            # Android user comes from the confirmed process UID, not 'all'.
            timeout 3 am kill --user "$_gfp_r_user" "$_gfp_r_pkg" >/dev/null 2>&1 || true
            _gfp_r_calls=$((_gfp_r_calls + 1))
            _gfp_r_last=$_gfp_r_now
        fi
        # A foreground process survives 'am kill': retain its exact identity
        # and retry after it moves to the background. Recycled PIDs are dropped.
        [ "$(_gfp_process_start "$_gfp_r_pid")" = "$_gfp_r_start" ] || continue
        awk -F '|' -v OFS='|' -v last="$_gfp_r_last" '{$6=last; print}' "$_gfp_r_keep" >> "$_gfp_r_next"
    done < "$_gfp_r_groups"
    mv -f "$_gfp_r_next" "$REFRESH_QUEUE"
    _gfp_r_rc=$?
    rm -f "$_gfp_r_groups" "$_gfp_r_open" "$_gfp_r_keep" "$_gfp_r_next"
    return "$_gfp_r_rc"
}

_gfp_identity() {
    stat -L -c '%d:%i:%s' "$1" 2>/dev/null
}

_gfp_owned_identity() {
    [ -s "$MOUNTS" ] || return 1
    # A child can inherit our inode in a new mount namespace. Inode ownership is
    # independent of PID/namespace, but must still match this exact target path.
    awk -F '|' -v target="$1" -v inode="$2" '$2 == target && $3 == inode {found=1} END {exit !found}' "$MOUNTS"
}

_gfp_clear_owned_pid() {
    _gfp_clear_pid="$1"; _gfp_clear_target="$2"; _gfp_clear_round=0
    while [ "$_gfp_clear_round" -lt 64 ]; do
        _gfp_clear_id=$(_gfp_identity "${LUOSHU_PROC_ROOT:-/proc}/$_gfp_clear_pid/root$_gfp_clear_target")
        [ -n "$_gfp_clear_id" ] || return 0
        _gfp_owned_identity "$_gfp_clear_target" "$_gfp_clear_id" || return 0
        _gfp_unmount_in_pid "$_gfp_clear_pid" "$_gfp_clear_target" || return 1
        _gfp_clear_round=$((_gfp_clear_round + 1))
    done
    return 1
}

_gfp_mount_journal_failed() {
    # All post-bind journal errors use the same rollback, including inability
    # to create/append the temporary file. Never remove an already-present or
    # externally replaced layer while reporting the write failure.
    if [ "$_gfp_mount_mode" != already ] && [ "$(_gfp_identity "$_gfp_mt_proc/$_gfp_mt_pid/root$_gfp_mt_target")" = "$_gfp_mt_id" ]; then
        _gfp_unmount_in_pid "$_gfp_mt_pid" "$_gfp_mt_target" || true
    fi
    rm -f "$_gfp_mt_tmp"
    _gfp_mount_detail=mount-journal-write-failed
}

_gfp_mount_target() {
    _gfp_mt_pid="$1"; _gfp_mt_clone="$2"; _gfp_mt_target="$3"
    _gfp_mt_proc="${LUOSHU_PROC_ROOT:-/proc}"
    _gfp_mt_ns=$(readlink "$_gfp_mt_proc/$_gfp_mt_pid/ns/mnt" 2>/dev/null)
    _gfp_mt_id=$(_gfp_identity "$_gfp_mt_proc/$_gfp_mt_pid/root$_gfp_mt_target")
    _gfp_mt_previous=${_gfp_mt_id%:*}
    if [ -n "$_gfp_mt_id" ] && [ -s "$MOUNTS" ] && \
        awk -F '|' -v target="$_gfp_mt_target" -v inode="$_gfp_mt_id" -v clone="$_gfp_mt_clone" \
            '$2 == target && $3 == inode && $4 == clone {found=1} END {exit !found}' "$MOUNTS"; then
        _gfp_mount_mode=already
    else
        _gfp_clear_owned_pid "$_gfp_mt_pid" "$_gfp_mt_target" || { _gfp_mount_detail=owned-unmount-failed; return 1; }
        _gfp_mount_in_pid "$_gfp_mt_pid" "$_gfp_mt_clone" "$_gfp_mt_target" || return 1
        _gfp_mt_id=$(_gfp_identity "$_gfp_mt_proc/$_gfp_mt_pid/root$_gfp_mt_target")
        [ "$_gfp_mount_mode" = already ] || _gfp_queue_all_consumers "$_gfp_mt_previous"
    fi
    # A process may exit immediately after bind. Its namespace then needs no
    # undo record; if it returns later its new namespace is discovered normally.
    if [ -n "$_gfp_mt_ns" ] && [ -n "$_gfp_mt_id" ]; then
        _gfp_mt_tmp="${MOUNTS}.tmp.$$"
        if [ -s "$MOUNTS" ]; then
            awk -F '|' -v ns="$_gfp_mt_ns" -v target="$_gfp_mt_target" '!($1 == ns && $2 == target)' "$MOUNTS" > "$_gfp_mt_tmp" || { _gfp_mount_journal_failed; return 1; }
        else
            printf '' > "$_gfp_mt_tmp" || { _gfp_mount_journal_failed; return 1; }
        fi
        printf '%s|%s|%s|%s\n' "$_gfp_mt_ns" "$_gfp_mt_target" "$_gfp_mt_id" "$_gfp_mt_clone" >> "$_gfp_mt_tmp" || { _gfp_mount_journal_failed; return 1; }
        if ! mv -f "$_gfp_mt_tmp" "$MOUNTS"; then
            _gfp_mount_journal_failed
            return 1
        fi
        chmod 0600 "$MOUNTS" 2>/dev/null || true
    fi
    return 0
}

_gfp_prune_journal() {
    [ -s "$MOUNTS" ] || return 0
    _gfp_pj_live="${MOUNTS}.live.$$"
    : > "$_gfp_pj_live" || return 1
    for _gfp_pj_pid in $_gfp_namespace_pid_list; do
        readlink "${LUOSHU_PROC_ROOT:-/proc}/$_gfp_pj_pid/ns/mnt" 2>/dev/null >> "$_gfp_pj_live"
    done
    awk -F '|' 'FILENAME == ARGV[1] {live[$1]=1; next} $1 in live' "$_gfp_pj_live" "$MOUNTS" > "${MOUNTS}.tmp.$$" && \
        mv -f "${MOUNTS}.tmp.$$" "$MOUNTS"
    _gfp_pj_rc=$?
    rm -f "$_gfp_pj_live" "${MOUNTS}.tmp.$$"
    return "$_gfp_pj_rc"
}

_gfp_prune_clones() {
    [ -s "$STATE" ] || return 0
    _gfp_keep=$(awk -F '|' 'NF >= 2 {print $2}' "$STATE")
    for _gfp_cached in "$CACHE"/*.ttf; do
        [ -f "$_gfp_cached" ] || continue
        case "
$_gfp_keep
" in *"
$_gfp_cached
"*) continue ;; esac
        # Old source selections/download identities otherwise leave one full
        # font per cache key forever. Existing kernel binds retain their inode;
        # only prune after every current target namespace has been handled.
        rm -f "$_gfp_cached" 2>/dev/null || true
    done
}

_gfp_apply_internal() {
    [ "$(_gfp_active_font)" != default ] || return 2
    mkdir -p "$CACHE" "$MODDIR/logs" 2>/dev/null || return 1
    _gfp_targets_file="$CACHE/.apply-targets.$$"
    _gfp_candidates_file="$CACHE/.apply-candidates.$$"
    _gfp_state_tmp="${STATE}.tmp.$$"
    _gfp_targets > "$_gfp_candidates_file" 2>/dev/null || true
    # No downloaded files means there is nothing for FontTools to identify.
    # In particular a phone without GMS should never start Python each retry.
    if [ ! -s "$_gfp_candidates_file" ]; then
        rm -f "$_gfp_candidates_file" 2>/dev/null || true
        return 2
    fi
    if ! _gfp_inspect_targets "$_gfp_candidates_file" "$_gfp_targets_file"; then
        rm -f "$_gfp_candidates_file" "$_gfp_targets_file" 2>/dev/null || true
        _gfp_log 'provider bridge 未生效：字体缓存识别失败（Python/FontTools）'
        return 1
    fi
    rm -f "$_gfp_candidates_file" 2>/dev/null || true
    : > "$_gfp_state_tmp" 2>/dev/null || return 1
    _gfp_found=0
    _gfp_prepared=0
    _gfp_mounted=0
    _gfp_failed=0
    _gfp_missing_sources=0
    _gfp_ns_attempted=0
    _gfp_ns_plain=0
    _gfp_ns_staging=0
    _gfp_ns_already=0
    _gfp_ns_failed=0
    _gfp_ns_first_error=
    _gfp_missing_first=
    _gfp_namespace_pid_list=
    if [ "${LUOSHU_GOOGLE_FONT_DRY_RUN:-0}" != 1 ]; then
        _gfp_namespace_pid_list=$(_gfp_unique_namespace_pids)
    fi
    while IFS="$(printf '\t')" read -r _gfp_target _gfp_weight_value; do
        _gfp_valid_font "$_gfp_target" || continue
        _gfp_found=$((_gfp_found + 1))
        _gfp_source=$(_gfp_source_for_weight "$_gfp_weight_value")
        if [ -z "$_gfp_source" ]; then
            _gfp_missing_sources=$((_gfp_missing_sources + 1))
            [ -n "$_gfp_missing_first" ] || _gfp_missing_first="weight=$_gfp_weight_value target=$_gfp_target"
            _gfp_failed=$((_gfp_failed + 1))
            continue
        fi
        _gfp_clone=$(_gfp_build_clone "$_gfp_target" "$_gfp_weight_value" "$_gfp_source")
        _gfp_clone_rc=$?
        if [ "$_gfp_clone_rc" -ne 0 ] || ! _gfp_valid_font "$_gfp_clone"; then
            _gfp_failed=$((_gfp_failed + 1))
            continue
        fi
        _gfp_prepared=$((_gfp_prepared + 1))
        _gfp_selected_hash=$(_gfp_hash "$_gfp_source")
        _gfp_original_target_hash=$(_gfp_hash "$_gfp_target")
        _gfp_original_identity=$(_gfp_identity "$_gfp_target")
        _gfp_original_identity=${_gfp_original_identity%:*}
        _gfp_clone_identity=$(_gfp_identity "$_gfp_clone")
        _gfp_clone_identity=${_gfp_clone_identity%:*}
        if [ "$_gfp_original_identity" = "$_gfp_clone_identity" ]; then
            _gfp_original_identity=$(awk -F '|' -v target="$_gfp_target" -v clone="$_gfp_clone" '$1 == target && $2 == clone && NF >= 8 {print $8; exit}' "$STATE" 2>/dev/null)
        fi
        # Paths may already show the clone while a Chrome process still dup()s
        # its earlier provider FD. Preserve and check the original inode too.
        if [ "${LUOSHU_GOOGLE_FONT_DRY_RUN:-0}" != 1 ]; then
            [ "$_gfp_original_identity" = "$_gfp_clone_identity" ] || _gfp_queue_all_consumers "$_gfp_original_identity"
        fi
        _gfp_target_mounts=0
        _gfp_target_attempts=0
        if [ "${LUOSHU_GOOGLE_FONT_DRY_RUN:-0}" != 1 ]; then
            for _gfp_pid in $_gfp_namespace_pid_list; do
                _gfp_target_attempts=$((_gfp_target_attempts + 1))
                _gfp_ns_attempted=$((_gfp_ns_attempted + 1))
                if _gfp_mount_target "$_gfp_pid" "$_gfp_clone" "$_gfp_target"; then
                    _gfp_target_mounts=$((_gfp_target_mounts + 1))
                    case "$_gfp_mount_mode" in
                        plain) _gfp_ns_plain=$((_gfp_ns_plain + 1)) ;;
                        staging) _gfp_ns_staging=$((_gfp_ns_staging + 1)) ;;
                        already) _gfp_ns_already=$((_gfp_ns_already + 1)) ;;
                    esac
                else
                    _gfp_ns_failed=$((_gfp_ns_failed + 1))
                    if [ -z "$_gfp_ns_first_error" ]; then
                        _gfp_ns_first_error="pid=$_gfp_pid target=$_gfp_target detail=${_gfp_mount_detail:-unknown}"
                    fi
                fi
            done
            if [ "$_gfp_target_attempts" -eq 0 ] && [ -z "$_gfp_ns_first_error" ]; then
                _gfp_ns_first_error="no-target-namespace-pids"
            fi
        fi
        if [ "${LUOSHU_GOOGLE_FONT_DRY_RUN:-0}" = 1 ] || [ "$_gfp_target_mounts" -gt 0 ]; then
            _gfp_mounted=$((_gfp_mounted + 1))
            printf '%s|%s|%s|%s|%s|%s|provider-v3|%s\n' "$_gfp_target" "$_gfp_clone" \
                "$_gfp_original_target_hash" "$(_gfp_hash "$_gfp_clone")" \
                "$_gfp_selected_hash" "$_gfp_weight_value" "$_gfp_original_identity" >> "$_gfp_state_tmp"
        else
            _gfp_failed=$((_gfp_failed + 1))
        fi
    done < "$_gfp_targets_file"
    rm -f "$_gfp_targets_file" 2>/dev/null || true
    _gfp_diag="命名空间=attempted:$_gfp_ns_attempted plain:$_gfp_ns_plain staging:$_gfp_ns_staging already:$_gfp_ns_already failed:$_gfp_ns_failed 缺源=$_gfp_missing_sources"
    [ -n "$_gfp_ns_first_error" ] && _gfp_diag="$_gfp_diag 首个挂载错误=$_gfp_ns_first_error"
    [ -n "$_gfp_missing_first" ] && _gfp_diag="$_gfp_diag 首个缺源=$_gfp_missing_first"
    if [ "$_gfp_mounted" -gt 0 ]; then
        if ! mv -f "$_gfp_state_tmp" "$STATE" 2>/dev/null; then
            rm -f "$_gfp_state_tmp" 2>/dev/null || true
            _gfp_log 'provider bridge 挂载记录保存失败，保留现有字体缓存等待重试'
            return 1
        fi
        chmod 0600 "$STATE" 2>/dev/null || true
        _gfp_log "provider bridge：发现=$_gfp_found 生成=$_gfp_prepared 挂载=$_gfp_mounted 失败=$_gfp_failed $_gfp_diag"
        # Refresh old consumer FDs through the bounded background-only queue.
        # Never force-stop Play/Chrome during boot or interrupt the current app.
        # A successful zygote bind alone does not prove GMS can open the clone.
        if [ "$_gfp_failed" -eq 0 ] && [ "$_gfp_ns_failed" -eq 0 ]; then
            if [ "${LUOSHU_GOOGLE_FONT_DRY_RUN:-0}" != 1 ]; then
                _gfp_prune_clones
                _gfp_prune_journal || return 1
            fi
            return 0
        fi
        return 1
    fi
    rm -f "$_gfp_state_tmp" 2>/dev/null || true
    _gfp_log "provider bridge 未生效：发现=$_gfp_found 生成=$_gfp_prepared 挂载=$_gfp_mounted 失败=$_gfp_failed $_gfp_diag"
    [ "$_gfp_found" -gt 0 ] && return 1
    return 2
}

_gfp_restore_internal() {
    rm -f "$REFRESH_QUEUE" "${REFRESH_QUEUE}.boot"
    [ -s "$MOUNTS" ] || { rm -f "$STATE"; return 0; }
    _gfp_restore_pids=$(_gfp_unique_namespace_pids)
    _gfp_restore_failed=0
    _gfp_restore_targets=$(awk -F '|' 'NF == 4 && !seen[$2]++ {print $2}' "$MOUNTS")
    while IFS= read -r _gfp_restore_target; do
        [ -n "$_gfp_restore_target" ] || continue
        for _gfp_restore_pid in $_gfp_restore_pids; do
            _gfp_clear_owned_pid "$_gfp_restore_pid" "$_gfp_restore_target" || _gfp_restore_failed=1
        done
    done <<EOF
$_gfp_restore_targets
EOF
    [ "$_gfp_restore_failed" -eq 0 ] || return 1
    rm -f "$STATE" "$MOUNTS" 2>/dev/null || true
    _gfp_log 'provider bridge 已撤销本模块拥有的命名空间挂载'
    return 0
}

_gfp_apply_cached() {
    _gfp_consumer_pids_loaded=
    _gfp_queued_identities=
    mkdir -p "$CACHE" 2>/dev/null || return 1
    _gfp_hash_cache="$CACHE/.apply-hashes.$$"
    : > "$_gfp_hash_cache" || return 1
    _gfp_apply_internal
    _gfp_apply_result=$?
    rm -f "$_gfp_hash_cache"
    _gfp_hash_cache=
    return "$_gfp_apply_result"
}

_gfp_apply_once() { _gfp_locked _gfp_apply_cached; }
_gfp_restore() { _gfp_locked _gfp_restore_internal; }
_gfp_refresh_consumers() { _gfp_locked _gfp_refresh_internal; }

_gfp_boot() {
    _gfp_attempt=1
    _gfp_limit="${LUOSHU_GOOGLE_FONT_RETRIES:-12}"
    case "$_gfp_limit" in ''|*[!0-9]*) _gfp_limit=12 ;; esac
    [ "$_gfp_limit" -ge 1 ] 2>/dev/null || _gfp_limit=1
    while [ "$_gfp_attempt" -le "$_gfp_limit" ]; do
        _gfp_apply_once && return 0
        _gfp_rc=$?
        [ "$_gfp_attempt" -lt "$_gfp_limit" ] || return "$_gfp_rc"
        sleep 5
        _gfp_attempt=$((_gfp_attempt + 1))
    done
    return 2
}

if [ "${0##*/}" = google_font_provider_bridge.sh ]; then
    case "${1:-boot}" in
        boot) _gfp_boot ;;
        apply|now) _gfp_apply_once ;;
        prepare) LUOSHU_GOOGLE_FONT_DRY_RUN=1 _gfp_apply_once ;;
        fingerprint) _gfp_fingerprint ;;
        refresh) _gfp_refresh_consumers ;;
        restore) _gfp_restore ;;
        invalidate)
            _gfp_restore >/dev/null 2>&1 || exit 1
            rm -rf "$CACHE" "$STATE" "$MOUNTS" 2>/dev/null || true
            ;;
        *) echo "Usage: $0 {boot|apply|prepare|fingerprint|restore|invalidate}" >&2; exit 2 ;;
    esac
fi
