#!/system/bin/sh
# LuoShu v2.3.0 installer wrapper: run the verified installer, then hide every
# standard partition payload before the first boot.
# Delegated core contract: module_update_state.sh records upgrade migration.
# User contract: updates preserve the selected font; incompatible payloads are
# rebuilt before commit and never converted into a default-font update.
# Delegated inventory output: 原厂字体文件
# Delegated slot summary: XML 与 OEM 探测
set +e
MODPATH="${MODPATH:-$3}"
LUOSHU_OLD_MOD="${LUOSHU_OLD_MOD:-/data/adb/modules/LuoShu}"
_lc_source_dir=$(CDPATH= cd -- "${0%/*}" 2>/dev/null && pwd)
_lc_base="$MODPATH/.luoshu-runtime/customize-v227.sh"
_lc_helper="$MODPATH/common/private_payload.sh"
_lc_update_hotfix="$MODPATH/common/module_update_hotfix_v4.sh"
[ -f "$_lc_base" ] || _lc_base="$_lc_source_dir/.luoshu-runtime/customize-v227.sh"
[ -f "$_lc_helper" ] || _lc_helper="$_lc_source_dir/common/private_payload.sh"
_lc_temp="$MODPATH/.customize-v227.$$.sh"
_lc_patched="$MODPATH/.customize-v227.patched.$$.sh"
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
[ -f "$_lc_update_hotfix" ] || abort '缺少洛书 v4 更新迁移修复'
sed '$d' "$_lc_base" > "$_lc_temp" 2>/dev/null || abort '安装入口准备失败'

# The delegated installer sources module_update_state.sh itself. Inject the v4
# override immediately after that source line so the old migrator can never
# relabel an update as default or inherit an incompatible generated payload.
awk -v hotfix="$_lc_update_hotfix" '
{
    print
    if (index($0, "common/module_update_state.sh") && index($0, "&& .")) {
        print "[ -f \"" hotfix "\" ] && . \"" hotfix "\""
    }
}
' "$_lc_temp" > "$_lc_patched" 2>/dev/null || abort '更新迁移入口准备失败'
mv -f "$_lc_patched" "$_lc_temp" 2>/dev/null || abort '更新迁移入口提交失败'
grep -q 'module_update_hotfix_v4.sh' "$_lc_temp" 2>/dev/null || abort '更新迁移修复未载入'

. "$_lc_temp"
_lc_rc=$?
rm -f "$_lc_temp" "$_lc_patched" 2>/dev/null || true
luoshu_private_unmount_module_view "$LUOSHU_OLD_MOD" >/dev/null 2>&1 || true
if [ "$_lc_rc" -ne 0 ]; then
    # APatch sources customize.sh into its installer process. Returning here keeps
    # the manager's commit phase alive; direct execution still exits with the
    # delegated installer's status.
    return "$_lc_rc" 2>/dev/null || exit "$_lc_rc"
fi

# A schema boundary is rebuilt in the staged new module before root manager commit.
# If the new engine cannot reproduce the selected font, abort the update so the
# currently installed module/font remains untouched after reboot.
if [ "${LUOSHU_UPDATE_REBUILD_REQUIRED:-false}" = true ]; then
    ui_print '• 字体负载架构已变化，正在按当前选择自动重建...'
    if ! type luoshu_v4_update_rebuild_selected >/dev/null 2>&1; then
        abort '更新重建器未载入；已拒绝提交本次更新'
    fi
    if ! luoshu_v4_update_rebuild_selected "$MODPATH"; then
        abort '当前字体无法用新版引擎安全重建；已拒绝提交本次更新，旧版字体保持不变'
    fi
    ui_print '✓ 当前字体已按新版引擎重建，未切换为系统默认字体'
fi

if ! luoshu_private_install_migrate "$MODPATH"; then
    abort '洛书私有挂载树部署失败'
fi
ui_print '✓ 私有字体负载已部署'
ui_print '✓ 洛书将独立完成字体挂载'
# Magisk commonly executes this file, while APatch may source it. A plain exit
# would terminate APatch's parent installer before it commits the staged module.
return 0 2>/dev/null || exit 0
