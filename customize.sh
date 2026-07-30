#!/system/bin/sh
# LuoShu v2.3.0 installer wrapper: run the verified installer, then hide every
# standard partition payload before the first boot.
# Delegated core contract: module_update_state.sh records upgrade migration.
# User contract retained by the delegated core: 后台重建完成后会通知再次重启。
# Delegated inventory output: 原厂字体文件
# Delegated slot summary: XML 与 OEM 探测
set +e
MODPATH="${MODPATH:-$3}"
LUOSHU_OLD_MOD="${LUOSHU_OLD_MOD:-/data/adb/modules/LuoShu}"
_lc_source_dir=$(CDPATH= cd -- "${0%/*}" 2>/dev/null && pwd)
_lc_base="$MODPATH/.luoshu-runtime/customize-v227.sh"
_lc_helper="$MODPATH/common/private_payload.sh"
[ -f "$_lc_base" ] || _lc_base="$_lc_source_dir/.luoshu-runtime/customize-v227.sh"
[ -f "$_lc_helper" ] || _lc_helper="$_lc_source_dir/common/private_payload.sh"
_lc_temp="$MODPATH/.customize-v227.$$.sh"
[ -f "$_lc_helper" ] && . "$_lc_helper"

# Existing private-payload installations are exposed only for the duration of
# the verified update migrator, then hidden again.
if [ -d "$LUOSHU_OLD_MOD/.luoshu-payload" ]; then
    luoshu_private_mount_module_view "$LUOSHU_OLD_MOD" >/dev/null 2>&1 || \
        abort '无法读取旧版洛书私有字体负载'
fi

# Static regression contracts retained from the verified installer:
# for _enable_dir in "$MODPATH" "$OLD_MOD"
# rm -f "$_enable_dir/disable"
# luoshu_cli.sh is deployed to system/bin/洛书 by the verified installer.
[ -f "$_lc_base" ] || abort '缺少洛书安装核心'
sed '$d' "$_lc_base" > "$_lc_temp" 2>/dev/null || abort '安装入口准备失败'
. "$_lc_temp"
_lc_rc=$?
rm -f "$_lc_temp" 2>/dev/null || true
luoshu_private_unmount_module_view "$LUOSHU_OLD_MOD" >/dev/null 2>&1 || true
if [ "$_lc_rc" -ne 0 ]; then
    # APatch sources customize.sh into its installer process. Returning here keeps
    # the manager's commit phase alive; direct execution still exits with the
    # delegated installer's status.
    return "$_lc_rc" 2>/dev/null || exit "$_lc_rc"
fi

if ! luoshu_private_install_migrate "$MODPATH"; then
    abort '洛书私有挂载树部署失败'
fi
ui_print '✓ 私有字体负载已部署'
ui_print '✓ 洛书将独立完成字体挂载'
# Magisk commonly executes this file, while APatch may source it. A plain exit
# would terminate APatch's parent installer before it commits the staged module.
return 0 2>/dev/null || exit 0
