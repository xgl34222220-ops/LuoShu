#!/system/bin/sh
# Coverage repair uses the same inventory engine as the initial font switch.
# A supplied plan updates only those slots inside an isolated next-boot tree.
set +e
MODDIR="${LUOSHU_REAL_MODDIR:-${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}}"
HELPER="$MODDIR/common/inventory_font_stage.sh"
[ -f "$HELPER" ] || {
    printf '{"status":"error","message":"通用字体生成组件缺失"}\n'
    exit 1
}
LUOSHU_REAL_MODDIR="$MODDIR" sh "$HELPER" "${1:-}" "${2:-direct}" "${3:-}" "${4:-}"
exit $?
