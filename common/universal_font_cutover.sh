#!/system/bin/sh
# Phase 9 controlled production cutover controller.
# Every switch (single font, composite, system default) runs on Universal only.
# The legacy engine is retired: a Universal failure is reported and nothing is
# staged. The current boot's live payload is never rewritten.
set +e

MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
MODULE_DIR="$MODDIR"
CONFIG_DIR="${CONFIG_DIR:-$MODDIR/config}"
PUBLIC_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}"
ENGINE_BRIDGE="$MODDIR/common/luoshu_engine.sh"
DEPLOYER="$MODDIR/common/luoshu_payload.py"
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

# Universal stops starting new work 30 s before the switch timeout, so it can
# report a clear failure instead of being killed by the task supervisor.
_uc_budget_seconds() {
    _ucb_value="${LUOSHU_UNIVERSAL_BUDGET_SECONDS:-}"
    case "$_ucb_value" in
        ''|*[!0-9]*)
            _ucb_total="${LUOSHU_SWITCH_TIMEOUT_SECONDS:-360}"
            case "$_ucb_total" in ''|*[!0-9]*) _ucb_total=360 ;; esac
            _ucb_value=$((_ucb_total - 30))
            ;;
    esac
    [ "$_ucb_value" -ge 15 ] 2>/dev/null || _ucb_value=15
    printf '%s\n' "$_ucb_value"
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

_uc_precondition() {
    [ -s "$CONFIG_DIR/device_font_topology.json" ] || return 1
    [ -f "$ENGINE_BRIDGE" ] || return 1
    return 0
}

# Non-core slots the engine left stock in this switch, for the task message.
KEPT_STOCK_FILE="$CONFIG_DIR/universal-kept-stock.conf"

_uc_record_kept_stock() {
    rm -f "$KEPT_STOCK_FILE" 2>/dev/null || true
    _uck_report=$(MODDIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" sh "$ENGINE_BRIDGE" report "$1")
    _uck_list=$(_uc_python - "$_uck_report" <<'PY' 2>/dev/null
import json, sys
from pathlib import Path
report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
names = sorted(Path(item["path"]).name for item in report.get("keptStock") or [])
if names:
    print(f"{len(names)}|{'、'.join(names[:5])}{' 等' if len(names) > 5 else ''}")
PY
)
    [ -n "$_uck_list" ] || return 0
    _uc_log "universal kept stock font=$1 slots=$_uck_list"
    {
        printf 'font=%s\n' "$1"
        printf 'count=%s\n' "${_uck_list%%|*}"
        printf 'files=%s\n' "${_uck_list#*|}"
    } > "$KEPT_STOCK_FILE" 2>/dev/null || true
}

# Runs the v3 engine (generate payload) -> stage-next for one family key.
# Returns 0 after staging (stage JSON on stdout). On failure nothing has been
# staged; UC_FAIL holds a reason code and UC_FAIL_DETAIL a short diagnostic.
_uc_universal() {
    _uc_font="$1"
    UC_FAIL=''
    UC_FAIL_DETAIL=''
    if ! _uc_precondition; then
        UC_FAIL=universal-precondition-missing
        return 1
    fi

    _uc_write_state preparing "$_uc_font" universal preparing
    rm -f "$KEPT_STOCK_FILE" 2>/dev/null || true
    _uc_progress 8 "字体引擎正在分析设备字体"
    _uc_budget=$(_uc_budget_seconds)
    _uc_started=$(date +%s 2>/dev/null || echo 0)
    _uc_log "engine prepare start font=$_uc_font budget=${_uc_budget}s"
    # The engine stops before starting new work past this deadline.
    _uc_prepare_output=$(MODDIR="$MODDIR" MODULE_DIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" \
        LUOSHU_PUBLIC_DIR="$PUBLIC_DIR" LUOSHU_SWITCH_PROGRESS_FILE="$PROGRESS_FILE" \
        LUOSHU_ENGINE_DEADLINE=$((_uc_started + _uc_budget)) \
        sh "$ENGINE_BRIDGE" prepare "$_uc_font" 2>&1)
    _uc_prepare_rc=$?
    _uc_log "engine prepare finished font=$_uc_font rc=$_uc_prepare_rc elapsed=$(( $(date +%s 2>/dev/null || echo 0) - _uc_started ))s result=$(printf '%s' "$_uc_prepare_output" | tail -c 600)"
    if [ "$_uc_prepare_rc" -ne 0 ] || ! printf '%s' "$_uc_prepare_output" | grep -q '"status":"ok"'; then
        UC_FAIL=universal-prepare-failed
        UC_FAIL_DETAIL=$(printf '%s\n' "$_uc_prepare_output" | sed -n 's/.*"message":"\([^"]*\)".*/\1/p' | tail -n1)
        return 1
    fi

    _uc_progress 88 "字体已生成，正在准备下一次启动"
    _uc_stage_output=$(MODDIR="$MODDIR" MODULE_DIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" \
        sh "$ENGINE_BRIDGE" stage "$_uc_font" 2>&1)
    _uc_stage_rc=$?
    if [ "$_uc_stage_rc" -ne 0 ] || ! printf '%s' "$_uc_stage_output" | grep -q '"status":"ok"'; then
        _uc_log "engine stage failed font=$_uc_font rc=$_uc_stage_rc output=$_uc_stage_output"
        UC_FAIL=universal-stage-failed
        return 1
    fi

    _uc_write_state staged "$_uc_font" universal ready-next-boot
    _uc_record_kept_stock "$_uc_font"
    _uc_progress 96 "字体负载已准备，完整重启后生效"
    printf '%s\n' "$_uc_stage_output"
    return 0
}

# Reports a Universal failure. Nothing was staged, so the running font and any
# previously queued request stay as they were; the legacy engine is retired.
_uc_fail() {
    _ucf_font="$1"; _ucf_subject="$2"
    _uc_write_state failed "$_ucf_font" universal "$UC_FAIL"
    _uc_log "universal failed font=$_ucf_font reason=$UC_FAIL detail=$UC_FAIL_DETAIL"
    _ucf_message="通用引擎无法应用该${_ucf_subject}，当前字体未改变"
    [ -z "$UC_FAIL_DETAIL" ] || _ucf_message="$_ucf_message（$UC_FAIL_DETAIL）"
    printf '{"status":"error","reason":"%s","message":"%s"}\n' "$UC_FAIL" \
        "$(printf '%s' "$_ucf_message" | sed 's/\\/\\\\/g; s/"/\\"/g')"
    return 1
}

# Restoring the system font stages an empty next payload; next_boot_payload.sh
# activates it in default mode and clears Universal runtime state.
_uc_switch_default() {
    _ucd_live=$(head -n1 "$CONFIG_DIR/active_font.conf" 2>/dev/null | tr -d '\r\n')
    # The font running in this boot, not a selection that is only queued.
    for _ucd_queued in "$CONFIG_DIR/universal-font-next.conf" "$CONFIG_DIR/font-payload-next.conf"; do
        if [ -s "$_ucd_queued" ]; then
            _ucd_previous=$(_uc_value "$_ucd_queued" previousFont)
            [ -z "$_ucd_previous" ] || _ucd_live="$_ucd_previous"
            break
        fi
    done
    [ -n "$_ucd_live" ] || _ucd_live=default
    _uc_progress 40 "正在准备恢复系统字体"
    _uc_prepare_empty_next || {
        printf '{"status":"error","message":"无法准备系统字体负载，当前字体未改变"}\n'
        return 1
    }
    rm -f "$CONFIG_DIR/universal-font-next.conf" 2>/dev/null || true
    {
        printf 'state=prepared\nfont=default\npreviousFont=%s\npreviousLegacy=false\n' "$_ucd_live"
        printf 'targetMode=default\ntime=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$CONFIG_DIR/font-payload-next.conf.tmp.$$" 2>/dev/null && \
        mv -f "$CONFIG_DIR/font-payload-next.conf.tmp.$$" "$CONFIG_DIR/font-payload-next.conf" 2>/dev/null || {
            rm -f "$CONFIG_DIR/font-payload-next.conf.tmp.$$" "$CONFIG_DIR/font-payload-next.conf" 2>/dev/null || true
            rm -rf "$MODDIR/.luoshu-payload-next" 2>/dev/null || true
            printf '{"status":"error","message":"无法保存系统字体请求，当前字体未改变"}\n'
            return 1
        }
    chmod 0644 "$CONFIG_DIR/font-payload-next.conf" 2>/dev/null || true
    printf 'default\n' > "$CONFIG_DIR/active_font.conf" 2>/dev/null || true
    {
        printf 'font=default\nreason=next-boot-payload-prepared\ntime=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$CONFIG_DIR/text_reboot_required.conf" 2>/dev/null || true
    chmod 0644 "$CONFIG_DIR/active_font.conf" "$CONFIG_DIR/text_reboot_required.conf" 2>/dev/null || true
    _uc_write_state staged default universal ready-next-boot
    _uc_progress 96 "系统字体已准备，完整重启后生效"
    printf '{"status":"ok","data":{"font":"default","rebootRequired":true,"pipeline":"universal-default"}}\n'
    return 0
}

_uc_switch() {
    _uc_font="$1"
    [ -n "$_uc_font" ] || { printf '{"status":"error","message":"未指定字体"}\n'; return 1; }
    # A new explicit user choice supersedes any previously staged automatic rollback.
    rm -f "$ROLLBACK_STATE" 2>/dev/null || true

    if [ "$_uc_font" = default ]; then
        _uc_switch_default
        return $?
    fi
    # Composites have their own entry (universal_composite.sh); the legacy
    # composite runtime and its temporary families are retired.
    if [ -n "${LUOSHU_REAL_MODDIR:-}" ]; then
        printf '{"status":"error","message":"旧组合运行时已停用，请在组合页面重新应用"}\n'
        return 1
    fi
    case "$_uc_font" in
        mix|LuoShuAutoMix|LuoShuMix*)
            printf '{"status":"error","message":"组合字体请在组合页面应用"}\n'
            return 1
            ;;
    esac

    _uc_universal "$_uc_font" && return 0
    _uc_fail "$_uc_font" 字体
}

# Composite (mix) switch from universal_composite.sh. There is no legacy
# fallback here: if Universal cannot apply the composite, report why and leave
# the current and any queued font untouched.
_uc_switch_composite() {
    [ -s "$CONFIG_DIR/universal-composite.conf" ] || {
        printf '{"status":"error","message":"组合字体设置缺失"}\n'
        return 1
    }
    rm -f "$ROLLBACK_STATE" 2>/dev/null || true
    _uc_universal mix && return 0
    _uc_fail mix 组合
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
    switch-composite) _uc_switch_composite ;;
    rollback-from-fail) _uc_schedule_rollback "${2:-}" ;;
    status)
        if [ -s "$CUTOVER_STATE" ]; then cat "$CUTOVER_STATE"
        else printf 'state=idle\ndecision=none\n'
        fi
        ;;
    *) echo "Usage: $0 {switch|switch-composite|rollback-from-fail|status} [font-family|boot-id]" >&2; exit 2 ;;
esac
