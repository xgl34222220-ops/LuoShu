#!/system/bin/sh
# 洛书 v14.1：完整复合字体引擎。
# 中文字体保留为完整基底，仅把英文与数字的对应字形写入同一份字体。
# 不裁剪 ROM 字体槽、不覆盖 fonts.xml / font_fallback.xml。
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
    else
        MODDIR="/data/adb/modules/LuoShu"
    fi
fi

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
LAST_MIX_ERROR=""

[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/font_check.sh" ] && . "$MODDIR/common/font_check.sh"
[ -f "$MODDIR/common/rom_adapters.sh" ] && . "$MODDIR/common/rom_adapters.sh"
[ -f "$MODDIR/common/mount_compat.sh" ] && . "$MODDIR/common/mount_compat.sh"

type check_coloros >/dev/null 2>&1 && check_coloros
type check_hyperos >/dev/null 2>&1 && check_hyperos

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
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

all_text_targets() {
    _files=""
    type get_all_hyperos_files >/dev/null 2>&1 && _files="$_files $(get_all_hyperos_files)"
    type get_all_generic_files >/dev/null 2>&1 && _files="$_files $(get_all_generic_files)"
    if type get_all_coloros_names >/dev/null 2>&1; then
        for _name in $(get_all_coloros_names); do _files="$_files ${_name}.ttf"; done
    fi
    printf '%s\n' "$_files"
}

clear_text_targets_in_dir() {
    _dir="$1"
    [ -d "$_dir" ] || return 0
    for _file in $(all_text_targets); do rm -f "$_dir/$_file" 2>/dev/null || true; done
    rm -rf "$_dir/.luoshu-font-store" 2>/dev/null || true
}

alias_core() {
    _anchor="$1"; shift
    for _file in "$@"; do
        _font_alias "$_anchor" "$SYSTEM_FONTS_DIR/$_file" >/dev/null 2>&1 || return 1
    done
}

alias_existing_list() {
    _anchor="$1"; shift
    for _file in "$@"; do
        _rom_exact_target_exists "$_file" || continue
        _font_alias "$_anchor" "$SYSTEM_FONTS_DIR/$_file" >/dev/null 2>&1 || true
    done
}

verify_core_files() {
    _dir="$1"; shift
    for _file in "$@"; do
        [ -s "$_dir/$_file" ] || return 1
        _size=$(wc -c < "$_dir/$_file" 2>/dev/null | tr -d '[:space:]')
        case "$_size" in ''|*[!0-9]*) _size=0 ;; esac
        [ "$_size" -ge 1024 ] || return 1
    done
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
    mkdir -p "$PAYLOAD_STAGE" 2>/dev/null || return 1
    if [ -d "$SYSTEM_FONTS_DIR" ]; then
        cp -af "$SYSTEM_FONTS_DIR/." "$PAYLOAD_STAGE/" 2>/dev/null || \
            cp -rfp "$SYSTEM_FONTS_DIR/." "$PAYLOAD_STAGE/" 2>/dev/null || return 1
    fi
    clear_text_targets_in_dir "$PAYLOAD_STAGE"
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

populate_coloros_payload() (
    SYSTEM_FONTS_DIR="$1"; _composite="$2"
    _font_store_reset "$SYSTEM_FONTS_DIR" || exit 1
    _ma=$(_font_anchor "$_composite" "$SYSTEM_FONTS_DIR" mix-composite) || exit 1
    alias_core "$_ma" SysSans-Hans-Regular.ttf SysSans-Hant-Regular.ttf SysFont-Hans-Regular.ttf SysFont-Hant-Regular.ttf SysFont-Static-Regular.ttf SysFont-Regular.ttf SysSans-En-Regular.ttf Roboto-Regular.ttf GoogleSans-Regular.ttf GoogleSansText-Regular.ttf || exit 1
    alias_existing_list "$_ma" Opposans-Hans-Regular.ttf Opposans-Hans-Bold.ttf Opposans-Hans-Medium.ttf Opposans-Hans-Light.ttf SysSans-Hans-Bold.ttf SysSans-Hans-Medium.ttf SysSans-Hans-Light.ttf SysSans-Hant-Bold.ttf SysSans-Hant-Medium.ttf SysSans-Hant-Light.ttf SysFont-Hans-Bold.ttf SysFont-Hans-Medium.ttf SysFont-Hans-Light.ttf SysFont-Hant-Bold.ttf SysFont-Hant-Medium.ttf SysFont-Hant-Light.ttf SysFont-Static-Bold.ttf SysFont-Static-Medium.ttf SysFont-Static-Light.ttf SysFont-Bold.ttf SysFont-Medium.ttf SysFont-Light.ttf SysFont-Thin.ttf SysFont-Black.ttf SysSans-En-Bold.ttf SysSans-En-Medium.ttf SysSans-En-Light.ttf SysSans-En-Thin.ttf SysSans-En-Black.ttf Opposans-En-Regular.ttf Opposans-En-Bold.ttf Opposans-En-Medium.ttf Opposans-En-Light.ttf OPSans-En-Regular.ttf Roboto-Medium.ttf Roboto-Bold.ttf Roboto-Light.ttf Roboto-Thin.ttf RobotoFlex-Regular.ttf RobotoStatic-Regular.ttf GoogleSans-Medium.ttf GoogleSans-Bold.ttf GoogleSansText-Medium.ttf GoogleSansText-Bold.ttf GoogleSansFlex-Regular.ttf SourceSansPro-Regular.ttf SourceSansPro-SemiBold.ttf SourceSansPro-Bold.ttf DINCondensedBold.ttf DINPro-Regular.ttf DINPro-Medium.ttf DINPro-Bold.ttf OPPODIN-Regular.ttf OPPODIN-Medium.ttf OPPODIN-Bold.ttf OPPODINCondensed-Regular.ttf OPPODINCondensed-Medium.ttf OPPODINCondensed-Bold.ttf
    verify_core_files "$SYSTEM_FONTS_DIR" SysSans-Hans-Regular.ttf SysSans-En-Regular.ttf Roboto-Regular.ttf || exit 1
)

populate_hyperos_payload() (
    SYSTEM_FONTS_DIR="$1"; _composite="$2"
    _font_store_reset "$SYSTEM_FONTS_DIR" || exit 1
    _ma=$(_font_anchor "$_composite" "$SYSTEM_FONTS_DIR" mix-composite) || exit 1
    alias_core "$_ma" MiSansVF.ttf MiSansVF_Overlay.ttf MiSansTCVF.ttf MiSansL3.otf MiSansLatinVF.ttf Roboto-Regular.ttf GoogleSans-Regular.ttf GoogleSansText-Regular.ttf 100.ttf 200.ttf 300.ttf 350.ttf 400.ttf 500.ttf 600.ttf 700.ttf 800.ttf 900.ttf || exit 1
    alias_existing_list "$_ma" Roboto-Medium.ttf Roboto-Bold.ttf Roboto-Light.ttf Roboto-Thin.ttf RobotoFlex-Regular.ttf RobotoStatic-Regular.ttf GoogleSans-Medium.ttf GoogleSans-Bold.ttf GoogleSansText-Medium.ttf GoogleSansText-Bold.ttf GoogleSansFlex-Regular.ttf
    verify_core_files "$SYSTEM_FONTS_DIR" MiSansVF.ttf MiSansLatinVF.ttf Roboto-Regular.ttf 400.ttf 700.ttf || exit 1
)

populate_generic_payload() (
    SYSTEM_FONTS_DIR="$1"; _composite="$2"
    _font_store_reset "$SYSTEM_FONTS_DIR" || exit 1
    _ma=$(_font_anchor "$_composite" "$SYSTEM_FONTS_DIR" mix-composite) || exit 1
    alias_core "$_ma" NotoSansCJK-Regular.ttc NotoSansSC-Regular.otf NotoSansTC-Regular.otf NotoSans-Regular.ttf Roboto-Regular.ttf Roboto-Medium.ttf Roboto-Bold.ttf Roboto-Light.ttf GoogleSans-Regular.ttf GoogleSansText-Regular.ttf DroidSans.ttf || exit 1
    verify_core_files "$SYSTEM_FONTS_DIR" NotoSansCJK-Regular.ttc Roboto-Regular.ttf || exit 1
)

sync_secondary_partition() {
    _part="$1"; _real_root="$2"; _dest="$MODDIR/$_part/fonts"
    _stage="$MODDIR/.${_part}-fonts-stage.$$"; _backup="$MODDIR/.${_part}-fonts-backup.$$"
    rm -rf "$_stage" "$_backup" 2>/dev/null || true
    mkdir -p "$_stage" 2>/dev/null || return 1
    if [ -d "$_dest" ]; then
        cp -af "$_dest/." "$_stage/" 2>/dev/null || cp -rfp "$_dest/." "$_stage/" 2>/dev/null || true
    fi
    clear_text_targets_in_dir "$_stage"
    for _src in "$SYSTEM_FONTS_DIR"/*; do
        [ -f "$_src" ] || continue
        _file=$(basename "$_src")
        [ -e "$_real_root/$_file" ] || continue
        link_or_copy_font "$_src" "$_stage/$_file" 2>/dev/null || { rm -rf "$_stage"; return 1; }
    done
    mkdir -p "${_dest%/*}" 2>/dev/null || { rm -rf "$_stage"; return 1; }
    [ ! -d "$_dest" ] || mv "$_dest" "$_backup" 2>/dev/null || { rm -rf "$_stage"; return 1; }
    if mv "$_stage" "$_dest" 2>/dev/null; then
        rm -rf "$_backup" 2>/dev/null || true
        chmod -R u=rwX,go=rX "$_dest" 2>/dev/null || true
        return 0
    fi
    rm -rf "$_dest" 2>/dev/null || true
    [ ! -d "$_backup" ] || mv "$_backup" "$_dest" 2>/dev/null || true
    rm -rf "$_stage" 2>/dev/null || true
    return 1
}

sync_secondary_coloros_dirs() {
    [ "$IS_COLOROS" = "true" ] || return 0
    sync_secondary_partition system_ext /system_ext/fonts || return 1
    sync_secondary_partition product /product/fonts || return 1
    return 0
}

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
    mkdir -p "$MODDIR/cache" 2>/dev/null || { set_mix_error "无法创建运行时自检目录"; return 1; }
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
    _cache="$1"; _keep=3; _count=0
    for _old in $(ls -1t "$_cache"/*.otf 2>/dev/null); do
        _count=$((_count + 1))
        [ "$_count" -le "$_keep" ] && continue
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
    _cache="$MODDIR/cache/full-composite-v5"
    mkdir -p "$_cache" "$MODDIR/cache/tmp" 2>/dev/null || { set_mix_error '无法创建复合字体缓存目录'; return 1; }
    _key_src="$(composite_hash_file "$_cjk_src")-$(composite_hash_file "$_latin_src")-$(composite_hash_file "$_digit_src")-full-composite-v5"
    _key=$(printf '%s' "$_key_src" | { if command -v sha256sum >/dev/null 2>&1; then sha256sum; elif command -v toybox >/dev/null 2>&1; then toybox sha256sum; else cksum; fi; } | awk '{print $1}')
    _cached="$_cache/${_key}.otf"; _report="$_cache/${_key}.json"; _progress="$CONFIG_DIR/composite_progress.json"
    rm -f "$_cache"/.*.tmp.* 2>/dev/null || true
    if [ -s "$_cached" ]; then
        COMPOSITE_CACHE_HIT=true
        touch "$_cached" "$_report" 2>/dev/null || true
        write_progress cache '已验证并使用现有复合字体缓存' 100
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
    return 0
}

prepare_mix_config() {
    _cjk="$1"; _latin="$2"; _digit="$3"; _font_tmp="$CONFIG_DIR/.font_mix.$$"; _active_tmp="$CONFIG_DIR/.active_font.$$"; _reboot_tmp="$CONFIG_DIR/.text_reboot.$$"
    {
        printf 'cjk=%s\n' "$_cjk"
        printf 'latin=%s\n' "$_latin"
        printf 'digit=%s\n' "$_digit"
        printf 'isolation=full-composite-v5\n'
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

    mkdir -p "$SYSTEM_FONTS_DIR" "$CONFIG_DIR" "$MODDIR/logs" 2>/dev/null || { set_mix_error '无法创建模块工作目录'; return 4; }
    build_composite_file "$_cjk_src" "$_latin_src" "$_digit_src" || return 5
    payload_stage_begin || { set_mix_error '无法创建字体负载暂存区'; return 5; }
    if [ "$IS_HYPEROS" = "true" ]; then
        populate_hyperos_payload "$PAYLOAD_STAGE" "$COMPOSITE_RESULT" || { set_mix_error '生成 HyperOS 字体负载失败'; return 5; }
    elif [ "$IS_COLOROS" = "true" ]; then
        populate_coloros_payload "$PAYLOAD_STAGE" "$COMPOSITE_RESULT" || { set_mix_error '生成 ColorOS 字体负载失败'; return 5; }
    else
        populate_generic_payload "$PAYLOAD_STAGE" "$COMPOSITE_RESULT" || { set_mix_error '生成通用 Android 字体负载失败'; return 5; }
    fi
    prepare_mix_config "$_cjk" "$_latin" "$_digit" || { set_mix_error '无法准备字体组合状态'; return 6; }
    payload_stage_activate || { set_mix_error '无法原子替换字体负载'; return 6; }
    if ! commit_mix_config; then
        set_mix_error '无法提交字体组合状态，已恢复旧字体负载'
        return 6
    fi
    payload_stage_finalize
    chmod 0755 "$SYSTEM_FONTS_DIR" 2>/dev/null || true
    chmod 0644 "$SYSTEM_FONTS_DIR"/* 2>/dev/null || true
    if [ "$IS_COLOROS" = "true" ]; then
        sync_secondary_coloros_dirs || echo '警告：ColorOS 辅助分区字体同步未完全成功，主字体负载已保留' >&2
    fi
    type luoshu_sync_mount_payload >/dev/null 2>&1 && luoshu_sync_mount_payload 2>/dev/null || true
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
