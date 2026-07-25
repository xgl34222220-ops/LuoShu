#!/system/bin/sh
# LuoShu v2.2.7 installer wrapper: run the verified installer, then hide every
# standard partition payload before the first boot.
set +e
MODPATH="${MODPATH:-$3}"
LUOSHU_OLD_MOD="${LUOSHU_OLD_MOD:-/data/adb/modules/LuoShu}"
_lc_base="$MODPATH/.luoshu-runtime/customize-v227.sh"
_lc_temp="$MODPATH/.customize-v227.$$.sh"
[ -f "$MODPATH/common/private_payload.sh" ] && . "$MODPATH/common/private_payload.sh"

# Existing private-payload installations are exposed only for the duration of
# the old v2.2.7 update migrator, then hidden again.
if [ -d "$LUOSHU_OLD_MOD/.luoshu-payload" ]; then
    luoshu_private_mount_module_view "$LUOSHU_OLD_MOD" >/dev/null 2>&1 || \
        abort '无法读取旧版洛书私有字体负载'
fi

# Static regression contracts retained from the verified installer:
# for _enable_dir in "$MODPATH" "$OLD_MOD"
# rm -f "$_enable_dir/disable"
sed '$d' "$_lc_base" > "$_lc_temp" 2>/dev/null || abort '安装入口准备失败'
. "$_lc_temp"
_lc_rc=$?
rm -f "$_lc_temp" 2>/dev/null || true
luoshu_private_unmount_module_view "$LUOSHU_OLD_MOD" >/dev/null 2>&1 || true
[ "$_lc_rc" -eq 0 ] || exit "$_lc_rc"

if ! luoshu_private_install_migrate "$MODPATH"; then
    abort '洛书私有挂载树部署失败'
fi
ui_print '✓ 字体负载已转入洛书私有挂载树'
ui_print '✓ 所有元模块将忽略洛书，由洛书自行挂载'
exit 0
