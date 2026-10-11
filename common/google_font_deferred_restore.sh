#!/system/bin/sh
# 洛书卸载后的单次恢复脚本（模板）。
#
# 卸载在下次开机的 post-fs-data 早期执行，那时 pm/dumpsys 还不可用，
# Google 字体兼容停用的 FontsProvider 组件无法当场恢复，而管理器随后会
# 删除整个模块目录。根 uninstall.sh 因此把本文件复制到模块目录之外的
# /data/adb/service.d/，由管理器在同一次开机的 late_start service 阶段执行：
#   1. 后台等待 sys.boot_completed=1（有上限）；
#   2. 只处理洛书恢复目录里经过校验的 user-N.json；GMS 安装身份一致、
#      组件仍是洛书设置的“停用”时，才用 pm 恢复记录里的原状态，并复核；
#   3. 任何不确定都保留记录、不改系统；全部完成或超过重试次数后删除自己。
# 本脚本不依赖模块目录、Python 或任何洛书运行环境。
set +e

LRD_SELF="$0"
LRD_STORE="${LUOSHU_GOOGLE_FALLBACK_STORE:-/data/adb/luoshu/google-font-fallback}"
LRD_LEGACY="${LUOSHU_GOOGLE_FALLBACK_LEGACY_STORE:-/data/adb/luoshu-google-font-fallback}"
LRD_ROOT="${LRD_STORE%/*}"
LRD_ATTEMPTS="$LRD_ROOT/.uninstall-restore-attempts"
LRD_MODULES="${LUOSHU_MODULES_DIR:-/data/adb/modules}"
LRD_MODULES_UPDATE="${LUOSHU_MODULES_UPDATE_DIR:-/data/adb/modules_update}"
LRD_WAIT="${LUOSHU_DEFERRED_RESTORE_WAIT:-300}"
LRD_MAX_BOOTS="${LUOSHU_DEFERRED_RESTORE_MAX_BOOTS:-3}"
LRD_GMS=com.google.android.gms
LRD_PROVIDER=com.google.android.gms.fonts.provider.FontsProvider
LRD_COMPONENT="$LRD_GMS/$LRD_PROVIDER"
LRD_SCHEMA=luoshu-google-font-fallback-v1
LRD_UID=$(id -u 2>/dev/null)

_lrd_log() {
    command -v log >/dev/null 2>&1 && log -t LuoShu "$1" >/dev/null 2>&1
    return 0
}

# 本脚本只能删除它自己和它的计数文件；恢复记录只在核验恢复成功后逐个删除。
_lrd_finish() {
    rm -f "$LRD_ATTEMPTS" 2>/dev/null
    rmdir "$LRD_ROOT" 2>/dev/null
    rm -f "$LRD_SELF" 2>/dev/null
}

_lrd_reinstalled() {
    [ -d "$LRD_MODULES_UPDATE/LuoShu" ] && return 0
    [ -d "$LRD_MODULES/LuoShu" ] && [ ! -e "$LRD_MODULES/LuoShu/remove" ] && \
        [ ! -L "$LRD_MODULES/LuoShu/remove" ] && return 0
    return 1
}

_lrd_secure_dir() {
    [ -d "$1" ] && [ ! -L "$1" ] || return 1
    _lrdsd=$(stat -c '%u %a' "$1" 2>/dev/null) || return 1
    [ "${_lrdsd%% *}" = "$LRD_UID" ] || return 1
    case "${_lrdsd##* }" in *[2367]?|*[2367]) return 1 ;; esac
    return 0
}

_lrd_records() {
    for _lrdr_dir in "$LRD_STORE" "$LRD_LEGACY"; do
        _lrd_secure_dir "$_lrdr_dir" || continue
        for _lrdr_file in "$_lrdr_dir"/user-*.json; do
            [ -f "$_lrdr_file" ] || [ -L "$_lrdr_file" ] || continue
            printf '%s\n' "$_lrdr_file"
        done
    done
}

# 取出 json.dump(indent=2) 写出的单个顶层字段；必须恰好出现一次。
_lrd_field() {
    _lrdf=$(sed -n "s/^  \"$2\": \\(.*\\)\$/\\1/p" "$1" 2>/dev/null)
    [ -n "$_lrdf" ] || return 1
    [ "$(printf '%s\n' "$_lrdf" | wc -l)" -eq 1 ] || return 1
    _lrdf=${_lrdf%,}
    case "$_lrdf" in
        \"*\") _lrdf=${_lrdf#\"}; _lrdf=${_lrdf%\"} ;;
    esac
    case "$_lrdf" in *\\*|*\"*) return 1 ;; esac
    printf '%s\n' "$_lrdf"
}

# 解析 dumpsys package com.google.android.gms，规则与 google_font_fallback_core.py
# 的 parse_snapshot 一致：唯一 Packages 区、唯一 GMS 包、指定用户的唯一 User 块。
# 输出：appId|firstInstallTime|componentState(0/1/2)|declared(0/1)；不确定就失败。
_lrd_snapshot() {
    _lrds_user="$1"
    _lrds_text=$(dumpsys -t 10 package "$LRD_GMS" 2>/dev/null) || return 1
    [ -n "$_lrds_text" ] || return 1
    printf '%s\n' "$_lrds_text" | awk -v user="$_lrds_user" -v gms="$LRD_GMS" -v provider="$LRD_PROVIDER" '
        function indent_of(s) { match(s, /^ */); return RLENGTH }
        { line[NR] = $0 }
        END {
            for (i = 1; i <= NR; i++) {
                low = tolower(line[i])
                if (low ~ /dump timed out|dump timeout|permission denial|can.t find service/) exit 1
            }
            declared = 0; sections = 0; start = 0; stop = NR
            for (i = 1; i <= NR; i++) {
                if (line[i] ~ /^Packages:[ \t]*$/) { sections++; start = i + 1; continue }
                if (sections == 0) {
                    t = line[i] " "
                    if (index(t, gms "/" provider) || index(t, gms "/.fonts.provider.FontsProvider")) {
                        n1 = gms "/" provider; n2 = gms "/.fonts.provider.FontsProvider"
                        p = index(t, n1); l = length(n1)
                        if (!p) { p = index(t, n2); l = length(n2) }
                        c = substr(t, p + l, 1)
                        if (c == " " || c == "\t" || c == "}" || c == "]") declared = 1
                    }
                }
            }
            if (sections != 1) exit 1
            for (i = start; i <= NR; i++) if (line[i] ~ /^[^ ]/) { stop = i - 1; break }
            pkgs = 0; ps = 0; pe = stop
            for (i = start; i <= stop; i++) {
                if (line[i] !~ /^  Package \[/) continue
                if (ps && pe == stop && i > ps) pe = i - 1
                if (index(line[i], "  Package [" gms "]") == 1) { pkgs++; ps = i + 1; pe = stop }
            }
            if (pkgs != 1) exit 1
            appid = ""; nusers = 0
            for (i = ps; i <= pe; i++) {
                if (appid == "" && line[i] ~ /^[ \t]+(appId|userId)=[0-9]+/) {
                    s = line[i]; sub(/^[ \t]+(appId|userId)=/, "", s); match(s, /^[0-9]+/); appid = substr(s, 1, RLENGTH)
                }
                if (line[i] ~ /^ +User [0-9]+:/) {
                    nusers++; uline[nusers] = i
                }
            }
            if (appid == "" || nusers == 0) exit 1
            hit = 0
            for (k = 1; k <= nusers; k++) {
                s = line[uline[k]]; sub(/^ +User /, "", s); sub(/:.*/, "", s)
                if (s + 0 == user + 0 && s == user "") { hit++; uk = k }
            }
            if (hit != 1) exit 1
            head = line[uline[uk]]
            if (head !~ /[^A-Za-z]installed=true([^A-Za-z]|$)/) exit 1
            if (head !~ /[^A-Za-z]enabled=[0-9]+/) exit 1
            uindent = indent_of(head)
            ustart = uline[uk] + 1
            uend = (uk < nusers) ? uline[uk + 1] - 1 : pe
            first = ""
            state = 0; seen1 = 0; seen2 = 0; list = 0; lindent = 0
            for (i = ustart; i <= uend; i++) {
                s = line[i]; st = s; gsub(/^[ \t]+|[ \t]+$/, "", st)
                if (st == "") continue
                ind = indent_of(s)
                if (ind <= uindent) break
                if (first == "" && s ~ /^[ \t]+firstInstallTime=/) { first = s; sub(/^[ \t]+firstInstallTime=/, "", first) }
                if ((st ~ /enabledComponents/ || st ~ /disabledComponents/) && st != "enabledComponents:" && st != "disabledComponents:") exit 1
                if (st == "enabledComponents:" || st == "disabledComponents:") {
                    list = (st == "enabledComponents:") ? 1 : 2; lindent = ind; continue
                }
                if (list && ind <= lindent) list = 0
                if (list) {
                    name = st
                    if (index(name, "/")) {
                        pk = substr(name, 1, index(name, "/") - 1); name = substr(name, index(name, "/") + 1)
                        if (pk != gms) continue
                    }
                    if (substr(name, 1, 1) == ".") name = gms name
                    if (name == provider) { state = list; if (list == 1) seen1 = 1; else seen2 = 1 }
                }
            }
            if (seen1 && seen2) exit 1
            if (first == "") {
                for (i = ps; i < uline[1]; i++) if (line[i] ~ /^[ \t]+firstInstallTime=/) {
                    first = line[i]; sub(/^[ \t]+firstInstallTime=/, "", first); break
                }
            }
            if (first == "") exit 1
            sub(/[ \t]+$/, "", first)
            printf "%s|%s|%d|%d\n", appid, first, state, declared
        }'
}

_lrd_restore_one() {
    _lrdo_file="$1"
    _lrdo_name=${_lrdo_file##*/}
    case "$_lrdo_name" in
        user-0.json) _lrdo_user=0 ;;
        user-[1-9]*.json)
            _lrdo_user=${_lrdo_name#user-}; _lrdo_user=${_lrdo_user%.json}
            case "$_lrdo_user" in *[!0-9]*|??????*) return 1 ;; esac
            [ "$_lrdo_user" -le 21474 ] || return 1 ;;
        *) return 1 ;;
    esac
    [ -f "$_lrdo_file" ] && [ ! -L "$_lrdo_file" ] || return 1
    _lrdo_meta=$(stat -c '%u %a %s' "$_lrdo_file" 2>/dev/null) || return 1
    set -- $_lrdo_meta
    [ "$1" = "$LRD_UID" ] || return 1
    case "$2" in *[2367]?|*[2367]) return 1 ;; esac
    [ "$3" -le 16384 ] 2>/dev/null || return 1

    [ "$(_lrd_field "$_lrdo_file" schema)" = "$LRD_SCHEMA" ] || return 1
    [ "$(_lrd_field "$_lrdo_file" component)" = "$LRD_COMPONENT" ] || return 1
    [ "$(_lrd_field "$_lrdo_file" user)" = "$_lrdo_user" ] || return 1
    _lrdo_original=$(_lrd_field "$_lrdo_file" original) || return 1
    case "$_lrdo_original" in 0|1) ;; *) return 1 ;; esac
    _lrdo_appid=$(_lrd_field "$_lrdo_file" appId) || return 1
    case "$_lrdo_appid" in ''|*[!0-9]*) return 1 ;; esac
    _lrdo_first=$(_lrd_field "$_lrdo_file" firstInstallTime) || return 1

    _lrdo_now=$(_lrd_snapshot "$_lrdo_user") || return 1
    IFS='|' read -r _lrdo_cur_appid _lrdo_cur_first _lrdo_cur_state _lrdo_declared <<EOF_SNAP
$_lrdo_now
EOF_SNAP
    # GMS 被重装或组件已不存在：不覆盖新安装状态，保留记录。
    [ "$_lrdo_cur_appid" = "$_lrdo_appid" ] && [ "$_lrdo_cur_first" = "$_lrdo_first" ] || return 1
    [ "$_lrdo_declared" = 1 ] || return 1
    if [ "$_lrdo_cur_state" = "$_lrdo_original" ]; then
        rm -f "$_lrdo_file"
        return 0
    fi
    # 只撤销洛书自己的“停用”；其他人改过的状态不碰。
    [ "$_lrdo_cur_state" = 2 ] || return 1
    case "$_lrdo_original" in 0) _lrdo_cmd=default-state ;; 1) _lrdo_cmd=enable ;; esac
    _lrdo_out=$(pm "$_lrdo_cmd" --user "$_lrdo_user" "$LRD_COMPONENT" 2>&1) || return 1
    case "$(printf '%s' "$_lrdo_out" | tr 'A-Z' 'a-z')" in *exception*|*error:*) return 1 ;; esac
    _lrdo_after=$(_lrd_snapshot "$_lrdo_user") || return 1
    IFS='|' read -r _lrdo_cur_appid _lrdo_cur_first _lrdo_cur_state _lrdo_declared <<EOF_SNAP
$_lrdo_after
EOF_SNAP
    [ "$_lrdo_cur_appid" = "$_lrdo_appid" ] && [ "$_lrdo_cur_first" = "$_lrdo_first" ] && \
        [ "$_lrdo_cur_state" = "$_lrdo_original" ] || return 1
    rm -f "$_lrdo_file"
    _lrd_log "洛书卸载后已恢复用户 $_lrdo_user 的 Google 字体提供组件"
    return 0
}

_lrd_cleanup_store() {
    # 恢复目录里只剩操作锁时才删除；仍有任何其他文件就原样保留。
    for _lrdc_dir in "$LRD_STORE" "$LRD_LEGACY"; do
        _lrd_secure_dir "$_lrdc_dir" || continue
        _lrdc_left=$(ls -A "$_lrdc_dir" 2>/dev/null)
        case "$_lrdc_left" in ''|operation.lock) ;; *) continue ;; esac
        rm -f "$_lrdc_dir/operation.lock" 2>/dev/null
        rmdir "$_lrdc_dir" 2>/dev/null
    done
    if [ -L "$LRD_LEGACY" ] && [ ! -e "$LRD_STORE" ]; then
        case "$(readlink "$LRD_LEGACY" 2>/dev/null)" in "$LRD_STORE"|"$LRD_STORE/") rm -f "$LRD_LEGACY" ;; esac
    fi
}

_lrd_main() {
    # 用户已经重新安装洛书：恢复记录交给新模块和 App 处理，本脚本退出。
    if _lrd_reinstalled; then _lrd_finish; return 0; fi
    if [ -z "$(_lrd_records)" ]; then _lrd_cleanup_store; _lrd_finish; return 0; fi

    _lrdm_count=$(cat "$LRD_ATTEMPTS" 2>/dev/null)
    case "$_lrdm_count" in ''|*[!0-9]*) _lrdm_count=0 ;; esac
    _lrdm_count=$((_lrdm_count + 1))
    if [ "$_lrdm_count" -gt "$LRD_MAX_BOOTS" ]; then
        # 保留恢复记录：重新安装洛书后可在 App 里“恢复原设置”。
        _lrd_log '洛书卸载后恢复多次未完成，已保留恢复记录并停止重试'
        _lrd_finish
        return 0
    fi
    printf '%s\n' "$_lrdm_count" > "$LRD_ATTEMPTS" 2>/dev/null

    _lrdm_waited=0
    while [ "$(getprop sys.boot_completed 2>/dev/null)" != 1 ]; do
        [ "$_lrdm_waited" -lt "$LRD_WAIT" ] || return 0   # 下次开机再试
        sleep 2
        _lrdm_waited=$((_lrdm_waited + 2))
    done
    if _lrd_reinstalled; then _lrd_finish; return 0; fi

    for _lrdm_file in $(_lrd_records); do
        _lrd_restore_one "$_lrdm_file" || \
            _lrd_log "洛书卸载后恢复 ${_lrdm_file##*/} 未完成，已保留记录"
    done
    if [ -z "$(_lrd_records)" ]; then
        _lrd_cleanup_store
        _lrd_finish
    fi
    return 0
}

if [ "${LUOSHU_DEFERRED_RESTORE_FOREGROUND:-0}" = 1 ]; then
    _lrd_main
else
    ( _lrd_main ) </dev/null >/dev/null 2>&1 &
fi
exit 0
