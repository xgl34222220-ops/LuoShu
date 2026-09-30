#!/system/bin/sh
# Phase 7/9 universal deployment next-boot activation.
# Swaps only a previously validated private payload. It does not compile fonts.
set +e

_ufnb_module() {
    printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
}

_ufnb_value() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

_ufnb_log() {
    _ufnb_mod=$(_ufnb_module)
    mkdir -p "$_ufnb_mod/logs" 2>/dev/null || true
    printf '[%s] [UNIVERSAL-NEXT] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$*" >> "$_ufnb_mod/logs/fontswitch.log" 2>/dev/null || true
}

_ufnb_python() {
    if [ -n "${LUOSHU_PYTHON:-}" ]; then
        "$LUOSHU_PYTHON" "$@"
        return $?
    fi
    _ufnb_mod=$(_ufnb_module)
    _ufnb_root="$_ufnb_mod/common/python"
    _ufnb_bin="$_ufnb_root/bin/luoshu-python"
    [ -x "$_ufnb_bin" ] || return 127
    PYTHONHOME="$_ufnb_root" \
    PYTHONPATH="$_ufnb_mod/common:$_ufnb_root/lib/python3.14:$_ufnb_root/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$_ufnb_root/lib:$_ufnb_root/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$_ufnb_bin" "$@"
}

_ufnb_manifest_value() {
    _ufnb_manifest="$1"
    _ufnb_key="$2"
    _ufnb_python - "$_ufnb_manifest" "$_ufnb_key" <<'PY'
import json,sys
p=json.load(open(sys.argv[1],encoding="utf-8"))
v=p.get(sys.argv[2],"")
print(v if isinstance(v,(str,int,float)) else "")
PY
}

_ufnb_restore_file() {
    _ufnb_restore_source="$1"; _ufnb_restore_target="$2"
    rm -f "$_ufnb_restore_target" 2>/dev/null || true
    [ -f "$_ufnb_restore_source" ] && cp -fp "$_ufnb_restore_source" "$_ufnb_restore_target" 2>/dev/null || true
}

_ufnb_restore_previous_selection() {
    _ufnb_cfg="$1"; _ufnb_previous="$2"
    [ -n "$_ufnb_previous" ] || _ufnb_previous=default
    printf '%s\n' "$_ufnb_previous" > "$_ufnb_cfg/active_font.conf" 2>/dev/null || true
    chmod 0644 "$_ufnb_cfg/active_font.conf" 2>/dev/null || true
    rm -f "$_ufnb_cfg/text_reboot_required.conf" 2>/dev/null || true
}

_ufnb_discard_invalid_next() {
    _ufnb_state="$1"; _ufnb_next="$2"; _ufnb_reason="$3"; _ufnb_previous="$4"
    _ufnb_failed="${_ufnb_state%.conf}.failed.conf"
    {
        printf 'state=failed\n'
        printf 'reason=%s\n' "$_ufnb_reason"
        printf 'previousFont=%s\n' "${_ufnb_previous:-default}"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_ufnb_failed.tmp.$$" 2>/dev/null && mv -f "$_ufnb_failed.tmp.$$" "$_ufnb_failed" 2>/dev/null || true
    _ufnb_restore_previous_selection "${_ufnb_state%/universal-font-next.conf}" "$_ufnb_previous"
    rm -f "$_ufnb_state" 2>/dev/null || true
    rm -rf "$_ufnb_next" 2>/dev/null || true
}

universal_font_next_boot_activate() {
    _ufnb_mod=$(_ufnb_module)
    _ufnb_cfg="$_ufnb_mod/config"
    _ufnb_state="$_ufnb_cfg/universal-font-next.conf"
    _ufnb_next="$_ufnb_mod/.luoshu-payload-next"
    _ufnb_live="$_ufnb_mod/.luoshu-payload"
    [ -s "$_ufnb_state" ] && [ -d "$_ufnb_next" ] || return 2

    _ufnb_font=$(_ufnb_value "$_ufnb_state" font)
    _ufnb_id=$(_ufnb_value "$_ufnb_state" deploymentId)
    _ufnb_digest=$(_ufnb_value "$_ufnb_state" payloadDigest)
    _ufnb_previous_font=$(_ufnb_value "$_ufnb_state" previousFont)
    _ufnb_previous_mode=$(_ufnb_value "$_ufnb_state" previousMode)
    _ufnb_previous_legacy=$(_ufnb_value "$_ufnb_state" previousLegacy)
    _ufnb_recovery=$(_ufnb_value "$_ufnb_state" recovery)
    [ "$_ufnb_previous_legacy" = true ] || _ufnb_previous_legacy=false
    [ "$_ufnb_recovery" = true ] || _ufnb_recovery=false

    [ -n "$_ufnb_previous_font" ] || {
        _ufnb_previous_font=$(head -n1 "$_ufnb_cfg/active_font.conf" 2>/dev/null | tr -d '\r\n')
        [ -n "$_ufnb_previous_font" ] || _ufnb_previous_font=default
    }
    # Cancellation can race the last foreground stage rename. Its durable
    # request tombstone remains authoritative even if a new selection replaced
    # mix-stage-next.conf before reboot; never activate that cancelled payload.
    _ufnb_request=$(_ufnb_value "$_ufnb_state" requestId)
    case "$_ufnb_request" in
        ''|*[!A-Za-z0-9._-]*) ;;
        *)
            if [ -f "$_ufnb_cfg/mix-cancelled-requests/$_ufnb_request" ]; then
                _ufnb_discard_invalid_next "$_ufnb_state" "$_ufnb_next" composite-request-cancelled "$_ufnb_previous_font"
                return 1
            fi
            ;;
    esac
    if [ -z "$_ufnb_previous_mode" ]; then
        if [ -s "$_ufnb_cfg/universal-font-runtime.conf" ]; then
            _ufnb_previous_mode=universal
        elif [ -s "$_ufnb_cfg/font_runtime_legacy_v14_4.conf" ]; then
            _ufnb_previous_mode=legacy
            _ufnb_previous_legacy=true
        elif [ "$_ufnb_previous_font" = default ]; then
            _ufnb_previous_mode=default
        else
            _ufnb_previous_mode=classic
        fi
    fi

    _ufnb_manifest="$_ufnb_next/.luoshu-runtime/deployment/deployment.json"
    [ -n "$_ufnb_font" ] && [ -n "$_ufnb_id" ] && [ -n "$_ufnb_digest" ] && [ -s "$_ufnb_manifest" ] || {
        _ufnb_log "staged universal state incomplete"
        _ufnb_discard_invalid_next "$_ufnb_state" "$_ufnb_next" incomplete-state "$_ufnb_previous_font"
        return 1
    }

    _ufnb_deployer="$_ufnb_mod/common/universal_font_deployment.py"
    [ -f "$_ufnb_deployer" ] || {
        _ufnb_log "universal deployer missing; keeping previous payload"
        _ufnb_discard_invalid_next "$_ufnb_state" "$_ufnb_next" deployer-missing "$_ufnb_previous_font"
        return 1
    }
    _ufnb_python "$_ufnb_deployer" --payload-root "$_ufnb_next" --validate-dynamic-generation --validate-payload-only "$_ufnb_manifest" >/dev/null 2>&1 || {
        _ufnb_log "staged payload validation failed"
        _ufnb_discard_invalid_next "$_ufnb_state" "$_ufnb_next" payload-validation-failed "$_ufnb_previous_font"
        return 1
    }
    [ "$(_ufnb_manifest_value "$_ufnb_manifest" deploymentId)" = "$_ufnb_id" ] || {
        _ufnb_discard_invalid_next "$_ufnb_state" "$_ufnb_next" deployment-id-mismatch "$_ufnb_previous_font"
        return 1
    }
    [ "$(_ufnb_manifest_value "$_ufnb_manifest" payloadDigest)" = "$_ufnb_digest" ] || {
        _ufnb_discard_invalid_next "$_ufnb_state" "$_ufnb_next" payload-digest-mismatch "$_ufnb_previous_font"
        return 1
    }

    _ufnb_boot=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')
    [ -n "$_ufnb_boot" ] || _ufnb_boot="$(date +%s 2>/dev/null || echo 0)-$$"
    _ufnb_retired_root="$_ufnb_mod/.luoshu-retired"
    _ufnb_retired="$_ufnb_retired_root/universal-${_ufnb_boot}"
    _ufnb_backup="$_ufnb_cfg/.universal-next-backup.$$"
    mkdir -p "$_ufnb_retired_root" "$_ufnb_backup" 2>/dev/null || {
        _ufnb_discard_invalid_next "$_ufnb_state" "$_ufnb_next" activation-state-dir-failed "$_ufnb_previous_font"
        return 1
    }
    [ ! -f "$_ufnb_cfg/universal-font-runtime.conf" ] || cp -fp "$_ufnb_cfg/universal-font-runtime.conf" "$_ufnb_backup/runtime.conf" 2>/dev/null || true
    [ ! -f "$_ufnb_cfg/font_runtime_legacy_v14_4.conf" ] || cp -fp "$_ufnb_cfg/font_runtime_legacy_v14_4.conf" "$_ufnb_backup/legacy.conf" 2>/dev/null || true
    [ ! -f "$_ufnb_cfg/active_font.conf" ] || cp -fp "$_ufnb_cfg/active_font.conf" "$_ufnb_backup/active.conf" 2>/dev/null || true
    rm -rf "$_ufnb_retired" 2>/dev/null || true

    if [ -d "$_ufnb_live" ]; then
        mv "$_ufnb_live" "$_ufnb_retired" 2>/dev/null || {
            _ufnb_discard_invalid_next "$_ufnb_state" "$_ufnb_next" retire-previous-payload-failed "$_ufnb_previous_font"
            rm -rf "$_ufnb_backup"
            return 1
        }
    fi
    if ! mv "$_ufnb_next" "$_ufnb_live" 2>/dev/null; then
        [ ! -d "$_ufnb_retired" ] || mv "$_ufnb_retired" "$_ufnb_live" 2>/dev/null || true
        _ufnb_discard_invalid_next "$_ufnb_state" "$_ufnb_next" activate-next-payload-failed "$_ufnb_previous_font"
        rm -rf "$_ufnb_backup" 2>/dev/null || true
        return 1
    fi

    _ufnb_runtime="$_ufnb_cfg/universal-font-runtime.conf"
    {
        printf 'state=active\n'
        printf 'pipeline=universal-font-deployment-v1\n'
        printf 'font=%s\n' "$_ufnb_font"
        printf 'requestId=%s\n' "$(_ufnb_value "$_ufnb_state" requestId)"
        printf 'deploymentId=%s\n' "$_ufnb_id"
        printf 'payloadDigest=%s\n' "$_ufnb_digest"
        printf 'bootId=%s\n' "$_ufnb_boot"
        printf 'recovery=%s\n' "$_ufnb_recovery"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_ufnb_runtime.tmp.$$" 2>/dev/null && mv -f "$_ufnb_runtime.tmp.$$" "$_ufnb_runtime" 2>/dev/null || {
        rm -rf "$_ufnb_live" 2>/dev/null || true
        [ ! -d "$_ufnb_retired" ] || mv "$_ufnb_retired" "$_ufnb_live" 2>/dev/null || true
        _ufnb_restore_file "$_ufnb_backup/runtime.conf" "$_ufnb_cfg/universal-font-runtime.conf"
        _ufnb_restore_file "$_ufnb_backup/legacy.conf" "$_ufnb_cfg/font_runtime_legacy_v14_4.conf"
        _ufnb_discard_invalid_next "$_ufnb_state" "$_ufnb_next" runtime-state-commit-failed "$_ufnb_previous_font"
        rm -rf "$_ufnb_backup" 2>/dev/null || true
        return 1
    }
    chmod 0600 "$_ufnb_runtime" 2>/dev/null || true

    {
        printf 'font=%s\n' "$_ufnb_font"
        printf 'requestId=%s\n' "$(_ufnb_value "$_ufnb_state" requestId)"
        printf 'deploymentId=%s\n' "$_ufnb_id"
        printf 'payloadDigest=%s\n' "$_ufnb_digest"
        printf 'previousFont=%s\n' "$_ufnb_previous_font"
        printf 'previousMode=%s\n' "$_ufnb_previous_mode"
        printf 'previousLegacy=%s\n' "$_ufnb_previous_legacy"
        printf 'recovery=%s\n' "$_ufnb_recovery"
        printf 'retired=%s\n' "$_ufnb_retired"
        printf 'bootId=%s\n' "$_ufnb_boot"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_ufnb_cfg/universal-font-activated.conf.tmp.$$" 2>/dev/null && \
        mv -f "$_ufnb_cfg/universal-font-activated.conf.tmp.$$" "$_ufnb_cfg/universal-font-activated.conf" 2>/dev/null || {
            rm -rf "$_ufnb_live" 2>/dev/null || true
            [ ! -d "$_ufnb_retired" ] || mv "$_ufnb_retired" "$_ufnb_live" 2>/dev/null || true
            _ufnb_restore_file "$_ufnb_backup/runtime.conf" "$_ufnb_cfg/universal-font-runtime.conf"
            _ufnb_restore_file "$_ufnb_backup/legacy.conf" "$_ufnb_cfg/font_runtime_legacy_v14_4.conf"
            _ufnb_discard_invalid_next "$_ufnb_state" "$_ufnb_next" activation-metadata-commit-failed "$_ufnb_previous_font"
            rm -f "$_ufnb_cfg/universal-font-activated.conf.tmp.$$" 2>/dev/null || true
            rm -rf "$_ufnb_backup" 2>/dev/null || true
            return 1
        }
    chmod 0644 "$_ufnb_cfg/universal-font-activated.conf" 2>/dev/null || true

    # Only after both runtime state and recovery metadata are committed do we
    # retire the previous engine mode for this boot.
    rm -f "$_ufnb_cfg/font_runtime_legacy_v14_4.conf" "$_ufnb_cfg/font-payload-schema.conf" 2>/dev/null || true
    printf '%s\n' "$_ufnb_font" > "$_ufnb_cfg/active_font.conf" 2>/dev/null || true
    chmod 0644 "$_ufnb_cfg/active_font.conf" 2>/dev/null || true

    rm -f "$_ufnb_state" "$_ufnb_cfg/font-payload-next.conf" \
          "$_ufnb_cfg/text_reboot_required.conf" \
          "$_ufnb_cfg/universal-font-runtime-verification.conf" \
          "$_ufnb_cfg/universal-font-runtime-verification.json" \
          "$_ufnb_cfg/universal-font-mount.conf" \
          "$_ufnb_cfg/universal-font-rollback.conf" 2>/dev/null || true
    rm -rf "$_ufnb_backup" 2>/dev/null || true
    _ufnb_log "activated deployment=$_ufnb_id font=$_ufnb_font previous=$_ufnb_previous_font mode=$_ufnb_previous_mode recovery=$_ufnb_recovery retired=$_ufnb_retired"
    return 0
}
