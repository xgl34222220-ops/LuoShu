#!/system/bin/sh
# LuoShu universal font topology snapshot wrapper.
# Read-only: collects FontManager evidence and merges it with the trusted stock inventory.
set +e

MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
MODULE_DIR="$MODDIR"
CONFIG_DIR="$MODDIR/config"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"
SCRIPT="$MODDIR/common/font_topology_snapshot.py"
INVENTORY="$CONFIG_DIR/device_font_inventory.json"
OUTPUT="$CONFIG_DIR/device_font_topology.json"
LOG="$MODDIR/logs/font-topology.log"

_topology_exec() {
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

_topology_timeout() {
    if command -v timeout >/dev/null 2>&1; then
        timeout 4 "$@"
    elif command -v toybox >/dev/null 2>&1 && toybox timeout 1 true >/dev/null 2>&1; then
        toybox timeout 4 "$@"
    else
        "$@"
    fi
}

_topology_font_manager_dump() {
    _tfd_out="$1"
    : > "$_tfd_out" 2>/dev/null || return 1
    if command -v cmd >/dev/null 2>&1; then
        if _topology_timeout cmd font dump >"$_tfd_out" 2>&1; then
            [ -s "$_tfd_out" ] && return 0
        fi
        : > "$_tfd_out" 2>/dev/null || true
        if _topology_timeout cmd font system >"$_tfd_out" 2>&1; then
            [ -s "$_tfd_out" ] && return 0
        fi
    fi
    : > "$_tfd_out" 2>/dev/null || true
    if command -v dumpsys >/dev/null 2>&1; then
        if _topology_timeout dumpsys font >"$_tfd_out" 2>&1; then
            [ -s "$_tfd_out" ] && return 0
        fi
    fi
    rm -f "$_tfd_out" 2>/dev/null || true
    return 1
}

_topology_refresh() {
    mkdir -p "$CONFIG_DIR" "$MODDIR/logs" 2>/dev/null || true
    rm -rf "$CONFIG_DIR/universal-font-plans" 2>/dev/null || true
    [ -f "$SCRIPT" ] || {
        printf '{"status":"error","message":"缺少字体拓扑组件"}\n'
        return 1
    }
    [ -s "$INVENTORY" ] || {
        printf '{"status":"error","message":"原厂字体清单尚未就绪"}\n'
        return 1
    }

    _tf_tmp="$CONFIG_DIR/.font-manager-dump.$$"
    _topology_font_manager_dump "$_tf_tmp" >/dev/null 2>&1 || true
    set -- "$SCRIPT" --inventory "$INVENTORY" --output "$OUTPUT"
    [ -s "$CONFIG_DIR/device_font_candidates.json" ] && \
        set -- "$@" --candidates "$CONFIG_DIR/device_font_candidates.json"
    [ -s "$_tf_tmp" ] && set -- "$@" --font-manager-dump "$_tf_tmp"
    [ -f /data/fonts/config/config.xml ] && set -- "$@" --data-fonts-config /data/fonts/config/config.xml
    [ -d /data/fonts/files ] && set -- "$@" --data-fonts-dir /data/fonts/files
    [ -r /proc/self/mountinfo ] && set -- "$@" --mountinfo /proc/self/mountinfo

    _tf_result=$(_topology_exec "$@" 2>>"$LOG")
    _tf_rc=$?
    rm -f "$_tf_tmp" 2>/dev/null || true
    if [ "$_tf_rc" -eq 0 ] && [ -s "$OUTPUT" ] && [ -f "$MODDIR/common/font_role_shadow.sh" ]; then
        MODDIR="$MODDIR" MODULE_DIR="$MODDIR" \
            sh "$MODDIR/common/font_role_shadow.sh" refresh >>"$MODDIR/logs/font-role-shadow.log" 2>&1 || true
    fi
    printf '%s\n' "$_tf_result"
    return "$_tf_rc"
}

# Upgrade the scanner through the existing locked, stock-safe entry point. Do
# not promote a mounted replacement to stock merely to make migration pass.
_topology_ensure() {
    _topology_exec "$SCRIPT" --validate-current --inventory "$INVENTORY" --output "$OUTPUT" >>"$LOG" 2>&1
    _tfe_current_rc=$?
    # Do not overwrite sealed original evidence with our visible bind overlay.
    [ "$_tfe_current_rc" -ne 3 ] || return 1
    if [ "$_tfe_current_rc" -ne 0 ]; then
        if ! _topology_exec -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d.get("scannerRevision")==6 and all(isinstance(s.get("stockIdentity"),dict) and s["stockIdentity"].get("captureRevision")==2 and isinstance(s.get("stockGeometryProfile"),dict) for s in d.get("slots",{}).values()) else 1)' "$INVENTORY" >/dev/null 2>&1; then
            [ -f "$MODDIR/common/font_manager.sh" ] || return 1
            MODDIR="$MODDIR" MODULE_DIR="$MODDIR" sh "$MODDIR/common/font_manager.sh" action stock_scan >>"$LOG" 2>&1 || return 1
        fi
        _topology_refresh >/dev/null || return 1
    fi
    # Role evidence is cheap to recompute and must describe this exact topology.
    MODDIR="$MODDIR" MODULE_DIR="$MODDIR" sh "$MODDIR/common/font_role_shadow.sh" refresh >/dev/null || return 1
    _topology_exec "$SCRIPT" --validate-current --inventory "$INVENTORY" --output "$OUTPUT"
}

case "${1:-refresh}" in
    ensure)
        mkdir -p "$MODDIR/logs" 2>/dev/null || true
        _topology_ensure
        ;;
    refresh|build)
        _topology_refresh
        ;;
    validate|status)
        [ -f "$SCRIPT" ] || exit 1
        _topology_exec "$SCRIPT" --validate --inventory "$INVENTORY" --output "$OUTPUT"
        ;;
    path)
        printf '%s\n' "$OUTPUT"
        ;;
    *)
        echo "Usage: $0 {ensure|refresh|validate|status|path}" >&2
        exit 2
        ;;
esac
