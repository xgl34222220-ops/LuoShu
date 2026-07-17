#!/system/bin/sh
# 洛书 v14.1：中文 / 英文 / 数字事务式字体组合引擎。
set +e
MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"; else MODDIR="/data/adb/modules/LuoShu"; fi
fi
CONFIG_DIR="$MODDIR/config"
USER_FONTS_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts"
TASK_FILE="$CONFIG_DIR/mix_task.conf"
MIX_CONF="$CONFIG_DIR/font_mix.conf"
ACTIVE_FONT_CONF="$CONFIG_DIR/active_font.conf"
TEXT_REBOOT_REQUIRED="$CONFIG_DIR/text_reboot_required.conf"
LOCK_FILE="$MODDIR/.font_switch.lock"
LOG_FILE="$MODDIR/logs/fontswitch.log"
for _lib in util_functions.sh font_check.sh rom_adapters.sh mount_compat.sh font_transaction.sh; do [ -f "$MODDIR/common/$_lib" ] && . "$MODDIR/common/$_lib"; done
type check_coloros >/dev/null 2>&1 && check_coloros
type check_hyperos >/dev/null 2>&1 && check_hyperos

json_escape(){ printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '; }
read_conf(){ _v=$(sed -n "s/^${1}=//p" "$MIX_CONF" 2>/dev/null | head -n1 | tr -d '\r\n'); [ -n "$_v" ] || _v="$2"; printf '%s' "$_v"; }
write_task(){
    _task="$1"; _state="$2"; _message="$3"; _cjk="$4"; _latin="$5"; _digit="$6"; _started="$7"; _finished="$8"; _tmp="$TASK_FILE.tmp.$$"
    mkdir -p "$CONFIG_DIR" 2>/dev/null || true
    {
        printf 'task=%s\n' "$_task"; printf 'state=%s\n' "$_state"; printf 'message=%s\n' "$_message"
        printf 'cjk=%s\n' "$_cjk"; printf 'latin=%s\n' "$_latin"; printf 'digit=%s\n' "$_digit"
        printf 'started=%s\n' "$_started"; printf 'finished=%s\n' "$_finished"
    } > "$_tmp" 2>/dev/null && mv -f "$_tmp" "$TASK_FILE" 2>/dev/null
    chmod 0644 "$TASK_FILE" 2>/dev/null || true
}
find_family_file(){
    _want="$1"
    for _f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
              "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_f" ] || continue
        [ "$(detect_font_family "$(basename "$_f")")" = "$_want" ] && { printf '%s\n' "$_f"; return 0; }
    done
    return 1
}
validate_source(){
    [ -f "$1" ] || { echo "错误：找不到$2字体" >&2; return 1; }
    if type font_validate >/dev/null 2>&1 && ! font_validate "$1" text; then echo "错误：$2字体无效：$FONT_CHECK_ERROR" >&2; return 1; fi
}
alias_core(){ _anchor="$1"; shift; for _file in "$@"; do _font_alias "$_anchor" "$LUOSHU_TXN_FONTS/$_file" >/dev/null 2>&1 || return 1; done; }
alias_existing(){ _anchor="$1"; shift; for _file in "$@"; do _rom_exact_target_exists "$_file" || continue; _font_alias "$_anchor" "$LUOSHU_TXN_FONTS/$_file" >/dev/null 2>&1 || true; done; }
role_anchor(){ _family="$1"; _role="$2"; _fallback="$3"; _key="$4"; _file=""; type get_weight_file >/dev/null 2>&1 && _file=$(get_weight_file "$_family" "$_role"); [ -f "$_file" ] || _file="$_fallback"; _font_anchor "$_file" "$LUOSHU_TXN_FONTS" "$_key"; }

apply_coloros_mix(){
    _cjk_src="$1"; _latin_src="$2"; _digit_src="$3"; _cjk_family="$4"; _latin_family="$5"; _digit_family="$6"
    _font_store_reset "$LUOSHU_TXN_FONTS"
    _ca=$(_font_anchor "$_cjk_src" "$LUOSHU_TXN_FONTS" mix-cjk) || return 1
    [ "$_latin_src" = "$_cjk_src" ] && _la="$_ca" || _la=$(_font_anchor "$_latin_src" "$LUOSHU_TXN_FONTS" mix-latin) || return 1
    if [ "$_digit_src" = "$_latin_src" ]; then _da="$_la"; elif [ "$_digit_src" = "$_cjk_src" ]; then _da="$_ca"; else _da=$(_font_anchor "$_digit_src" "$LUOSHU_TXN_FONTS" mix-digit) || return 1; fi
    alias_core "$_ca" SysSans-Hans-Regular.ttf SysSans-Hant-Regular.ttf SysFont-Hans-Regular.ttf SysFont-Hant-Regular.ttf SysFont-Static-Regular.ttf SysFont-Regular.ttf || return 1
    alias_core "$_la" SysSans-En-Regular.ttf Roboto-Regular.ttf GoogleSans-Regular.ttf GoogleSansText-Regular.ttf || return 1
    alias_existing "$_ca" Opposans-Hans-Regular.ttf SysSans-Hans-Bold.ttf SysSans-Hans-Medium.ttf SysSans-Hans-Light.ttf SysSans-Hant-Bold.ttf SysSans-Hant-Medium.ttf SysSans-Hant-Light.ttf SysFont-Hans-Bold.ttf SysFont-Hans-Medium.ttf SysFont-Hans-Light.ttf SysFont-Hant-Bold.ttf SysFont-Hant-Medium.ttf SysFont-Hant-Light.ttf SysFont-Static-Bold.ttf SysFont-Static-Medium.ttf SysFont-Static-Light.ttf SysFont-Bold.ttf SysFont-Medium.ttf SysFont-Light.ttf SysFont-Thin.ttf SysFont-Black.ttf
    alias_existing "$_la" SysSans-En-Bold.ttf SysSans-En-Medium.ttf SysSans-En-Light.ttf SysSans-En-Thin.ttf SysSans-En-Black.ttf Opposans-En-Regular.ttf Opposans-En-Bold.ttf Opposans-En-Medium.ttf Opposans-En-Light.ttf OPSans-En-Regular.ttf Roboto-Medium.ttf Roboto-Bold.ttf Roboto-Light.ttf Roboto-Thin.ttf RobotoFlex-Regular.ttf RobotoStatic-Regular.ttf GoogleSans-Medium.ttf GoogleSans-Bold.ttf GoogleSansText-Medium.ttf GoogleSansText-Bold.ttf GoogleSansFlex-Regular.ttf SourceSansPro-Regular.ttf SourceSansPro-SemiBold.ttf SourceSansPro-Bold.ttf
    alias_existing "$_da" DINCondensedBold.ttf DINPro-Regular.ttf DINPro-Medium.ttf DINPro-Bold.ttf OPPODIN-Regular.ttf OPPODIN-Medium.ttf OPPODIN-Bold.ttf OPPODINCondensed-Regular.ttf OPPODINCondensed-Medium.ttf OPPODINCondensed-Bold.ttf
    for _spec in light:Light medium:Medium bold:Bold black:Black; do
        _role=${_spec%%:*}; _cap=${_spec#*:}
        _a=$(role_anchor "$_cjk_family" "$_role" "$_cjk_src" "mix-cjk-$_role"); alias_existing "$_a" "SysSans-Hans-${_cap}.ttf" "SysSans-Hant-${_cap}.ttf" "SysFont-Hans-${_cap}.ttf" "SysFont-Hant-${_cap}.ttf" "SysFont-Static-${_cap}.ttf" "SysFont-${_cap}.ttf"
        _a=$(role_anchor "$_latin_family" "$_role" "$_latin_src" "mix-latin-$_role"); alias_existing "$_a" "SysSans-En-${_cap}.ttf" "Roboto-${_cap}.ttf" "GoogleSans-${_cap}.ttf" "GoogleSansText-${_cap}.ttf"
        _a=$(role_anchor "$_digit_family" "$_role" "$_digit_src" "mix-digit-$_role"); alias_existing "$_a" "DINPro-${_cap}.ttf" "OPPODIN-${_cap}.ttf" "OPPODINCondensed-${_cap}.ttf"
    done
}

apply_hyperos_mix(){
    _cjk_src="$1"; _latin_src="$2"; _digit_src="$3"; _latin_family="$5"; _digit_family="$6"
    _font_store_reset "$LUOSHU_TXN_FONTS"
    _ca=$(_font_anchor "$_cjk_src" "$LUOSHU_TXN_FONTS" mix-cjk) || return 1
    [ "$_latin_src" = "$_cjk_src" ] && _la="$_ca" || _la=$(_font_anchor "$_latin_src" "$LUOSHU_TXN_FONTS" mix-latin) || return 1
    if [ "$_digit_src" = "$_latin_src" ]; then _da="$_la"; elif [ "$_digit_src" = "$_cjk_src" ]; then _da="$_ca"; else _da=$(_font_anchor "$_digit_src" "$LUOSHU_TXN_FONTS" mix-digit) || return 1; fi
    alias_core "$_ca" MiSansVF.ttf MiSansVF_Overlay.ttf MiSansTCVF.ttf MiSansL3.otf || return 1
    alias_core "$_la" MiSansLatinVF.ttf Roboto-Regular.ttf GoogleSans-Regular.ttf GoogleSansText-Regular.ttf || return 1
    alias_existing "$_la" RobotoFlex-Regular.ttf RobotoStatic-Regular.ttf GoogleSansFlex-Regular.ttf
    alias_core "$_da" 100.ttf 200.ttf 300.ttf 350.ttf 400.ttf 500.ttf 600.ttf 700.ttf 800.ttf 900.ttf || return 1
    for _spec in thin:100:Thin light:300:Light medium:500:Medium semibold:600:SemiBold bold:700:Bold black:900:ExtraBold; do
        _role=${_spec%%:*}; _rest=${_spec#*:}; _num=${_rest%%:*}; _cap=${_rest#*:}
        _a=$(role_anchor "$_latin_family" "$_role" "$_latin_src" "mix-latin-$_role"); alias_existing "$_a" "Roboto-${_cap}.ttf" "Roboto-${_cap}Italic.ttf" "GoogleSans-${_cap}.ttf" "GoogleSansText-${_cap}.ttf"
        _a=$(role_anchor "$_digit_family" "$_role" "$_digit_src" "mix-digit-$_role"); _font_alias "$_a" "$LUOSHU_TXN_FONTS/${_num}.ttf" >/dev/null 2>&1 || true
    done
}

apply_generic_mix(){
    _cjk_src="$1"; _latin_src="$2"
    _font_store_reset "$LUOSHU_TXN_FONTS"
    _ca=$(_font_anchor "$_cjk_src" "$LUOSHU_TXN_FONTS" mix-cjk) || return 1
    [ "$_latin_src" = "$_cjk_src" ] && _la="$_ca" || _la=$(_font_anchor "$_latin_src" "$LUOSHU_TXN_FONTS" mix-latin) || return 1
    alias_core "$_ca" NotoSansCJK-Regular.ttc NotoSansSC-Regular.otf NotoSansTC-Regular.otf NotoSans-Regular.ttf || return 1
    alias_core "$_la" Roboto-Regular.ttf Roboto-Medium.ttf Roboto-Bold.ttf Roboto-Light.ttf GoogleSans-Regular.ttf GoogleSansText-Regular.ttf DroidSans.ttf || return 1
}

sync_coloros_secondary(){
    [ "${IS_COLOROS:-false}" = true ] || return 0
    mkdir -p "$MODDIR/system_ext/fonts" "$MODDIR/product/fonts" 2>/dev/null || true
    for _src in "$MODDIR/system/fonts"/*; do
        [ -f "$_src" ] || continue; _file=$(basename "$_src")
        [ -e "/system_ext/fonts/$_file" ] && link_or_copy_font "$_src" "$MODDIR/system_ext/fonts/$_file" 2>/dev/null || true
        [ -e "/product/fonts/$_file" ] && link_or_copy_font "$_src" "$MODDIR/product/fonts/$_file" 2>/dev/null || true
    done
}

apply_mix(){
    _cjk="$1"; _latin="$2"; _digit="$3"
    [ -n "$_cjk" ] && [ -n "$_latin" ] && [ -n "$_digit" ] || { echo '错误：组合配置不完整' >&2; return 1; }
    if [ -e "$LOCK_FILE" ]; then _pid=$(cat "$LOCK_FILE" 2>/dev/null); [ -n "$_pid" ] && kill -0 "$_pid" 2>/dev/null && { echo '错误：字体正在切换中' >&2; return 2; }; rm -f "$LOCK_FILE" 2>/dev/null || true; fi
    [ ! -f "$TEXT_REBOOT_REQUIRED" ] || { echo '错误：本次开机已更改文字字体，请先重启手机' >&2; return 3; }
    echo $$ > "$LOCK_FILE"; trap 'rm -f "$LOCK_FILE" 2>/dev/null; luoshu_txn_abort' EXIT HUP INT TERM
    _cjk_src=$(find_family_file "$_cjk"); _latin_src=$(find_family_file "$_latin"); _digit_src=$(find_family_file "$_digit")
    validate_source "$_cjk_src" 中文 || return 4; validate_source "$_latin_src" 英文 || return 4; validate_source "$_digit_src" 数字 || return 4
    luoshu_txn_begin mix || return 5
    if [ "${IS_HYPEROS:-false}" = true ]; then apply_hyperos_mix "$_cjk_src" "$_latin_src" "$_digit_src" "$_cjk" "$_latin" "$_digit" || return 5
    elif [ "${IS_COLOROS:-false}" = true ]; then apply_coloros_mix "$_cjk_src" "$_latin_src" "$_digit_src" "$_cjk" "$_latin" "$_digit" || return 5
    else apply_generic_mix "$_cjk_src" "$_latin_src" || return 5; fi
    luoshu_txn_verify mix || return 6
    luoshu_txn_commit || { echo '错误：无法提交字体组合，原配置已保留' >&2; return 7; }
    sync_coloros_secondary
    mkdir -p "$CONFIG_DIR" 2>/dev/null || true
    { printf 'cjk=%s\n' "$_cjk"; printf 'latin=%s\n' "$_latin"; printf 'digit=%s\n' "$_digit"; printf 'time=%s\n' "$(date +%s)"; } > "$MIX_CONF" 2>/dev/null || return 8
    printf 'mix\n' > "$ACTIVE_FONT_CONF" 2>/dev/null || return 8
    printf 'font=mix\ntime=%s\n' "$(date +%s)" > "$TEXT_REBOOT_REQUIRED" 2>/dev/null || return 8
    chmod 0644 "$MIX_CONF" "$ACTIVE_FONT_CONF" "$TEXT_REBOOT_REQUIRED" 2>/dev/null || true
    type luoshu_sync_mount_payload >/dev/null 2>&1 && luoshu_sync_mount_payload 2>/dev/null || true
    rm -f "$LOCK_FILE" 2>/dev/null || true; trap - EXIT HUP INT TERM
}

status_json(){ _active=$(head -n1 "$ACTIVE_FONT_CONF" 2>/dev/null | tr -d '\r\n'); _enabled=false; [ "$_active" = mix ] && _enabled=true; printf '{"status":"ok","data":{"enabled":%s,"cjk":"%s","latin":"%s","digit":"%s"}}\n' "$_enabled" "$(json_escape "$(read_conf cjk '')")" "$(json_escape "$(read_conf latin '')")" "$(json_escape "$(read_conf digit '')")"; }
case "${1:-status}" in
    start)
        _cjk="$2"; _latin="$3"; _digit="$4"
        [ -n "$_cjk" ] && [ -n "$_latin" ] && [ -n "$_digit" ] || { printf '{"status":"error","message":"请选择中文、英文和数字字体"}\n'; exit 0; }
        [ ! -f "$TEXT_REBOOT_REQUIRED" ] || { printf '{"status":"error","message":"本次开机已更改文字字体，请先重启手机"}\n'; exit 0; }
        mkdir -p "$CONFIG_DIR" "$MODDIR/logs" 2>/dev/null || true
        _task="mix-$(date +%s)-$$"; _started=$(date +%s); write_task "$_task" running '正在安全生成字体组合' "$_cjk" "$_latin" "$_digit" "$_started" ''
        (
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] v14.1 mix start: cjk=$_cjk latin=$_latin digit=$_digit task=$_task" >> "$LOG_FILE" 2>/dev/null
            if MODDIR="$MODDIR" apply_mix "$_cjk" "$_latin" "$_digit" >> "$LOG_FILE" 2>&1; then
                write_task "$_task" success '字体组合已准备，完整重启后生效' "$_cjk" "$_latin" "$_digit" "$_started" "$(date +%s)"
                command -v cmd >/dev/null 2>&1 && cmd notification post -t 洛书 luoshu-mix "字体组合已准备，请完整重启手机。" >/dev/null 2>&1 || true
            else _rc=$?; write_task "$_task" failed "字体组合失败（代码 $_rc），原字体配置未被破坏" "$_cjk" "$_latin" "$_digit" "$_started" "$(date +%s)"; fi
        ) &
        printf '{"status":"ok","data":{"task":"%s"}}\n' "$(json_escape "$_task")"
        ;;
    apply) apply_mix "$2" "$3" "$4" ;;
    status) status_json ;;
    *) printf '{"status":"error","message":"未知组合命令"}\n' ;;
esac
exit 0
