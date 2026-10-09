#!/system/bin/sh
# LuoShu native App font-manager router.
# Inventory, preview and delete actions stay on the current manager.
# Final font apply uses the isolated safe physical switch core, which builds the
# next-boot payload off-line and never rewrites the source tree mounted by this boot.
# Source-check compatibility markers owned by font_manager_v4.sh: native-v3 manifest-fast
# The current inventory contract remains config/native_font_index.json.
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
    else
        MODDIR="/data/adb/modules/LuoShu"
    fi
fi
_manager_boot_stock_scan=0
_manager_scope_timeout=900
if [ "${1:-}" = action ] && [ "${2:-}" = stock_scan ] && \
   [ "${LUOSHU_STOCK_VIEW_VERIFIED:-0}" = 1 ]; then
    _manager_boot_complete=$(getprop sys.boot_completed 2>/dev/null)
    _manager_mount_state=$(sed -n 's/^state=//p' "$MODDIR/config/self-mount.conf" 2>/dev/null | head -n1)
    _manager_mount_components=$(sed -n 's/^mounted=//p' "$MODDIR/config/self-mount.conf" 2>/dev/null | head -n1)
    _manager_mount_root="${LUOSHU_SELF_MOUNT_STATE_ROOT:-/data/adb/luoshu/self-mount}"
    _manager_mount_boot=$(head -n1 "$_manager_mount_root/boot-id" 2>/dev/null)
    _manager_current_boot=$(head -n1 /proc/sys/kernel/random/boot_id 2>/dev/null)
    _manager_view_early=1
    [ "$_manager_boot_complete" != 1 ] || _manager_view_early=0
    # Failed verification can leave mounts active. Within this boot (or with
    # unknown journal identity), only an explicitly empty/idle mount state with
    # no recorded components can keep the pre-mount stock assertion.
    if [ -z "$_manager_mount_boot" ] || [ -z "$_manager_current_boot" ] || \
       [ "$_manager_mount_boot" = "$_manager_current_boot" ]; then
        case "$_manager_mount_state:$_manager_mount_components" in
            :|idle:) ;;
            *) _manager_view_early=0 ;;
        esac
    fi
    if [ "$_manager_boot_complete" != 1 ] && [ "${LUOSHU_FRESH_STOCK_SCAN:-0}" = 1 ]; then
        _manager_boot_stock_scan=1
        _manager_scope_timeout="${LUOSHU_BOOT_STOCK_SCAN_TIMEOUT_SECONDS:-3}"
        case "$_manager_scope_timeout" in ''|*[!0-9]*) _manager_scope_timeout=3 ;; esac
        [ "$_manager_scope_timeout" -ge 1 ] 2>/dev/null || _manager_scope_timeout=1
        [ "$_manager_scope_timeout" -le 5 ] 2>/dev/null || _manager_scope_timeout=5
    fi
    if [ "$_manager_view_early" -ne 1 ] || [ "${LUOSHU_FRESH_STOCK_SCAN:-0}" != 1 ]; then
        # Never carry the frozen pre-mount assertion into an after-mount scan.
        # The scanner must prove lower/mirror/snapshot safety on its own.
        unset LUOSHU_STOCK_VIEW_VERIFIED
    fi
fi
if [ -z "${LUOSHU_TASK_SCOPE_PID:-}" ] && \
   { [ "$_manager_boot_stock_scan" -ne 1 ] || [ -n "${LUOSHU_BOOT_STOCK_SCAN_STAGE:-}" ]; }; then
    # The supervisor only returns timeout after collecting descendant cleanup
    # evidence; unconfirmed cleanup remains an error with its identity retained.
    exec sh "$MODDIR/common/task_scope.sh" request-run "manager-$$-$(date +%s)" "$_manager_scope_timeout" -- sh "$0" "$@"
fi
LUOSHU_PUBLIC_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}"
CURRENT_MANAGER="$MODDIR/common/font_manager_v4.sh"
SAFE_SWITCH="$MODDIR/common/legacy_v14_4/font_switch_safe.sh"
LEGACY_SWITCH="$MODDIR/common/legacy_v14_4_switch.sh"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"
STOCK_SCANNER="$MODDIR/common/stock_inventory_scan.py"
STOCK_INVENTORY="$MODDIR/config/device_font_inventory.json"
STOCK_SCAN_OUTPUT="$STOCK_INVENTORY"
if [ -n "${LUOSHU_BOOT_STOCK_SCAN_STAGE:-}" ]; then
    # This directory was issued by the finite boot launcher, never a ROM lower.
    case "$LUOSHU_BOOT_STOCK_SCAN_STAGE" in
        "$MODDIR"/.luoshu-state/tmp/boot-stock-scan.*) ;;
        *) exit 126 ;;
    esac
    [ -d "$LUOSHU_BOOT_STOCK_SCAN_STAGE" ] && [ ! -L "$LUOSHU_BOOT_STOCK_SCAN_STAGE" ] || exit 126
    STOCK_SCAN_OUTPUT="$LUOSHU_BOOT_STOCK_SCAN_STAGE/device_font_inventory.json"
fi
STOCK_SCAN_LOCK="$MODDIR/.stock-inventory-scan.lock"
export MODDIR LUOSHU_PUBLIC_DIR

json_escape_router() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

stock_scan_available() {
    [ -x "$PYBIN" ] && [ -f "$STOCK_SCANNER" ] && [ -f "$MODDIR/common/font_inventory.py" ] && [ -f "$MODDIR/common/font_check.sh" ]
}

stock_scan_lock_acquire() {
    # The boot launcher holds the shared lock until cleanup and publication. Its
    # supervised child may borrow that exact live lease but cannot release it.
    if [ -n "${LUOSHU_BOOT_STOCK_SCAN_STAGE:-}" ] && \
       [ -n "${LUOSHU_BOOT_STOCK_SCAN_LOCK_OWNER:-}" ] && \
       [ "$(head -n1 "$STOCK_SCAN_LOCK/pid" 2>/dev/null)" = "$LUOSHU_BOOT_STOCK_SCAN_LOCK_OWNER" ] && \
       kill -0 "$LUOSHU_BOOT_STOCK_SCAN_LOCK_OWNER" 2>/dev/null; then
        STOCK_SCAN_WAITED=false
        return 0
    fi
    _ssl_tries=0
    STOCK_SCAN_WAITED=false
    while [ "$_ssl_tries" -lt 180 ]; do
        if mkdir "$STOCK_SCAN_LOCK" 2>/dev/null; then
            printf '%s\n' "$$" >"$STOCK_SCAN_LOCK/pid" 2>/dev/null || {
                rmdir "$STOCK_SCAN_LOCK" 2>/dev/null || true
                return 1
            }
            cat /proc/sys/kernel/random/boot_id >"$STOCK_SCAN_LOCK/boot-id" 2>/dev/null || true
            return 0
        fi
        # Early boot never waits for, edits or reaps an unknown scan lease.
        [ "$_manager_boot_stock_scan" -ne 1 ] || return 1
        STOCK_SCAN_WAITED=true
        _ssl_owner=$(sed -n '1p' "$STOCK_SCAN_LOCK/pid" 2>/dev/null)
        _ssl_saved_boot=$(sed -n '1p' "$STOCK_SCAN_LOCK/boot-id" 2>/dev/null)
        _ssl_current_boot=$(sed -n '1p' /proc/sys/kernel/random/boot_id 2>/dev/null)
        _ssl_scope_task=$(head -n1 "$STOCK_SCAN_LOCK/task" 2>/dev/null)
        _ssl_cleanup_pending=$(head -n1 "$STOCK_SCAN_LOCK/cleanup-pending" 2>/dev/null)
        _ssl_old_boot=0
        if [ -n "$_ssl_saved_boot" ] && [ -n "$_ssl_current_boot" ] && [ "$_ssl_saved_boot" != "$_ssl_current_boot" ]; then
            _ssl_old_boot=1
        fi
        case "$_ssl_owner" in ''|*[!0-9]*) _ssl_owner='' ;; esac
        if [ "$_ssl_old_boot" -ne 1 ] && [ "$_ssl_cleanup_pending" = 1 ] && \
           { [ -z "$_ssl_owner" ] || ! kill -0 "$_ssl_owner" 2>/dev/null; }; then
            return 125
        fi
        if [ "$_ssl_old_boot" -eq 1 ] || \
           [ -z "$_ssl_owner" ] || ! kill -0 "$_ssl_owner" 2>/dev/null; then
            if [ "$_ssl_old_boot" -ne 1 ] && [ -n "$_ssl_scope_task" ]; then
                case "$_ssl_scope_task" in *[!A-Za-z0-9_.-]*|.|..) return 125 ;; esac
                sh "$MODDIR/common/task_scope.sh" cleaned \
                    "${LUOSHU_TASKS_DIR:-$MODDIR/.luoshu-state/tasks}/request-$_ssl_scope_task.pid" \
                    "$_ssl_scope_task" >/dev/null 2>&1 || return 125
            fi
            rm -f "$STOCK_SCAN_LOCK/pid" "$STOCK_SCAN_LOCK/boot-id" \
                "$STOCK_SCAN_LOCK/task" "$STOCK_SCAN_LOCK/cleanup-pending" 2>/dev/null || return 1
            # An unrecognized extra file is evidence, not permission to erase
            # the directory or spin forever trying to remove it.
            rmdir "$STOCK_SCAN_LOCK" 2>/dev/null || return 1
            continue
        fi
        sleep 1
        _ssl_tries=$((_ssl_tries + 1))
    done
    return 1
}

stock_scan_lock_release() {
    _ssl_owner=$(sed -n '1p' "$STOCK_SCAN_LOCK/pid" 2>/dev/null)
    [ -z "$_ssl_owner" ] || [ "$_ssl_owner" = "$$" ] || return 0
    rm -f "$STOCK_SCAN_LOCK/pid" "$STOCK_SCAN_LOCK/boot-id" \
        "$STOCK_SCAN_LOCK/task" "$STOCK_SCAN_LOCK/cleanup-pending" 2>/dev/null || true
    rmdir "$STOCK_SCAN_LOCK" 2>/dev/null || true
}

stock_scan_json() {
    if ! stock_scan_available; then
        printf '{"status":"error","message":"%s"}\n' "$(json_escape_router '原厂字体扫描组件不完整')"
        return 1
    fi
    mkdir -p "$MODDIR/config" "$MODDIR/logs" 2>/dev/null || true
    stock_scan_lock_acquire
    _stock_lock_rc=$?
    if [ "$_stock_lock_rc" -ne 0 ]; then
        if [ "$_stock_lock_rc" -eq 125 ]; then
            printf '{"status":"error","message":"上次原厂扫描清理未确认，保留任务证据"}\n'
        else
            printf '{"status":"error","message":"%s"}\n' "$(json_escape_router '原厂字体扫描仍在进行，请稍后重试')"
        fi
        return "$_stock_lock_rc"
    fi
    trap 'stock_scan_lock_release' EXIT HUP INT TERM
    if [ -n "${LUOSHU_BOOT_STOCK_SCAN_STAGE:-}" ] && \
       [ "${LUOSHU_STOCK_VIEW_VERIFIED:-0}" != 1 ]; then
        # The mount/boot state may change between launch and child entry. A
        # short boot scope cannot safely abandon a newly created bind snapshot
        # on SIGKILL, so it must never enter the unverified snapshot resolver.
        printf '{"status":"error","message":"启动期原厂视图未确认，保留待办等待启动后重采"}\n'
        return 1
    fi
    # If the boot service completed the same scan while the App was waiting for
    # the lock, validate and reuse that fresh inventory instead of scanning twice.
    if [ "$STOCK_SCAN_WAITED" = true ] && [ -s "$STOCK_INVENTORY" ] && \
       [ ! -e "$MODDIR/config/stock_inventory_scan_pending" ]; then
        _stock_out=$(
            PYTHONHOME="$PYROOT" \
            PYTHONPATH="$MODDIR/common:$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" \
            LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
                "$PYBIN" "$STOCK_SCANNER" --validate --output "$STOCK_INVENTORY" 2>&1
        )
        _stock_rc=$?
        if [ "$_stock_rc" -eq 0 ]; then
            rm -f "$MODDIR/config/stock_inventory_scan_pending" 2>/dev/null || true
            stock_scan_lock_release
            trap - EXIT HUP INT TERM
            printf '%s\n' "$(printf '%s\n' "$_stock_out" | tail -n1)"
            return 0
        fi
    fi
    _stock_out=$(
        PYTHONHOME="$PYROOT" \
        PYTHONPATH="$MODDIR/common:$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" \
        LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
            "$PYBIN" "$STOCK_SCANNER" \
                --scan --force \
                --overlay-module "$MODDIR" \
                --font-check "$MODDIR/common/font_check.sh" \
                --output "$STOCK_SCAN_OUTPUT" 2>&1
    )
    _stock_rc=$?
    _stock_last=$(printf '%s\n' "$_stock_out" | tail -n1)
    if [ "$_stock_rc" -eq 0 ] && [ -s "$STOCK_SCAN_OUTPUT" ]; then
        [ -n "${LUOSHU_BOOT_STOCK_SCAN_STAGE:-}" ] || \
            rm -f "$MODDIR/config/stock_inventory_scan_pending" 2>/dev/null || true
        stock_scan_lock_release
        trap - EXIT HUP INT TERM
        printf '%s\n' "$_stock_last"
        return 0
    fi
    _stock_message=$(printf '%s\n' "$_stock_last" | sed -n 's/^.*"message"[[:space:]]*:[[:space:]]*"\([^"]*\)".*$/\1/p')
    [ -n "$_stock_message" ] || _stock_message="$_stock_out"
    [ -n "$_stock_message" ] || _stock_message='原厂字体扫描失败'
    stock_scan_lock_release
    trap - EXIT HUP INT TERM
    printf '{"status":"error","message":"%s"}\n' "$(json_escape_router "$_stock_message")"
    return 1
}

# The boot worker writes all artifacts off-line. Only its launcher publishes,
# after a successful supervisor exit has proved descendant cleanup. Holding the
# scan lock across that boundary prevents a concurrent foreground scan from
# being overwritten by an older staged result.
boot_stock_scan_uptime() {
    IFS=' ' read -r _manager_uptime _manager_unused < /proc/uptime 2>/dev/null || return 1
    _manager_uptime=${_manager_uptime%%.*}
    case "$_manager_uptime" in ''|*[!0-9]*) return 1 ;; esac
    printf '%s\n' "$_manager_uptime"
}

boot_stock_scan_receipt() {
    _manager_receipt_result="$1"
    _manager_receipt_published="${2:-no}"
    _manager_receipt_elapsed=unknown
    _manager_receipt_now=$(boot_stock_scan_uptime)
    case "$_manager_scan_started:$_manager_receipt_now" in
        *[!0-9:]*|:*|*:) ;;
        *) _manager_receipt_elapsed=$((_manager_receipt_now - _manager_scan_started)) ;;
    esac
    _manager_receipt="$MODDIR/config/boot-stock-scan.state"
    {
        printf 'schema=luoshu-boot-stock-scan-v1\n'
        printf 'result=%s\n' "$_manager_receipt_result"
        printf 'budgetSeconds=%s\n' "$_manager_scope_timeout"
        printf 'elapsedSeconds=%s\n' "$_manager_receipt_elapsed"
        printf 'inventoryPublished=%s\n' "$_manager_receipt_published"
        # Local provenance only. App exports compare this with the current boot
        # and expose yes/no/unknown, never the raw identifier.
        printf 'bootId=%s\n' "$(head -n1 /proc/sys/kernel/random/boot_id 2>/dev/null)"
    } > "$_manager_receipt.tmp.$$" 2>/dev/null && \
        mv -f "$_manager_receipt.tmp.$$" "$_manager_receipt" 2>/dev/null || true
    chmod 0644 "$_manager_receipt" 2>/dev/null || true
}

boot_stock_scan_publish() {
    _manager_publish_files='device_font_candidates.json device_font_partitions.conf device_font_inventory.json'
    _manager_publish_backup="$_manager_scan_stage/previous"
    _manager_publish_restore="$_manager_scan_stage/restore"
    mkdir -p "$_manager_publish_backup" "$_manager_publish_restore" || return 1
    [ -w "$MODDIR/config" ] || return 1
    # Verify every input/destination before changing the first metadata file.
    for _manager_publish_name in $_manager_publish_files; do
        _manager_publish_source="$_manager_scan_stage/$_manager_publish_name"
        _manager_publish_target="$MODDIR/config/$_manager_publish_name"
        [ -f "$_manager_publish_source" ] && [ ! -L "$_manager_publish_source" ] || return 1
        [ ! -L "$_manager_publish_target" ] && [ ! -d "$_manager_publish_target" ] || return 1
        if [ -e "$_manager_publish_target" ]; then
            [ -f "$_manager_publish_target" ] && [ -w "$_manager_publish_target" ] || return 1
            cp -p "$_manager_publish_target" "$_manager_publish_backup/$_manager_publish_name" || return 1
        fi
    done
    _manager_publish_done=''
    _manager_publish_failed=0
    # Inventory is last. A failed metadata publish never installs its new stock
    # contract; restore any preceding metadata from this controlled backup.
    for _manager_publish_name in $_manager_publish_files; do
        if mv -f "$_manager_scan_stage/$_manager_publish_name" "$MODDIR/config/$_manager_publish_name"; then
            _manager_publish_done="$_manager_publish_done $_manager_publish_name"
        else
            _manager_publish_failed=1
            break
        fi
    done
    [ "$_manager_publish_failed" -eq 1 ] || return 0
    _manager_publish_rollback_failed=0
    for _manager_publish_name in $_manager_publish_done; do
        _manager_publish_old="$_manager_publish_backup/$_manager_publish_name"
        _manager_publish_target="$MODDIR/config/$_manager_publish_name"
        if [ -f "$_manager_publish_old" ]; then
            cp -p "$_manager_publish_old" "$_manager_publish_restore/$_manager_publish_name" && \
                mv -f "$_manager_publish_restore/$_manager_publish_name" "$_manager_publish_target" || \
                _manager_publish_rollback_failed=1
        else
            rm -f "$_manager_publish_target" || _manager_publish_rollback_failed=1
        fi
    done
    [ "$_manager_publish_rollback_failed" -eq 0 ] || return 125
    return 1
}

boot_stock_scan_json() {
    _manager_scan_started=$(boot_stock_scan_uptime)
    [ -f "$MODDIR/common/runtime_paths.sh" ] || return 126
    . "$MODDIR/common/runtime_paths.sh"
    luoshu_runtime_paths_init "$MODDIR" || return 126
    if [ "${_manager_view_early:-0}" -ne 1 ]; then
        boot_stock_scan_receipt failed no
        printf '{"status":"error","message":"启动期原厂视图未确认，保留旧清单和待办"}\n'
        return 1
    fi
    stock_scan_lock_acquire
    _manager_lock_rc=$?
    if [ "$_manager_lock_rc" -ne 0 ]; then
        if [ "$_manager_lock_rc" -eq 125 ]; then boot_stock_scan_receipt cleanup-pending no
        else boot_stock_scan_receipt busy no; fi
        printf '{"status":"error","message":"原厂字体扫描仍在进行或清理未确认，保留待办并继续启动"}\n'
        return "$_manager_lock_rc"
    fi
    _manager_scan_stage=$(mktemp -d "$LUOSHU_TMP_DIR/boot-stock-scan.XXXXXX") || {
        stock_scan_lock_release
        boot_stock_scan_receipt failed no
        return 126
    }
    _manager_scan_task="boot-stock-scan-$$-$(date +%s)"
    _manager_stage_preserve=1
    trap '[ "$_manager_stage_preserve" -eq 1 ] || { stock_scan_lock_release; rm -rf "$_manager_scan_stage" 2>/dev/null || true; }' EXIT
    printf '%s\n' "$_manager_scan_task" > "$STOCK_SCAN_LOCK/task" || {
        _manager_stage_preserve=0
        boot_stock_scan_receipt failed no
        return 126
    }
    # Reserve the fail-closed marker before any work starts. No error path
    # relies on creating a new file when storage or permissions may have failed.
    # A live launcher can still be waited for; a dead one cannot be taken over
    # until confirmed cleanup/publication has released its owned lease.
    printf '1\n' > "$STOCK_SCAN_LOCK/cleanup-pending" || {
        _manager_stage_preserve=0
        boot_stock_scan_receipt failed no
        return 126
    }
    _manager_scan_response=$(
        MODDIR="$MODDIR" LUOSHU_BOOT_STOCK_SCAN_STAGE="$_manager_scan_stage" \
            LUOSHU_BOOT_STOCK_SCAN_LOCK_OWNER="$$" \
            sh "$MODDIR/common/task_scope.sh" request-run "$_manager_scan_task" "$_manager_scope_timeout" -- \
                sh "$0" "$@"
    )
    _manager_scan_rc=$?
    [ "$_manager_scan_rc" -eq 125 ] || _manager_stage_preserve=0
    if [ "$_manager_scan_rc" -eq 0 ]; then
        _manager_scan_output="$_manager_scan_stage/device_font_inventory.json"
        if [ ! -s "$_manager_scan_output" ] || [ -L "$_manager_scan_output" ]; then
            boot_stock_scan_receipt failed no
            return 1
        fi
        # Preserve backups and prevent same-boot lease takeover if publication
        # is interrupted or its rollback cannot be confirmed.
        _manager_stage_preserve=1
        boot_stock_scan_publish
        _manager_publish_rc=$?
        if [ "$_manager_publish_rc" -ne 0 ]; then
            if [ "$_manager_publish_rc" -eq 125 ]; then
                _manager_stage_preserve=1
                boot_stock_scan_receipt cleanup-pending no
            else
                _manager_stage_preserve=0
                boot_stock_scan_receipt failed no
            fi
            return "$_manager_publish_rc"
        fi
        _manager_stage_preserve=0
        rm -f "$MODDIR/config/stock_inventory_scan_pending" 2>/dev/null || true
        boot_stock_scan_receipt success yes
        printf '%s\n' "$_manager_scan_response"
    else
        case "$_manager_scan_rc" in
            124) boot_stock_scan_receipt timeout no ;;
            125) boot_stock_scan_receipt cleanup-pending no ;;
            *) boot_stock_scan_receipt failed no ;;
        esac
        printf '{"status":"error","message":"启动期原厂扫描未完成，旧清单与待办已保留","code":%s}\n' "$_manager_scan_rc"
    fi
    # 124 reaches here only after verified cleanup. 125 retains the lock, stage
    # and task identity instead of calling an unconfirmed scan complete.
    return "$_manager_scan_rc"
}

if [ "${1:-}" = action ] && [ "${2:-}" = switch ]; then
    # The legacy composite runtime creates a temporary family (LuoShuAutoMix etc.)
    # only as a source container. It must never become the persisted active font.
    # Keep the user-visible/runtime identity as `mix`, while the safe switch still
    # resolves and validates the temporary source family normally.
    if [ -n "${LUOSHU_REAL_MODDIR:-}" ]; then
        case "$MODDIR" in
            */legacy-v14-runtime|*/.legacy-v14-runtime)
                LUOSHU_SWITCH_ACTIVE_LABEL="${LUOSHU_SWITCH_ACTIVE_LABEL:-mix}"
                export LUOSHU_SWITCH_ACTIVE_LABEL
                ;;
        esac
    fi
    if [ -f "$SAFE_SWITCH" ]; then
        exec sh "$SAFE_SWITCH" "$@"
    fi
    if [ -f "$LEGACY_SWITCH" ]; then
        exec sh "$LEGACY_SWITCH" "$@"
    fi
    printf '{"status":"error","message":"%s"}\n' "$(json_escape_router '缺少字体切换核心')"
    exit 1
fi

if [ "${1:-}" = action ] && [ "${2:-}" = stock_scan ]; then
    if [ "$_manager_boot_stock_scan" -eq 1 ] && [ -z "${LUOSHU_BOOT_STOCK_SCAN_STAGE:-}" ]; then
        boot_stock_scan_json "$@"
    else
        stock_scan_json
    fi
    exit $?
fi

if [ ! -f "$CURRENT_MANAGER" ]; then
    printf '{"status":"error","message":"%s"}\n' "$(json_escape_router '缺少当前字体管理后端')"
    exit 1
fi

# Keep the existing fast user-font index, but report the stock scanner as available
# whenever its real runtime dependencies are present. Older v4 code hard-coded
# nativeAvailable=false even though the stock scanner was packaged and usable.
case "${1:-}:${2:-}" in
    action:list|list:*)
        if stock_scan_available; then
            _manager_out=$(sh "$CURRENT_MANAGER" "$@")
            _manager_rc=$?
            # Android mksh has no printf builtin: passing a 1000-row list as an argv
            # to toybox printf can fail with E2BIG. Stream it through a here-doc.
            sed 's/"nativeAvailable":false/"nativeAvailable":true/g' <<LUOSHU_MANAGER_OUTPUT
$_manager_out
LUOSHU_MANAGER_OUTPUT
            exit "$_manager_rc"
        fi
        ;;
esac
exec sh "$CURRENT_MANAGER" "$@"
