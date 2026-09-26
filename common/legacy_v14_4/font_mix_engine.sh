#!/system/bin/sh
# 洛书 v14.1：完整复合字体引擎。
# 中文字体保留为完整基底，仅把英文与数字的对应字形写入同一份字体。
# 仅生成组合源，实际替换路径由本机字体清单决定；不覆盖系统 XML。
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
    else
        MODDIR="/data/adb/modules/LuoShu"
    fi
fi

# All mutating engine work must be hosted by the isolated router runtime.
case "$MODDIR" in
    "${LUOSHU_REAL_MODDIR:-}/.legacy-v14-runtime") ;;
    *)
        case "${1:-status}" in
            start|recover) exec sh "$MODDIR/common/font_mix.sh" "$@" ;;
            status) exec sh "$MODDIR/common/font_mix.sh" config ;;
            *) printf '{"status":"error","message":"字体源引擎需要隔离暂存目录"}\n'; exit 1 ;;
        esac
        ;;
esac

CONFIG_DIR="$MODDIR/config"
SYSTEM_FONTS_DIR="$MODDIR/system/fonts"
USER_FONTS_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts"
TASK_FILE="$CONFIG_DIR/mix_task.conf"
MIX_CONF="$CONFIG_DIR/font_mix.conf"
ACTIVE_FONT_CONF="$CONFIG_DIR/active_font.conf"
TEXT_REBOOT_REQUIRED="$CONFIG_DIR/text_reboot_required.conf"
LOCK_FILE="$MODDIR/.font_switch.lock"
LOG_FILE="$MODDIR/logs/fontswitch.log"
MODULE_DIR="$MODDIR"
PAYLOAD_STAGE=""
PAYLOAD_BACKUP=""
PAYLOAD_ACTIVATED=0
PAYLOAD_COMMIT_MARKER="$MODDIR/.font-payload-commit.ok"
COMPOSITE_RESULT=""
COMPOSITE_REPORT=""
COMPOSITE_CACHE_HIT=false
COMPOSITE_CJK_HASH=""
COMPOSITE_LATIN_HASH=""
COMPOSITE_DIGIT_HASH=""
COMPOSITE_OUTPUT_HASH=""
LAST_MIX_ERROR=""

[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/font_check.sh" ] && . "$MODDIR/common/font_check.sh"
[ -f "$MODDIR/common/mount_compat.sh" ] && . "$MODDIR/common/mount_compat.sh"


json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

ensure_work_dir() {
    _ewd_dir="$1"
    _ewd_label="${2:-工作目录}"
    # Compatibility runtimes intentionally expose config/logs/system through
    # symlinks. Some Android toybox builds return EEXIST for "mkdir -p" when
    # the final component itself is a symlink to a directory. Never mkdir an
    # already valid directory; only create paths that are genuinely absent.
    [ -d "$_ewd_dir" ] && return 0
    if [ -L "$_ewd_dir" ]; then
        _ewd_target=$(readlink "$_ewd_dir" 2>/dev/null)
        set_mix_error "${_ewd_label}链接失效：${_ewd_dir}${_ewd_target:+ -> $_ewd_target}"
        return 1
    fi
    mkdir -p "$_ewd_dir" 2>/dev/null || {
        set_mix_error "无法创建${_ewd_label}：$_ewd_dir"
        return 1
    }
    [ -d "$_ewd_dir" ] || {
        set_mix_error "${_ewd_label}不可用：$_ewd_dir"
        return 1
    }
    return 0
}

read_conf() {
    _key="$1"; _fallback="$2"; _value=""
    [ -f "$MIX_CONF" ] && _value=$(sed -n "s/^${_key}=//p" "$MIX_CONF" 2>/dev/null | head -n1 | tr -d '\r\n')
    [ -n "$_value" ] || _value="$_fallback"
    printf '%s' "$_value"
}

write_task() {
    _task="$1"; _state="$2"; _message="$3"; _cjk="$4"; _latin="$5"; _digit="$6"; _started="$7"; _finished="$8"
    _tmp="$TASK_FILE.tmp.$$"
    {
        printf 'task=%s\n' "$_task"
        printf 'state=%s\n' "$_state"
        printf 'message=%s\n' "$_message"
        printf 'cjk=%s\n' "$_cjk"
        printf 'latin=%s\n' "$_latin"
        printf 'digit=%s\n' "$_digit"
        printf 'started=%s\n' "$_started"
        printf 'finished=%s\n' "$_finished"
    } > "$_tmp" 2>/dev/null && mv -f "$_tmp" "$TASK_FILE" 2>/dev/null
    chmod 0644 "$TASK_FILE" 2>/dev/null || true
}

rotate_mix_log() {
    [ -f "$LOG_FILE" ] || return 0
    _size=$(wc -c < "$LOG_FILE" 2>/dev/null | tr -d '[:space:]')
    case "$_size" in ''|*[!0-9]*) _size=0 ;; esac
    [ "$_size" -le 1048576 ] && return 0
    _tmp="$LOG_FILE.trim.$$"
    tail -n 1200 "$LOG_FILE" > "$_tmp" 2>/dev/null && mv -f "$_tmp" "$LOG_FILE" 2>/dev/null
}

find_family_file() {
    _want="$1"; _chosen=""
    if type get_weight_file >/dev/null 2>&1; then
        _chosen=$(get_weight_file "$_want" regular 2>/dev/null)
        [ -f "$_chosen" ] && { printf '%s\n' "$_chosen"; return 0; }
    fi
    for _f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
              "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_f" ] || continue
        _fam=$(detect_font_family "$(basename "$_f")")
        [ "$_fam" = "$_want" ] && { printf '%s\n' "$_f"; return 0; }
    done
    return 1
}

validate_source() {
    _src="$1"; _label="$2"
    [ -f "$_src" ] || { echo "错误：找不到${_label}字体" >&2; return 1; }
    if type font_validate >/dev/null 2>&1 && ! font_validate "$_src" text; then
        echo "错误：${_label}字体无效：$FONT_CHECK_ERROR" >&2
        return 1
    fi
    return 0
}

recover_interrupted_payload() {
    if [ -f "$PAYLOAD_COMMIT_MARKER" ]; then
        rm -rf "$MODDIR"/.font-payload-backup.* "$MODDIR"/.font-payload-stage.* 2>/dev/null || true
        rm -f "$PAYLOAD_COMMIT_MARKER" 2>/dev/null || true
        return 0
    fi
    for _backup in "$MODDIR"/.font-payload-backup.*; do
        [ -d "$_backup" ] || continue
        rm -rf "$SYSTEM_FONTS_DIR" 2>/dev/null || true
        mv "$_backup" "$SYSTEM_FONTS_DIR" 2>/dev/null || true
        break
    done
    rm -rf "$MODDIR"/.font-payload-backup.* "$MODDIR"/.font-payload-stage.* 2>/dev/null || true
}

payload_stage_begin() {
    PAYLOAD_STAGE="$MODDIR/.font-payload-stage.$$"
    PAYLOAD_BACKUP="$MODDIR/.font-payload-backup.$$"
    PAYLOAD_ACTIVATED=0
    rm -rf "$PAYLOAD_STAGE" "$PAYLOAD_BACKUP" "$PAYLOAD_COMMIT_MARKER" 2>/dev/null || true
    # This directory belongs to the isolated mix stage. Start with only the
    # selected source; physical targets are populated once by the inventory stage.
    # PAYLOAD_BACKUP remains the atomic rollback point for this source handoff.
    mkdir -p "$PAYLOAD_STAGE" 2>/dev/null || return 1
    return 0
}

payload_stage_abort() {
    [ -z "$PAYLOAD_STAGE" ] || rm -rf "$PAYLOAD_STAGE" 2>/dev/null || true
    PAYLOAD_STAGE=""
}

payload_stage_activate() {
    mkdir -p "${SYSTEM_FONTS_DIR%/*}" 2>/dev/null || return 1
    if [ -d "$SYSTEM_FONTS_DIR" ]; then
        mv "$SYSTEM_FONTS_DIR" "$PAYLOAD_BACKUP" 2>/dev/null || return 1
    else
        mkdir -p "$PAYLOAD_BACKUP" 2>/dev/null || return 1
    fi
    if ! mv "$PAYLOAD_STAGE" "$SYSTEM_FONTS_DIR" 2>/dev/null; then
        rm -rf "$SYSTEM_FONTS_DIR" 2>/dev/null || true
        mv "$PAYLOAD_BACKUP" "$SYSTEM_FONTS_DIR" 2>/dev/null || true
        return 1
    fi
    PAYLOAD_STAGE=""
    PAYLOAD_ACTIVATED=1
    return 0
}

payload_stage_rollback() {
    [ "$PAYLOAD_ACTIVATED" -eq 1 ] || return 0
    rm -rf "$SYSTEM_FONTS_DIR" 2>/dev/null || true
    mv "$PAYLOAD_BACKUP" "$SYSTEM_FONTS_DIR" 2>/dev/null || true
    rm -f "$PAYLOAD_COMMIT_MARKER" 2>/dev/null || true
    PAYLOAD_BACKUP=""
    PAYLOAD_ACTIVATED=0
}

payload_stage_finalize() {
    [ "$PAYLOAD_ACTIVATED" -eq 1 ] || return 0
    rm -rf "$PAYLOAD_BACKUP" 2>/dev/null || true
    rm -f "$PAYLOAD_COMMIT_MARKER" 2>/dev/null || true
    PAYLOAD_BACKUP=""
    PAYLOAD_ACTIVATED=0
}

cleanup_mix_process() {
    payload_stage_abort
    payload_stage_rollback
    rm -f "$LOCK_FILE" 2>/dev/null || true
}

write_fixed_source_weights() {
    _wfs_helper="$LUOSHU_REAL_MODDIR/common/mix_source_manifest.py"
    _wfs_python="$MODDIR/common/python"
    [ -f "$_wfs_helper" ] || return 1
    PYTHONHOME="$_wfs_python" \
    PYTHONPATH="$_wfs_python/lib/python3.14:$_wfs_python/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$_wfs_python/lib:$_wfs_python/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$_wfs_python/bin/luoshu-python" "$_wfs_helper" \
        --manifest "$PAYLOAD_STAGE/.luoshu-font-store/.luoshu-mix-source-weights.json" \
        --anchor mix-composite.font --composite "$COMPOSITE_RESULT" \
        --cjk "$1" --latin "$2" --digit "$3"
}

stage_composite_source() (
    _scs_store="$1/.luoshu-font-store"
    _scs_source="$2"
    [ -s "$_scs_source" ] || exit 1
    mkdir -p "$_scs_store" 2>/dev/null || exit 1
    # Keep one immutable source; the inventory stage derives only real targets.
    ln "$_scs_source" "$_scs_store/mix-composite.font" 2>/dev/null ||
        cp -f "$_scs_source" "$_scs_store/mix-composite.font" 2>/dev/null || exit 1
    chmod 0644 "$_scs_store/mix-composite.font" 2>/dev/null || true
    [ -s "$_scs_store/mix-composite.font" ]
)

composite_hash_file() {
    _hf="$1"
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "$_hf" | awk '{print $1}'
    elif command -v toybox >/dev/null 2>&1; then toybox sha256sum "$_hf" | awk '{print $1}'
    else cksum "$_hf" | awk '{print $1 "-" $2}'
    fi
}

set_mix_error() {
    LAST_MIX_ERROR="$1"
    printf '%s\n' "$LAST_MIX_ERROR" > "$CONFIG_DIR/mix_last_error.txt" 2>/dev/null || true
    chmod 0644 "$CONFIG_DIR/mix_last_error.txt" 2>/dev/null || true
    echo "错误：$LAST_MIX_ERROR" >&2
}

extract_composite_error() {
    _ef="$1"; _rc="$2"; _msg=""
    if [ -s "$_ef" ]; then
        _msg=$(sed -n 's/^.*"message":"\([^"]*\)".*$/\1/p' "$_ef" 2>/dev/null | tail -n1)
        [ -n "$_msg" ] || _msg=$(tail -n1 "$_ef" 2>/dev/null | tr -d '\r')
    fi
    case "$_rc" in
        124) _msg="复合字体生成超过 8 分钟，已安全终止" ;;
        137|9) _msg="复合字体生成进程被系统终止，通常是内存不足" ;;
        126) _msg="复合字体运行程序没有执行权限" ;;
        127) _msg="复合字体运行时无法启动" ;;
        20) _msg="复合字体运行时文件缺失" ;;
        21) _msg="当前设备不是 ARM64，无法运行复合字体引擎" ;;
    esac
    [ -n "$_msg" ] || _msg="完整复合字体生成失败（底层返回 $_rc）"
    printf '%s' "$_msg"
}

check_composite_runtime() {
    _runner="$MODDIR/common/luoshu_composite.sh"
    ensure_work_dir "$MODDIR/cache" "运行时缓存目录" || return 1
    _runtime_key=$(composite_hash_file "$MODDIR/common/python/bin/luoshu-python" 2>/dev/null)
    [ -n "$_runtime_key" ] || _runtime_key=unknown
    _ok="$MODDIR/cache/runtime_probe.${_runtime_key}.ok"
    [ -s "$_ok" ] && return 0
    rm -f "$MODDIR/cache"/runtime_probe.*.ok 2>/dev/null || true
    _probe="$MODDIR/cache/runtime_probe.txt"
    rm -f "$_probe" 2>/dev/null || true
    MODDIR="$MODDIR" sh "$_runner" --self-test >"$_probe" 2>&1
    _rc=$?
    if [ "$_rc" -ne 0 ] || ! grep -q '^ok$' "$_probe" 2>/dev/null; then
        _detail=$(tail -n1 "$_probe" 2>/dev/null | tr -d '\r')
        [ -n "$_detail" ] || _detail="返回 $_rc"
        set_mix_error "复合字体运行时自检失败：$_detail"
        return 1
    fi
    printf 'ok\n' > "$_ok" 2>/dev/null || true
    return 0
}

write_progress() {
    _stage="$1"; _message="$2"; _percent="$3"; _progress="$CONFIG_DIR/composite_progress.json"
    _tmp="$_progress.$$"
    printf '{"stage":"%s","message":"%s","percent":%s,"time":%s}\n' \
        "$(json_escape "$_stage")" "$(json_escape "$_message")" "$_percent" "$(date +%s)" > "$_tmp" 2>/dev/null && mv -f "$_tmp" "$_progress" 2>/dev/null
}

prune_composite_cache() {
    # Keep enough recent combinations for normal back-and-forth switching, with a
    # storage cap so cached CJK composites cannot grow without bound.
    _cache="$1"; _keep=8; _max_kb=262144; _count=0; _total_kb=0
    for _old in $(ls -1t "$_cache"/*.otf 2>/dev/null); do
        _count=$((_count + 1))
        _size_kb=$(du -k "$_old" 2>/dev/null | awk '{print $1}')
        case "$_size_kb" in ''|*[!0-9]*) _size_kb=0 ;; esac
        _total_kb=$((_total_kb + _size_kb))
        [ "$_count" -le "$_keep" ] && [ "$_total_kb" -le "$_max_kb" ] && continue
        _base=${_old%.otf}
        rm -f "$_old" "${_base}.json" 2>/dev/null || true
    done
    rm -f "$_cache"/.*.tmp.* 2>/dev/null || true
}

build_composite_file() {
    _cjk_src="$1"; _latin_src="$2"; _digit_src="$3"
    COMPOSITE_RESULT=""; COMPOSITE_REPORT=""; COMPOSITE_CACHE_HIT=false; LAST_MIX_ERROR=""
    _runner="$MODDIR/common/luoshu_composite.sh"
    [ -f "$MODDIR/common/composite_font.py" ] && [ -f "$_runner" ] || { set_mix_error '完整复合字体引擎缺失'; return 1; }
    [ -x "$MODDIR/common/python/bin/luoshu-python" ] || chmod 0755 "$MODDIR/common/python/bin/luoshu-python" 2>/dev/null || true
    check_composite_runtime || return 1
    _cache="$MODDIR/cache/full-composite-v7"
    mkdir -p "$_cache" "$MODDIR/cache/tmp" 2>/dev/null || { set_mix_error '无法创建复合字体缓存目录'; return 1; }
    _cjk_hash=$(composite_hash_file "$_cjk_src")
    _latin_hash=$(composite_hash_file "$_latin_src")
    _digit_hash=$(composite_hash_file "$_digit_src")
    COMPOSITE_CJK_HASH="$_cjk_hash"
    COMPOSITE_LATIN_HASH="$_latin_hash"
    COMPOSITE_DIGIT_HASH="$_digit_hash"
    _key_src="${_cjk_hash}-${_latin_hash}-${_digit_hash}-full-composite-v7-metrics"
    _key=$(printf '%s' "$_key_src" | { if command -v sha256sum >/dev/null 2>&1; then sha256sum; elif command -v toybox >/dev/null 2>&1; then toybox sha256sum; else cksum; fi; } | awk '{print $1}')
    _cached="$_cache/${_key}.otf"; _report="$_cache/${_key}.json"; _progress="$CONFIG_DIR/composite_progress.json"
    rm -f "$_cache"/.*.tmp.* 2>/dev/null || true
    if [ -s "$_cached" ]; then
        COMPOSITE_CACHE_HIT=true
        touch "$_cached" "$_report" 2>/dev/null || true
        write_progress cache '已验证并使用现有复合字体缓存' 100
    elif [ -n "$_cjk_hash" ] && [ "$_cjk_hash" = "$_latin_hash" ] && [ "$_cjk_hash" = "$_digit_hash" ]; then
        # Selecting one complete font for all three roles needs no glyph rewrite.
        # Reuse the validated source directly instead of serializing the entire CJK
        # font through embedded Python.
        ln "$_cjk_src" "$_cached" 2>/dev/null || cp -f "$_cjk_src" "$_cached" 2>/dev/null || {
            set_mix_error '无法保存同源复合字体缓存'
            return 1
        }
        chmod 0644 "$_cached" 2>/dev/null || true
        printf '{"status":"ok","fastPath":"same-source"}\n' >"$_report" 2>/dev/null || true
        write_progress cache '三项字体来源相同，已跳过重复合成' 100
    else
        _tmp="$_cache/.${_key}.$$.tmp.otf"; _tmp_report="$_cache/.${_key}.$$.tmp.json"; _tmp_error="$_cache/.${_key}.$$.tmp.err"
        rm -f "$_tmp" "$_tmp_report" "$_tmp_error" "$_progress" 2>/dev/null || true
        if command -v timeout >/dev/null 2>&1; then
            MODDIR="$MODDIR" timeout 480 sh "$_runner" --cjk "$_cjk_src" --latin "$_latin_src" --digit "$_digit_src" --output "$_tmp" --progress "$_progress" > "$_tmp_report" 2> "$_tmp_error"
            _run_rc=$?
        elif command -v toybox >/dev/null 2>&1 && toybox timeout --help >/dev/null 2>&1; then
            MODDIR="$MODDIR" toybox timeout 480 sh "$_runner" --cjk "$_cjk_src" --latin "$_latin_src" --digit "$_digit_src" --output "$_tmp" --progress "$_progress" > "$_tmp_report" 2> "$_tmp_error"
            _run_rc=$?
        else
            MODDIR="$MODDIR" sh "$_runner" --cjk "$_cjk_src" --latin "$_latin_src" --digit "$_digit_src" --output "$_tmp" --progress "$_progress" > "$_tmp_report" 2> "$_tmp_error"
            _run_rc=$?
        fi
        [ ! -s "$_tmp_error" ] || cat "$_tmp_error" >> "$LOG_FILE" 2>/dev/null || true
        if [ "$_run_rc" -ne 0 ]; then
            _detail=$(extract_composite_error "$_tmp_error" "$_run_rc")
            rm -f "$_tmp" "$_tmp_report" "$_tmp_error" 2>/dev/null || true
            set_mix_error "$_detail"
            return 1
        fi
        [ -s "$_tmp" ] || { rm -f "$_tmp" "$_tmp_report" "$_tmp_error"; set_mix_error '复合字体输出为空'; return 1; }
        if type font_validate >/dev/null 2>&1 && ! font_validate "$_tmp" text; then
            rm -f "$_tmp" "$_tmp_report" "$_tmp_error" 2>/dev/null || true
            set_mix_error "复合字体验证失败：$FONT_CHECK_ERROR"
            return 1
        fi
        chmod 0644 "$_tmp" "$_tmp_report" 2>/dev/null || true
        mv -f "$_tmp" "$_cached" || { set_mix_error '无法保存复合字体缓存'; return 1; }
        mv -f "$_tmp_report" "$_report" 2>/dev/null || true
        rm -f "$_tmp_error" 2>/dev/null || true
        write_progress done '复合字体已生成并通过验证' 100
    fi
    prune_composite_cache "$_cache"
    COMPOSITE_RESULT="$_cached"; COMPOSITE_REPORT="$_report"
    COMPOSITE_OUTPUT_HASH=$(composite_hash_file "$_cached")
    return 0
}

write_mix_generation_manifest() {
    _manifest="${LUOSHU_MIX_MANIFEST:-}"
    _request="${LUOSHU_MIX_REQUEST_ID:-}"
    _expected_cjk="${LUOSHU_MIX_EXPECTED_CJK:-$1}"
    _expected_latin="${LUOSHU_MIX_EXPECTED_LATIN:-$2}"
    _expected_digit="${LUOSHU_MIX_EXPECTED_DIGIT:-$3}"
    [ -n "$_manifest" ] && [ -n "$_request" ] || return 0
    mkdir -p "${_manifest%/*}" 2>/dev/null || return 1
    _tmp="${_manifest}.tmp.$$"
    {
        printf 'requestId=%s\n' "$_request"
        printf 'cjk=%s\nlatin=%s\ndigit=%s\n' "$_expected_cjk" "$_expected_latin" "$_expected_digit"
        printf 'engineCjk=%s\nengineLatin=%s\nengineDigit=%s\n' "$1" "$2" "$3"
        printf 'cjkHash=%s\nlatinHash=%s\ndigitHash=%s\n' \
            "$COMPOSITE_CJK_HASH" "$COMPOSITE_LATIN_HASH" "$COMPOSITE_DIGIT_HASH"
        printf 'compositeHash=%s\n' "$COMPOSITE_OUTPUT_HASH"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } >"$_tmp" 2>/dev/null || return 1
    mv -f "$_tmp" "$_manifest" 2>/dev/null || return 1
    chmod 0644 "$_manifest" 2>/dev/null || true
}

prepare_mix_config() {
    _cjk="$1"; _latin="$2"; _digit="$3"; _font_tmp="$CONFIG_DIR/.font_mix.$$"; _active_tmp="$CONFIG_DIR/.active_font.$$"; _reboot_tmp="$CONFIG_DIR/.text_reboot.$$"
    {
        printf 'cjk=%s\n' "$_cjk"
        printf 'latin=%s\n' "$_latin"
        printf 'digit=%s\n' "$_digit"
        printf 'isolation=full-composite-v7\n'
        printf 'characterIsolation=true\n'
        printf 'composite=true\n'
        printf 'xmlOverlay=false\n'
        printf 'cacheHit=%s\n' "$COMPOSITE_CACHE_HIT"
        printf 'time=%s\n' "$(date +%s)"
    } > "$_font_tmp" 2>/dev/null || return 1
    printf 'mix\n' > "$_active_tmp" 2>/dev/null || return 1
    printf 'font=mix\ntime=%s\n' "$(date +%s)" > "$_reboot_tmp" 2>/dev/null || return 1
    MIX_CONF_TMP="$_font_tmp"; ACTIVE_CONF_TMP="$_active_tmp"; REBOOT_CONF_TMP="$_reboot_tmp"
    return 0
}

commit_mix_config() {
    mv -f "$MIX_CONF_TMP" "$MIX_CONF" 2>/dev/null || return 1
    mv -f "$ACTIVE_CONF_TMP" "$ACTIVE_FONT_CONF" 2>/dev/null || return 1
    mv -f "$REBOOT_CONF_TMP" "$TEXT_REBOOT_REQUIRED" 2>/dev/null || return 1
    printf 'time=%s\n' "$(date +%s)" > "$PAYLOAD_COMMIT_MARKER" 2>/dev/null || return 1
    chmod 0644 "$MIX_CONF" "$ACTIVE_FONT_CONF" "$TEXT_REBOOT_REQUIRED" 2>/dev/null || true
    return 0
}

apply_mix() {
    _cjk="$1"; _latin="$2"; _digit="$3"
    [ -n "$_cjk" ] && [ -n "$_latin" ] && [ -n "$_digit" ] || { set_mix_error '组合配置不完整'; return 1; }
    recover_interrupted_payload
    if [ -e "$LOCK_FILE" ]; then
        _pid=$(cat "$LOCK_FILE" 2>/dev/null)
        if [ -n "$_pid" ] && kill -0 "$_pid" 2>/dev/null; then set_mix_error '字体正在切换中'; return 2; fi
        rm -f "$LOCK_FILE" 2>/dev/null || true
    fi
    [ ! -f "$TEXT_REBOOT_REQUIRED" ] || { set_mix_error '本次开机已更改文字字体，请先重启手机'; return 3; }
    echo $$ > "$LOCK_FILE"
    trap cleanup_mix_process EXIT INT TERM

    _cjk_src=$(find_family_file "$_cjk")
    _latin_src=$(find_family_file "$_latin")
    _digit_src=$(find_family_file "$_digit")
    validate_source "$_cjk_src" 中文 || { set_mix_error "中文字体源文件不可用：${FONT_CHECK_ERROR:-找不到文件}"; return 4; }
    validate_source "$_latin_src" 英文 || { set_mix_error "英文字体源文件不可用：${FONT_CHECK_ERROR:-找不到文件}"; return 4; }
    validate_source "$_digit_src" 数字 || { set_mix_error "数字字体源文件不可用：${FONT_CHECK_ERROR:-找不到文件}"; return 4; }

    ensure_work_dir "$SYSTEM_FONTS_DIR" "字体暂存目录" || return 4
    ensure_work_dir "$CONFIG_DIR" "任务状态目录" || return 4
    ensure_work_dir "$MODDIR/logs" "日志目录" || return 4
    build_composite_file "$_cjk_src" "$_latin_src" "$_digit_src" || return 5
    payload_stage_begin || { set_mix_error '无法创建字体负载暂存区'; return 5; }
    stage_composite_source "$PAYLOAD_STAGE" "$COMPOSITE_RESULT" || {
        set_mix_error '保存组合字体源失败'; return 5;
    }
    write_fixed_source_weights "$_cjk_src" "$_latin_src" "$_digit_src" || {
        set_mix_error '记录组合源真实字重失败'; return 6;
    }
    write_mix_generation_manifest "$_cjk" "$_latin" "$_digit" || { set_mix_error '无法写入本次组合字体校验清单'; return 6; }
    prepare_mix_config "$_cjk" "$_latin" "$_digit" || { set_mix_error '无法准备字体组合状态'; return 6; }
    payload_stage_activate || { set_mix_error '无法原子替换字体负载'; return 6; }
    if ! commit_mix_config; then
        set_mix_error '无法提交字体组合状态，已恢复旧字体负载'
        return 6
    fi
    payload_stage_finalize
    chmod 0755 "$SYSTEM_FONTS_DIR" 2>/dev/null || true
    chmod 0644 "$SYSTEM_FONTS_DIR"/* 2>/dev/null || true
    rm -f "$LOCK_FILE" 2>/dev/null || true
    trap - EXIT INT TERM
    return 0
}

status_json() {
    _active=$(head -n1 "$ACTIVE_FONT_CONF" 2>/dev/null | tr -d '\r\n')
    _cjk=$(read_conf cjk '')
    _latin=$(read_conf latin '')
    _digit=$(read_conf digit '')
    _enabled=false; [ "$_active" = mix ] && _enabled=true
    printf '{"status":"ok","data":{"enabled":%s,"cjk":"%s","latin":"%s","digit":"%s"}}\n' \
        "$_enabled" "$(json_escape "$_cjk")" "$(json_escape "$_latin")" "$(json_escape "$_digit")"
}

case "${1:-status}" in
    start)
        _cjk="$2"; _latin="$3"; _digit="$4"
        if [ -z "$_cjk" ] || [ -z "$_latin" ] || [ -z "$_digit" ]; then
            printf '{"status":"error","message":"请选择中文、英文和数字字体"}\n'
            exit 0
        fi
        if [ -f "$TEXT_REBOOT_REQUIRED" ]; then
            printf '{"status":"error","message":"本次开机已更改文字字体，请先重启手机"}\n'
            exit 0
        fi
        mkdir -p "$CONFIG_DIR" "$MODDIR/logs" 2>/dev/null || true
        rotate_mix_log
        rm -f "$CONFIG_DIR/mix_last_error.txt" "$CONFIG_DIR/composite_progress.json" 2>/dev/null || true
        _task="mix-$(date +%s)-$$"; _started=$(date +%s)
        write_task "$_task" running '正在生成完整复合字体' "$_cjk" "$_latin" "$_digit" "$_started" ''
        (
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] mix start: cjk=$_cjk latin=$_latin digit=$_digit task=$_task"
            if MODDIR="$MODDIR" apply_mix "$_cjk" "$_latin" "$_digit"; then
                _finished=$(date +%s)
                _message='完整复合字体已准备，完整重启后生效'
                [ "$COMPOSITE_CACHE_HIT" = true ] && _message='已使用验证缓存准备字体组合，完整重启后生效'
                write_task "$_task" success "$_message" "$_cjk" "$_latin" "$_digit" "$_started" "$_finished"
                command -v cmd >/dev/null 2>&1 && cmd notification post -t 洛书 luoshu-mix "字体组合已准备，请完整重启手机。" >/dev/null 2>&1 || true
            else
                _rc=$?; _finished=$(date +%s)
                _failure="${LAST_MIX_ERROR:-}"
                [ -n "$_failure" ] || _failure=$(tail -n1 "$CONFIG_DIR/mix_last_error.txt" 2>/dev/null | tr -d '\r')
                [ -n "$_failure" ] || _failure="字体组合失败（阶段代码 $_rc）"
                write_task "$_task" failed "$_failure" "$_cjk" "$_latin" "$_digit" "$_started" "$_finished"
            fi
            rm -f "$CONFIG_DIR/mix_worker.pid" 2>/dev/null || true
        ) </dev/null >> "$LOG_FILE" 2>&1 &
        _bg=$!
        printf '%s\n' "$_bg" > "$CONFIG_DIR/mix_worker.pid" 2>/dev/null || true
        printf '{"status":"ok","data":{"task":"%s"}}\n' "$(json_escape "$_task")"
        ;;
    status) status_json ;;
    recover) recover_interrupted_payload; printf '{"status":"ok"}\n' ;;
    *) printf '{"status":"error","message":"未知组合命令"}\n' ;;
esac
exit 0
