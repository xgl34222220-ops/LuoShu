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
LOG="$MODDIR/logs/google-font-provider.log"

_gfp_log() {
    mkdir -p "$MODDIR/logs" 2>/dev/null || true
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$*" >> "$LOG" 2>/dev/null || true
}

_gfp_hash() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" 2>/dev/null | awk '{print $1}'
    elif command -v busybox >/dev/null 2>&1; then
        busybox sha256sum "$1" 2>/dev/null | awk '{print $1}'
    else
        cksum "$1" 2>/dev/null | awk '{print $1 "-" $2}'
    fi
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

_gfp_weight() {
    _gfp_name=$(basename "$1")
    _gfp_value=$(printf '%s\n' "$_gfp_name" | tr '._-' '\n' | awk '/^(100|200|300|400|500|600|700|800|900)$/ { print; exit }')
    case "$_gfp_value" in 100|200|300|400|500|600|700|800|900) printf '%s\n' "$_gfp_value"; return 0 ;; esac
    case "$_gfp_name" in
        *Thin*) printf '100\n' ;;
        *ExtraLight*|*UltraLight*) printf '200\n' ;;
        *Light*) printf '300\n' ;;
        *Medium*) printf '500\n' ;;
        *SemiBold*|*DemiBold*) printf '600\n' ;;
        *ExtraBold*|*UltraBold*) printf '800\n' ;;
        *Black*|*Heavy*) printf '900\n' ;;
        *Bold*) printf '700\n' ;;
        *) printf '400\n' ;;
    esac
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
    for _gfp_w in $_gfp_order; do
        for _gfp_candidate in \
            "$MODDIR/config/device-font-sources/LuoShu-${_gfp_w}.ttf" \
            "$MODDIR/system/fonts/LuoShu-${_gfp_w}.ttf" \
            "$MODDIR/.luoshu-payload/system/fonts/LuoShu-${_gfp_w}.ttf"; do
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
    for _gfp_root in \
        /data/data/com.google.android.gms/files/fonts \
        /data/user/*/com.google.android.gms/files/fonts \
        /data/user_de/*/com.google.android.gms/files/fonts \
        /data/data/com.android.vending/files/fonts \
        /data/user/*/com.android.vending/files/fonts \
        /data/user_de/*/com.android.vending/files/fonts; do
        [ -d "$_gfp_root" ] || continue
        find "$_gfp_root" -maxdepth 6 -type f \( \
            -iname 'Google*Sans*.ttf' -o -iname 'Google*Sans*.otf' -o \
            -iname 'Google_Sans*.ttf' -o -iname 'Google_Sans*.otf' \
        \) -print 2>/dev/null >> "$_gfp_list"
    done
    if [ -d /data/fonts/files ]; then
        find /data/fonts/files -maxdepth 3 -type f \( \
            -iname 'Google*Sans*.ttf' -o -iname 'Google*Sans*.otf' -o \
            -iname 'Google_Sans*.ttf' -o -iname 'Google_Sans*.otf' \
        \) -print 2>/dev/null >> "$_gfp_list"
    fi
    awk 'NF && !seen[$0]++' "$_gfp_list" 2>/dev/null
    rm -f "$_gfp_list" 2>/dev/null || true
}

_gfp_build_clone() {
    _gfp_target="$1"
    _gfp_weight_value="$2"
    _gfp_source="$3"
    _gfp_source_hash=$(_gfp_hash "$_gfp_source")
    _gfp_target_hash=$(_gfp_hash "$_gfp_target")
    [ -n "$_gfp_source_hash" ] && [ -n "$_gfp_target_hash" ] || return 1
    _gfp_key=$(printf '%s\n%s\n%s\n' "$_gfp_source_hash" "$_gfp_target_hash" "$_gfp_weight_value" | _gfp_hash_text)
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
        for _gfp_pid in $(pidof com.android.vending 2>/dev/null); do
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
        grep -al -e zygote -e com.android.vending -e com.google.android.gms \
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

_gfp_pid_cmdline() {
    _gfp_pc_root="${LUOSHU_PROC_ROOT:-/proc}"
    tr '\000' ' ' < "$_gfp_pc_root/$1/cmdline" 2>/dev/null
}

_gfp_parent_pid() {
    _gfp_pp_root="${LUOSHU_PROC_ROOT:-/proc}"
    awk '/^PPid:[[:space:]]*/ { print $2; exit }' "$_gfp_pp_root/$1/status" 2>/dev/null
}

# Prefer the zygote that actually parented the currently running Play Store. If Play Store is not
# running, require every available app zygote to carry the complete replacement set; accepting an
# arbitrary one is a false positive on mixed 32/64-bit devices.
_gfp_vending_parent_zygotes() {
    for _gfp_vpid in $(pidof com.android.vending 2>/dev/null); do
        _gfp_ancestor="$_gfp_vpid"
        _gfp_depth=0
        while [ "$_gfp_depth" -lt 8 ]; do
            _gfp_ancestor=$(_gfp_parent_pid "$_gfp_ancestor")
            case "$_gfp_ancestor" in ''|0|1|*[!0-9]*) break ;; esac
            case "$(_gfp_pid_cmdline "$_gfp_ancestor")" in
                zygote*) printf '%s\n' "$_gfp_ancestor"; break ;;
            esac
            _gfp_depth=$((_gfp_depth + 1))
        done
    done | awk '/^[0-9]+$/ && !seen[$0]++'
}

_gfp_all_zygote_pids() {
    for _gfp_zpid in $(pidof zygote64 zygote zygote_secondary zygote64_32 zygote_ocomp 2>/dev/null); do
        case "$(_gfp_pid_cmdline "$_gfp_zpid")" in
            zygote*) printf '%s\n' "$_gfp_zpid" ;;
        esac
    done | awk '/^[0-9]+$/ && !seen[$0]++'
}

# Validate the exact targets from this apply transaction and their clone hashes in one process's
# namespace. Merely finding some path containing "files/fonts" can match a stale bind from an older
# font and must never be treated as proof that the current transaction reached zygote.
_gfp_verify_pid_state() {
    _gfp_vps_pid="$1"
    _gfp_vps_state="$2"
    _gfp_vps_root="${LUOSHU_PROC_ROOT:-/proc}"
    _gfp_verify_detail=
    [ -r "$_gfp_vps_root/$_gfp_vps_pid/mounts" ] || {
        _gfp_verify_detail=mount-table-unreadable
        return 1
    }
    [ -s "$_gfp_vps_state" ] || {
        _gfp_verify_detail=empty-transaction-state
        return 1
    }

    _gfp_vps_count=0
    while IFS='|' read -r _gfp_vps_target _gfp_vps_clone _gfp_vps_target_hash _gfp_vps_clone_hash; do
        [ -n "$_gfp_vps_target" ] || continue
        _gfp_vps_count=$((_gfp_vps_count + 1))
        if ! awk -v target="$_gfp_vps_target" '$2 == target { found=1 } END { exit(found ? 0 : 1) }' \
            "$_gfp_vps_root/$_gfp_vps_pid/mounts" 2>/dev/null; then
            _gfp_verify_detail="target-not-mounted:$_gfp_vps_target"
            return 1
        fi
        _gfp_vps_live_hash=$(_gfp_hash "$_gfp_vps_root/$_gfp_vps_pid/root$_gfp_vps_target")
        if [ -z "$_gfp_vps_clone_hash" ] || [ "$_gfp_vps_live_hash" != "$_gfp_vps_clone_hash" ]; then
            _gfp_verify_detail="target-hash-mismatch:$_gfp_vps_target"
            return 1
        fi
    done < "$_gfp_vps_state"
    [ "$_gfp_vps_count" -gt 0 ] || {
        _gfp_verify_detail=empty-transaction-state
        return 1
    }
    return 0
}

_gfp_verify_relevant_zygotes() {
    _gfp_vrz_state="$1"
    _gfp_zygote_scope=vending-parent
    _gfp_vrz_pids=$(_gfp_vending_parent_zygotes)
    if [ -z "$_gfp_vrz_pids" ]; then
        _gfp_zygote_scope=all-app-zygotes
        _gfp_vrz_pids=$(_gfp_all_zygote_pids)
    fi

    _gfp_zygote_seen=0
    _gfp_zygote_verified=0
    _gfp_zygote_verify_first_error=
    for _gfp_vrz_pid in $_gfp_vrz_pids; do
        _gfp_zygote_seen=$((_gfp_zygote_seen + 1))
        if _gfp_verify_pid_state "$_gfp_vrz_pid" "$_gfp_vrz_state"; then
            _gfp_zygote_verified=$((_gfp_zygote_verified + 1))
        elif [ -z "$_gfp_zygote_verify_first_error" ]; then
            _gfp_zygote_verify_first_error="pid=$_gfp_vrz_pid detail=${_gfp_verify_detail:-unknown}"
        fi
    done

    [ "$_gfp_zygote_seen" -gt 0 ] && [ "$_gfp_zygote_verified" -eq "$_gfp_zygote_seen" ]
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
    _gfp_mount_detail=
    _gfp_mount_mode=
    [ -d "/proc/$_gfp_pid/ns" ] || { _gfp_mount_detail=namespace-missing; return 1; }
    command -v nsenter >/dev/null 2>&1 || { _gfp_mount_detail=nsenter-missing; return 1; }
    _gfp_proc_source="/proc/1/root$_gfp_source"
    _gfp_stage_dir="${LUOSHU_GOOGLE_FONT_STAGE_DIR:-/data/local/tmp}"
    _gfp_ns_shell="${LUOSHU_GOOGLE_FONT_NS_SHELL:-/system/bin/sh}"
    _gfp_mount_detail=$(nsenter -t "$_gfp_pid" -m -- "$_gfp_ns_shell" -c '
        plain="$1"; proc_src="$2"; dst="$3"; stage_dir="$4"; owner_pid="$5"
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
    ' sh "$_gfp_source" "$_gfp_proc_source" "$_gfp_target" "$_gfp_stage_dir" "$_gfp_pid" 2>&1)
    _gfp_mount_rc=$?
    case "$_gfp_mount_detail" in
        ok:plain) _gfp_mount_mode=plain; _gfp_mount_detail=; return 0 ;;
        ok:staging) _gfp_mount_mode=staging; _gfp_mount_detail=; return 0 ;;
    esac
    [ "$_gfp_mount_rc" -eq 0 ] && _gfp_mount_detail=unexpected-success-without-mode
    return 1
}

_gfp_unmount_in_pid() {
    _gfp_pid="$1"
    _gfp_target="$2"
    [ -d "/proc/$_gfp_pid/ns" ] || return 1
    command -v nsenter >/dev/null 2>&1 || return 1
    nsenter -t "$_gfp_pid" -m -- umount "$_gfp_target" >/dev/null 2>&1
}

_gfp_apply_once() {
    [ "$(_gfp_active_font)" != default ] || return 2
    mkdir -p "$CACHE" "$MODDIR/logs" 2>/dev/null || return 1
    _gfp_targets_file="$CACHE/.apply-targets.$$"
    _gfp_state_tmp="${STATE}.tmp.$$"
    _gfp_targets > "$_gfp_targets_file" 2>/dev/null || true
    : > "$_gfp_state_tmp" 2>/dev/null || return 1
    _gfp_found=0
    _gfp_prepared=0
    _gfp_mounted=0
    _gfp_failed=0
    _gfp_missing_sources=0
    _gfp_ns_attempted=0
    _gfp_ns_plain=0
    _gfp_ns_staging=0
    _gfp_ns_failed=0
    _gfp_ns_first_error=
    _gfp_zygote_ok=0
    _gfp_zygote_fail=0
    _gfp_zygote_first_error=
    _gfp_missing_first=
    _gfp_namespace_pid_list=
    if [ "${LUOSHU_GOOGLE_FONT_DRY_RUN:-0}" != 1 ]; then
        _gfp_namespace_pid_list=$(_gfp_namespace_pids)
    fi
    while IFS= read -r _gfp_target; do
        _gfp_valid_font "$_gfp_target" || continue
        case "$(basename "$_gfp_target")" in *Emoji*|*Color*Emoji*|*Code*) continue ;; esac
        _gfp_found=$((_gfp_found + 1))
        _gfp_weight_value=$(_gfp_weight "$_gfp_target")
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
        _gfp_target_mounts=0
        _gfp_target_attempts=0
        if [ "${LUOSHU_GOOGLE_FONT_DRY_RUN:-0}" != 1 ]; then
            for _gfp_pid in $_gfp_namespace_pid_list; do
                _gfp_target_attempts=$((_gfp_target_attempts + 1))
                _gfp_ns_attempted=$((_gfp_ns_attempted + 1))
                if _gfp_mount_in_pid "$_gfp_pid" "$_gfp_clone" "$_gfp_target"; then
                    _gfp_target_mounts=$((_gfp_target_mounts + 1))
                    case "$_gfp_mount_mode" in
                        plain) _gfp_ns_plain=$((_gfp_ns_plain + 1)) ;;
                        staging) _gfp_ns_staging=$((_gfp_ns_staging + 1)) ;;
                    esac
                    # Whether a restarted Play Store inherits anything depends entirely on the zygote
                    # bind, so its outcome is recorded by name instead of being averaged into a count.
                    case "$(_gfp_pid_cmdline "$_gfp_pid")" in
                        zygote*) _gfp_zygote_ok=$((_gfp_zygote_ok + 1)) ;;
                    esac
                else
                    case "$(_gfp_pid_cmdline "$_gfp_pid")" in
                        zygote*)
                            _gfp_zygote_fail=$((_gfp_zygote_fail + 1))
                            [ -n "$_gfp_zygote_first_error" ] || \
                                _gfp_zygote_first_error="pid=$_gfp_pid detail=${_gfp_mount_detail:-unknown}"
                            ;;
                    esac
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
            printf '%s|%s|%s|%s\n' "$_gfp_target" "$_gfp_clone" "$(_gfp_hash "$_gfp_target")" "$(_gfp_hash "$_gfp_clone")" >> "$_gfp_state_tmp"
        else
            _gfp_failed=$((_gfp_failed + 1))
        fi
    done < "$_gfp_targets_file"
    rm -f "$_gfp_targets_file" 2>/dev/null || true
    _gfp_diag="命名空间=attempted:$_gfp_ns_attempted plain:$_gfp_ns_plain staging:$_gfp_ns_staging failed:$_gfp_ns_failed 缺源=$_gfp_missing_sources zygote=ok:$_gfp_zygote_ok/fail:$_gfp_zygote_fail"
    [ -n "$_gfp_zygote_first_error" ] && _gfp_diag="$_gfp_diag 首个zygote错误=$_gfp_zygote_first_error"
    [ -n "$_gfp_ns_first_error" ] && _gfp_diag="$_gfp_diag 首个挂载错误=$_gfp_ns_first_error"
    [ -n "$_gfp_missing_first" ] && _gfp_diag="$_gfp_diag 首个缺源=$_gfp_missing_first"
    if [ "$_gfp_mounted" -gt 0 ]; then
        if [ "${LUOSHU_GOOGLE_FONT_DRY_RUN:-0}" = 1 ]; then
            # prepare only builds clones. It made no mounts, so replacing the real undo list with
            # this synthetic state would make existing bindings impossible to restore correctly.
            rm -f "$_gfp_state_tmp" 2>/dev/null || true
            _gfp_log "provider bridge 预准备：发现=$_gfp_found 生成=$_gfp_prepared 失败=$_gfp_failed"
            return 0
        fi

        # A future Play Store process inherits from its actual parent zygote. Verify every exact
        # target and clone hash from this transaction there; if Play Store is not running, require
        # the complete transaction in every available app zygote.
        _gfp_verify_relevant_zygotes "$_gfp_state_tmp"
        _gfp_verify_rc=$?

        # The binds that were made are real and have to be undoable, so the state file is written
        # whichever way the verdict goes -- it is the undo list, not a success flag. The verdict is
        # carried by the log line and the exit code.
        if ! mv -f "$_gfp_state_tmp" "$STATE" 2>/dev/null; then
            _gfp_log "provider bridge 状态保存失败：临时清单=$_gfp_state_tmp，已保留现场且未停止 Play 商店"
            return 1
        fi
        chmod 0600 "$STATE" 2>/dev/null || true

        if [ "$_gfp_verify_rc" -eq 0 ]; then
            # Clear the currently running Play Store so its next launch forks from the bound zygote.
            if am force-stop com.android.vending >/dev/null 2>&1; then
                _gfp_stop_result='已停止 Play 商店进程，下次打开即生效'
            else
                _gfp_stop_result='停止 Play 商店进程失败，请手动关闭后重新打开'
            fi
            _gfp_log "provider bridge：发现=$_gfp_found 生成=$_gfp_prepared 挂载=$_gfp_mounted 失败=$_gfp_failed $_gfp_diag zygote校验=完整($_gfp_zygote_verified/$_gfp_zygote_seen scope=$_gfp_zygote_scope)，$_gfp_stop_result"
            return 0
        fi

        # Without the zygote bind a restart changes nothing, so do not disrupt the running app.
        _gfp_log "provider bridge 未继承：发现=$_gfp_found 生成=$_gfp_prepared 挂载=$_gfp_mounted 失败=$_gfp_failed $_gfp_diag zygote校验=不完整($_gfp_zygote_verified/$_gfp_zygote_seen scope=$_gfp_zygote_scope)，首个校验错误=${_gfp_zygote_verify_first_error:-no-zygote}，已跳过停止 Play 商店"
        return 1
    fi
    rm -f "$_gfp_state_tmp" 2>/dev/null || true
    _gfp_log "provider bridge 未生效：发现=$_gfp_found 生成=$_gfp_prepared 挂载=$_gfp_mounted 失败=$_gfp_failed $_gfp_diag"
    [ "$_gfp_found" -gt 0 ] && return 1
    return 2
}

_gfp_restore() {
    [ -s "$STATE" ] || return 0
    _gfp_restore_pids=$(_gfp_namespace_pids)
    while IFS='|' read -r _gfp_target _gfp_source _gfp_th _gfp_sh; do
        [ -n "$_gfp_target" ] || continue
        for _gfp_pid in $_gfp_restore_pids; do
            _gfp_unmount_in_pid "$_gfp_pid" "$_gfp_target" || true
        done
    done < "$STATE"
    rm -f "$STATE" 2>/dev/null || true
    _gfp_log 'provider bridge 已撤销当前命名空间挂载'
    return 0
}

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
        restore) _gfp_restore ;;
        invalidate)
            _gfp_restore >/dev/null 2>&1 || true
            rm -rf "$CACHE" "$STATE" 2>/dev/null || true
            ;;
        *) echo "Usage: $0 {boot|apply|prepare|restore|invalidate}" >&2; exit 2 ;;
    esac
fi
