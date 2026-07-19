#!/system/bin/sh
# 洛书 Full 模块内置 App 安装器。
# customize.sh、service.sh 与 action.sh 共用同一套版本判断和覆盖安装逻辑。
set +e

MODDIR="${MODDIR:-$(CDPATH= cd -- "$(dirname -- "$0")/.." 2>/dev/null && pwd)}"
APK="$MODDIR/bundled/LuoShu-App.apk"
META="$MODDIR/bundled/app.prop"
PENDING="$MODDIR/config/app_install_pending"
STATE="$MODDIR/config/app_install_state.conf"
LOG="${APP_INSTALL_LOG:-$MODDIR/logs/app-install.log}"
MODE="${1:-auto}"

mkdir -p "$MODDIR/config" "$MODDIR/logs" 2>/dev/null || true

log_app() {
    _level="$1"
    shift
    _message="$*"
    _time=$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)
    printf '[%s] [APP-INSTALL] [%s] %s\n' "$_time" "$_level" "$_message" >> "$LOG" 2>/dev/null || true
}

read_prop() {
    _key="$1"
    _file="$2"
    sed -n "s/^${_key}=//p" "$_file" 2>/dev/null | head -n1
}

resolve_tool() {
    _override="$1"
    _name="$2"
    if [ -n "$_override" ]; then
        [ -x "$_override" ] && printf '%s\n' "$_override"
        return
    fi
    command -v "$_name" 2>/dev/null
}

write_state() {
    _status="$1"
    _detail="$2"
    {
        printf 'status=%s\n' "$_status"
        printf 'package=%s\n' "$APP_PACKAGE"
        printf 'versionCode=%s\n' "$APP_VERSION_CODE"
        printf 'apkSha256=%s\n' "$APK_SHA256"
        printf 'mode=%s\n' "$MODE"
        printf 'detail=%s\n' "$_detail" | tr '\n' ' '
        printf 'updatedAt=%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z' 2>/dev/null || echo unknown)"
    } > "$STATE" 2>/dev/null || true
}

if [ ! -s "$APK" ]; then
    rm -f "$PENDING" 2>/dev/null || true
    log_app INFO "当前模块不内置 App，跳过安装"
    printf 'not-bundled\n'
    exit 20
fi

APP_PACKAGE=$(read_prop package "$META")
APP_VERSION_CODE=$(read_prop versionCode "$META")
APK_SHA256=$(read_prop sha256 "$META")

[ -n "$APP_PACKAGE" ] || APP_PACKAGE="io.github.xgl34222220.luoshu.debug"
case "$APP_PACKAGE" in
    io.github.xgl34222220.luoshu|io.github.xgl34222220.luoshu.debug) ;;
    *)
        log_app ERROR "拒绝安装未知包名：$APP_PACKAGE"
        touch "$PENDING" 2>/dev/null || true
        printf 'invalid-package\n'
        exit 21
        ;;
esac

case "$APP_VERSION_CODE" in
    ''|*[!0-9]*)
        _module_code=$(read_prop versionCode "$MODDIR/module.prop")
        case "$_module_code" in ''|*[!0-9]*) _module_code=0 ;; esac
        APP_VERSION_CODE=$((_module_code * 100 + 1))
        ;;
esac

if [ -z "$APK_SHA256" ]; then
    if command -v sha256sum >/dev/null 2>&1; then
        APK_SHA256=$(sha256sum "$APK" 2>/dev/null | awk '{print $1}')
    else
        APK_SHA256="unknown"
    fi
fi

PM_BIN=$(resolve_tool "${APP_INSTALL_PM_BIN:-}" pm)
DUMPSYS_BIN=$(resolve_tool "${APP_INSTALL_DUMPSYS_BIN:-}" dumpsys)
TIMEOUT_BIN=$(resolve_tool "${APP_INSTALL_TIMEOUT_BIN:-}" timeout)

installed_version_code() {
    _dump=""
    if [ -n "$DUMPSYS_BIN" ]; then
        _dump=$($DUMPSYS_BIN package "$APP_PACKAGE" 2>/dev/null)
    fi
    if [ -z "$_dump" ] && [ -n "$PM_BIN" ]; then
        _dump=$($PM_BIN dump "$APP_PACKAGE" 2>/dev/null)
    fi
    printf '%s\n' "$_dump" | sed -n 's/.*versionCode=\([0-9][0-9]*\).*/\1/p' | head -n1
}

INSTALLED_VERSION=$(installed_version_code)
if [ "$INSTALLED_VERSION" = "$APP_VERSION_CODE" ]; then
    rm -f "$PENDING" 2>/dev/null || true
    write_state up_to_date "已安装版本与模块内置 App 一致"
    log_app INFO "$APP_PACKAGE 已是目标版本 $APP_VERSION_CODE，跳过覆盖安装"
    printf 'already-current\n'
    exit 0
fi

if [ -z "$PM_BIN" ]; then
    touch "$PENDING" 2>/dev/null || true
    write_state deferred "当前环境无法调用 Android 包管理器"
    log_app INFO "pm 不可用，已安排首次开机补装 $APP_PACKAGE"
    printf 'deferred\n'
    exit 10
fi

log_app INFO "开始覆盖安装 $APP_PACKAGE，目标版本 $APP_VERSION_CODE，当前版本 ${INSTALLED_VERSION:-未安装}"
if [ -n "$TIMEOUT_BIN" ]; then
    INSTALL_RESULT=$($TIMEOUT_BIN 60 "$PM_BIN" install -r -d --user 0 "$APK" 2>&1)
    INSTALL_CODE=$?
else
    INSTALL_RESULT=$($PM_BIN install -r -d --user 0 "$APK" 2>&1)
    INSTALL_CODE=$?
fi

printf '%s\n' "$INSTALL_RESULT" >> "$LOG" 2>/dev/null || true
if [ "$INSTALL_CODE" -eq 0 ] && printf '%s' "$INSTALL_RESULT" | grep -q 'Success'; then
    rm -f "$PENDING" 2>/dev/null || true
    write_state installed "覆盖安装成功"
    log_app INFO "洛书 App 已安装或更新到 $APP_VERSION_CODE"
    printf 'installed\n'
    exit 0
fi

touch "$PENDING" 2>/dev/null || true
write_state failed "${INSTALL_RESULT:-安装命令失败}"
log_app ERROR "App 安装失败，保留首次开机重试标记"
printf 'failed\n'
exit 11
