#!/system/bin/sh
# LuoShu Phase 7 backend-neutral deployment bridge.
# Phase 9 may stage an already validated prepared payload for the official next boot.
set +e

MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
MODULE_DIR="$MODDIR"
CONFIG_DIR="${CONFIG_DIR:-$MODDIR/config}"
DEPLOYER="$MODDIR/common/universal_font_deployment.py"
COMPILER_BRIDGE="$MODDIR/common/universal_font_compiler.sh"
PLAN_BRIDGE="$MODDIR/common/universal_font_plan.sh"
ROUTE_BRIDGE="$MODDIR/common/minimal_xml_router.sh"
DEPLOY_ROOT="$CONFIG_DIR/universal-font-deployments"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"


# Shared short-lived commit lease; source beside this script for host fixtures too.
for _lpc_helper in "$MODDIR/common/payload_commit_lock.sh" "${0%/*}/payload_commit_lock.sh" "${0%/*}/../payload_commit_lock.sh"; do
    [ ! -f "$_lpc_helper" ] || { . "$_lpc_helper"; break; }
done

_ud_exec() {
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

_ud_value() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

_ud_family_key() {
    _udk_family="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        printf '%s' "$_udk_family" | sha256sum | awk '{print substr($1,1,24)}'
    elif command -v busybox >/dev/null 2>&1; then
        printf '%s' "$_udk_family" | busybox sha256sum | awk '{print substr($1,1,24)}'
    else
        printf '%s' "$_udk_family" | cksum | awk '{print $1 "-" $2}'
    fi
}

_ud_dir() {
    _udd_key=$(_ud_family_key "$1") || return 1
    printf '%s/%s\n' "$DEPLOY_ROOT" "$_udd_key"
}

_ud_manifest() {
    _udm_dir=$(_ud_dir "$1") || return 1
    printf '%s/deployment.json\n' "$_udm_dir"
}

_ud_payload() {
    _udp_dir=$(_ud_dir "$1") || return 1
    printf '%s/payload\n' "$_udp_dir"
}

_ud_upstream_paths() {
    _udu_family="$1"
    UD_FONT_PLAN=$(MODDIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" sh "$PLAN_BRIDGE" path "$_udu_family") || return 1
    UD_ROUTE_PLAN=$(MODDIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" sh "$ROUTE_BRIDGE" path "$_udu_family") || return 1
    UD_ARTIFACT_MANIFEST=$(MODDIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" sh "$COMPILER_BRIDGE" manifest "$_udu_family") || return 1
    [ -s "$UD_FONT_PLAN" ] && [ -s "$UD_ROUTE_PLAN" ] && [ -s "$UD_ARTIFACT_MANIFEST" ]
}

_ud_prepare() {
    _udp_family="$1"
    [ -n "$_udp_family" ] || { printf '{"status":"error","message":"未指定字体家族"}\n'; return 1; }
    [ -f "$DEPLOYER" ] || { printf '{"status":"error","message":"Universal Deployment 组件不可用"}\n'; return 1; }

    _udp_compile=$(MODDIR="$MODDIR" MODULE_DIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" \
        sh "$COMPILER_BRIDGE" compile "$_udp_family" 2>&1)
    _udp_rc=$?
    [ "$_udp_rc" -eq 0 ] || { printf '%s\n' "$_udp_compile"; return "$_udp_rc"; }

    _ud_upstream_paths "$_udp_family" || {
        printf '{"status":"error","message":"Phase 4/5/6 产物不完整"}\n'
        return 1
    }
    # Preserve actionable blocked reasons in the existing log before the
    # deployment's all-or-nothing gate returns its aggregate rejection.
    mkdir -p "$MODDIR/logs" 2>/dev/null || true
    _ud_exec - "$UD_ARTIFACT_MANIFEST" >> "$MODDIR/logs/fontswitch.log" 2>/dev/null <<'PYBLOCK'
import json, re, sys
from pathlib import Path
manifest = json.loads(Path(sys.argv[1]).read_text())
blocked = [a for a in manifest.get('artifacts', []) if a.get('status') == 'blocked']
for item in blocked[:50]:
    print('[UNIVERSAL-BLOCKED] ' + json.dumps({
        'targetPath': item.get('targetPath'), 'role': item.get('role'),
        'reason': re.sub(r'/[^\s]+', '<path>', str(item.get('reason', '')))
    }, ensure_ascii=False, separators=(',', ':')))
if blocked:
    print('[UNIVERSAL-BLOCKED] count=' + str(len(blocked)))
PYBLOCK
    _udp_dir=$(_ud_dir "$_udp_family") || return 1
    _udp_manifest=$(_ud_manifest "$_udp_family") || return 1
    _udp_payload=$(_ud_payload "$_udp_family") || return 1
    rm -rf "$_udp_dir" 2>/dev/null || true
    mkdir -p "$_udp_dir" 2>/dev/null || return 1

    _ud_exec "$DEPLOYER" \
        --font-plan "$UD_FONT_PLAN" \
        --route-plan "$UD_ROUTE_PLAN" \
        --artifact-manifest "$UD_ARTIFACT_MANIFEST" \
        --payload-root "$_udp_payload" \
        --manifest "$_udp_manifest"
}

_ud_validate() {
    _udv_family="$1"
    _ud_upstream_paths "$_udv_family" || return 1
    _udv_manifest=$(_ud_manifest "$_udv_family") || return 1
    _udv_payload=$(_ud_payload "$_udv_family") || return 1
    [ -s "$_udv_manifest" ] && [ -d "$_udv_payload" ] || return 1
    _ud_exec "$DEPLOYER" \
        --font-plan "$UD_FONT_PLAN" \
        --route-plan "$UD_ROUTE_PLAN" \
        --artifact-manifest "$UD_ARTIFACT_MANIFEST" \
        --payload-root "$_udv_payload" \
        --validate "$_udv_manifest"
}

_ud_manifest_identity() {
    _udi_manifest="$1"
    _ud_exec - "$_udi_manifest" <<'PY'
import json, sys
p=json.load(open(sys.argv[1],encoding='utf-8'))
print(p.get('deploymentId',''))
print(p.get('payloadDigest',''))
PY
}

_ud_capture_previous() {
    UD_PREVIOUS_FONT=$(head -n1 "$CONFIG_DIR/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$UD_PREVIOUS_FONT" ] || UD_PREVIOUS_FONT=default
    UD_PREVIOUS_MODE=''
    UD_PREVIOUS_LEGACY=false

    # Replacing an already queued request must keep the identity of the payload
    # actually used by this Android boot, not the selection that was merely queued.
    _udp_pending_universal="$CONFIG_DIR/universal-font-next.conf"
    _udp_pending_legacy="$CONFIG_DIR/font-payload-next.conf"
    if [ -s "$_udp_pending_universal" ]; then
        _udp_saved_font=$(_ud_value "$_udp_pending_universal" previousFont)
        _udp_saved_mode=$(_ud_value "$_udp_pending_universal" previousMode)
        _udp_saved_legacy=$(_ud_value "$_udp_pending_universal" previousLegacy)
        [ -n "$_udp_saved_font" ] && UD_PREVIOUS_FONT="$_udp_saved_font"
        [ -n "$_udp_saved_mode" ] && UD_PREVIOUS_MODE="$_udp_saved_mode"
        [ "$_udp_saved_legacy" = true ] && UD_PREVIOUS_LEGACY=true
    elif [ -s "$_udp_pending_legacy" ]; then
        _udp_saved_font=$(_ud_value "$_udp_pending_legacy" previousFont)
        _udp_saved_legacy=$(_ud_value "$_udp_pending_legacy" previousLegacy)
        [ -n "$_udp_saved_font" ] && UD_PREVIOUS_FONT="$_udp_saved_font"
        # A queued legacy request does not change the current boot. If Universal
        # runtime is still active, the payload we may need to recover is Universal.
        if [ -s "$CONFIG_DIR/universal-font-runtime.conf" ]; then
            UD_PREVIOUS_MODE=universal
            UD_PREVIOUS_LEGACY=false
        elif [ "$_udp_saved_legacy" = true ]; then
            UD_PREVIOUS_MODE=legacy
            UD_PREVIOUS_LEGACY=true
        elif [ "$UD_PREVIOUS_FONT" = default ]; then
            UD_PREVIOUS_MODE=default
        else
            UD_PREVIOUS_MODE=classic
        fi
    fi

    if [ -z "$UD_PREVIOUS_MODE" ]; then
        if [ -s "$CONFIG_DIR/universal-font-runtime.conf" ]; then
            UD_PREVIOUS_MODE=universal
        elif [ -s "$CONFIG_DIR/font_runtime_legacy_v14_4.conf" ]; then
            UD_PREVIOUS_MODE=legacy
            UD_PREVIOUS_LEGACY=true
        elif [ "$UD_PREVIOUS_FONT" = default ]; then
            UD_PREVIOUS_MODE=default
        else
            UD_PREVIOUS_MODE=classic
        fi
    fi

    UD_PREVIOUS_DEPLOYMENT_ID=$(_ud_value "$CONFIG_DIR/universal-font-runtime.conf" deploymentId)
    UD_PREVIOUS_PAYLOAD_DIGEST=$(_ud_value "$CONFIG_DIR/universal-font-runtime.conf" payloadDigest)
}

_ud_stage_prepared_locked() {
    _uds_family="$1"
    [ -n "$_uds_family" ] || return 1
    _uds_manifest=$(_ud_manifest "$_uds_family") || return 1
    _uds_payload=$(_ud_payload "$_uds_family") || return 1
    _ud_validate "$_uds_family" >/dev/null 2>&1 || return 1

    _uds_values=$(_ud_manifest_identity "$_uds_manifest") || return 1
    _uds_id=$(printf '%s\n' "$_uds_values" | sed -n '1p')
    _uds_digest=$(printf '%s\n' "$_uds_values" | sed -n '2p')
    [ -n "$_uds_id" ] && [ -n "$_uds_digest" ] || return 1

    _ud_capture_previous
    _uds_label="$_uds_family"
    if [ "${LUOSHU_SWITCH_ACTIVE_LABEL:-}" = mix ]; then
        _uds_request=$(_ud_value "$CONFIG_DIR/mix-stage-next.conf" requestId)
        [ -n "${LUOSHU_MIX_REQUEST_ID:-}" ] && [ "$_uds_request" = "$LUOSHU_MIX_REQUEST_ID" ] || return 1
        [ "$(_ud_value "$CONFIG_DIR/mix-stage-next.conf" state)" != cancelled ] || return 1
        _uds_label=mix
        # Fixed compositor may already have written its configured selection.
        _uds_previous=$(_ud_value "$CONFIG_DIR/mix-stage-next.conf" previousFont)
        if [ ! -s "$CONFIG_DIR/universal-font-next.conf" ] && [ ! -s "$CONFIG_DIR/font-payload-next.conf" ]; then
            [ -z "$_uds_previous" ] || UD_PREVIOUS_FONT="$_uds_previous"
        fi
    fi

    _uds_next="$MODDIR/.luoshu-payload-next"
    _uds_stage="$MODDIR/.luoshu-payload-next.stage.$$"
    rm -rf "$_uds_stage" 2>/dev/null || true
    mkdir -p "$_uds_stage" "$CONFIG_DIR" 2>/dev/null || return 1
    cp -af "$_uds_payload/." "$_uds_stage/" 2>/dev/null || {
        rm -rf "$_uds_stage" 2>/dev/null || true
        return 1
    }

    if [ "$_uds_label" = mix ] && { [ "$(_ud_value "$CONFIG_DIR/mix-stage-next.conf" requestId)" != "$LUOSHU_MIX_REQUEST_ID" ] || [ "$(_ud_value "$CONFIG_DIR/mix-stage-next.conf" state)" = cancelled ]; }; then
        rm -rf "$_uds_stage" 2>/dev/null || true
        return 1
    fi
    # Universal and legacy next-boot markers are mutually exclusive.
    rm -f "$CONFIG_DIR/font-payload-next.conf" 2>/dev/null || true
    rm -rf "$_uds_next" 2>/dev/null || true
    mv "$_uds_stage" "$_uds_next" 2>/dev/null || {
        rm -rf "$_uds_stage" 2>/dev/null || true
        return 1
    }

    _uds_state="$CONFIG_DIR/universal-font-next.conf"
    {
        printf 'state=prepared\n'
        printf 'font=%s\n' "$_uds_label"
        [ "$_uds_label" != mix ] || printf 'requestId=%s\n' "$LUOSHU_MIX_REQUEST_ID"
        printf 'deploymentId=%s\n' "$_uds_id"
        printf 'payloadDigest=%s\n' "$_uds_digest"
        printf 'previousFont=%s\n' "$UD_PREVIOUS_FONT"
        printf 'previousMode=%s\n' "$UD_PREVIOUS_MODE"
        printf 'previousLegacy=%s\n' "$UD_PREVIOUS_LEGACY"
        printf 'previousDeploymentId=%s\n' "$UD_PREVIOUS_DEPLOYMENT_ID"
        printf 'previousPayloadDigest=%s\n' "$UD_PREVIOUS_PAYLOAD_DIGEST"
        printf 'recovery=false\n'
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_uds_state.tmp.$$" 2>/dev/null && mv -f "$_uds_state.tmp.$$" "$_uds_state" 2>/dev/null || {
        rm -f "$_uds_state" "$_uds_state.tmp.$$" "$CONFIG_DIR/text_reboot_required.conf" 2>/dev/null || true
        rm -rf "$_uds_next" 2>/dev/null || true
        return 1
    }
    chmod 0600 "$_uds_state" 2>/dev/null || true

    # active_font.conf is the user's configured selection, not a claim that this
    # boot already renders it. Keep it in sync immediately; App status uses the
    # reboot marker/effectiveActive to distinguish configured vs. effective font.
    _uds_active="$CONFIG_DIR/active_font.conf"
    printf '%s\n' "$_uds_label" > "$_uds_active.tmp.$$" 2>/dev/null && \
        mv -f "$_uds_active.tmp.$$" "$_uds_active" 2>/dev/null || {
            rm -f "$_uds_state" "$_uds_active.tmp.$$" "$CONFIG_DIR/text_reboot_required.conf" 2>/dev/null || true
            rm -rf "$_uds_next" 2>/dev/null || true
            printf '%s\n' "$UD_PREVIOUS_FONT" > "$_uds_active" 2>/dev/null || true
            return 1
        }
    chmod 0644 "$_uds_active" 2>/dev/null || true

    _uds_reboot="$CONFIG_DIR/text_reboot_required.conf"
    {
        printf 'font=%s\n' "$_uds_label"
        [ "$_uds_label" != mix ] || printf 'requestId=%s\n' "$LUOSHU_MIX_REQUEST_ID"
        printf 'reason=universal-next-boot-prepared\n'
        printf 'pipeline=universal-font-deployment-v1\n'
        printf 'deploymentId=%s\n' "$_uds_id"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_uds_reboot.tmp.$$" 2>/dev/null && mv -f "$_uds_reboot.tmp.$$" "$_uds_reboot" 2>/dev/null || {
        rm -f "$_uds_state" "$_uds_reboot" "$_uds_reboot.tmp.$$" 2>/dev/null || true
        rm -rf "$_uds_next" 2>/dev/null || true
        printf '%s\n' "$UD_PREVIOUS_FONT" > "$_uds_active" 2>/dev/null || true
        chmod 0644 "$_uds_active" 2>/dev/null || true
        return 1
    }
    chmod 0644 "$_uds_reboot" 2>/dev/null || true
    rm -f "$CONFIG_DIR/universal-font-rollback.conf" 2>/dev/null || true
    {
        printf 'state=staged\nfont=%s\ndecision=universal\nreason=ready-next-boot\n' "$_uds_label"
    } > "$CONFIG_DIR/universal-font-cutover.conf.tmp.$$" &&
        mv -f "$CONFIG_DIR/universal-font-cutover.conf.tmp.$$" "$CONFIG_DIR/universal-font-cutover.conf" || true

    printf '{"status":"ok","state":"staged-next-boot","pipeline":"universal","fallback":false,"deploymentId":"%s","previousMode":"%s"}\n' \
        "$_uds_id" "$UD_PREVIOUS_MODE"
}

_ud_stage_prepared() {
    type luoshu_payload_commit_run >/dev/null 2>&1 || return 1
    luoshu_payload_commit_run "$MODDIR" _ud_stage_prepared_locked "$@"
}

_ud_stage_next() {
    _uds_family="$1"
    _ud_prepare "$_uds_family" >/dev/null || return $?
    _ud_stage_prepared "$_uds_family"
}

case "${1:-prepare}" in
    prepare|build|refresh) _ud_prepare "${2:-}" ;;
    validate) _ud_validate "${2:-}" ;;
    manifest|path) _ud_manifest "${2:-}" ;;
    payload) _ud_payload "${2:-}" ;;
    stage-prepared) _ud_stage_prepared "${2:-}" ;;
    stage-next) _ud_stage_next "${2:-}" ;;
    *)
        echo "Usage: $0 {prepare|validate|manifest|payload|stage-prepared|stage-next} <font-family>" >&2
        exit 2
        ;;
esac
