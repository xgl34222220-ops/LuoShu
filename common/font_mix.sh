#!/system/bin/sh
# 洛书 v14：中文 / 英文 / 数字字体组合引擎。
# 通过 ROM 已有的脚本专用字体入口分别映射，不修改 fonts.xml，也不裁剪用户字体。
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

find_family_file() {
    _want="$1"
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

clear_mix_targets() {
    _files=""
    type get_all_hyperos_files >/dev/null 2>&1 && _files="$_files $(get_all_hyperos_files)"
    type get_all_generic_files >/dev/null 2>&1 && _files="$_files $(get_all_generic_files)"
    if type get_all_coloros_names >/dev/null 2>&1; then
        for _name in $(get_all_coloros_names); do _files="$_files ${_name}.ttf"; done
    fi
    for _file in $_files; do
        rm -f "$SYSTEM_FONTS_DIR/$_file" "$MODDIR/system_ext/fonts/$_file" "$MODDIR/product/fonts/$_file" 2>/dev/null || true
    done
    rm -rf "$SYSTEM_FONTS_DIR/.luoshu-font-store" 2>/dev/null || true
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

role_file() {
    _family="$1"; _role="$2"; _fallback="$3"
    _file=""
    type get_weight_file >/dev/null 2>&1 && _file=$(get_weight_file "$_family" "$_role")
    [ -f "$_file" ] || _file="$_fallback"
    printf '%s\n' "$_file"
}

role_anchor() {
    _family="$1"; _role="$2"; _fallback="$3"; _key="$4"
    _file=$(role_file "$_family" "$_role" "$_fallback")
    _font_anchor "$_file" "$SYSTEM_FONTS_DIR" "$_key"
}

apply_coloros_mix() {
    _cjk_src="$1"; _latin_src="$2"; _digit_src="$3"; _cjk_family="$4"; _latin_family="$5"; _digit_family="$6"
    _font_store_reset "$SYSTEM_FONTS_DIR"
    _cjk_anchor=$(_font_anchor "$_cjk_src" "$SYSTEM_FONTS_DIR" mix-cjk) || return 1
    if [ "$_latin_src" = "$_cjk_src" ]; then _latin_anchor="$_cjk_anchor"; else _latin_anchor=$(_font_anchor "$_latin_src" "$SYSTEM_FONTS_DIR" mix-latin) || return 1; fi
    if [ "$_digit_src" = "$_latin_src" ]; then _digit_anchor="$_latin_anchor"; elif [ "$_digit_src" = "$_cjk_src" ]; then _digit_anchor="$_cjk_anchor"; else _digit_anchor=$(_font_anchor "$_digit_src" "$SYSTEM_FONTS_DIR" mix-digit) || return 1; fi

    alias_core "$_cjk_anchor" SysSans-Hans-Regular.ttf SysSans-Hant-Regular.ttf SysFont-Hans-Regular.ttf SysFont-Hant-Regular.ttf SysFont-Static-Regular.ttf SysFont-Regular.ttf
    alias_core "$_latin_anchor" SysSans-En-Regular.ttf Roboto-Regular.ttf GoogleSans-Regular.ttf GoogleSansText-Regular.ttf
    alias_existing_list "$_cjk_anchor" Opposans-Hans-Regular.ttf Opposans-Hans-Bold.ttf Opposans-Hans-Medium.ttf Opposans-Hans-Light.ttf \
        SysSans-Hans-Bold.ttf SysSans-Hans-Medium.ttf SysSans-Hans-Light.ttf SysSans-Hant-Bold.ttf SysSans-Hant-Medium.ttf SysSans-Hant-Light.ttf \
        SysFont-Hans-Bold.ttf SysFont-Hans-Medium.ttf SysFont-Hans-Light.ttf SysFont-Hant-Bold.ttf SysFont-Hant-Medium.ttf SysFont-Hant-Light.ttf \
        SysFont-Static-Bold.ttf SysFont-Static-Medium.ttf SysFont-Static-Light.ttf SysFont-Bold.ttf SysFont-Medium.ttf SysFont-Light.ttf SysFont-Thin.ttf SysFont-Black.ttf
    alias_existing_list "$_latin_anchor" SysSans-En-Bold.ttf SysSans-En-Medium.ttf SysSans-En-Light.ttf SysSans-En-Thin.ttf SysSans-En-Black.ttf \
        Opposans-En-Regular.ttf Opposans-En-Bold.ttf Opposans-En-Medium.ttf Opposans-En-Light.ttf OPSans-En-Regular.ttf \
        Roboto-Medium.ttf Roboto-Bold.ttf Roboto-Light.ttf Roboto-Thin.ttf RobotoFlex-Regular.ttf RobotoStatic-Regular.ttf \
        GoogleSans-Medium.ttf GoogleSans-Bold.ttf GoogleSansText-Medium.ttf GoogleSansText-Bold.ttf GoogleSansFlex-Regular.ttf \
        SourceSansPro-Regular.ttf SourceSansPro-SemiBold.ttf SourceSansPro-Bold.ttf
    alias_existing_list "$_digit_anchor" DINCondensedBold.ttf DINPro-Regular.ttf DINPro-Medium.ttf DINPro-Bold.ttf \
        OPPODIN-Regular.ttf OPPODIN-Medium.ttf OPPODIN-Bold.ttf OPPODINCondensed-Regular.ttf OPPODINCondensed-Medium.ttf OPPODINCondensed-Bold.ttf

    for _role in light medium bold black; do
        case "$_role" in light) _cap=Light ;; medium) _cap=Medium ;; bold) _cap=Bold ;; black) _cap=Black ;; esac
        _a=$(role_anchor "$_cjk_family" "$_role" "$_cjk_src" "mix-cjk-$_role")
        alias_existing_list "$_a" "SysSans-Hans-${_cap}.ttf" "SysSans-Hant-${_cap}.ttf" "SysFont-Hans-${_cap}.ttf" "SysFont-Hant-${_cap}.ttf" "SysFont-Static-${_cap}.ttf" "SysFont-${_cap}.ttf" "Opposans-Hans-${_cap}.ttf"
        _a=$(role_anchor "$_latin_family" "$_role" "$_latin_src" "mix-latin-$_role")
        alias_existing_list "$_a" "SysSans-En-${_cap}.ttf" "Opposans-En-${_cap}.ttf" "Roboto-${_cap}.ttf" "GoogleSans-${_cap}.ttf" "GoogleSansText-${_cap}.ttf"
        _a=$(role_anchor "$_digit_family" "$_role" "$_digit_src" "mix-digit-$_role")
        alias_existing_list "$_a" "DINPro-${_cap}.ttf" "OPPODIN-${_cap}.ttf" "OPPODINCondensed-${_cap}.ttf"
    done
    return 0
}

apply_hyperos_mix() {
    _cjk_src="$1"; _latin_src="$2"; _digit_src="$3"; _cjk_family="$4"; _latin_family="$5"; _digit_family="$6"
    _font_store_reset "$SYSTEM_FONTS_DIR"
    _cjk_anchor=$(_font_anchor "$_cjk_src" "$SYSTEM_FONTS_DIR" mix-cjk) || return 1
    if [ "$_latin_src" = "$_cjk_src" ]; then _latin_anchor="$_cjk_anchor"; else _latin_anchor=$(_font_anchor "$_latin_src" "$SYSTEM_FONTS_DIR" mix-latin) || return 1; fi
    if [ "$_digit_src" = "$_latin_src" ]; then _digit_anchor="$_latin_anchor"; elif [ "$_digit_src" = "$_cjk_src" ]; then _digit_anchor="$_cjk_anchor"; else _digit_anchor=$(_font_anchor "$_digit_src" "$SYSTEM_FONTS_DIR" mix-digit) || return 1; fi

    alias_core "$_cjk_anchor" MiSansVF.ttf MiSansVF_Overlay.ttf MiSansTCVF.ttf MiSansL3.otf
    alias_core "$_latin_anchor" MiSansLatinVF.ttf Roboto-Regular.ttf GoogleSans-Regular.ttf GoogleSansText-Regular.ttf
    alias_existing_list "$_latin_anchor" RobotoFlex-Regular.ttf RobotoStatic-Regular.ttf GoogleSansFlex-Regular.ttf
    alias_core "$_digit_anchor" 100.ttf 200.ttf 300.ttf 350.ttf 400.ttf 500.ttf 600.ttf 700.ttf 800.ttf 900.ttf

    for _spec in 'thin:100:Thin' 'light:300:Light' 'medium:500:Medium' 'semibold:600:SemiBold' 'bold:700:Bold' 'black:900:ExtraBold'; do
        _role=${_spec%%:*}; _rest=${_spec#*:}; _num=${_rest%%:*}; _rb=${_rest#*:}
        _la=$(role_anchor "$_latin_family" "$_role" "$_latin_src" "mix-latin-$_role")
        alias_existing_list "$_la" "Roboto-${_rb}.ttf" "Roboto-${_rb}Italic.ttf" "GoogleSans-${_rb}.ttf" "GoogleSansText-${_rb}.ttf"
        _da=$(role_anchor "$_digit_family" "$_role" "$_digit_src" "mix-digit-$_role")
        _font_alias "$_da" "$SYSTEM_FONTS_DIR/${_num}.ttf" >/dev/null 2>&1 || true
    done
    return 0
}

apply_generic_mix() {
    _cjk_src="$1"; _latin_src="$2"; _digit_src="$3"
    _font_store_reset "$SYSTEM_FONTS_DIR"
    _cjk_anchor=$(_font_anchor "$_cjk_src" "$SYSTEM_FONTS_DIR" mix-cjk) || return 1
    if [ "$_latin_src" = "$_cjk_src" ]; then _latin_anchor="$_cjk_anchor"; else _latin_anchor=$(_font_anchor "$_latin_src" "$SYSTEM_FONTS_DIR" mix-latin) || return 1; fi
    alias_core "$_cjk_anchor" NotoSansCJK-Regular.ttc NotoSansSC-Regular.otf NotoSansTC-Regular.otf NotoSans-Regular.ttf
    alias_core "$_latin_anchor" Roboto-Regular.ttf Roboto-Medium.ttf Roboto-Bold.ttf Roboto-Light.ttf GoogleSans-Regular.ttf GoogleSansText-Regular.ttf DroidSans.ttf
    # 通用 AOSP 没有稳定的独立数字入口，数字会跟随英文字体。
    return 0
}

sync_secondary_coloros_dirs() {
    [ "$IS_COLOROS" = "true" ] || return 0
    mkdir -p "$MODDIR/system_ext/fonts" "$MODDIR/product/fonts" 2>/dev/null || true
    for _src in "$SYSTEM_FONTS_DIR"/*; do
        [ -f "$_src" ] || continue
        _file=$(basename "$_src")
        [ -e "/system_ext/fonts/$_file" ] && link_or_copy_font "$_src" "$MODDIR/system_ext/fonts/$_file" 2>/dev/null || true
        [ -e "/product/fonts/$_file" ] && link_or_copy_font "$_src" "$MODDIR/product/fonts/$_file" 2>/dev/null || true
    done
}

apply_mix() {
    _cjk="$1"; _latin="$2"; _digit="$3"
    [ -n "$_cjk" ] && [ -n "$_latin" ] && [ -n "$_digit" ] || { echo '错误：组合配置不完整' >&2; return 1; }
    if [ -e "$LOCK_FILE" ]; then
        _pid=$(cat "$LOCK_FILE" 2>/dev/null)
        if [ -n "$_pid" ] && kill -0 "$_pid" 2>/dev/null; then echo '错误：字体正在切换中' >&2; return 2; fi
        rm -f "$LOCK_FILE" 2>/dev/null || true
    fi
    [ ! -f "$TEXT_REBOOT_REQUIRED" ] || { echo '错误：本次开机已更改文字字体，请先重启手机' >&2; return 3; }
    echo $$ > "$LOCK_FILE"
    trap 'rm -f "$LOCK_FILE" 2>/dev/null' EXIT

    _cjk_src=$(find_family_file "$_cjk")
    _latin_src=$(find_family_file "$_latin")
    _digit_src=$(find_family_file "$_digit")
    validate_source "$_cjk_src" 中文 || return 4
    validate_source "$_latin_src" 英文 || return 4
    validate_source "$_digit_src" 数字 || return 4

    mkdir -p "$SYSTEM_FONTS_DIR" "$CONFIG_DIR" "$MODDIR/logs" 2>/dev/null || true
    clear_mix_targets
    if [ "$IS_HYPEROS" = "true" ]; then
        apply_hyperos_mix "$_cjk_src" "$_latin_src" "$_digit_src" "$_cjk" "$_latin" "$_digit" || return 5
    elif [ "$IS_COLOROS" = "true" ]; then
        apply_coloros_mix "$_cjk_src" "$_latin_src" "$_digit_src" "$_cjk" "$_latin" "$_digit" || return 5
        sync_secondary_coloros_dirs
    else
        apply_generic_mix "$_cjk_src" "$_latin_src" "$_digit_src" || return 5
    fi

    {
        printf 'cjk=%s\n' "$_cjk"
        printf 'latin=%s\n' "$_latin"
        printf 'digit=%s\n' "$_digit"
        printf 'time=%s\n' "$(date +%s)"
    } > "$MIX_CONF" 2>/dev/null || return 6
    printf 'mix\n' > "$ACTIVE_FONT_CONF" 2>/dev/null || return 6
    printf 'font=mix\ntime=%s\n' "$(date +%s)" > "$TEXT_REBOOT_REQUIRED" 2>/dev/null || return 6
    chmod 0644 "$MIX_CONF" "$ACTIVE_FONT_CONF" "$TEXT_REBOOT_REQUIRED" "$SYSTEM_FONTS_DIR"/* 2>/dev/null || true
    type luoshu_sync_mount_payload >/dev/null 2>&1 && luoshu_sync_mount_payload 2>/dev/null || true
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
        _task="mix-$(date +%s)-$$"; _started=$(date +%s)
        write_task "$_task" running '正在生成字体组合' "$_cjk" "$_latin" "$_digit" "$_started" ''
        (
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] mix start: cjk=$_cjk latin=$_latin digit=$_digit task=$_task" >> "$LOG_FILE" 2>/dev/null
            if MODDIR="$MODDIR" apply_mix "$_cjk" "$_latin" "$_digit" >> "$LOG_FILE" 2>&1; then
                _finished=$(date +%s)
                write_task "$_task" success '字体组合已准备，完整重启后生效' "$_cjk" "$_latin" "$_digit" "$_started" "$_finished"
                command -v cmd >/dev/null 2>&1 && cmd notification post -t 洛书 luoshu-mix "字体组合已准备，请完整重启手机。" >/dev/null 2>&1 || true
            else
                _rc=$?; _finished=$(date +%s)
                write_task "$_task" failed "字体组合失败（代码 $_rc）" "$_cjk" "$_latin" "$_digit" "$_started" "$_finished"
            fi
        ) &
        printf '{"status":"ok","data":{"task":"%s"}}\n' "$(json_escape "$_task")"
        ;;
    status) status_json ;;
    *) printf '{"status":"error","message":"未知组合命令"}\n' ;;
esac
exit 0
