#!/system/bin/sh
# One inventory-driven staging entry for direct, prewarm, mix and coverage repair.
set +e

MODDIR="${LUOSHU_REAL_MODDIR:-${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}}"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"
SCANNER="$MODDIR/common/stock_inventory_scan.py"
INVENTORY="$MODDIR/config/device_font_inventory.json"
ENGINE="$MODDIR/common/inventory_font_stage.py"

json_error() {
    printf '{"status":"error","message":"%s"}\n' \
        "$(printf '%s' "$*" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  ')"
}

run_python() {
    PYTHONHOME="$PYROOT" \
    PYTHONPATH="$MODDIR/common:$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$PYBIN" "$@"
}

ensure_inventory() {
    [ -x "$PYBIN" ] && [ -f "$SCANNER" ] && [ -f "$ENGINE" ] || {
        json_error '通用字体扫描或生成组件不完整'
        return 1
    }
    run_python "$SCANNER" --validate --output "$INVENTORY" >/dev/null 2>&1 && return 0
    # The manager owns the shared scan lock and recovers a verified stock view.
    # Never reuse an old scanner revision or scan our active overlay as stock.
    [ -f "$MODDIR/common/font_manager.sh" ] || {
        json_error '本机字体清单无效且自动检测入口缺失'
        return 1
    }
    if ! MODDIR="$MODDIR" LUOSHU_REAL_MODDIR="$MODDIR" \
        sh "$MODDIR/common/font_manager.sh" action stock_scan >&2; then
        return 1
    fi
    run_python "$SCANNER" --validate --output "$INVENTORY" >/dev/null 2>&1 || {
        json_error '自动检测未生成有效的原厂字体清单'
        return 1
    }
}

if [ "${1:-}" = --ensure-inventory ]; then
    ensure_inventory
    exit $?
fi

STAGE="${1:-}"
MODE="${2:-direct}"
FAMILY="${3:-}"
SOURCE="${4:-}"
[ "${STAGE%/*}" = "$MODDIR" ] || { json_error '暂存负载必须直接位于模块目录'; exit 1; }
case "$STAGE" in
    "$MODDIR"/.luoshu-payload-stage.*|"$MODDIR"/.luoshu-mix-stage|"$MODDIR"/.luoshu-payload-next) ;;
    *) json_error '目标不是受信任的下一启动暂存负载'; exit 1 ;;
esac
[ -d "$STAGE" ] && [ ! -L "$STAGE" ] || {
    json_error '下一启动字体暂存负载不存在或不是独立目录'
    exit 1
}
case "$MODE" in direct|mix) ;; *) json_error '未知字体生成模式'; exit 1 ;; esac
PLAN="${LUOSHU_COVERAGE_PLAN:-}"
if [ -n "$PLAN" ]; then
    case "$PLAN" in "$MODDIR"/config/*) ;; *) json_error '字体补齐计划路径不受信任'; exit 1 ;; esac
    [ -s "$PLAN" ] && [ ! -L "$PLAN" ] || { json_error '字体补齐计划为空或不存在'; exit 1; }
fi
ensure_inventory || exit 1
set -- "$ENGINE" --module "$MODDIR" --stage "$STAGE" --mode "$MODE" --family "$FAMILY"
[ -z "$SOURCE" ] || set -- "$@" --source "$SOURCE"
[ -z "$PLAN" ] || set -- "$@" --plan "$PLAN"
run_python "$@"
exit $?
