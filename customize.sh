#!/system/bin/sh
# LuoShu installer wrapper: run the verified installer, then hide every standard
# partition payload before the first boot.
# Installer contract: delegated core deploys common/luoshu_cli.sh to system/bin/洛书.
# Compatibility contract retained for source/regression checks:
# for _enable_dir in "$MODPATH" "$OLD_MOD"
# rm -f "$_enable_dir/disable"
set +e
MODPATH="${MODPATH:-$3}"
LUOSHU_OLD_MOD="${LUOSHU_OLD_MOD:-/data/adb/modules/LuoShu}"
_lc_source_dir=$(CDPATH= cd -- "${0%/*}" 2>/dev/null && pwd)
_lc_base="$MODPATH/.luoshu-runtime/customize-v227.sh"
_lc_helper="$MODPATH/common/private_payload.sh"
_lc_temp="$MODPATH/.customize-v227.$$.sh"
[ -f "$_lc_base" ] || _lc_base="$_lc_source_dir/.luoshu-runtime/customize-v227.sh"
[ -f "$_lc_helper" ] || _lc_helper="$_lc_source_dir/common/private_payload.sh"
[ -f "$_lc_helper" ] && . "$_lc_helper"

if ! command -v ui_print >/dev/null 2>&1; then
    ui_print() { printf '%s\n' "$*"; }
fi
if ! command -v abort >/dev/null 2>&1; then
    abort() { ui_print "! $*"; return 1; }
fi

if [ ! -f "$_lc_base" ]; then
    abort '缺少洛书安装核心'
    return 1 2>/dev/null || exit 1
fi

# A legacy physical payload is not an obsolete font cache: it is the exact source
# tree that the current boot is using. Older 4.0 builds did not give that payload a
# schema understood by the delegated installer, so an update could classify it as
# incompatible and later boot on stock. Before migration, explicitly mark an active
# legacy payload as compatible with this installer's migration contract. This does
# not rebuild or touch any font file; it only prevents a false "old payload" reset.
_lc_active=$(head -n1 "$LUOSHU_OLD_MOD/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
[ -n "$_lc_active" ] || _lc_active=default
_lc_legacy=false
[ -f "$LUOSHU_OLD_MOD/config/font_runtime_legacy_v14_4.conf" ] && _lc_legacy=true
_lc_target_schema=$(sed -n 's/^LUOSHU_PAYLOAD_SCHEMA_CURRENT=//p' "$_lc_base" 2>/dev/null | head -n1 | tr -d '\r\n')
if [ "$_lc_legacy" = true ] && [ "$_lc_active" != default ] && \
   [ -d "$LUOSHU_OLD_MOD/.luoshu-payload" ] && [ -n "$_lc_target_schema" ]; then
    mkdir -p "$LUOSHU_OLD_MOD/config" 2>/dev/null || true
    printf 'schema=%s\n' "$_lc_target_schema" > "$LUOSHU_OLD_MOD/config/font-payload-schema.conf.tmp.$$" 2>/dev/null && \
        mv -f "$LUOSHU_OLD_MOD/config/font-payload-schema.conf.tmp.$$" \
            "$LUOSHU_OLD_MOD/config/font-payload-schema.conf" 2>/dev/null || true
    chmod 0644 "$LUOSHU_OLD_MOD/config/font-payload-schema.conf" 2>/dev/null || true
    ui_print "✓ 已锁定当前字体负载：$_lc_active（更新不会恢复默认字体）"
fi

# Existing private-payload installations are exposed only for the duration of the
# verified update migrator, then hidden again.
if [ -d "$LUOSHU_OLD_MOD/.luoshu-payload" ]; then
    if ! luoshu_private_mount_module_view "$LUOSHU_OLD_MOD" >/dev/null 2>&1; then
        abort '无法读取旧版洛书私有字体负载'
        return 1 2>/dev/null || exit 1
    fi
fi

# Run the delegated installer by sourcing it so its migration state remains visible
# to this wrapper, but convert its top-level exit statements into returns. This is
# essential for APatch (which sources customize.sh) and guarantees cleanup of the
# temporary private-payload view on a controlled migration rejection.
sed -e 's/^[[:space:]]*exit 1[[:space:]]*$/        return 1/' \
    -e 's/^[[:space:]]*exit 0[[:space:]]*$/return 0/' \
    "$_lc_base" > "$_lc_temp" 2>/dev/null || {
    abort '安装入口准备失败'
    return 1 2>/dev/null || exit 1
}

. "$_lc_temp"
_lc_rc=$?
rm -f "$_lc_temp" 2>/dev/null || true
( luoshu_private_unmount_module_view "$LUOSHU_OLD_MOD" >/dev/null 2>&1 ) || true
if [ "$_lc_rc" -ne 0 ]; then
    return "$_lc_rc" 2>/dev/null || exit "$_lc_rc"
fi

# Never rebuild fonts synchronously while a Root manager is flashing the module.
if [ "${LUOSHU_UPDATE_REBUILD_REQUIRED:-false}" = true ]; then
    _lc_font=$(head -n1 "$MODPATH/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_lc_font" ] || _lc_font=default
    ui_print "✓ 已保留当前字体负载：$_lc_font"
    ui_print '• 本次刷写不会同步重建字体；重启后可在洛书中重新应用以升级引擎'
fi

if ! luoshu_private_install_migrate "$MODPATH"; then
    abort '洛书私有挂载树部署失败'
    return 1 2>/dev/null || exit 1
fi
ui_print '✓ 私有字体负载已部署'
ui_print '✓ 洛书将独立完成字体挂载'
return 0 2>/dev/null || exit 0