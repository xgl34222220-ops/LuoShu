#!/system/bin/sh
# Phase 9 controlled production cutover controller.
# Official single-font switches try Universal first and fall back to the existing
# production switcher without ever rewriting the current boot's live payload.
set +e

MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
MODULE_DIR="$MODDIR"
CONFIG_DIR="${CONFIG_DIR:-$MODDIR/config}"
PUBLIC_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}"
LEGACY_SWITCH="$MODDIR/common/legacy_v14_4/font_switch_safe.sh"
DEPLOYMENT="$MODDIR/common/universal_font_deployment.sh"
PLAN_BRIDGE="$MODDIR/common/universal_font_plan.sh"
ROUTE_BRIDGE="$MODDIR/common/minimal_xml_router.sh"
COMPILER_BRIDGE="$MODDIR/common/universal_font_compiler.sh"
GATE="$MODDIR/common/universal_font_cutover_gate.py"
DEPLOYER="$MODDIR/common/universal_font_deployment.py"
TOPOLOGY_REFRESH="$MODDIR/common/font_topology_snapshot.sh"
ROLE_REFRESH="$MODDIR/common/font_role_shadow.sh"
STOCK_INVENTORY="$CONFIG_DIR/device_font_inventory.json"
TOPOLOGY_JSON="$CONFIG_DIR/device_font_topology.json"
ROLES_JSON="$CONFIG_DIR/device_font_roles.json"
ACTIVATED_CONF="$CONFIG_DIR/universal-font-activated.conf"
VERIFY_CONF="$CONFIG_DIR/universal-font-runtime-verification.conf"
ROLLBACK_STATE="$CONFIG_DIR/universal-font-rollback.conf"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"
CUTOVER_STATE="$CONFIG_DIR/universal-font-cutover.conf"
LOG_FILE="$MODDIR/logs/fontswitch.log"
PROGRESS_FILE="${LUOSHU_SWITCH_PROGRESS_FILE:-}"

_uc_log() {
    mkdir -p "$MODDIR/logs" 2>/dev/null || true
    printf '[%s] [CUTOVER] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$*" >> "$LOG_FILE" 2>/dev/null || true
}

_uc_progress() {
    _ucp_percent="$1"; shift
    [ -n "$PROGRESS_FILE" ] || return 0
    {
        printf 'percent=%s\n' "$_ucp_percent"
        printf 'message=%s\n' "$*"
    } > "$PROGRESS_FILE.tmp.$$" 2>/dev/null && mv -f "$PROGRESS_FILE.tmp.$$" "$PROGRESS_FILE" 2>/dev/null || true
}

_uc_python() {
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

_uc_json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

_uc_repair_prerequisites() {
    # Phase 9 should not silently fall back just because install/boot-time
    # discovery has not materialized its derived files yet. Repair only the
    # read-only discovery products here; never mutate the live font payload.
    if [ ! -s "$TOPOLOGY_JSON" ] && [ -s "$STOCK_INVENTORY" ] && [ -f "$TOPOLOGY_REFRESH" ]; then
        _uc_log "repairing missing topology before cutover"
        MODDIR="$MODDIR" MODULE_DIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" \
            sh "$TOPOLOGY_REFRESH" refresh >>"$LOG_FILE" 2>&1 || true
    fi

    if [ -s "$TOPOLOGY_JSON" ] && [ -f "$ROLE_REFRESH" ]; then
        if [ ! -s "$ROLES_JSON" ] || ! MODDIR="$MODDIR" MODULE_DIR="$MODDIR" \
            sh "$ROLE_REFRESH" validate >/dev/null 2>&1; then
            _uc_log "repairing missing/stale role map before cutover"
            MODDIR="$MODDIR" MODULE_DIR="$MODDIR" \
                sh "$ROLE_REFRESH" refresh >>"$LOG_FILE" 2>&1 || true
        fi
    fi
}

_uc_value() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

_uc_json_identity() {
    _ucj_manifest="$1"
    _uc_python - "$_ucj_manifest" <<'PY'
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8'))
print(p.get('deploymentId',''))
print(p.get('payloadDigest',''))
PY
}


_uc_write_state() {
    _ucs_state="$1"; _ucs_font="$2"; _ucs_decision="$3"; _ucs_reason="$4"
    mkdir -p "$CONFIG_DIR" 2>/dev/null || true
    {
        printf 'state=%s\n' "$_ucs_state"
        printf 'font=%s\n' "$_ucs_font"
        printf 'decision=%s\n' "$_ucs_decision"
        printf 'reason=%s\n' "$_ucs_reason"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$CUTOVER_STATE.tmp.$$" 2>/dev/null && mv -f "$CUTOVER_STATE.tmp.$$" "$CUTOVER_STATE" 2>/dev/null || true
    chmod 0644 "$CUTOVER_STATE" 2>/dev/null || true
}

_uc_cleanup_universal_next() {
    rm -f "$CONFIG_DIR/universal-font-next.conf" 2>/dev/null || true
    # A switch request supersedes any previously queued next-boot payload.
    rm -rf "$MODDIR/.luoshu-payload-next" "$MODDIR"/.luoshu-payload-next.stage.* 2>/dev/null || true
}

_uc_legacy() {
    _ucl_font="$1"; _ucl_reason="$2"
    _uc_log "legacy fallback font=$_ucl_font reason=$_ucl_reason"
    _uc_write_state fallback "$_ucl_font" legacy "$_ucl_reason"
    _uc_progress 25 "Universal 未接管，正在使用兼容引擎"

    # A queued Universal request updates active_font.conf to the user's configured
    # choice before reboot. If this new request falls back to legacy, restore the
    # queued request's previousFont first so the legacy switcher records the real
    # current-boot font as its rollback source.
    if [ -s "$CONFIG_DIR/universal-font-next.conf" ]; then
        _ucl_live_font=$(_uc_value "$CONFIG_DIR/universal-font-next.conf" previousFont)
        if [ -n "$_ucl_live_font" ]; then
            printf '%s\n' "$_ucl_live_font" > "$CONFIG_DIR/active_font.conf.tmp.$" 2>/dev/null && \
                mv -f "$CONFIG_DIR/active_font.conf.tmp.$" "$CONFIG_DIR/active_font.conf" 2>/dev/null || true
            chmod 0644 "$CONFIG_DIR/active_font.conf" 2>/dev/null || true
        fi
    fi

    _uc_cleanup_universal_next
    [ -f "$LEGACY_SWITCH" ] || {
        printf '{"status":"error","message":"缺少兼容字体切换核心"}\n'
        return 1
    }

    _ucl_output=$(MODDIR="$MODDIR" MODULE_DIR="$MODDIR" LUOSHU_PUBLIC_DIR="$PUBLIC_DIR" \
        sh "$LEGACY_SWITCH" action switch "$_ucl_font" 2>&1)
    _ucl_rc=$?
    if [ "$_ucl_rc" -eq 0 ] && printf '%s\n' "$_ucl_output" | grep -q '"status":"ok"'; then
        _ucl_message=$(printf '%s\n' "$_ucl_output" | sed -n 's/.*"message":"\([^"]*\)".*/\1/p' | tail -n1)
        [ -n "$_ucl_message" ] || _ucl_message="兼容字体引擎已准备完成"
        printf '{"status":"ok","state":"legacy-fallback","pipeline":"legacy","fallback":true,"fallbackReason":"%s","message":"%s"}\n' \
            "$(_uc_json_escape "$_ucl_reason")" "$(_uc_json_escape "$_ucl_message")"
        return 0
    fi
    printf '%s\n' "$_ucl_output"
    return "$_ucl_rc"
}

_uc_precondition() {
    _uc_repair_prerequisites
    [ -s "$TOPOLOGY_JSON" ] || return 1
    [ -s "$ROLES_JSON" ] || return 1
    [ -f "$DEPLOYMENT" ] || return 1
    [ -f "$GATE" ] || return 1
    [ -f "$PLAN_BRIDGE" ] || return 1
    [ -f "$ROUTE_BRIDGE" ] || return 1
    [ -f "$COMPILER_BRIDGE" ] || return 1
    return 0
}

_uc_paths() {
    _ucx_font="$1"
    UC_PLAN=$(MODDIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" sh "$PLAN_BRIDGE" path "$_ucx_font") || return 1
    UC_ROUTE=$(MODDIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" sh "$ROUTE_BRIDGE" path "$_ucx_font") || return 1
    UC_ARTIFACTS=$(MODDIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" sh "$COMPILER_BRIDGE" manifest "$_ucx_font") || return 1
    UC_DEPLOYMENT=$(MODDIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" sh "$DEPLOYMENT" manifest "$_ucx_font") || return 1
    UC_PAYLOAD=$(MODDIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" sh "$DEPLOYMENT" payload "$_ucx_font") || return 1
    [ -s "$UC_PLAN" ] && [ -s "$UC_ROUTE" ] && [ -s "$UC_ARTIFACTS" ] && [ -s "$UC_DEPLOYMENT" ] && [ -d "$UC_PAYLOAD" ]
}

_uc_switch() {
    _uc_font="$1"
    [ -n "$_uc_font" ] || { printf '{"status":"error","message":"未指定字体"}\n'; return 1; }
    # A new explicit user choice supersedes any previously staged automatic rollback.
    rm -f "$ROLLBACK_STATE" 2>/dev/null || true

    # System default and composite temporary families stay on the proven legacy
    # production path during controlled rollout.
    if [ "$_uc_font" = default ]; then
        _uc_legacy "$_uc_font" default-font
        return $?
    fi
    if [ -n "${LUOSHU_REAL_MODDIR:-}" ]; then
        _uc_legacy "$_uc_font" composite-runtime
        return $?
    fi
    case "$_uc_font" in
        mix|LuoShuAutoMix|LuoShuMix*) _uc_legacy "$_uc_font" composite-family; return $? ;;
    esac

    if ! _uc_precondition; then
        _uc_legacy "$_uc_font" universal-precondition-missing
        return $?
    fi

    _uc_write_state preparing "$_uc_font" universal preparing
    _uc_progress 8 "通用引擎正在分析设备字体拓扑"
    _uc_log "universal prepare start font=$_uc_font"
    _uc_prepare_output=$(MODDIR="$MODDIR" MODULE_DIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" \
        LUOSHU_PUBLIC_DIR="$PUBLIC_DIR" sh "$DEPLOYMENT" prepare "$_uc_font" 2>&1)
    _uc_prepare_rc=$?
    if [ "$_uc_prepare_rc" -ne 0 ]; then
        _uc_log "universal prepare failed font=$_uc_font rc=$_uc_prepare_rc output=$(printf '%s' "$_uc_prepare_output" | tail -c 600)"
        _uc_legacy "$_uc_font" universal-prepare-failed
        return $?
    fi

    _uc_progress 72 "正在检查正式接管安全条件"
    if ! _uc_paths "$_uc_font"; then
        _uc_legacy "$_uc_font" universal-artifacts-missing
        return $?
    fi

    _uc_gate_output=$(_uc_python "$GATE" \
        --font-plan "$UC_PLAN" \
        --route-plan "$UC_ROUTE" \
        --artifact-manifest "$UC_ARTIFACTS" \
        --deployment "$UC_DEPLOYMENT" \
        --payload-root "$UC_PAYLOAD" 2>&1)
    _uc_gate_rc=$?
    _uc_log "gate font=$_uc_font rc=$_uc_gate_rc result=$_uc_gate_output"
    if [ "$_uc_gate_rc" -ne 0 ] || ! printf '%s' "$_uc_gate_output" | grep -q '"eligible":true'; then
        _uc_legacy "$_uc_font" universal-readiness-gate-rejected
        return $?
    fi

    _uc_progress 88 "通用引擎验证通过，正在准备下一次启动"
    _uc_stage_output=$(MODDIR="$MODDIR" MODULE_DIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" \
        LUOSHU_PUBLIC_DIR="$PUBLIC_DIR" sh "$DEPLOYMENT" stage-prepared "$_uc_font" 2>&1)
    _uc_stage_rc=$?
    if [ "$_uc_stage_rc" -ne 0 ] || ! printf '%s' "$_uc_stage_output" | grep -q '"status":"ok"'; then
        _uc_log "universal stage failed font=$_uc_font rc=$_uc_stage_rc output=$_uc_stage_output"
        _uc_legacy "$_uc_font" universal-stage-failed
        return $?
    fi

    _uc_write_state staged "$_uc_font" universal ready-next-boot
    _uc_progress 96 "通用字体负载已准备，完整重启后自动验收"
    printf '%s\n' "$_uc_stage_output"
    return 0
}

_uc_write_rollback_state() {
    _ucr_state="$1"; _ucr_target_font="$2"; _ucr_target_mode="$3"; _ucr_reason="$4"; _ucr_source="$5"
    {
        printf 'state=%s\n' "$_ucr_state"
        printf 'targetFont=%s\n' "$_ucr_target_font"
        printf 'targetMode=%s\n' "$_ucr_target_mode"
        printf 'reason=%s\n' "$_ucr_reason"
        printf 'source=%s\n' "$_ucr_source"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$ROLLBACK_STATE.tmp.$$" 2>/dev/null && mv -f "$ROLLBACK_STATE.tmp.$$" "$ROLLBACK_STATE" 2>/dev/null || true
    chmod 0600 "$ROLLBACK_STATE" 2>/dev/null || true
}

_uc_copy_retired_to_next() {
    _ucr_source="$1"
    _ucr_stage="$MODDIR/.luoshu-payload-next.recovery.$$"
    _ucr_next="$MODDIR/.luoshu-payload-next"
    rm -rf "$_ucr_stage" 2>/dev/null || true
    mkdir -p "$_ucr_stage" 2>/dev/null || return 1
    cp -af "$_ucr_source/." "$_ucr_stage/" 2>/dev/null || {
        rm -rf "$_ucr_stage" 2>/dev/null || true
        return 1
    }
    rm -rf "$_ucr_next" 2>/dev/null || true
    mv "$_ucr_stage" "$_ucr_next" 2>/dev/null || {
        rm -rf "$_ucr_stage" 2>/dev/null || true
        return 1
    }
    return 0
}

_uc_prepare_empty_next() {
    _uce_stage="$MODDIR/.luoshu-payload-next.default.$$"
    _uce_next="$MODDIR/.luoshu-payload-next"
    rm -rf "$_uce_stage" 2>/dev/null || true
    mkdir -p "$_uce_stage" 2>/dev/null || return 1
    rm -rf "$_uce_next" 2>/dev/null || true
    mv "$_uce_stage" "$_uce_next" 2>/dev/null || {
        rm -rf "$_uce_stage" 2>/dev/null || true
        return 1
    }
    return 0
}

_uc_schedule_rollback() {
    _ucr_boot="${1:-}"
    [ -s "$VERIFY_CONF" ] || return 2
    [ "$(_uc_value "$VERIFY_CONF" grade)" = FAIL ] || return 2
    [ -s "$ACTIVATED_CONF" ] || return 2

    _ucr_verified_boot=$(_uc_value "$VERIFY_CONF" bootId)
    _ucr_activated_boot=$(_uc_value "$ACTIVATED_CONF" bootId)
    [ -n "$_ucr_boot" ] || _ucr_boot="$_ucr_verified_boot"
    [ -n "$_ucr_boot" ] && [ "$_ucr_verified_boot" = "$_ucr_boot" ] && [ "$_ucr_activated_boot" = "$_ucr_boot" ] || {
        _uc_write_rollback_state skipped '' '' boot-identity-mismatch ''
        return 2
    }

    _ucr_recovery=$(_uc_value "$ACTIVATED_CONF" recovery)
    if [ "$_ucr_recovery" = true ]; then
        _uc_write_rollback_state suppressed '' '' recovery-already-attempted ''
        _uc_log "rollback suppressed: current deployment is already a recovery activation"
        return 2
    fi

    # Never overwrite a newer user request created after boot.
    if [ -s "$CONFIG_DIR/universal-font-next.conf" ] || [ -s "$CONFIG_DIR/font-payload-next.conf" ] || [ -d "$MODDIR/.luoshu-payload-next" ]; then
        _uc_write_rollback_state deferred '' '' newer-next-boot-request-present ''
        _uc_log "rollback deferred because a newer next-boot request already exists"
        return 2
    fi

    _ucr_previous_font=$(_uc_value "$ACTIVATED_CONF" previousFont)
    _ucr_previous_mode=$(_uc_value "$ACTIVATED_CONF" previousMode)
    _ucr_previous_legacy=$(_uc_value "$ACTIVATED_CONF" previousLegacy)
    _ucr_current_font=$(_uc_value "$ACTIVATED_CONF" font)
    [ -n "$_ucr_previous_font" ] || _ucr_previous_font=default
    [ -n "$_ucr_previous_mode" ] || {
        if [ "$_ucr_previous_legacy" = true ]; then _ucr_previous_mode=legacy
        elif [ "$_ucr_previous_font" = default ]; then _ucr_previous_mode=default
        else _ucr_previous_mode=classic
        fi
    }
    if [ "$_ucr_previous_font" = default ]; then
        _ucr_previous_mode=default
        _ucr_previous_legacy=false
    fi

    _ucr_retired=$(_uc_value "$ACTIVATED_CONF" retired)
    if [ "$_ucr_previous_mode" = default ]; then
        # System default has no previous LuoShu payload by design. Stage an
        # empty next payload so next_boot_payload can retire the failed
        # Universal payload and return to pure ROM font routing.
        _uc_prepare_empty_next || {
            _uc_write_rollback_state failed default default default-payload-stage-failed ''
            return 1
        }
        _ucr_retired=''
    else
        case "$_ucr_retired" in
            "$MODDIR"/.luoshu-retired/universal-*) ;;
            *)
                _uc_write_rollback_state failed "$_ucr_previous_font" "$_ucr_previous_mode" retired-path-untrusted "$_ucr_retired"
                return 1
                ;;
        esac
        [ -d "$_ucr_retired" ] || {
            _uc_write_rollback_state failed "$_ucr_previous_font" "$_ucr_previous_mode" retired-payload-missing "$_ucr_retired"
            return 1
        }
    fi

    if [ "$_ucr_previous_mode" = universal ]; then
        _ucr_manifest="$_ucr_retired/.luoshu-runtime/deployment/deployment.json"
        [ -f "$DEPLOYER" ] && [ -s "$_ucr_manifest" ] || {
            _uc_write_rollback_state failed "$_ucr_previous_font" universal retired-universal-manifest-missing "$_ucr_retired"
            return 1
        }
        _uc_python "$DEPLOYER" --payload-root "$_ucr_retired" --validate-payload-only "$_ucr_manifest" >/dev/null 2>&1 || {
            _uc_write_rollback_state failed "$_ucr_previous_font" universal retired-universal-integrity-failed "$_ucr_retired"
            return 1
        }
        _ucr_identity=$(_uc_json_identity "$_ucr_manifest") || return 1
        _ucr_id=$(printf '%s\n' "$_ucr_identity" | sed -n '1p')
        _ucr_digest=$(printf '%s\n' "$_ucr_identity" | sed -n '2p')
        [ -n "$_ucr_id" ] && [ -n "$_ucr_digest" ] || return 1
        _uc_copy_retired_to_next "$_ucr_retired" || return 1
        rm -f "$CONFIG_DIR/font-payload-next.conf" 2>/dev/null || true
        {
            printf 'state=prepared\n'
            printf 'font=%s\n' "$_ucr_previous_font"
            printf 'deploymentId=%s\n' "$_ucr_id"
            printf 'payloadDigest=%s\n' "$_ucr_digest"
            printf 'previousFont=%s\n' "${_ucr_current_font:-default}"
            printf 'previousMode=universal\n'
            printf 'previousLegacy=false\n'
            printf 'recovery=true\n'
            printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
        } > "$CONFIG_DIR/universal-font-next.conf.tmp.$$" 2>/dev/null && \
            mv -f "$CONFIG_DIR/universal-font-next.conf.tmp.$$" "$CONFIG_DIR/universal-font-next.conf" 2>/dev/null || {
                rm -f "$CONFIG_DIR/universal-font-next.conf" "$CONFIG_DIR/universal-font-next.conf.tmp.$$" 2>/dev/null || true
                rm -rf "$MODDIR/.luoshu-payload-next" 2>/dev/null || true
                _uc_write_rollback_state failed "$_ucr_previous_font" universal rollback-marker-write-failed "$_ucr_retired"
                return 1
            }
        chmod 0600 "$CONFIG_DIR/universal-font-next.conf" 2>/dev/null || true
    else
        if [ "$_ucr_previous_mode" != default ]; then
            _uc_copy_retired_to_next "$_ucr_retired" || return 1
        fi
        rm -f "$CONFIG_DIR/universal-font-next.conf" 2>/dev/null || true
        {
            printf 'state=prepared\n'
            printf 'font=%s\n' "$_ucr_previous_font"
            printf 'previousFont=%s\n' "${_ucr_current_font:-default}"
            printf 'previousLegacy=false\n'
            printf 'targetMode=%s\n' "$_ucr_previous_mode"
            printf 'recovery=true\n'
            printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
        } > "$CONFIG_DIR/font-payload-next.conf.tmp.$$" 2>/dev/null && \
            mv -f "$CONFIG_DIR/font-payload-next.conf.tmp.$$" "$CONFIG_DIR/font-payload-next.conf" 2>/dev/null || {
                rm -f "$CONFIG_DIR/font-payload-next.conf" "$CONFIG_DIR/font-payload-next.conf.tmp.$$" 2>/dev/null || true
                rm -rf "$MODDIR/.luoshu-payload-next" 2>/dev/null || true
                _uc_write_rollback_state failed "$_ucr_previous_font" "$_ucr_previous_mode" rollback-marker-write-failed "$_ucr_retired"
                return 1
            }
        chmod 0644 "$CONFIG_DIR/font-payload-next.conf" 2>/dev/null || true
    fi

    {
        printf 'font=%s\n' "$_ucr_previous_font"
        printf 'reason=universal-runtime-verification-failed-rollback\n'
        printf 'targetMode=%s\n' "$_ucr_previous_mode"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$CONFIG_DIR/text_reboot_required.conf.tmp.$$" 2>/dev/null && \
        mv -f "$CONFIG_DIR/text_reboot_required.conf.tmp.$$" "$CONFIG_DIR/text_reboot_required.conf" 2>/dev/null || {
            rm -f "$CONFIG_DIR/text_reboot_required.conf" "$CONFIG_DIR/text_reboot_required.conf.tmp.$$" \
                  "$CONFIG_DIR/universal-font-next.conf" "$CONFIG_DIR/font-payload-next.conf" 2>/dev/null || true
            rm -rf "$MODDIR/.luoshu-payload-next" 2>/dev/null || true
            _uc_write_rollback_state failed "$_ucr_previous_font" "$_ucr_previous_mode" reboot-marker-write-failed "$_ucr_retired"
            return 1
        }
    chmod 0644 "$CONFIG_DIR/text_reboot_required.conf" 2>/dev/null || true

    _uc_write_rollback_state staged "$_ucr_previous_font" "$_ucr_previous_mode" runtime-verification-failed "$_ucr_retired"
    _uc_write_state rollback-staged "${_ucr_current_font:-unknown}" rollback "$_ucr_previous_mode:$_ucr_previous_font"
    _uc_log "runtime FAIL rollback staged target=$_ucr_previous_font mode=$_ucr_previous_mode source=$_ucr_retired"
    printf '{"status":"ok","state":"rollback-staged","targetFont":"%s","targetMode":"%s"}\n' "$_ucr_previous_font" "$_ucr_previous_mode"
    return 0
}

case "${1:-switch}" in
    switch) _uc_switch "${2:-}" ;;
    rollback-from-fail) _uc_schedule_rollback "${2:-}" ;;
    status)
        if [ -s "$CUTOVER_STATE" ]; then cat "$CUTOVER_STATE"
        else printf 'state=idle\ndecision=none\n'
        fi
        ;;
    *) echo "Usage: $0 {switch|rollback-from-fail|status} [font-family|boot-id]" >&2; exit 2 ;;
esac
