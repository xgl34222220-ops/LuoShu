#!/system/bin/sh
# LuoShu Phase 5 Minimal XML Router bridge.
# Planning/capture only. Never publishes XML overlays or mounts anything.
set +e

MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
MODULE_DIR="$MODDIR"
CONFIG_DIR="${CONFIG_DIR:-$MODDIR/config}"
ROUTER="$MODDIR/common/minimal_xml_router.py"
UNIVERSAL_PLAN="$MODDIR/common/universal_font_plan.sh"
ROUTE_DIR="$CONFIG_DIR/minimal-xml-route-plans"
SNAPSHOT_ROOT="$CONFIG_DIR/font-config-source"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"

[ -f "$MODDIR/common/font_config_runtime.sh" ] && . "$MODDIR/common/font_config_runtime.sh"
[ -f "$MODDIR/common/font_config_partitions.sh" ] && . "$MODDIR/common/font_config_partitions.sh"

_mxr_exec() {
    if [ -n "${LUOSHU_PYTHON:-}" ]; then
        "$LUOSHU_PYTHON" "$@"
        return $?
    fi
    [ -x "$PYBIN" ] || return 127
    PYTHONHOME="$PYROOT" \
    PYTHONPATH="$MODDIR/common:$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$PYBIN" "$@"
}

_mxr_family_key() {
    _mxk_family="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        printf '%s' "$_mxk_family" | sha256sum | awk '{print substr($1,1,24)}'
    elif command -v busybox >/dev/null 2>&1; then
        printf '%s' "$_mxk_family" | busybox sha256sum | awk '{print substr($1,1,24)}'
    else
        printf '%s' "$_mxk_family" | cksum | awk '{print $1 "-" $2}'
    fi
}

_mxr_output() {
    _mxo_key=$(_mxr_family_key "$1") || return 1
    printf '%s/%s.json\n' "$ROUTE_DIR" "$_mxo_key"
}

_mxr_font_plan_path() {
    MODDIR="$MODDIR" MODULE_DIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" \
        sh "$UNIVERSAL_PLAN" path "$1"
}

_mxr_capture_stock() {
    type font_config_capture_original >/dev/null 2>&1 || return 1
    font_config_capture_original >/dev/null 2>&1
}

_mxr_build() {
    _mxb_family="$1"
    [ -n "$_mxb_family" ] || { printf '{"status":"error","message":"未指定字体家族"}\n'; return 1; }
    [ -f "$ROUTER" ] || { printf '{"status":"error","message":"Minimal XML Router 组件不可用"}\n'; return 1; }
    [ -f "$UNIVERSAL_PLAN" ] || { printf '{"status":"error","message":"Universal FontPlan 组件不可用"}\n'; return 1; }

    _mxb_plan_result=$(MODDIR="$MODDIR" MODULE_DIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" \
        sh "$UNIVERSAL_PLAN" build "$_mxb_family" 2>&1)
    _mxb_rc=$?
    if [ "$_mxb_rc" -ne 0 ]; then
        printf '%s\n' "$_mxb_plan_result"
        return "$_mxb_rc"
    fi

    _mxb_plan=$(_mxr_font_plan_path "$_mxb_family") || return 1
    [ -s "$_mxb_plan" ] || { printf '{"status":"error","message":"Universal FontPlan 未生成"}\n'; return 1; }

    _mxr_capture_stock >/dev/null 2>&1 || true
    # Compiled artifacts stay cached; the compiler reuses only exact matches.
    rm -rf "$CONFIG_DIR/universal-font-artifact-manifests" 2>/dev/null || true
    mkdir -p "$ROUTE_DIR" 2>/dev/null || {
        printf '{"status":"error","message":"无法创建 XML Route Plan 缓存目录"}\n'
        return 1
    }
    _mxb_output=$(_mxr_output "$_mxb_family") || return 1
    rm -f "$_mxb_output" 2>/dev/null || true

    _mxr_exec "$ROUTER" \
        --font-plan "$_mxb_plan" \
        --snapshot-root "$SNAPSHOT_ROOT" \
        --output "$_mxb_output"
}

_mxr_validate() {
    _mxv_family="$1"
    _mxv_plan=$(_mxr_font_plan_path "$_mxv_family") || return 1
    _mxv_output=$(_mxr_output "$_mxv_family") || return 1
    [ -s "$_mxv_plan" ] || { printf '{"status":"error","message":"Universal FontPlan 未生成"}\n'; return 1; }
    [ -s "$_mxv_output" ] || { printf '{"status":"error","message":"Minimal XML Route Plan 未生成"}\n'; return 1; }
    _mxr_exec "$ROUTER" \
        --font-plan "$_mxv_plan" \
        --validate "$_mxv_output"
}

case "${1:-build}" in
    build|refresh)
        _mxr_build "${2:-}"
        ;;
    validate)
        _mxr_validate "${2:-}"
        ;;
    path)
        _mxr_output "${2:-}"
        ;;
    *)
        echo "Usage: $0 {build|refresh|validate|path} <font-family>" >&2
        exit 2
        ;;
esac
