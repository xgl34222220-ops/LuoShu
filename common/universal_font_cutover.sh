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
ROUTE_BRIDGE="${LUOSHU_ROUTE_BRIDGE:-$MODDIR/common/minimal_xml_router.sh}"
COMPILER_BRIDGE="$MODDIR/common/universal_font_compiler.sh"
GATE="$MODDIR/common/universal_font_cutover_gate.py"
DEPLOYER="$MODDIR/common/universal_font_deployment.py"
ACTIVATED_CONF="$CONFIG_DIR/universal-font-activated.conf"
VERIFY_CONF="$CONFIG_DIR/universal-font-runtime-verification.conf"
ROLLBACK_STATE="$CONFIG_DIR/universal-font-rollback.conf"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"
CUTOVER_STATE="$CONFIG_DIR/universal-font-cutover.conf"
LOG_FILE="$MODDIR/logs/fontswitch.log"
PROGRESS_FILE="${LUOSHU_SWITCH_PROGRESS_FILE:-}"


# Shared short-lived commit lease; source beside this script for host fixtures too.
for _lpc_helper in "$MODDIR/common/payload_commit_lock.sh" "${0%/*}/payload_commit_lock.sh" "${0%/*}/../payload_commit_lock.sh"; do
    [ ! -f "$_lpc_helper" ] || { . "$_lpc_helper"; break; }
done

_uc_log() {
    mkdir -p "$MODDIR/logs" 2>/dev/null || true
    printf '[%s] [CUTOVER] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$*" >> "$LOG_FILE" 2>/dev/null || true
}

_uc_progress() {
    _ucp_percent="$1"; shift
    [ -n "$PROGRESS_FILE" ] || return 0
    {
        if [ "${UC_COMPOSITE_REQUEST:-false}" = true ]; then
            printf 'requestId=%s\nstate=running\nupdated=%s\n' "$LUOSHU_MIX_REQUEST_ID" "$(date +%s)"
            _ucp_percent=$((80 + _ucp_percent * 16 / 100))
        fi
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

_uc_value() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

_uc_capture_prepare_failure() {
    [ "${UC_COMPOSITE_REQUEST:-false}" = true ] || return 0
    [ -n "$PROGRESS_FILE" ] && [ -s "$PROGRESS_FILE" ] || return 0
    # Fallback updates the UI phase. Keep the last actual compiler phase first,
    # so a timeout can be diagnosed without running another long compilation.
    _uc_last="$CONFIG_DIR/universal-mixed-last-prepare.conf"
    cp -f "$PROGRESS_FILE" "$_uc_last.tmp.$$" 2>/dev/null || return 0
    if [ "$(_uc_value "$_uc_last.tmp.$$" requestId)" != "${LUOSHU_MIX_REQUEST_ID:-}" ]; then
        rm -f "$_uc_last.tmp.$$"
        return 0
    fi
    mv -f "$_uc_last.tmp.$$" "$_uc_last" 2>/dev/null || return 0
    _uc_log "universal prepare last phase request=$LUOSHU_MIX_REQUEST_ID percent=$(_uc_value "$_uc_last" percent) message=$(_uc_value "$_uc_last" message) updated=$(_uc_value "$_uc_last" updated)"
    # The existing App already exports fontswitch.log. Include bounded phase
    # records (no font filenames) so this evidence needs no APK update.
    if [ -s "$CONFIG_DIR/universal-compile-trace.jsonl" ]; then
        grep -F "\"requestId\":\"$LUOSHU_MIX_REQUEST_ID\"" "$CONFIG_DIR/universal-compile-trace.jsonl" | \
            grep -F '"event":"phase"' | tail -n 4 | while IFS= read -r _uc_trace; do
                _uc_log "universal prepare phase trace $_uc_trace"
            done
    fi
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
    [ "${UC_COMPOSITE_REQUEST:-false}" != true ] || _ucs_font=mix
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

# Scope cleanup is appended after the compiler JSON. Preserve the actionable
# error before applying the short log budget, rather than truncating it away.
_uc_failure_summary() {
    _ucfs_error=$(printf '%s\n' "$1" | grep -E '"status"[[:space:]]*:[[:space:]]*"error"' | tail -n 1)
    if [ -n "$_ucfs_error" ]; then
        printf '%s' "$_ucfs_error" | tail -c 600
    else
        printf '%s' "$1" | tail -c 600
    fi
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
    _uc_progress 25 "通用引擎未接管，正在使用兼容切换路径"
    # Composite caller owns its already-generated legacy fallback. Leave an
    # existing queued payload untouched until that caller can commit successfully.
    [ "${UC_COMPOSITE_REQUEST:-false}" != true ] || return 2

    # A queued Universal request updates active_font.conf to the user's configured
    # choice before reboot. If this new request falls back to legacy, restore the
    # queued request's previousFont first so the legacy switcher records the real
    # current-boot font as its rollback source.

    # Legacy commits supersede pending payloads only after successful preparation.
    [ -f "$LEGACY_SWITCH" ] || {
        printf '{"status":"error","message":"缺少兼容字体切换核心"}\n'
        return 1
    }
    MODDIR="$MODDIR" MODULE_DIR="$MODDIR" LUOSHU_PUBLIC_DIR="$PUBLIC_DIR" \
        sh "$LEGACY_SWITCH" action switch "$_ucl_font"
}

_uc_precondition() {
    mkdir -p "$MODDIR/logs" 2>/dev/null || return 1
    if [ -f "$MODDIR/common/font_topology_snapshot.sh" ]; then
        MODDIR="$MODDIR" MODULE_DIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" \
            sh "$MODDIR/common/font_topology_snapshot.sh" ensure >> "$LOG_FILE" 2>&1 || return 1
    fi
    [ -s "$CONFIG_DIR/device_font_topology.json" ] || return 1
    [ -s "$CONFIG_DIR/device_font_roles.json" ] || return 1
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
    if [ -n "${LUOSHU_REAL_MODDIR:-}" ] && [ "${UC_COMPOSITE_REQUEST:-false}" != true ]; then
        _uc_legacy "$_uc_font" composite-runtime
        return $?
    fi
    if [ "${UC_COMPOSITE_REQUEST:-false}" != true ]; then
        case "$_uc_font" in
            mix|LuoShuAutoMix|LuoShuMix*) _uc_legacy "$_uc_font" composite-family; return $? ;;
        esac
    fi

    if ! _uc_precondition; then
        _uc_legacy "$_uc_font" universal-precondition-missing
        return $?
    fi

    _uc_write_state preparing "$_uc_font" universal preparing
    _uc_progress 8 "通用引擎正在分析设备字体拓扑"
    _uc_log "universal prepare start font=$_uc_font"
    if [ "${UC_COMPOSITE_REQUEST:-false}" = true ] && [ -f "$MODDIR/common/task_scope.py" ]; then
        _uc_prepare_output=$(MODDIR="$MODDIR" MODULE_DIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" \
            LUOSHU_PUBLIC_DIR="$PUBLIC_DIR" _uc_python "$MODDIR/common/task_scope.py" \
            --task "$LUOSHU_MIX_REQUEST_ID" --timeout "${LUOSHU_MIX_PREPARE_TIMEOUT:-180}" \
            -- sh "$DEPLOYMENT" prepare "$_uc_font" 2>&1)
        _uc_prepare_rc=$?
    else
        _uc_prepare_output=$(MODDIR="$MODDIR" MODULE_DIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" \
            LUOSHU_PUBLIC_DIR="$PUBLIC_DIR" sh "$DEPLOYMENT" prepare "$_uc_font" 2>&1)
        _uc_prepare_rc=$?
    fi
    if [ "$_uc_prepare_rc" -ne 0 ]; then
        _uc_capture_prepare_failure
        _uc_log "universal prepare failed font=$_uc_font rc=$_uc_prepare_rc output=$(_uc_failure_summary "$_uc_prepare_output")"
        _uc_scope_cleanup=$(printf '%s\n' "$_uc_prepare_output" | grep '^\[TASK-CLEANUP\]' | tail -n 1)
        [ -z "$_uc_scope_cleanup" ] || _uc_log "universal prepare cleanup: $_uc_scope_cleanup"
        _uc_reason=universal-prepare-failed
        [ "$_uc_prepare_rc" -ne 124 ] || _uc_reason=universal-prepare-timeout
        _uc_legacy "$_uc_font" "$_uc_reason"
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

    if [ "${UC_COMPOSITE_REQUEST:-false}" = true ]; then
        _uc_python - "$UC_ROUTE" "$CONFIG_DIR/universal-mixed-coverage.conf" "$LUOSHU_MIX_REQUEST_ID" "$UC_ARTIFACTS" <<'PYCOVER'
import json,os,sys
from pathlib import Path
route=json.loads(Path(sys.argv[1]).read_text())
count=len(route.get('preservedRoutes') or [])+int(route.get('summary',{}).get('preservedOriginalStyleCount') or 0)
deferred=int(route.get('summary',{}).get('representationDeferralCount') or 0)
artifacts=json.loads(Path(sys.argv[4]).read_text())
math_count=sum(int((item.get('report', {}).get('transformed', {}).get('layout', {}) or {}).get('preservedMathGlyphs') or 0)
               for item in artifacts.get('artifacts', []))
mark_count=sum(int((item.get('report', {}).get('transformed', {}).get('layout', {}) or {}).get('preservedSharedMarks') or 0)
               for item in artifacts.get('artifacts', []))
clock_count=sum(int((item.get('report', {}).get('transformed', {}).get('layout', {}) or {}).get('preservedClockPunctuation') or 0)
                for item in artifacts.get('artifacts', []))
coverage='partial-protected-typography' if math_count or mark_count or clock_count else ('partial-style-preserved' if count or deferred else 'planned-targets')
parts=[]
if count: parts.append('保留 %s 条原厂样式路由' % count)
if deferred: parts.append('%s 条路由仍使用已验证兼容表示' % deferred)
if math_count: parts.append('保留 %s 处数学/专用字形' % math_count)
if mark_count: parts.append('保留 %s 处跨文字共享标记' % mark_count)
if clock_count: parts.append('保留 %s 处原厂钟表标点' % clock_count)
message=('通用引擎已准备，'+ '，'.join(parts)+'（部分覆盖），请完整重启'
         if parts else '通用引擎字体负载已准备，请完整重启')
p=Path(sys.argv[2]);tmp=p.with_name(p.name+'.tmp.'+str(os.getpid()))
tmp.write_text('requestId='+sys.argv[3]+'\ncoverage='+coverage+'\npreservedStyleRoutes='+str(count)+'\nrepresentationDeferrals='+str(deferred)+'\npreservedMathGlyphs='+str(math_count)+'\npreservedSharedMarks='+str(mark_count)+'\npreservedClockPunctuation='+str(clock_count)+'\nmessage='+message+'\n')
os.replace(tmp,p)
PYCOVER
        _uc_log "mixed coverage: $(_uc_value "$CONFIG_DIR/universal-mixed-coverage.conf" message)"
    fi
    # Deployment commits the staged selection/status under the shared lease.
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

_uc_schedule_rollback_locked() {
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

_uc_schedule_rollback() {
    type luoshu_payload_commit_run >/dev/null 2>&1 || return 1
    luoshu_payload_commit_run "$MODDIR" _uc_schedule_rollback_locked "$@"
}

case "${1:-switch}" in
    switch) _uc_switch "${2:-}" ;;
    prepare-mixed)
        [ "${LUOSHU_SWITCH_ACTIVE_LABEL:-}" = mix ] && [ -n "${LUOSHU_MIX_REQUEST_ID:-}" ] || exit 1
        _uc_python "$MODDIR/common/universal_mixed_font.py" --module "$MODDIR" \
            --request "$LUOSHU_MIX_REQUEST_ID" --check || exit 1
        UC_COMPOSITE_REQUEST=true
        _uc_switch "${2:-}"
        ;;
    rollback-from-fail) _uc_schedule_rollback "${2:-}" ;;
    status)
        if [ -s "$CUTOVER_STATE" ]; then cat "$CUTOVER_STATE"
        else printf 'state=idle\ndecision=none\n'
        fi
        ;;
    *) echo "Usage: $0 {switch|rollback-from-fail|status} [font-family|boot-id]" >&2; exit 2 ;;
esac
