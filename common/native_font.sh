#!/system/bin/sh
# 洛书「全局字体增强（Zygisk）」配置层。默认关闭。
#
#   native_font.sh prepare          由 zygisk/<abi>.so 的 root companion 每次开机调用一次：
#                                   把开关、排除名单和已验证生效的洛书正文字体编译成
#                                   zygisk/runtime/config.bin、faces.bin（带本次 boot_id）。
#   native_font.sh status           App 读取开关与本次开机的加载状态（一行 JSON）。
#   native_font.sh set KEY 0|1      App 写开关（KEY: enabled、verbose），重启后生效。
#
# 没有 Zygisk 时 zygisk/*.so 不会被加载，prepare 也不会被调用，本脚本对系统没有任何影响。
# 任何一步失败都只会让 Zygisk 库读不到可用配置并跳过，不改变任何进程。
set +e
MODDIR="${LUOSHU_NATIVE_FONT_MODDIR:-${MODDIR:-}}"
[ -n "$MODDIR" ] || MODDIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." 2>/dev/null && pwd)
CONF_DIR="$MODDIR/config"
CONF="$CONF_DIR/native-font.conf"
EXCLUDE="$CONF_DIR/native-font-exclude.list"
FORCE="$CONF_DIR/native-font-force.list"
LEGACY_DIR="${LUOSHU_NATIVE_FONT_LEGACY_DIR:-/data/adb/luoshu_native_font}"
ZDIR="$MODDIR/zygisk"
RUNTIME="$ZDIR/runtime"
BOOT_ID_FILE="${LUOSHU_NATIVE_FONT_BOOT_ID:-/proc/sys/kernel/random/boot_id}"

nf_conf_value() {
    sed -n "s/^$2=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n '
}

nf_bool() {
    case "$1" in 1|true|on|yes) echo 1 ;; *) echo 0 ;; esac
}

# 新配置优先；新配置不存在时只读兼容旧的独立模块路径。
nf_setting() {
    _nf_key="$1"
    if [ -f "$CONF" ]; then
        _nf_v=$(nf_conf_value "$CONF" "$_nf_key")
        case "$_nf_key" in
            java_font) [ -n "$_nf_v" ] || _nf_v=1 ;;
        esac
        nf_bool "$_nf_v"
        return 0
    fi
    case "$_nf_key" in
        enabled) [ -f "$LEGACY_DIR/enabled" ] && echo 1 || echo 0 ;;
        verbose) [ -f "$LEGACY_DIR/verbose" ] && echo 1 || echo 0 ;;
        java_font) [ -f "$LEGACY_DIR/java_font.off" ] && echo 0 || echo 1 ;;
        allow_newer_api) [ -f "$LEGACY_DIR/allow_newer_api" ] && echo 1 || echo 0 ;;
        *) echo 0 ;;
    esac
}

nf_list() {
    # $1 = new path, $2 = legacy file name
    if [ -f "$1" ]; then echo "$1"; elif [ ! -f "$CONF" ] && [ -f "$LEGACY_DIR/$2" ]; then echo "$LEGACY_DIR/$2"; fi
}

nf_abi() {
    case "${LUOSHU_NATIVE_FONT_ABI:-$(getprop ro.product.cpu.abi 2>/dev/null)}" in
        arm64-v8a) echo arm64-v8a ;;
        armeabi-v7a|armeabi) echo armeabi-v7a ;;
        x86_64) echo x86_64 ;;
        x86) echo x86 ;;
        *) echo arm64-v8a ;;
    esac
}

nf_boot_id() {
    head -n1 "$BOOT_ID_FILE" 2>/dev/null | tr -d '\r\n '
}

# 洛书当前应用且已验证的正文字体。只有主模块确认字体已生效（active_font 非 default、无待重启、
# 加载验证 verified）才写 faces.bin；否则不写，替换不安装（全部让出）。
nf_write_faces() {
    _nf_active=$(head -n1 "$CONF_DIR/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_nf_active" ] && [ "$_nf_active" != default ] || return 1
    [ ! -s "$CONF_DIR/text_reboot_required.conf" ] || return 1
    [ ! -s "$CONF_DIR/font-payload-rebuild-pending.conf" ] || return 1
    _nf_verify="$CONF_DIR/device-font-load-verification.conf"
    [ "$(nf_conf_value "$_nf_verify" state)" = verified ] || return 1
    [ "$(sed -n 's/^activeFont=//p' "$_nf_verify" 2>/dev/null | head -n1 | tr -d '\r\n')" = "$_nf_active" ] || return 1
    case "$(nf_conf_value "$_nf_verify" mode)" in
        aligned|mount-verified|mount-confirmed) ;;
        *) return 1 ;;
    esac
    set --
    for _nf_f in "$MODDIR"/system/fonts/LuoShu-[1-9][0-9][0-9]*.ttf "$MODDIR"/system/fonts/LuoShu-[1-9][0-9][0-9]*.otf; do
        [ -f "$_nf_f" ] && set -- "$@" "$_nf_f"
    done
    [ "$#" -gt 0 ] || return 1
    "$TOOL" faces --out "$RUNTIME/faces.bin" "$@"
}

nf_prepare() {
    TOOL="${LUOSHU_NATIVE_FONT_TOOL:-$ZDIR/bin/$(nf_abi)/lsnf-config}"
    OUT="$RUNTIME/config.bin"
    LOG="$RUNTIME/config.log"
    mkdir -p "$RUNTIME" || return 0
    [ -x "$TOOL" ] || chmod 0755 "$TOOL" 2>/dev/null
    rm -f "$OUT" "$RUNTIME/faces.bin" "$RUNTIME/state.conf"
    : > "$LOG.faces"
    enabled=$(nf_setting enabled)
    # 洛书模块被禁用或待删除时整体关闭。
    if [ -f "$MODDIR/disable" ] || [ -f "$MODDIR/remove" ]; then enabled=0; fi
    verbose=$(nf_setting verbose)
    java_font=$(nf_setting java_font)
    allow_newer=$(nf_setting allow_newer_api)

    if [ "$enabled" = 1 ] && [ "$java_font" = 1 ]; then
        if nf_write_faces >> "$LOG.faces" 2>&1; then chmod 0644 "$RUNTIME/faces.bin"; else rm -f "$RUNTIME/faces.bin"; fi
    fi

    set -- build --out "$OUT" --enabled "$enabled" --verbose "$verbose" --java-font "$java_font" \
        --allow-newer-api "$allow_newer"
    [ -f "$ZDIR/defaults/exclude.list" ] && set -- "$@" --exclude "$ZDIR/defaults/exclude.list"
    _nf_ex=$(nf_list "$EXCLUDE" exclude.list)
    [ -n "$_nf_ex" ] && set -- "$@" --exclude "$_nf_ex"
    _nf_fo=$(nf_list "$FORCE" force.list)
    [ -n "$_nf_fo" ] && set -- "$@" --force "$_nf_fo"

    if "$TOOL" "$@" > "$LOG" 2>&1; then
        chmod 0644 "$OUT"
    else
        rm -f "$OUT" "$RUNTIME/faces.bin"
        # 名单等出错时仍写一份关闭状态的配置，避免每个进程反复请求 companion。
        "$TOOL" build --out "$OUT" --enabled 0 --verbose 0 --java-font 0 --allow-newer-api 0 >> "$LOG" 2>&1 \
            && chmod 0644 "$OUT" || rm -f "$OUT"
        enabled=0
    fi
    _nf_faces=0
    [ -s "$RUNTIME/faces.bin" ] && _nf_faces=1
    {
        printf 'boot_id=%s\n' "$(nf_boot_id)"
        printf 'enabled=%s\n' "$enabled"
        printf 'faces=%s\n' "$_nf_faces"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$RUNTIME/state.conf.tmp" 2>/dev/null && mv -f "$RUNTIME/state.conf.tmp" "$RUNTIME/state.conf"
    chmod 0644 "$RUNTIME/state.conf" 2>/dev/null
    return 0
}

nf_json_bool() {
    [ "$1" = 1 ] && printf true || printf false
}

nf_status() {
    _nf_lib=0
    [ -f "$ZDIR/$(nf_abi).so" ] && _nf_lib=1
    _nf_loaded=0
    _nf_faces=0
    _nf_active_enabled=0
    _nf_now=$(nf_boot_id)
    if [ -n "$_nf_now" ] && [ "$(nf_conf_value "$RUNTIME/state.conf" boot_id)" = "$_nf_now" ]; then
        _nf_loaded=1
        _nf_faces=$(nf_bool "$(nf_conf_value "$RUNTIME/state.conf" faces)")
        _nf_active_enabled=$(nf_bool "$(nf_conf_value "$RUNTIME/state.conf" enabled)")
    fi
    _nf_legacy=0
    [ ! -f "$CONF" ] && [ -d "$LEGACY_DIR" ] && _nf_legacy=1
    printf '{"status":"ok","data":{"enabled":%s,"verbose":%s,"library":%s,"zygiskLoaded":%s,"activeEnabled":%s,"faces":%s,"legacyConfig":%s}}\n' \
        "$(nf_json_bool "$(nf_setting enabled)")" "$(nf_json_bool "$(nf_setting verbose)")" \
        "$(nf_json_bool "$_nf_lib")" "$(nf_json_bool "$_nf_loaded")" \
        "$(nf_json_bool "$_nf_active_enabled")" "$(nf_json_bool "$_nf_faces")" \
        "$(nf_json_bool "$_nf_legacy")"
}

nf_set() {
    _nf_key="$1"
    case "$_nf_key" in
        enabled|verbose) ;;
        *) printf '{"status":"error","message":"未知设置项"}\n'; return 0 ;;
    esac
    case "$2" in
        0|1) _nf_val="$2" ;;
        *) printf '{"status":"error","message":"设置值必须为 0 或 1"}\n'; return 0 ;;
    esac
    mkdir -p "$CONF_DIR" 2>/dev/null
    # 首次写入时把旧路径的设置一并带过来，之后只读新配置。
    _nf_enabled=$(nf_setting enabled)
    _nf_verbose=$(nf_setting verbose)
    _nf_java=$(nf_setting java_font)
    _nf_newer=$(nf_setting allow_newer_api)
    case "$_nf_key" in
        enabled) _nf_enabled="$_nf_val" ;;
        verbose) _nf_verbose="$_nf_val" ;;
    esac
    if [ ! -f "$EXCLUDE" ] && [ ! -f "$CONF" ] && [ -f "$LEGACY_DIR/exclude.list" ]; then
        cp -f "$LEGACY_DIR/exclude.list" "$EXCLUDE" 2>/dev/null && chmod 0644 "$EXCLUDE" 2>/dev/null
    fi
    if [ ! -f "$FORCE" ] && [ ! -f "$CONF" ] && [ -f "$LEGACY_DIR/force.list" ]; then
        cp -f "$LEGACY_DIR/force.list" "$FORCE" 2>/dev/null && chmod 0644 "$FORCE" 2>/dev/null
    fi
    _nf_tmp="$CONF.tmp.$$"
    {
        printf '# 洛书全局字体增强（Zygisk）。修改后重启生效。\n'
        printf 'enabled=%s\n' "$_nf_enabled"
        printf 'verbose=%s\n' "$_nf_verbose"
        printf 'java_font=%s\n' "$_nf_java"
        printf 'allow_newer_api=%s\n' "$_nf_newer"
    } > "$_nf_tmp" 2>/dev/null && mv -f "$_nf_tmp" "$CONF" 2>/dev/null || {
        rm -f "$_nf_tmp" 2>/dev/null
        printf '{"status":"error","message":"无法写入全局字体增强配置"}\n'
        return 0
    }
    chmod 0644 "$CONF" 2>/dev/null
    nf_status
}

case "${1:-}" in
    prepare) nf_prepare ;;
    status) nf_status ;;
    set) nf_set "${2:-}" "${3:-}" ;;
    *) printf '{"status":"error","message":"未知全局字体增强命令"}\n' ;;
esac
exit 0
