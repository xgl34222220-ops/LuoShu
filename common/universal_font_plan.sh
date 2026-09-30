#!/system/bin/sh
# LuoShu Phase 4 universal FontPlan bridge. Planning only; never mutates Android fonts.
set +e

MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
MODULE_DIR="$MODDIR"
CONFIG_DIR="$MODDIR/config"
TOPOLOGY="$CONFIG_DIR/device_font_topology.json"
ROLES="$CONFIG_DIR/device_font_roles.json"
PROFILE_BRIDGE="$MODDIR/common/font_source_profile.sh"
PLANNER="$MODDIR/common/universal_font_plan.py"
PLAN_DIR="$CONFIG_DIR/universal-font-plans"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"

_ufp_exec() {
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

_ufp_family_key() {
    _ufk_family="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        printf "%s" "$_ufk_family" | sha256sum | awk '{print substr($1,1,24)}'
    elif command -v busybox >/dev/null 2>&1; then
        printf "%s" "$_ufk_family" | busybox sha256sum | awk '{print substr($1,1,24)}'
    else
        printf "%s" "$_ufk_family" | cksum | awk '{print $1 "-" $2}'
    fi
}

_ufp_output() {
    _ufo_key=$(_ufp_family_key "$1") || return 1
    printf "%s/%s.json\n" "$PLAN_DIR" "$_ufo_key"
}

_ufp_profile_path() {
    MODDIR="$MODDIR" MODULE_DIR="$MODDIR" sh "$PROFILE_BRIDGE" path "$1"
}

_ufp_build() {
    _ufb_family="$1"
    [ -n "$_ufb_family" ] || { printf '{"status":"error","message":"未指定字体家族"}\n'; return 1; }
    MODDIR="$MODDIR" MODULE_DIR="$MODDIR" sh "$MODDIR/common/font_topology_snapshot.sh" ensure >/dev/null 2>&1 || {
        printf '{"status":"error","message":"字体拓扑升级或动态配置解析未完成"}\n'
        return 1
    }
    [ -s "$TOPOLOGY" ] || { printf '{"status":"error","message":"设备字体拓扑尚未生成"}\n'; return 1; }
    [ -s "$ROLES" ] || { printf '{"status":"error","message":"字体角色映射尚未生成"}\n'; return 1; }
    [ -f "$PROFILE_BRIDGE" ] || { printf '{"status":"error","message":"源字体 Profile 组件不可用"}\n'; return 1; }
    [ -f "$PLANNER" ] || { printf '{"status":"error","message":"Universal FontPlan 组件不可用"}\n'; return 1; }

    _ufb_profile_result=$(MODDIR="$MODDIR" MODULE_DIR="$MODDIR" sh "$PROFILE_BRIDGE" refresh "$_ufb_family" 2>&1)
    _ufb_rc=$?
    if [ "$_ufb_rc" -ne 0 ]; then
        printf "%s\n" "$_ufb_profile_result"
        return "$_ufb_rc"
    fi
    _ufb_profile=$(_ufp_profile_path "$_ufb_family") || return 1
    [ -s "$_ufb_profile" ] || { printf '{"status":"error","message":"源字体 Profile 未生成"}\n'; return 1; }
    rm -rf "$CONFIG_DIR/minimal-xml-route-plans" 2>/dev/null || true
    mkdir -p "$PLAN_DIR" 2>/dev/null || { printf '{"status":"error","message":"无法创建 FontPlan 缓存目录"}\n'; return 1; }
    _ufb_output=$(_ufp_output "$_ufb_family") || return 1
    _ufp_exec "$PLANNER" \
        --topology "$TOPOLOGY" \
        --roles "$ROLES" \
        --source-profile "$_ufb_profile" \
        --output "$_ufb_output"
}

_ufp_validate() {
    _ufv_family="$1"
    _ufv_profile=$(_ufp_profile_path "$_ufv_family") || return 1
    _ufv_output=$(_ufp_output "$_ufv_family") || return 1
    [ -s "$_ufv_profile" ] || { printf '{"status":"error","message":"源字体 Profile 未生成"}\n'; return 1; }
    [ -s "$_ufv_output" ] || { printf '{"status":"error","message":"Universal FontPlan 未生成"}\n'; return 1; }
    _ufp_exec "$PLANNER" \
        --topology "$TOPOLOGY" \
        --roles "$ROLES" \
        --source-profile "$_ufv_profile" \
        --validate "$_ufv_output"
}

case "${1:-build}" in
    build|refresh)
        _ufp_build "${2:-}"
        ;;
    validate)
        _ufp_validate "${2:-}"
        ;;
    path)
        _ufp_output "${2:-}"
        ;;
    *)
        echo "Usage: $0 {build|refresh|validate|path} <font-family>" >&2
        exit 2
        ;;
esac
