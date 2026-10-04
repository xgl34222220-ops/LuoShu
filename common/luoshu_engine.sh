#!/system/bin/sh
# LuoShu font engine v3 bridge: build a next-boot payload for one family (or
# the composite "mix") and stage it. Never touches the running boot's payload.
#   prepare <family|mix>   build payload + deployment.json + report
#   stage <family|mix>     move the prepared payload to .luoshu-payload-next
#   report|manifest|payload <family|mix>
set +e

MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
MODULE_DIR="$MODDIR"
CONFIG_DIR="${CONFIG_DIR:-$MODDIR/config}"
USER_FONTS_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts"
ENGINE="$MODDIR/common/luoshu_engine.py"
DEPLOYER="$MODDIR/common/luoshu_payload.py"
BUILD_DIR="$CONFIG_DIR/luoshu-engine-build"
CACHE_DIR="${LUOSHU_ENGINE_CACHE:-$MODDIR/cache/luoshu-engine}"
COMPOSITE_CONF="$CONFIG_DIR/universal-composite.conf"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"

LE_CONFIG_DIR="$CONFIG_DIR"
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/font_config_runtime.sh" ] && . "$MODDIR/common/font_config_runtime.sh"
[ -f "$MODDIR/common/font_config_partitions.sh" ] && . "$MODDIR/common/font_config_partitions.sh"
# The sourced helpers reset CONFIG_DIR from MODULE_DIR; keep the caller's value.
CONFIG_DIR="$LE_CONFIG_DIR"

_le_python() {
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

_le_value() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

_le_safe_family() {
    case "$1" in ''|*/*) return 1 ;; esac
    return 0
}

# Prints the user font files of one family, one per line.
_le_family_files() {
    for _lff_file in \
        "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc "$USER_FONTS_DIR"/*.otc \
        "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC "$USER_FONTS_DIR"/*.OTC \
        "$USER_FONTS_DIR"/*.woff "$USER_FONTS_DIR"/*.woff2 "$USER_FONTS_DIR"/*.WOFF "$USER_FONTS_DIR"/*.WOFF2; do
        [ -f "$_lff_file" ] || continue
        if type detect_font_family >/dev/null 2>&1; then
            _lff_detected=$(detect_font_family "$(basename "$_lff_file")")
        else
            _lff_detected="${_lff_file##*/}"
            _lff_detected="${_lff_detected%.*}"
        fi
        [ "$_lff_detected" = "$1" ] && printf '%s\n' "$_lff_file"
    done
}

_le_prepare() {
    _lep_family="$1"
    [ -f "$ENGINE" ] || { printf '{"status":"error","message":"字体引擎组件不可用"}\n'; return 1; }
    [ -s "$CONFIG_DIR/device_font_topology.json" ] || {
        printf '{"status":"error","message":"设备字体拓扑尚未生成，请重新刷入模块"}\n'
        return 1
    }
    # Stock XML snapshots (never LuoShu's own overlay) are what gets rewritten.
    type font_config_capture_original >/dev/null 2>&1 && font_config_capture_original >/dev/null 2>&1

    set -- "$ENGINE" \
        --topology "$CONFIG_DIR/device_font_topology.json" \
        --xml-root "$CONFIG_DIR/font-config-source" \
        --cache-dir "$CACHE_DIR" \
        --payload-root "$BUILD_DIR/payload" \
        --manifest "$BUILD_DIR/deployment.json" \
        --report "$BUILD_DIR/report.json"
    [ -n "${LUOSHU_SWITCH_PROGRESS_FILE:-}" ] && set -- "$@" --progress "$LUOSHU_SWITCH_PROGRESS_FILE"

    if [ "$_lep_family" = mix ]; then
        [ -s "$COMPOSITE_CONF" ] || { printf '{"status":"error","message":"组合字体设置缺失"}\n'; return 1; }
        for _lep_role in cjk latin digit; do
            _lep_name=$(_le_value "$COMPOSITE_CONF" "$_lep_role")
            _le_safe_family "$_lep_name" || { printf '{"status":"error","message":"组合字体 ID 无效"}\n'; return 1; }
            _lep_files=$(_le_family_files "$_lep_name")
            [ -n "$_lep_files" ] || {
                printf '{"status":"error","message":"找不到组合字体家族：%s"}\n' "$_lep_name"
                return 1
            }
            while IFS= read -r _lep_file; do
                [ -n "$_lep_file" ] && set -- "$@" --role-font "$_lep_role:$_lep_file"
            done <<EOF_LE_FILES
$_lep_files
EOF_LE_FILES
            set -- "$@" \
                --role-mode "$_lep_role=$(_le_value "$COMPOSITE_CONF" "${_lep_role}Mode")" \
                --role-axes "$_lep_role=$(_le_value "$COMPOSITE_CONF" "${_lep_role}Axes")"
        done
    else
        _le_safe_family "$_lep_family" || { printf '{"status":"error","message":"字体 ID 无效"}\n'; return 1; }
        _lep_files=$(_le_family_files "$_lep_family")
        [ -n "$_lep_files" ] || { printf '{"status":"error","message":"找不到字体家族"}\n'; return 1; }
        while IFS= read -r _lep_file; do
            [ -n "$_lep_file" ] && set -- "$@" --font "$_lep_file"
        done <<EOF_LE_FILES
$_lep_files
EOF_LE_FILES
    fi

    rm -rf "$BUILD_DIR" 2>/dev/null || true
    mkdir -p "$BUILD_DIR" "$CACHE_DIR" 2>/dev/null || {
        printf '{"status":"error","message":"无法创建字体生成目录"}\n'
        return 1
    }
    printf '%s\n' "$_lep_family" > "$BUILD_DIR/family" 2>/dev/null || true
    _le_python "$@"
}

_le_identity() {
    _le_python - "$1" <<'PY'
import json, sys
p = json.load(open(sys.argv[1], encoding="utf-8"))
print(p.get("deploymentId", ""))
print(p.get("payloadDigest", ""))
PY
}

# The payload used by this Android boot, to recover to if the new one fails.
_le_capture_previous() {
    LE_PREVIOUS_FONT=$(head -n1 "$CONFIG_DIR/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$LE_PREVIOUS_FONT" ] || LE_PREVIOUS_FONT=default
    LE_PREVIOUS_MODE=''
    for _lec_queued in "$CONFIG_DIR/universal-font-next.conf" "$CONFIG_DIR/font-payload-next.conf"; do
        [ -s "$_lec_queued" ] || continue
        _lec_font=$(_le_value "$_lec_queued" previousFont)
        [ -z "$_lec_font" ] || LE_PREVIOUS_FONT="$_lec_font"
        LE_PREVIOUS_MODE=$(_le_value "$_lec_queued" previousMode)
        break
    done
    if [ -z "$LE_PREVIOUS_MODE" ]; then
        if [ -s "$CONFIG_DIR/universal-font-runtime.conf" ]; then
            LE_PREVIOUS_MODE=universal
        elif [ "$LE_PREVIOUS_FONT" = default ]; then
            LE_PREVIOUS_MODE=default
        else
            LE_PREVIOUS_MODE=classic
        fi
    fi
    LE_PREVIOUS_DEPLOYMENT_ID=$(_le_value "$CONFIG_DIR/universal-font-runtime.conf" deploymentId)
    LE_PREVIOUS_PAYLOAD_DIGEST=$(_le_value "$CONFIG_DIR/universal-font-runtime.conf" payloadDigest)
}

_le_stage() {
    _les_family="$1"
    [ "$(head -n1 "$BUILD_DIR/family" 2>/dev/null)" = "$_les_family" ] || return 1
    [ -s "$BUILD_DIR/deployment.json" ] && [ -d "$BUILD_DIR/payload" ] || return 1
    _le_python "$DEPLOYER" --payload-root "$BUILD_DIR/payload" \
        --validate-payload-only "$BUILD_DIR/deployment.json" >/dev/null 2>&1 || return 1
    _les_values=$(_le_identity "$BUILD_DIR/deployment.json") || return 1
    _les_id=$(printf '%s\n' "$_les_values" | sed -n '1p')
    _les_digest=$(printf '%s\n' "$_les_values" | sed -n '2p')
    [ -n "$_les_id" ] && [ -n "$_les_digest" ] || return 1

    _le_capture_previous
    _les_next="$MODDIR/.luoshu-payload-next"
    # Universal and default next-boot markers are mutually exclusive.
    rm -f "$CONFIG_DIR/font-payload-next.conf" 2>/dev/null || true
    rm -rf "$_les_next" "$_les_next".stage.* 2>/dev/null || true
    mv "$BUILD_DIR/payload" "$_les_next" 2>/dev/null || return 1

    _les_state="$CONFIG_DIR/universal-font-next.conf"
    {
        printf 'state=prepared\n'
        printf 'font=%s\n' "$_les_family"
        printf 'deploymentId=%s\n' "$_les_id"
        printf 'payloadDigest=%s\n' "$_les_digest"
        printf 'previousFont=%s\n' "$LE_PREVIOUS_FONT"
        printf 'previousMode=%s\n' "$LE_PREVIOUS_MODE"
        printf 'previousLegacy=false\n'
        printf 'previousDeploymentId=%s\n' "$LE_PREVIOUS_DEPLOYMENT_ID"
        printf 'previousPayloadDigest=%s\n' "$LE_PREVIOUS_PAYLOAD_DIGEST"
        printf 'recovery=false\n'
        printf 'engine=luoshu-engine-v3\n'
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_les_state.tmp.$$" 2>/dev/null && mv -f "$_les_state.tmp.$$" "$_les_state" 2>/dev/null || {
        rm -f "$_les_state" "$_les_state.tmp.$$" 2>/dev/null || true
        rm -rf "$_les_next" 2>/dev/null || true
        return 1
    }
    chmod 0600 "$_les_state" 2>/dev/null || true

    # active_font.conf is the configured selection; the reboot marker tells the
    # App it is not rendered yet.
    printf '%s\n' "$_les_family" > "$CONFIG_DIR/active_font.conf.tmp.$$" 2>/dev/null && \
        mv -f "$CONFIG_DIR/active_font.conf.tmp.$$" "$CONFIG_DIR/active_font.conf" 2>/dev/null || {
            rm -f "$_les_state" "$CONFIG_DIR/active_font.conf.tmp.$$" 2>/dev/null || true
            rm -rf "$_les_next" 2>/dev/null || true
            return 1
        }
    {
        printf 'font=%s\n' "$_les_family"
        printf 'reason=universal-next-boot-prepared\n'
        printf 'pipeline=luoshu-engine-v3\n'
        printf 'deploymentId=%s\n' "$_les_id"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$CONFIG_DIR/text_reboot_required.conf" 2>/dev/null || true
    chmod 0644 "$CONFIG_DIR/active_font.conf" "$CONFIG_DIR/text_reboot_required.conf" 2>/dev/null || true
    printf '{"status":"ok","state":"staged-next-boot","pipeline":"luoshu-engine-v3","deploymentId":"%s","previousMode":"%s"}\n' \
        "$_les_id" "$LE_PREVIOUS_MODE"
}

case "${1:-}" in
    prepare) _le_prepare "${2:-}" ;;
    stage) _le_stage "${2:-}" ;;
    report) printf '%s\n' "$BUILD_DIR/report.json" ;;
    manifest) printf '%s\n' "$BUILD_DIR/deployment.json" ;;
    payload) printf '%s\n' "$BUILD_DIR/payload" ;;
    *)
        echo "Usage: $0 {prepare|stage|report|manifest|payload} <family|mix>" >&2
        exit 2
        ;;
esac
