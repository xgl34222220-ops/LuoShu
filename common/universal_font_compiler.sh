#!/system/bin/sh
# LuoShu Phase 6 universal font compiler bridge.
# Compiles private artifacts only. Never publishes or mounts them.
set +e

MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
MODULE_DIR="$MODDIR"
CONFIG_DIR="${CONFIG_DIR:-$MODDIR/config}"
COMPILER="$MODDIR/common/universal_font_compiler.py"
FONT_PLAN_BRIDGE="$MODDIR/common/universal_font_plan.sh"
ROUTE_BRIDGE="${LUOSHU_ROUTE_BRIDGE:-$MODDIR/common/minimal_xml_router.sh}"
MANIFEST_DIR="$CONFIG_DIR/universal-font-artifact-manifests"
CACHE_ROOT="${LUOSHU_COMPILER_CACHE:-$MODDIR/cache/universal-font-artifacts}"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"

_ufc_exec() {
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

_ufc_family_key() {
    _ufk_family="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        printf "%s" "$_ufk_family" | sha256sum | awk '{print substr($1,1,24)}'
    elif command -v busybox >/dev/null 2>&1; then
        printf "%s" "$_ufk_family" | busybox sha256sum | awk '{print substr($1,1,24)}'
    else
        printf "%s" "$_ufk_family" | cksum | awk '{print $1 "-" $2}'
    fi
}

_ufc_manifest() {
    _ufm_key=$(_ufc_family_key "$1") || return 1
    printf "%s/%s.json\n" "$MANIFEST_DIR" "$_ufm_key"
}

_ufc_output_dir() {
    _ufo_key=$(_ufc_family_key "$1") || return 1
    printf "%s/%s\n" "$CACHE_ROOT" "$_ufo_key"
}

_ufc_font_plan() {
    MODDIR="$MODDIR" MODULE_DIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" \
        sh "$FONT_PLAN_BRIDGE" path "$1"
}

_ufc_route_plan() {
    MODDIR="$MODDIR" MODULE_DIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" \
        sh "$ROUTE_BRIDGE" path "$1"
}

_ufc_compile() {
    _uc_family="$1"
    [ -n "$_uc_family" ] || { printf '{"status":"error","message":"未指定字体家族"}\n'; return 1; }
    [ -f "$COMPILER" ] || { printf '{"status":"error","message":"Universal Font Compiler 组件不可用"}\n'; return 1; }
    [ -f "$FONT_PLAN_BRIDGE" ] || { printf '{"status":"error","message":"Universal FontPlan 组件不可用"}\n'; return 1; }
    [ -f "$ROUTE_BRIDGE" ] || { printf '{"status":"error","message":"Minimal XML Router 组件不可用"}\n'; return 1; }

    _uc_route_result=$(MODDIR="$MODDIR" MODULE_DIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" \
        sh "$ROUTE_BRIDGE" build "$_uc_family" 2>&1)
    _uc_rc=$?
    if [ "$_uc_rc" -ne 0 ]; then
        printf "%s\n" "$_uc_route_result"
        return "$_uc_rc"
    fi

    _uc_font_plan=$(_ufc_font_plan "$_uc_family") || return 1
    _uc_route_plan=$(_ufc_route_plan "$_uc_family") || return 1
    [ -s "$_uc_font_plan" ] || { printf '{"status":"error","message":"Universal FontPlan 未生成"}\n'; return 1; }
    [ -s "$_uc_route_plan" ] || { printf '{"status":"error","message":"Minimal XML Route Plan 未生成"}\n'; return 1; }

    _uc_manifest=$(_ufc_manifest "$_uc_family") || return 1
    _uc_output=$(_ufc_output_dir "$_uc_family") || return 1
    rm -rf "$_uc_output" 2>/dev/null || true
    rm -f "$_uc_manifest" 2>/dev/null || true
    mkdir -p "$_uc_output" "$MANIFEST_DIR" 2>/dev/null || {
        printf '{"status":"error","message":"无法创建字体编译缓存"}\n'
        return 1
    }

    set -- "$COMPILER" \
        --font-plan "$_uc_font_plan" \
        --route-plan "$_uc_route_plan" \
        --output-dir "$_uc_output" \
        --manifest "$_uc_manifest"
    if [ -n "${LUOSHU_STOCK_FONT_MAP:-}" ]; then
        set -- "$@" --stock-map "$LUOSHU_STOCK_FONT_MAP"
    fi
    if [ "${LUOSHU_COMPILER_ALLOW_LIVE_STOCK:-0}" = 1 ]; then
        set -- "$@" --allow-live-stock
    fi
    _ufc_exec "$@"
}

_ufc_validate() {
    _uv_family="$1"
    _uv_font_plan=$(_ufc_font_plan "$_uv_family") || return 1
    _uv_route_plan=$(_ufc_route_plan "$_uv_family") || return 1
    _uv_manifest=$(_ufc_manifest "$_uv_family") || return 1
    [ -s "$_uv_font_plan" ] || { printf '{"status":"error","message":"Universal FontPlan 未生成"}\n'; return 1; }
    [ -s "$_uv_route_plan" ] || { printf '{"status":"error","message":"Minimal XML Route Plan 未生成"}\n'; return 1; }
    [ -s "$_uv_manifest" ] || { printf '{"status":"error","message":"Universal Font Artifacts manifest 未生成"}\n'; return 1; }
    _ufc_exec "$COMPILER" \
        --font-plan "$_uv_font_plan" \
        --route-plan "$_uv_route_plan" \
        --validate "$_uv_manifest"
}

case "${1:-compile}" in
    compile|build|refresh)
        _ufc_compile "${2:-}"
        ;;
    validate)
        _ufc_validate "${2:-}"
        ;;
    manifest|path)
        _ufc_manifest "${2:-}"
        ;;
    output-dir)
        _ufc_output_dir "${2:-}"
        ;;
    *)
        echo "Usage: $0 {compile|validate|manifest|output-dir} <font-family>" >&2
        exit 2
        ;;
esac
