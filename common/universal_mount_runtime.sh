#!/system/bin/sh
# Phase 7 unified mount runtime for Magisk / KernelSU / APatch.
# One payload, one transaction; Root manager changes only the hook stage.
set +e

MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
MODULE_DIR="$MODDIR"
CONFIG_DIR="${CONFIG_DIR:-$MODDIR/config}"
PAYLOAD="$MODDIR/.luoshu-payload"
RUNTIME_CONF="$CONFIG_DIR/universal-font-runtime.conf"
MOUNT_STATE="$CONFIG_DIR/universal-font-mount.conf"
STATE_ROOT="${LUOSHU_UNIVERSAL_MOUNT_STATE_ROOT:-/data/adb/luoshu/universal-mount}"
DYNAMIC_LIST="$STATE_ROOT/dynamic.mounts"
_ufmr_validated_deployment_id=''
_ufmr_validated_payload_digest=''

[ -f "$MODDIR/common/private_payload.sh" ] && . "$MODDIR/common/private_payload.sh"
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/font_config_runtime.sh" ] && . "$MODDIR/common/font_config_runtime.sh"
[ -f "$MODDIR/common/font_config_partitions.sh" ] && . "$MODDIR/common/font_config_partitions.sh"
[ -f "$MODDIR/common/mount_compat.sh" ] && . "$MODDIR/common/mount_compat.sh"
[ -f "$MODDIR/common/mount_self_backend.sh" ] && . "$MODDIR/common/mount_self_backend.sh"

_ufmr_log() {
    mkdir -p "$MODDIR/logs" 2>/dev/null || true
    printf '[%s] [UNIVERSAL-MOUNT] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$*" >> "$MODDIR/logs/universal-mount.log" 2>/dev/null || true
}

_ufmr_python() {
    _ufmr_root="$MODDIR/common/python"
    _ufmr_bin="$_ufmr_root/bin/luoshu-python"
    if [ -n "${LUOSHU_PYTHON:-}" ]; then
        "$LUOSHU_PYTHON" "$@"
        return $?
    fi
    [ -x "$_ufmr_bin" ] || return 127
    PYTHONHOME="$_ufmr_root" \
    PYTHONPATH="$MODDIR/common:$_ufmr_root/lib/python3.14:$_ufmr_root/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$_ufmr_root/lib:$_ufmr_root/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$_ufmr_bin" "$@"
}

_ufmr_validate_payload() {
    _ufmr_deployer="$MODDIR/common/universal_font_deployment.py"
    _ufmr_manifest="$PAYLOAD/.luoshu-runtime/deployment/deployment.json"
    [ -f "$_ufmr_deployer" ] && [ -s "$_ufmr_manifest" ] || return 1
    _ufmr_validated_deployment_id=$(_ufmr_value "$RUNTIME_CONF" deploymentId)
    _ufmr_validated_payload_digest=$(_ufmr_value "$RUNTIME_CONF" payloadDigest)
    _ufmr_validation_output=$(_ufmr_python "$_ufmr_deployer" \
        --payload-root "$PAYLOAD" \
        --expected-deployment-id "$_ufmr_validated_deployment_id" \
        --expected-payload-digest "$_ufmr_validated_payload_digest" \
        --validate-dynamic-generation --validate-device-generation --validate-payload-only "$_ufmr_manifest" 2>&1)
    _ufmr_validation_rc=$?
    if [ "$_ufmr_validation_rc" -ne 0 ]; then
        _ufmr_log "payload validation detail: $(printf '%s' "$_ufmr_validation_output" | head -c 1024)"
    fi
    return "$_ufmr_validation_rc"
}

_ufmr_has_partition_payload() {
    for _ufmr_part in system system_ext product vendor odm oem my_product my_engineering my_company my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust hw_product; do
        [ -d "$PAYLOAD/$_ufmr_part" ] || continue
        find "$PAYLOAD/$_ufmr_part" -type f -print -quit 2>/dev/null | grep -q . && return 0
    done
    return 1
}

_ufmr_value() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

_ufmr_hash() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" 2>/dev/null | awk '{print $1}'
    elif command -v busybox >/dev/null 2>&1; then
        busybox sha256sum "$1" 2>/dev/null | awk '{print $1}'
    else
        return 1
    fi
}

_ufmr_mount() {
    if [ -n "${LUOSHU_UNIVERSAL_MOUNT_COMMAND:-}" ]; then
        "$LUOSHU_UNIVERSAL_MOUNT_COMMAND" "$@"
    elif type _luoshu_mount_cmd >/dev/null 2>&1; then
        _luoshu_mount_cmd "$@"
    else
        mount "$@"
    fi
}

_ufmr_umount() {
    if [ -n "${LUOSHU_UNIVERSAL_UMOUNT_COMMAND:-}" ]; then
        "$LUOSHU_UNIVERSAL_UMOUNT_COMMAND" "$@"
    elif type _luoshu_umount_cmd >/dev/null 2>&1; then
        _luoshu_umount_cmd "$@"
    else
        umount "$@"
    fi
}

_ufmr_visible_target() {
    _ufmr_logical="$1"
    if [ -n "${LUOSHU_UNIVERSAL_TEST_VISIBLE_ROOT:-}" ]; then
        printf '%s%s\n' "${LUOSHU_UNIVERSAL_TEST_VISIBLE_ROOT%/}" "$_ufmr_logical"
    else
        printf '%s\n' "$_ufmr_logical"
    fi
}

_ufmr_real_target() {
    _ufmr_path="$1"
    _ufmr_real=''
    if command -v readlink >/dev/null 2>&1; then
        _ufmr_real=$(readlink -f "$_ufmr_path" 2>/dev/null)
    elif command -v busybox >/dev/null 2>&1; then
        _ufmr_real=$(busybox readlink -f "$_ufmr_path" 2>/dev/null)
    fi
    [ -n "$_ufmr_real" ] || _ufmr_real="$_ufmr_path"
    printf '%s\n' "$_ufmr_real"
}

_ufmr_stage_for_manager() {
    case "$1" in
        KernelSU|KernelSU*|SukiSU|SukiSU*|APatch) printf 'post-mount\n' ;;
        *) printf 'post-fs-data\n' ;;
    esac
}

_ufmr_xml_labels() (
    source="$1"; stock="$2"
    [ "$(id -u)" = 0 ] && [ "$(getenforce 2>/dev/null)" = Enforcing ] || exit 1
    [ -d "$stock" ] && [ ! -L "$stock" ] || exit 1
    label=$(_luoshu_file_context "$stock") || exit 1
    printf '.|%s\n' "$label"
    for file in "$source"/* "$source"/.[!.]* "$source"/..?*; do
        [ -e "$file" ] || [ -L "$file" ] || continue
        name="${file##*/}"
        case "$name" in fonts.xml|font_fallback.xml) ;; *) exit 1 ;; esac
        [ -f "$file" ] && [ ! -L "$file" ] || exit 1
        [ -f "$stock/$name" ] && [ ! -L "$stock/$name" ] || exit 1
        label=$(_luoshu_file_context "$stock/$name") || exit 1
        printf '%s|%s\n' "$name" "$label"
    done
)

_ufmr_validate_xml_scope() (
    source="$1"; stock="$2"; copy="${3:-}"
    [ -n "$_ufmr_validated_deployment_id" ] && [ -n "$_ufmr_validated_payload_digest" ] || exit 1
    [ "$(_ufmr_value "$RUNTIME_CONF" deploymentId)" = "$_ufmr_validated_deployment_id" ] &&
    [ "$(_ufmr_value "$RUNTIME_CONF" payloadDigest)" = "$_ufmr_validated_payload_digest" ] || {
        _ufmr_log 'system XML transaction identity changed after validation'; exit 1;
    }
    set -- --payload-root "$PAYLOAD" --system-xml-source-root "$source" \
        --system-xml-stock-root "$stock" \
        --expected-deployment-id "$_ufmr_validated_deployment_id" \
        --expected-payload-digest "$_ufmr_validated_payload_digest" \
        --validate-device-generation --validate-dynamic-generation \
        --validate-payload-only "$PAYLOAD/.luoshu-runtime/deployment/deployment.json"
    [ -z "$copy" ] || set -- "$@" --system-xml-copy-root "$copy"
    output=$(_ufmr_python "$MODDIR/common/universal_font_deployment.py" "$@" 2>&1)
    rc=$?
    if [ "$rc" -ne 0 ]; then
        _ufmr_log "system XML proof failed: $(printf '%s' "$output" | head -c 1024)"
    fi
    return "$rc"
)

# A repeated hook may see our published XML. Reuse only this boot's exact
# owned overlay and its private lower; never a loose stale directory of files.
_ufmr_xml_stock_root() (
    state=$(_luoshu_self_state_root) || exit 1
    target="$(_luoshu_partition_root system)/etc"
    intent="$state/overlay-intents/system-etc"
    boot=$(_luoshu_atomic_boot_id)
    if [ -f "$intent" ] && [ -n "$boot" ] && [ "$boot" != unknown ] &&
       [ "$(cat "$state/boot-id" 2>/dev/null)" = "$boot" ]; then
        IFS='|' read -r source lower saved_target baseline owned < "$intent" || exit 1
        [ "$saved_target" = "$(_ufmr_real_target "$target")" ] || exit 1
        [ "$lower" = "$state/lower/system-etc" ] || exit 1
        case "$source" in "$PAYLOAD/system/etc"|"$state/memory-layers/system-etc") ;; *) exit 1 ;; esac
        [ -n "$owned" ] && [ "$(_luoshu_visible_mount_id "$saved_target")" = "$owned" ] || exit 1
        _luoshu_owned_mount_matches overlay "$saved_target" "$owned" "$source" "$lower" || exit 1
        grep -Fqx "$lower" "$state/mounts.list" || exit 1
        awk -v p="$lower" '$5==p{ok=1}END{exit !ok}' /proc/self/mountinfo || exit 1
        printf '%s\n' "$lower"
    else
        printf '%s\n' "$target"
    fi
)

_ufmr_system_mount() (
    # Scope the strict requirement to this validated deployment transaction.
    # Subshell keeps legacy mounts from inheriting a persistent policy change.
    export LUOSHU_REQUIRED_PAYLOAD_FILES=1
    # Presence is trustworthy only after the whole execution tree was validated.
    # This proof runs before the self-mount engine can mount even its first font.
    if [ -f "$PAYLOAD/.luoshu-runtime/deployment/fixed-static-route-plan.json" ]; then
        _ufmr_xml_stock=$(_ufmr_xml_stock_root) || { _ufmr_log 'system XML stock ownership proof failed'; return 1; }
        _ufmr_validate_xml_scope "$PAYLOAD/system/etc" "$_ufmr_xml_stock" >/dev/null || return 1
        _ufmr_xml_original_labels=$(_ufmr_xml_labels "$PAYLOAD/system/etc" "$_ufmr_xml_stock") || {
            _ufmr_log 'system XML preflight requires root, Enforcing and readable original labels'; return 1;
        }
        _luoshu_universal_xml_copy_check() (
            source="$1"; lower="$2"; copy="${3:-}"
            state=$(_luoshu_self_state_root) || exit 1
            [ "$lower" = "$state/lower/system-etc" ] || exit 1
            grep -Fqx "$lower" "$_lsme_mount_list" || exit 1
            awk -v p="$lower" '$5==p{ok=1}END{exit !ok}' /proc/self/mountinfo || exit 1
            _ufmr_validate_xml_scope "$source" "$lower" "$copy" >/dev/null || exit 1
            [ "$(_ufmr_xml_labels "$source" "$lower")" = "$_ufmr_xml_original_labels" ] || exit 1
            if [ -n "$copy" ]; then
                [ "$copy" = "$state/memory-layers/system-etc" ] || exit 1
                [ "$(_ufmr_xml_labels "$source" "$copy")" = "$_ufmr_xml_original_labels" ] || exit 1
            fi
        )
    fi
    if [ -n "${LUOSHU_UNIVERSAL_TEST_SYSTEM_MOUNT_COMMAND:-}" ]; then
        "$LUOSHU_UNIVERSAL_TEST_SYSTEM_MOUNT_COMMAND"
    else
        type luoshu_private_self_mount_ensure >/dev/null 2>&1 || return 1
        luoshu_private_self_mount_ensure
    fi
)

_ufmr_system_rollback() {
    if [ -n "${LUOSHU_UNIVERSAL_TEST_SYSTEM_ROLLBACK_COMMAND:-}" ]; then
        "$LUOSHU_UNIVERSAL_TEST_SYSTEM_ROLLBACK_COMMAND" >/dev/null 2>&1 || true
        return 0
    fi
    _ufmr_rollback_system
}

_ufmr_is_mounted() {
    _ufmr_target="$1"
    _ufmr_mountinfo="${LUOSHU_UNIVERSAL_MOUNTINFO:-/proc/self/mountinfo}"
    awk -v path="$_ufmr_target" '$5 == path {found=1} END {exit !found}' "$_ufmr_mountinfo" 2>/dev/null
}

_ufmr_is_readonly() {
    _ufmr_target="$1"
    [ "${LUOSHU_UNIVERSAL_TEST_ASSUME_RO:-0}" = 1 ] && return 0
    _ufmr_mountinfo="${LUOSHU_UNIVERSAL_MOUNTINFO:-/proc/self/mountinfo}"
    awk -v path="$_ufmr_target" '
        $5 == path && $6 ~ /(^|,)ro(,|$)/ {found=1}
        END {exit !found}
    ' "$_ufmr_mountinfo" 2>/dev/null
}

_ufmr_rollback_dynamic() {
    [ -s "$DYNAMIC_LIST" ] || return 0
    awk '{item[NR]=$0} END {for(i=NR;i>=1;i--) print item[i]}' "$DYNAMIC_LIST" 2>/dev/null | while IFS= read -r _ufmr_target; do
        [ -n "$_ufmr_target" ] || continue
        case "$_ufmr_target" in "${LUOSHU_UNIVERSAL_TEST_VISIBLE_ROOT:-}/data/fonts/"*) _ufmr_umount "$_ufmr_target" >/dev/null 2>&1 || true ;; esac
    done
    : > "$DYNAMIC_LIST" 2>/dev/null || true
}

_ufmr_apply_dynamic() {
    _ufmr_conf="$PAYLOAD/.luoshu-runtime/deployment/dynamic-mounts.conf"
    mkdir -p "$STATE_ROOT" 2>/dev/null || return 1
    _ufmr_boot=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null)
    _ufmr_owned="$STATE_ROOT/dynamic.previous.$$"
    : > "$_ufmr_owned" 2>/dev/null || return 1
    if [ "$(cat "$STATE_ROOT/boot-id" 2>/dev/null)" = "$_ufmr_boot" ] && [ -f "$DYNAMIC_LIST" ]; then
        cp -f "$DYNAMIC_LIST" "$_ufmr_owned" || return 1
    fi
    printf '%s\n' "$_ufmr_boot" > "$STATE_ROOT/boot-id" || return 1
    : > "$DYNAMIC_LIST" 2>/dev/null || return 1
    [ -s "$_ufmr_conf" ] || { rm -f "$_ufmr_owned"; return 0; }
    while IFS='|' read -r _ufmr_source_rel _ufmr_target _ufmr_expected; do
        [ -n "$_ufmr_source_rel" ] && [ -n "$_ufmr_target" ] && [ -n "$_ufmr_expected" ] || continue
        case "$_ufmr_source_rel" in .luoshu-dynamic/*) ;; *) return 1 ;; esac
        case "$_ufmr_target" in /data/fonts/*) ;; *) return 1 ;; esac
        _ufmr_source="$PAYLOAD/$_ufmr_source_rel"
        _ufmr_actual_target=$(_ufmr_visible_target "$_ufmr_target")
        [ -f "$_ufmr_source" ] && [ -f "$_ufmr_actual_target" ] || return 1
        _ufmr_actual_target=$(_ufmr_real_target "$_ufmr_actual_target")
        [ -f "$_ufmr_actual_target" ] || return 1
        [ "$(_ufmr_hash "$_ufmr_source")" = "$_ufmr_expected" ] || return 1
        case "$_ufmr_actual_target" in
            "${LUOSHU_UNIVERSAL_TEST_VISIBLE_ROOT:-}/data/fonts/"*) ;;
            *) return 1 ;;
        esac
        if _ufmr_is_mounted "$_ufmr_actual_target"; then
            # Equal bytes do not grant ownership of another producer's mount.
            grep -Fqx "$_ufmr_actual_target" "$_ufmr_owned" || return 1
            printf '%s\n' "$_ufmr_actual_target" >> "$DYNAMIC_LIST" || return 1
            _ufmr_is_readonly "$_ufmr_actual_target" || return 1
            [ "$(_ufmr_hash "$_ufmr_actual_target")" = "$_ufmr_expected" ] || return 1
            continue
        fi
        _ufmr_mount --bind "$_ufmr_source" "$_ufmr_actual_target" >/dev/null 2>&1 || \
            _ufmr_mount -o bind "$_ufmr_source" "$_ufmr_actual_target" >/dev/null 2>&1 || return 1
        _ufmr_mount -o remount,bind,ro "$_ufmr_actual_target" >/dev/null 2>&1 || \
            _ufmr_mount -o bind,remount,ro "$_ufmr_actual_target" >/dev/null 2>&1 || {
                _ufmr_umount "$_ufmr_actual_target" >/dev/null 2>&1 || true
                return 1
            }
        if ! _ufmr_is_readonly "$_ufmr_actual_target"; then
            _ufmr_umount "$_ufmr_actual_target" >/dev/null 2>&1 || true
            return 1
        fi
        [ "$(_ufmr_hash "$_ufmr_actual_target")" = "$_ufmr_expected" ] || {
            _ufmr_umount "$_ufmr_actual_target" >/dev/null 2>&1 || true
            return 1
        }
        printf '%s\n' "$_ufmr_actual_target" >> "$DYNAMIC_LIST" || return 1
    done < "$_ufmr_conf"
    rm -f "$_ufmr_owned" 2>/dev/null || true
    return 0
}

_ufmr_rollback_system() {
    if type _luoshu_atomic_rollback >/dev/null 2>&1 && type _luoshu_self_state_root >/dev/null 2>&1; then
        _ufmr_system_list="$(_luoshu_self_state_root)/mounts.list"
        _luoshu_atomic_rollback "$_ufmr_system_list" >/dev/null 2>&1 || return 1
    fi
}

_ufmr_write_state() {
    _ufmr_state="$1"; _ufmr_manager="$2"; _ufmr_stage="$3"; _ufmr_dynamic="$4"; _ufmr_error="$5"
    mkdir -p "$CONFIG_DIR" 2>/dev/null || true
    _ufmr_id=$(_ufmr_value "$RUNTIME_CONF" deploymentId)
    _ufmr_digest=$(_ufmr_value "$RUNTIME_CONF" payloadDigest)
    {
        printf 'state=%s\n' "$_ufmr_state"
        printf 'backend=self-mount\n'
        printf 'manager=%s\n' "$_ufmr_manager"
        printf 'stage=%s\n' "$_ufmr_stage"
        printf 'deploymentId=%s\n' "$_ufmr_id"
        printf 'payloadDigest=%s\n' "$_ufmr_digest"
        printf 'dynamicMounted=%s\n' "$_ufmr_dynamic"
        printf 'error=%s\n' "$_ufmr_error"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$MOUNT_STATE.tmp.$$" 2>/dev/null && mv -f "$MOUNT_STATE.tmp.$$" "$MOUNT_STATE" 2>/dev/null || true
}

universal_font_mount_hook() {
    _ufmr_hook="$1"
    [ -s "$RUNTIME_CONF" ] || return 2
    [ "$(_ufmr_value "$RUNTIME_CONF" state)" = active ] || return 2
    [ "$(_ufmr_value "$RUNTIME_CONF" pipeline)" = universal-font-deployment-v1 ] || return 1
    [ -d "$PAYLOAD" ] || return 1
    [ -s "$PAYLOAD/.luoshu-runtime/deployment/deployment.json" ] || return 1
    if [ -n "${LUOSHU_UNIVERSAL_TEST_MANAGER:-}" ]; then
        _ufmr_manager="$LUOSHU_UNIVERSAL_TEST_MANAGER"
    else
        type luoshu_detect_root_manager >/dev/null 2>&1 || return 1
        _ufmr_manager=$(luoshu_detect_root_manager 2>/dev/null | head -n1)
    fi
    if type luoshu_self_mount_stage_for_manager >/dev/null 2>&1; then
        _ufmr_stage=$(luoshu_self_mount_stage_for_manager "$_ufmr_manager" 2>/dev/null)
    else
        _ufmr_stage=$(_ufmr_stage_for_manager "$_ufmr_manager")
    fi
    [ "$_ufmr_stage" = "$_ufmr_hook" ] || return 2

    _ufmr_validate_payload || {
        _ufmr_write_state failed "$_ufmr_manager" "$_ufmr_stage" 0 payload-integrity-failed
        _ufmr_log "payload integrity validation failed before mount"
        return 1
    }

    _ufmr_system_mounted=0
    if _ufmr_has_partition_payload; then
        if ! _ufmr_system_mount >/dev/null 2>&1; then
            _ufmr_write_state failed "$_ufmr_manager" "$_ufmr_stage" 0 system-mount-failed
            _ufmr_log "system payload mount failed manager=$_ufmr_manager stage=$_ufmr_stage"
            return 1
        fi
        _ufmr_system_mounted=1
    fi

    if ! _ufmr_apply_dynamic; then
        _ufmr_rollback_dynamic
        [ "$_ufmr_system_mounted" -eq 0 ] || _ufmr_system_rollback
        type _luoshu_self_state_write >/dev/null 2>&1 && _luoshu_self_state_write failed rollback '' dynamic-mount-failed
        _ufmr_write_state failed "$_ufmr_manager" "$_ufmr_stage" 0 dynamic-mount-failed
        _ufmr_log "dynamic mount failed; system payload rolled back"
        return 1
    fi
    _ufmr_dynamic_count=$(wc -l < "$DYNAMIC_LIST" 2>/dev/null | tr -d '[:space:]')
    case "$_ufmr_dynamic_count" in ''|*[!0-9]*) _ufmr_dynamic_count=0 ;; esac
    _ufmr_write_state mounted "$_ufmr_manager" "$_ufmr_stage" "$_ufmr_dynamic_count" ''
    _ufmr_log "mounted deployment=$(_ufmr_value "$RUNTIME_CONF" deploymentId) manager=$_ufmr_manager stage=$_ufmr_stage dynamic=$_ufmr_dynamic_count"
    return 0
}

case "${1:-hook}" in
    hook) universal_font_mount_hook "${2:-post-fs-data}" ;;
    service) exit 0 ;;
    rollback)
        _ufmr_rollback_dynamic
        if ! _ufmr_rollback_system; then
            _ufmr_write_state rollback-failed unknown manual 0 system-unmount-incomplete
            exit 1
        fi
        _ufmr_write_state rolled-back "$(type luoshu_detect_root_manager >/dev/null 2>&1 && luoshu_detect_root_manager || echo unknown)" manual 0 manual
        ;;
    *) echo "Usage: $0 {hook <post-fs-data|post-mount>|service|rollback}" >&2; exit 2 ;;
esac
