#!/system/bin/sh
# LuoShu safe physical font switch core.
# Foreground switching never renames, deletes or rewrites the payload used by the
# current Android boot. It builds .luoshu-payload-next off-line; post-fs-data activates
# that tree before LuoShu mounts fonts on the following complete boot.
set +e
# Keep the worker entry time before runtime-path and helper initialization. A
# shell read avoids starting a clock process; wall-clock changes cannot affect
# the phase durations recorded below.
_SAFE_SWITCH_ENTRY_UPTIME=''
IFS=' ' read -r _SAFE_SWITCH_ENTRY_UPTIME _safe_entry_unused < /proc/uptime 2>/dev/null || true

# Composite compatibility workers execute inside .legacy-v14-runtime and pass that
# directory as MODDIR. Their actual module is exported as LUOSHU_REAL_MODDIR. Always
# commit next-boot payload/state to the real module when that trusted hint is present.
_REALMOD_HINT="${LUOSHU_REAL_MODDIR:-}"
if [ -n "$_REALMOD_HINT" ] && [ -f "$_REALMOD_HINT/module.prop" ]; then
    MODDIR="$_REALMOD_HINT"
else
    MODDIR="${MODDIR:-}"
    if [ -z "$MODDIR" ]; then
        if [ -f "${0%/*}/../../module.prop" ]; then
            MODDIR="$(CDPATH= cd -- "${0%/*}/../.." 2>/dev/null && pwd)"
        else
            MODDIR="/data/adb/modules/LuoShu"
        fi
    fi
fi
MODULE_DIR="$MODDIR"
. "$MODDIR/common/runtime_paths.sh" || exit 126
luoshu_runtime_paths_init "$MODDIR" || exit 126
. "$MODDIR/common/background_task.sh" || exit 126
# Direct callers receive the same bounded ownership as App request callers.
# Re-entry is private to this scope; all font tools remain its descendants.
if [ "${1:-}" = action ] && [ "${LUOSHU_SAFE_SWITCH_SCOPED:-}" != 1 ]; then
    case "${2:-}" in
        switch|prewarm)
            _safe_task="safe-${2}-$(date +%s)-$$"
            _safe_timeout="${LUOSHU_SAFE_SWITCH_TIMEOUT:-360}"
            case "$_safe_timeout" in ''|*[!0-9]*) _safe_timeout=360 ;; esac
            exec sh "$(luoshu_scope_runner)" run --pid-file "$LUOSHU_TASKS_DIR/$_safe_task.pid" \
                --task "$_safe_task" --timeout "$_safe_timeout" -- \
                env LUOSHU_SAFE_SWITCH_SCOPED=1 sh "$0" "$@"
            ;;
    esac
fi
CONFIG_DIR="$LUOSHU_CONFIG_DIR"
LEGACY_DIR="$MODDIR/common/legacy_v14_4"
USER_ROOT="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}"
USER_FONTS_DIR="$USER_ROOT/fonts"
LIVE_PAYLOAD="$MODDIR/.luoshu-payload"
STAGE_PAYLOAD="${LUOSHU_TASK_SCOPE_TMPDIR:+$LUOSHU_TASK_SCOPE_TMPDIR/font-payload-stage}"
NEXT_PAYLOAD="$MODDIR/.luoshu-payload-next"
NEXT_STATE="$CONFIG_DIR/font-payload-next.conf"
ACTIVE_FONT_CONF="$CONFIG_DIR/active_font.conf"
LEGACY_MODE_CONF="$CONFIG_DIR/font_runtime_legacy_v14_4.conf"
TEXT_REBOOT_REQUIRED="$CONFIG_DIR/text_reboot_required.conf"
LOG_FILE="$LUOSHU_LOG_DIR/fontswitch.log"
SWITCH_LOCK="$MODDIR/.font_switch.lock"
PROGRESS_FILE="${LUOSHU_SWITCH_PROGRESS_FILE:-}"
SWITCH_CACHE_ROOT="$LUOSHU_CACHE_DIR/safe-switch-cache"
SWITCH_VALIDATION_CACHE_ROOT="$LUOSHU_CACHE_DIR/safe-switch-validation"
SWITCH_CACHE_SCHEMA="safe-switch-metrics-v2"
SWITCH_CACHE_MAX_ENTRIES="${LUOSHU_SWITCH_CACHE_MAX_ENTRIES:-3}"
SWITCH_CACHE_MAX_KB="${LUOSHU_SWITCH_CACHE_MAX_KB:-786432}"
case "$SWITCH_CACHE_MAX_ENTRIES" in ''|*[!0-9]*) SWITCH_CACHE_MAX_ENTRIES=3 ;; esac
case "$SWITCH_CACHE_MAX_KB" in ''|*[!0-9]*) SWITCH_CACHE_MAX_KB=786432 ;; esac
[ "$SWITCH_CACHE_MAX_ENTRIES" -ge 1 ] 2>/dev/null || SWITCH_CACHE_MAX_ENTRIES=1
[ "$SWITCH_CACHE_MAX_KB" -ge 131072 ] 2>/dev/null || SWITCH_CACHE_MAX_KB=131072
PREWARM_LOCK="$LUOSHU_TASKS_DIR/safe-switch-prewarm.lock"
LOCK_HELD=false
PREWARM_LOCK_HELD=false

# These records measure this switch worker, including its EXIT cleanup. The
# supervisor's .cleanup.json remains the proof of descendant reaping; synthesis,
# supervisor cleanup and a complete phone reboot are separate measurements.
SAFE_TIMING_ENABLED=false
SAFE_TIMING_PHASE=''
SAFE_CLEANUP_DONE=false
safe_timing_clock() {
    _stc_raw="${1:-}"
    if [ -z "$_stc_raw" ]; then
        IFS=' ' read -r _stc_raw _stc_unused < /proc/uptime 2>/dev/null || return 1
    fi
    case "$_stc_raw" in *.*) ;; *) return 1 ;; esac
    _stc_s=${_stc_raw%%.*}; _stc_fraction=${_stc_raw#*.}
    case "$_stc_s:$_stc_fraction" in :*|*:|*[!0-9:]*) return 1 ;; esac
    _stc_fraction="${_stc_fraction}000"
    _stc_fraction=${_stc_fraction%"${_stc_fraction#???}"}
    SAFE_TIMING_NOW_S=$_stc_s
    SAFE_TIMING_NOW_MS=$((1$_stc_fraction - 1000))
    SAFE_TIMING_NOW_UPTIME=$_stc_raw
}

safe_timing_elapsed() {
    # Subtract seconds before multiplying: mksh uses 32-bit arithmetic, so an
    # absolute uptime in milliseconds can overflow on a long-running phone.
    SAFE_TIMING_ELAPSED_MS=$(((SAFE_TIMING_NOW_S - $1) * 1000 + SAFE_TIMING_NOW_MS - $2))
    [ "$SAFE_TIMING_ELAPSED_MS" -ge 0 ] 2>/dev/null || SAFE_TIMING_ELAPSED_MS=0
}

safe_timing_record() {
    # Android mksh has builtin print, while printf can be an external command.
    # Keep each phase transition free of clock/logging subprocesses.
    if [ -n "${KSH_VERSION:-}" ]; then print -r -- "$1"
    else printf '%s\n' "$1"; fi >> "$LOG_FILE" 2>/dev/null || true
}

safe_timing_phase_end() {
    [ "$SAFE_TIMING_ENABLED" = true ] && [ -n "$SAFE_TIMING_PHASE" ] || return 0
    safe_timing_clock || return 0
    safe_timing_elapsed "$SAFE_TIMING_PHASE_S" "$SAFE_TIMING_PHASE_MS"
    safe_timing_record "[SAFE-TIMING] task=$SAFE_TIMING_TASK event=end phase=$SAFE_TIMING_PHASE status=${1:-completed} uptime=$SAFE_TIMING_NOW_UPTIME elapsedMs=$SAFE_TIMING_ELAPSED_MS"
    SAFE_TIMING_PHASE=''
}

safe_timing_phase() {
    [ "$SAFE_TIMING_ENABLED" = true ] || return 0
    safe_timing_phase_end completed
    safe_timing_clock || return 0
    SAFE_TIMING_PHASE="$1"
    SAFE_TIMING_PHASE_S=$SAFE_TIMING_NOW_S
    SAFE_TIMING_PHASE_MS=$SAFE_TIMING_NOW_MS
    safe_timing_record "[SAFE-TIMING] task=$SAFE_TIMING_TASK event=begin phase=$SAFE_TIMING_PHASE uptime=$SAFE_TIMING_NOW_UPTIME"
}

safe_timing_start() {
    safe_timing_clock "$_SAFE_SWITCH_ENTRY_UPTIME" || return 0
    SAFE_TIMING_ENABLED=true
    SAFE_TIMING_TASK="${LUOSHU_TASK_SCOPE_TASK:-unscoped}"
    SAFE_TIMING_START_S=$SAFE_TIMING_NOW_S
    SAFE_TIMING_START_MS=$SAFE_TIMING_NOW_MS
    SAFE_TIMING_PHASE=initialization
    SAFE_TIMING_PHASE_S=$SAFE_TIMING_NOW_S
    SAFE_TIMING_PHASE_MS=$SAFE_TIMING_NOW_MS
    safe_timing_record "[SAFE-TIMING] task=$SAFE_TIMING_TASK event=begin phase=initialization scope=safe-switch-worker clock=proc-uptime uptime=$SAFE_TIMING_NOW_UPTIME"
}

case "${1:-}:${2:-}" in action:switch) safe_timing_start ;; esac

export MODULE_DIR LUOSHU_PUBLIC_DIR="$USER_ROOT"
[ -f "$LEGACY_DIR/util_functions.sh" ] && . "$LEGACY_DIR/util_functions.sh"
[ -f "$LEGACY_DIR/font_check.sh" ] && . "$LEGACY_DIR/font_check.sh"
[ -f "$LEGACY_DIR/rom_adapters.sh" ] && . "$LEGACY_DIR/rom_adapters.sh"
[ -f "$MODDIR/common/font_switch_lock.sh" ] && . "$MODDIR/common/font_switch_lock.sh"
[ -f "$MODDIR/common/background_task.sh" ] && . "$MODDIR/common/background_task.sh"
[ -f "$LEGACY_DIR/payload_clone.sh" ] && . "$LEGACY_DIR/payload_clone.sh"
. "$MODDIR/common/font_next_transaction.sh" || exit 126
HYPEROS_COMPAT="$LEGACY_DIR/hyperos_full_coverage.sh"
[ -f "$HYPEROS_COMPAT" ] && . "$HYPEROS_COMPAT"

type ensure_public_storage >/dev/null 2>&1 && ensure_public_storage
type check_coloros >/dev/null 2>&1 && check_coloros
type check_hyperos >/dev/null 2>&1 && check_hyperos
mkdir -p "$CONFIG_DIR" "$MODDIR/logs" "$USER_FONTS_DIR" 2>/dev/null || true

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

read_state_value() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

safe_hash_stream() {
    if command -v sha256sum >/dev/null 2>&1; then
        _shs_output=$(sha256sum) || return 1
        _shs_hash=${_shs_output%% *}
    elif command -v busybox >/dev/null 2>&1; then
        _shs_output=$(busybox sha256sum) || return 1
        _shs_hash=${_shs_output%% *}
    else
        _shs_output=$(cksum) || return 1
        _shs_crc=${_shs_output%% *}
        _shs_output=${_shs_output#* }
        _shs_size=${_shs_output%% *}
        case "$_shs_crc:$_shs_size" in :*|*:|*[!0-9:]*) return 1 ;; esac
        printf '%s-%s\n' "$_shs_crc" "$_shs_size"
        return 0
    fi
    # The checksum commands emit one token followed by their stdin marker.
    # Parse it with shell builtins instead of launching awk for every nested
    # family/inventory/mapper/key hash in a foreground cache lookup.
    [ "${#_shs_hash}" -eq 64 ] || return 1
    case "$_shs_hash" in *[!0-9a-f]*) return 1 ;; esac
    printf '%s\n' "$_shs_hash"
}

safe_source_identity() {
    _ssi_file="$1"
    if command -v stat >/dev/null 2>&1; then
        stat -c '%d:%i:%s:%Y:%Z:%y:%z' "$_ssi_file" 2>/dev/null && return 0
    fi
    if command -v toybox >/dev/null 2>&1; then
        toybox stat -c '%d:%i:%s:%Y:%Z:%y:%z' "$_ssi_file" 2>/dev/null && return 0
    fi
    return 1
}

safe_inventory_identity() {
    _sii_build="${LUOSHU_BUILD_KEY:-}"
    if [ -z "$_sii_build" ] && command -v getprop >/dev/null 2>&1; then
        _sii_build=$(getprop ro.build.fingerprint 2>/dev/null)
        [ -n "$_sii_build" ] || _sii_build=$(getprop ro.build.display.id 2>/dev/null)
    fi
    _sii_inventory=no-inventory
    _sii_partitions=no-partition-manifest
    if [ -e "$CONFIG_DIR/device_font_inventory.json" ]; then
        _sii_inventory=$(safe_code_identity "$CONFIG_DIR/device_font_inventory.json") || return 1
    fi
    if [ -e "$CONFIG_DIR/device_font_partitions.conf" ]; then
        _sii_partitions=$(safe_code_identity "$CONFIG_DIR/device_font_partitions.conf") || return 1
    fi
    case "$_sii_build" in *'
'*) return 1 ;; esac
    # Keep the complete canonical snapshot in the final cache key/manifest.
    # Hashing these already bounded records again adds a subprocess without
    # adding input evidence; the final key still hashes the whole snapshot.
    printf 'build:%s:%s;inventory:%s:%s;partitions:%s:%s\n' \
        "${#_sii_build}" "$_sii_build" "${#_sii_inventory}" "$_sii_inventory" \
        "${#_sii_partitions}" "$_sii_partitions"
}

safe_code_identity() {
    for _sci_file in "$@"; do
        [ -f "$_sci_file" ] && [ -r "$_sci_file" ] || return 1
    done
    # Both Android cksum and BusyBox accept multiple paths. Hash the exact
    # output in one process instead of spawning cksum+awk for every helper.
    if command -v cksum >/dev/null 2>&1; then
        _sci_input=$(cksum "$@" 2>/dev/null) || return 1
        _sci_verify_cksum=1
    elif command -v busybox >/dev/null 2>&1; then
        _sci_input=$(busybox cksum "$@" 2>/dev/null) || return 1
        _sci_verify_cksum=1
    else
        _sci_verify_cksum=0
        _sci_input=''
        for _sci_file in "$@"; do
            _sci_identity=$(safe_source_identity "$_sci_file") || return 1
            _sci_input="$_sci_input
$_sci_file|$_sci_identity"
        done
    fi
    [ -n "$_sci_input" ] || return 1
    if [ "$_sci_verify_cksum" -eq 1 ]; then
        _sci_records=''
        # A successful exit with truncated/malformed output is not evidence.
        # Each requested helper must have one checksum/size/path record.
        while IFS=' ' read -r _sci_crc _sci_size _sci_path; do
            [ "$#" -gt 0 ] || return 1
            case "$_sci_crc:$_sci_size" in :*|*:|*[!0-9:]*) return 1 ;; esac
            [ "$_sci_crc" -le 4294967295 ] 2>/dev/null || return 1
            [ "$_sci_path" = "$1" ] || return 1
            case "$_sci_path" in *'
'*) return 1 ;; esac
            _sci_records="$_sci_records${#_sci_path}:$_sci_path|$_sci_crc:$_sci_size;"
            shift
        done <<EOF_SAFE_CHECKSUMS
$_sci_input
EOF_SAFE_CHECKSUMS
        [ "$#" -eq 0 ] || return 1
        printf 'code-cksum-v1:%s\n' "$_sci_records"
        return 0
    fi
    printf '%s\n' "$_sci_input" | safe_hash_stream
}

safe_mapper_identity() {
    # The shell wrappers do not change when a Python slot policy is fixed. All
    # code that selects donors, targets, routing or metrics belongs to the key.
    safe_code_identity "$LEGACY_DIR/rom_adapters.sh" "$LEGACY_DIR/util_functions.sh" \
        "$LEGACY_DIR/font_switch_safe.sh" "$LEGACY_DIR/hyperos_full_coverage.sh" \
        "$MODDIR/common/hyperos_stage_complete.sh" "$MODDIR/common/coloros_stage_complete.sh" \
        "$MODDIR/common/hyperos_metrics_batch.py" "$MODDIR/common/coloros_metrics_batch.py" \
        "$MODDIR/common/font_metrics_normalize.py" "$MODDIR/common/font_slot_coverage.py" \
        "$MODDIR/common/font_inventory.py" "$MODDIR/common/font_inventory_scan.py" \
        "$MODDIR/common/hyperos_physical_policy.py" "$MODDIR/common/hyperos_global.sh" \
        "$MODDIR/common/util_functions.sh" "$MODDIR/common/rom_adapters.sh"
}

safe_validator_identity() {
    safe_code_identity "$LEGACY_DIR/font_check.sh" "$LEGACY_DIR/font_coverage.py"
}

safe_family_identity() {
    _sfi_family="$1"
    # The mapper can select any weight in this family. A primary Regular file
    # staying unchanged must not hide an edited/added/removed Bold donor.
    type detect_font_family >/dev/null 2>&1 || return 1
    _sfi_input=''
    for _sfi_file in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
                     "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_sfi_file" ] || continue
        [ "$(detect_font_family "${_sfi_file##*/}")" = "$_sfi_family" ] || continue
        _sfi_identity=$(safe_source_identity "$_sfi_file") || return 1
        _sfi_input="$_sfi_input
$_sfi_file|$_sfi_identity"
    done
    printf '%s\n' "$_sfi_input" | safe_hash_stream
}

safe_rom_identity() {
    if [ "${IS_HYPEROS:-false}" = true ]; then
        printf 'hyperos\n'
    elif [ "${IS_COLOROS:-false}" = true ]; then
        printf 'coloros\n'
    else
        printf 'generic\n'
    fi
}

safe_partition_list() {
    _spl_base='system system_ext product vendor odm oem my_product my_engineering my_company my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust hw_product'
    printf '%s\n' "$_spl_base"
    _spl_manifest="$CONFIG_DIR/device_font_partitions.conf"
    [ -f "$_spl_manifest" ] || return 0
    _spl_seen=" $_spl_base "
    while IFS= read -r _spl_part; do
        case "$_spl_part" in ''|*[!A-Za-z0-9_]*|[0-9]*|_*) continue ;; esac
        case "$_spl_seen" in *" $_spl_part "*) continue ;; esac
        printf '%s\n' "$_spl_part"
        _spl_seen="$_spl_seen$_spl_part "
    done < "$_spl_manifest"
}

safe_validation_key() {
    _svk_file="$1"
    _svk_identity=$(safe_source_identity "$_svk_file") || return 1
    _svk_validator=$(safe_validator_identity) || return 1
    {
        printf 'safe-validation-v2\n'
        printf '%s\n' "$_svk_file"
        printf '%s\n' "$_svk_identity"
        printf '%s\n' "$_svk_validator"
    } | safe_hash_stream
}

safe_validation_restore() {
    _svr_file="$1"
    _svr_key=$(safe_validation_key "$_svr_file") || return 1
    _svr_conf="$SWITCH_VALIDATION_CACHE_ROOT/$_svr_key.conf"
    [ -s "$_svr_conf" ] || return 1
    _svr_identity=$(safe_source_identity "$_svr_file") || return 1
    _svr_seen=' '
    while IFS='=' read -r _svr_name _svr_value; do
        case "$_svr_name" in
            valid) _svr_wanted=true ;;
            identity) _svr_wanted="$_svr_identity" ;;
            *) continue ;;
        esac
        case "$_svr_seen" in *" $_svr_name "*) return 1 ;; esac
        [ "$_svr_value" = "$_svr_wanted" ] || return 1
        _svr_seen="$_svr_seen$_svr_name "
    done < "$_svr_conf"
    case "$_svr_seen" in *" valid "*) ;; *) return 1 ;; esac
    case "$_svr_seen" in *" identity "*) ;; *) return 1 ;; esac
}

safe_validation_store() {
    _svs_file="$1"
    _svs_key=$(safe_validation_key "$_svs_file") || return 1
    _svs_identity=$(safe_source_identity "$_svs_file") || return 1
    mkdir -p "$SWITCH_VALIDATION_CACHE_ROOT" 2>/dev/null || return 1
    _svs_conf="$SWITCH_VALIDATION_CACHE_ROOT/$_svs_key.conf"
    {
        printf 'valid=true\n'
        printf 'identity=%s\n' "$_svs_identity"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_svs_conf.tmp.$$" 2>/dev/null || return 1
    mv -f "$_svs_conf.tmp.$$" "$_svs_conf" 2>/dev/null || return 1
    chmod 0600 "$_svs_conf" 2>/dev/null || true
}

safe_switch_cache_key() {
    _sck_file="$1"; _sck_font="$2"
    _sck_identity=$(safe_source_identity "$_sck_file") || return 1
    _sck_inventory=$(safe_inventory_identity) || return 1
    _sck_rom=$(safe_rom_identity)
    _sck_mapper=$(safe_mapper_identity) || return 1
    _sck_family=$(safe_family_identity "$_sck_font") || return 1
    {
        printf '%s\n' "$SWITCH_CACHE_SCHEMA"
        printf '%s\n' "$_sck_font"
        printf '%s\n' "$_sck_file"
        printf '%s\n' "$_sck_identity"
        printf '%s\n' "$_sck_family"
        printf '%s\n' "$_sck_inventory"
        printf '%s\n' "$_sck_rom"
        printf '%s\n' "$_sck_mapper"
    } | safe_hash_stream
}

safe_switch_cache_matches() {
    _scm_conf="$1"; _scm_file="$2"; _scm_font="$3"
    _scm_source=$(safe_source_identity "$_scm_file") || return 1
    _scm_family=$(safe_family_identity "$_scm_font") || return 1
    _scm_inventory=$(safe_inventory_identity) || return 1
    _scm_rom=$(safe_rom_identity) || return 1
    _scm_mapper=$(safe_mapper_identity) || return 1
    _scm_seen=' '
    # One shell read replaces six sed/head/tr pipelines. Recompute identities
    # after selecting the key as before, so an intervening policy edit is a miss.
    while IFS='=' read -r _scm_name _scm_value; do
        case "$_scm_name" in
            schema) _scm_wanted="$SWITCH_CACHE_SCHEMA" ;;
            font) _scm_wanted="$_scm_font" ;;
            sourceIdentity) _scm_wanted="$_scm_source" ;;
            familyIdentity) _scm_wanted="$_scm_family" ;;
            inventoryIdentity) _scm_wanted="$_scm_inventory" ;;
            rom) _scm_wanted="$_scm_rom" ;;
            mapperIdentity) _scm_wanted="$_scm_mapper" ;;
            *) continue ;;
        esac
        case "$_scm_seen" in *" $_scm_name "*) return 1 ;; esac
        [ "$_scm_value" = "$_scm_wanted" ] || return 1
        _scm_seen="$_scm_seen$_scm_name "
    done < "$_scm_conf"
    for _scm_name in schema font sourceIdentity familyIdentity inventoryIdentity rom mapperIdentity; do
        case "$_scm_seen" in *" $_scm_name "*) ;; *) return 1 ;; esac
    done
}

safe_switch_cache_restore() {
    _scr_file="$1"; _scr_font="$2"
    _scr_key=$(safe_switch_cache_key "$_scr_file" "$_scr_font") || return 1
    _scr_root="$SWITCH_CACHE_ROOT/$_scr_key"
    _scr_conf="$_scr_root/cache.conf"
    [ -s "$_scr_conf" ] && [ -d "$_scr_root/tree" ] || return 1
    safe_switch_cache_matches "$_scr_conf" "$_scr_file" "$_scr_font" || return 1

    _scr_restored=0
    for _scr_part in $(safe_partition_list); do
        _scr_src="$_scr_root/tree/$_scr_part/fonts"
        [ -d "$_scr_src" ] || continue
        mkdir -p "$STAGE_PAYLOAD/$_scr_part" 2>/dev/null || return 1
        rm -rf "$STAGE_PAYLOAD/$_scr_part/fonts" 2>/dev/null || true
        if cp -al "$_scr_src" "$STAGE_PAYLOAD/$_scr_part/fonts" 2>/dev/null ||            cp -af "$_scr_src" "$STAGE_PAYLOAD/$_scr_part/fonts" 2>/dev/null; then
            _scr_restored=$((_scr_restored + 1))
        else
            return 1
        fi
    done
    [ "$_scr_restored" -gt 0 ] || return 1
    [ ! -f "$_scr_root/tree/.luoshu-metrics-report.json" ] ||         cp -f "$_scr_root/tree/.luoshu-metrics-report.json" "$STAGE_PAYLOAD/.luoshu-metrics-report.json" 2>/dev/null || true
    printf '[%s] [SAFE-SWITCH] cache hit font=%s key=%s partitions=%s\n'         "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$_scr_font" "$_scr_key" "$_scr_restored"         >> "$LOG_FILE" 2>/dev/null || true
    return 0
}

safe_switch_cache_dir_kb() {
    _scdk_dir="$1"
    if command -v du >/dev/null 2>&1; then
        _scdk_value=$(du -sk "$_scdk_dir" 2>/dev/null | awk 'NR==1 {print $1}')
    elif command -v busybox >/dev/null 2>&1; then
        _scdk_value=$(busybox du -sk "$_scdk_dir" 2>/dev/null | awk 'NR==1 {print $1}')
    else
        _scdk_value=0
    fi
    case "$_scdk_value" in ''|*[!0-9]*) _scdk_value=0 ;; esac
    printf '%s\n' "$_scdk_value"
}

safe_switch_cache_prune() {
    [ -d "$SWITCH_CACHE_ROOT" ] || return 0
    _scp_kept=0
    _scp_used=0
    for _scp_dir in $(ls -1dt "$SWITCH_CACHE_ROOT"/* 2>/dev/null); do
        [ -d "$_scp_dir" ] || continue
        _scp_kb=$(safe_switch_cache_dir_kb "$_scp_dir")
        _scp_next=$((_scp_used + _scp_kb))
        if [ "$_scp_kept" -eq 0 ] || {
            [ "$_scp_kept" -lt "$SWITCH_CACHE_MAX_ENTRIES" ] &&
            [ "$_scp_next" -le "$SWITCH_CACHE_MAX_KB" ]
        }; then
            _scp_kept=$((_scp_kept + 1))
            _scp_used=$_scp_next
            continue
        fi
        rm -rf "$_scp_dir" 2>/dev/null || true
    done
    printf '[%s] [SAFE-SWITCH] cache prune kept=%s budget_kb=%s used_kb=%s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" \
        "$_scp_kept" "$SWITCH_CACHE_MAX_KB" "$_scp_used" >> "$LOG_FILE" 2>/dev/null || true
}

safe_switch_cache_store() {
    _scs_file="$1"; _scs_font="$2"
    _scs_expected="${3:-}"
    [ -n "$_scs_expected" ] || return 1
    _scs_key=$(safe_switch_cache_key "$_scs_file" "$_scs_font") || return 1
    [ "$_scs_key" = "$_scs_expected" ] || return 1
    _scs_root="$SWITCH_CACHE_ROOT/$_scs_key"
    _scs_stage="$LUOSHU_TASK_SCOPE_TMPDIR/switch-cache-$_scs_key"
    rm -rf "$_scs_stage" 2>/dev/null || true
    mkdir -p "$_scs_stage/tree" 2>/dev/null || return 1
    _scs_saved=0
    for _scs_part in $(safe_partition_list); do
        _scs_src="$STAGE_PAYLOAD/$_scs_part/fonts"
        [ -d "$_scs_src" ] || continue
        find "$_scs_src" -type f -print -quit 2>/dev/null | grep -q . || continue
        mkdir -p "$_scs_stage/tree/$_scs_part" 2>/dev/null || { rm -rf "$_scs_stage"; return 1; }
        cp -al "$_scs_src" "$_scs_stage/tree/$_scs_part/fonts" 2>/dev/null ||             cp -af "$_scs_src" "$_scs_stage/tree/$_scs_part/fonts" 2>/dev/null || {
                rm -rf "$_scs_stage" 2>/dev/null || true
                return 1
            }
        _scs_saved=$((_scs_saved + 1))
    done
    [ "$_scs_saved" -gt 0 ] || { rm -rf "$_scs_stage" 2>/dev/null || true; return 1; }
    [ ! -f "$STAGE_PAYLOAD/.luoshu-metrics-report.json" ] ||         cp -f "$STAGE_PAYLOAD/.luoshu-metrics-report.json" "$_scs_stage/tree/.luoshu-metrics-report.json" 2>/dev/null || true
    _scs_identity=$(safe_source_identity "$_scs_file") || { rm -rf "$_scs_stage"; return 1; }
    _scs_family=$(safe_family_identity "$_scs_font") || { rm -rf "$_scs_stage"; return 1; }
    _scs_inventory=$(safe_inventory_identity) || { rm -rf "$_scs_stage"; return 1; }
    _scs_mapper=$(safe_mapper_identity) || { rm -rf "$_scs_stage"; return 1; }
    {
        printf 'schema=%s\n' "$SWITCH_CACHE_SCHEMA"
        printf 'font=%s\n' "$_scs_font"
        printf 'sourceIdentity=%s\n' "$_scs_identity"
        printf 'familyIdentity=%s\n' "$_scs_family"
        printf 'inventoryIdentity=%s\n' "$_scs_inventory"
        printf 'rom=%s\n' "$(safe_rom_identity)"
        printf 'mapperIdentity=%s\n' "$_scs_mapper"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_scs_stage/cache.conf" 2>/dev/null || { rm -rf "$_scs_stage"; return 1; }
    # The generated tree belongs to the inputs captured before mapping. Never
    # label it with newer donors or policy observed only after the work finished.
    _scs_current=$(safe_switch_cache_key "$_scs_file" "$_scs_font") || { rm -rf "$_scs_stage"; return 1; }
    [ "$_scs_current" = "$_scs_expected" ] || { rm -rf "$_scs_stage"; return 1; }
    mkdir -p "$SWITCH_CACHE_ROOT" 2>/dev/null || { rm -rf "$_scs_stage"; return 1; }
    rm -rf "$_scs_root" 2>/dev/null || true
    mv -f "$_scs_stage" "$_scs_root" 2>/dev/null || { rm -rf "$_scs_stage"; return 1; }
    safe_switch_cache_prune
    printf '[%s] [SAFE-SWITCH] cache store font=%s key=%s partitions=%s\n'         "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$_scs_font" "$_scs_key" "$_scs_saved"         >> "$LOG_FILE" 2>/dev/null || true
    return 0
}

progress() {
    _p="$1"; shift; _m="$*"
    printf '[%s] [SAFE-SWITCH] stage=%s message=%s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$_p" "$_m" >> "$LOG_FILE" 2>/dev/null || true
    [ -n "$PROGRESS_FILE" ] || return 0
    _tmp="${PROGRESS_FILE}.tmp.$$"
    {
        printf 'percent=%s\n' "$_p"
        printf 'message=%s\n' "$_m"
    } > "$_tmp" 2>/dev/null && mv -f "$_tmp" "$PROGRESS_FILE" 2>/dev/null || true
    chmod 0644 "$PROGRESS_FILE" 2>/dev/null || true
}

safe_error() {
    safe_timing_phase_end failed
    progress 100 "$1"
    printf '{"status":"error","message":"%s","pipeline":"next-boot-stage"}\n' "$(json_escape "$1")"
    return 1
}

lock_cleanup() {
    [ "$LOCK_HELD" = true ] || return 0
    if type luoshu_font_lock_release >/dev/null 2>&1; then
        luoshu_font_lock_release "$SWITCH_LOCK" "$$" >/dev/null 2>&1 || \
            luoshu_font_lock_force_clear "$SWITCH_LOCK" "$$" >/dev/null 2>&1 || true
    fi
    LOCK_HELD=false
}

prewarm_lock_cleanup() {
    [ "$PREWARM_LOCK_HELD" = true ] || return 0
    if type luoshu_font_lock_release >/dev/null 2>&1; then
        luoshu_font_lock_release "$PREWARM_LOCK" "$$" >/dev/null 2>&1 || \
            luoshu_font_lock_force_clear "$PREWARM_LOCK" "$$" >/dev/null 2>&1 || true
    fi
    PREWARM_LOCK_HELD=false
}

prewarm_lock_acquire() {
    type luoshu_font_lock_acquire >/dev/null 2>&1 || return 1
    luoshu_font_lock_acquire "$PREWARM_LOCK" "$$"
    _pl_rc=$?
    [ "$_pl_rc" -eq 0 ] || return "$_pl_rc"
    PREWARM_LOCK_HELD=true
    return 0
}

switch_busy() {
    if type luoshu_font_lock_active >/dev/null 2>&1; then
        luoshu_font_lock_active "$SWITCH_LOCK"
        return $?
    fi
    [ -e "$SWITCH_LOCK" ]
}

safe_switch_cache_ready() {
    _scrd_file="$1"; _scrd_font="$2"
    _scrd_key=$(safe_switch_cache_key "$_scrd_file" "$_scrd_font") || return 1
    _scrd_root="$SWITCH_CACHE_ROOT/$_scrd_key"
    _scrd_conf="$_scrd_root/cache.conf"
    [ -s "$_scrd_conf" ] && [ -d "$_scrd_root/tree" ] || return 1
    safe_switch_cache_matches "$_scrd_conf" "$_scrd_file" "$_scrd_font" || return 1
    find "$_scrd_root/tree" -type f \( -iname '*.ttf' -o -iname '*.otf' -o -iname '*.ttc' \) \
        -print -quit 2>/dev/null | grep -q .
}

wait_for_prewarm_cache() {
    _wfpc_file="$1"; _wfpc_font="$2"
    # Without an active producer there is nothing to wait for. Foreground
    # restore proves readiness after taking the switch lock; duplicating that
    # full donor/policy proof here only slows an ordinary warm switch.
    type luoshu_font_lock_active >/dev/null 2>&1 || return 1
    luoshu_font_lock_active "$PREWARM_LOCK" >/dev/null 2>&1 || return 1
    safe_switch_cache_ready "$_wfpc_file" "$_wfpc_font" && return 0
    _wfpc_steps=0
    while [ "$_wfpc_steps" -lt 16 ]; do
        sleep 0.25 2>/dev/null || sleep 1
        safe_switch_cache_ready "$_wfpc_file" "$_wfpc_font" && return 0
        luoshu_font_lock_active "$PREWARM_LOCK" >/dev/null 2>&1 || break
        _wfpc_steps=$((_wfpc_steps + 1))
    done
    return 1
}

lock_acquire() {
    type luoshu_font_lock_acquire >/dev/null 2>&1 || { safe_error '缺少字体切换身份锁'; return 1; }
    luoshu_font_lock_acquire "$SWITCH_LOCK" "$$"
    _rc=$?
    case "$_rc" in
        0) LOCK_HELD=true; return 0 ;;
        2) safe_error '字体正在切换中，请稍后再试'; return 1 ;;
        *) safe_error '无法创建字体切换锁'; return 1 ;;
    esac
}

cleanup_stage() {
    [ -z "$STAGE_PAYLOAD" ] || rm -rf "$STAGE_PAYLOAD" 2>/dev/null || true
}

cleanup_stale_stages() {
    for _stale_stage in "$MODDIR"/.luoshu-payload-stage.*; do
        [ -e "$_stale_stage" ] || continue
        [ "$_stale_stage" = "$STAGE_PAYLOAD" ] && continue
        rm -rf "$_stale_stage" 2>/dev/null || true
    done
}

safe_exit_cleanup() {
    _sec_result="$1"; _sec_status="$2"
    [ "$SAFE_CLEANUP_DONE" != true ] || return 0
    SAFE_CLEANUP_DONE=true
    safe_timing_phase_end "$_sec_status"
    safe_timing_phase worker_cleanup
    luoshu_next_transaction_rollback "$MODDIR" >/dev/null 2>&1 || true
    cleanup_stage; prewarm_lock_cleanup; lock_cleanup
    safe_timing_phase_end finished
    if [ "$SAFE_TIMING_ENABLED" = true ] && safe_timing_clock; then
        safe_timing_elapsed "$SAFE_TIMING_START_S" "$SAFE_TIMING_START_MS"
        safe_timing_record "[SAFE-TIMING] task=$SAFE_TIMING_TASK event=total scope=safe-switch-worker status=$_sec_status result=$_sec_result uptime=$SAFE_TIMING_NOW_UPTIME elapsedMs=$SAFE_TIMING_ELAPSED_MS"
    fi
}

trap '_safe_exit_rc=$?; if [ "$_safe_exit_rc" -eq 0 ]; then safe_exit_cleanup "$_safe_exit_rc" completed; else safe_exit_cleanup "$_safe_exit_rc" failed; fi' EXIT
trap 'safe_exit_cleanup 129 interrupted; exit 129' HUP
trap 'safe_exit_cleanup 130 interrupted; exit 130' INT
trap 'safe_exit_cleanup 143 interrupted; exit 143' TERM

find_text_font_file() {
    _wanted="$1"
    for _file in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
                 "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_file" ] || continue
        if type detect_font_family >/dev/null 2>&1; then
            _family="$(detect_font_family "$(basename "$_file")")"
        else
            _family="${_file##*/}"; _family="${_family%.*}"
        fi
        case "$_family" in SysFont*|SysSans*) continue ;; esac
        [ "$_family" = "$_wanted" ] && { printf '%s\n' "$_file"; return 0; }
    done
    return 1
}

validate_global() {
    _file="$1"
    if safe_validation_restore "$_file"; then
        printf '[%s] [SAFE-SWITCH] validation cache hit: %s\n' \
            "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$_file" >> "$LOG_FILE" 2>/dev/null || true
        return 0
    fi
    if type font_validate >/dev/null 2>&1; then
        font_validate "$_file" text || return 1
    fi
    _python="$MODDIR/common/python/bin/luoshu-python"
    _checker="$LEGACY_DIR/font_coverage.py"
    if [ -x "$_python" ] && [ -f "$_checker" ]; then
        _pyroot="$MODDIR/common/python"
        _coverage=$(PYTHONHOME="$_pyroot" \
            PYTHONPATH="$_pyroot/lib/python3.14:$_pyroot/lib/python3.14/site-packages" \
            LD_LIBRARY_PATH="$_pyroot/lib:$_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
            "$_python" "$_checker" --brief "$_file" 2>/dev/null)
        _rc=$?
        if [ "$_rc" -ne 0 ]; then
            FONT_CHECK_ERROR="${_coverage:-字体缺少全局替换所需字形}"
            return 1
        fi
    fi
    safe_validation_store "$_file" >/dev/null 2>&1 || true
    return 0
}

payload_clone_source() {
    if [ -d "$LIVE_PAYLOAD" ]; then
        printf '%s\n' "$LIVE_PAYLOAD"
        return 0
    fi

    # If an early-boot activation was interrupted after retiring the previous tree,
    # recover from the activation record instead of permanently blocking future
    # switches. Only trust retired paths owned by this module.
    _activated="$CONFIG_DIR/font-payload-activated.conf"
    _retired=$(read_state_value "$_activated" retired)
    case "$_retired" in
        "$MODDIR"/.luoshu-retired/*)
            [ -d "$_retired" ] && { printf '%s\n' "$_retired"; return 0; }
            ;;
    esac
    return 1
}

clone_payload_tree() {
    _clone_source="$1"
    cleanup_stage
    mkdir -p "$STAGE_PAYLOAD" 2>/dev/null || return 1

    if luoshu_clone_payload_metadata "$_clone_source" "$STAGE_PAYLOAD"; then
        return 0
    fi
    cleanup_stage
    return 1
}

stage_clone_live() {
    _clone_source=$(payload_clone_source) || {
        safe_error '当前启动字体负载不可读取，请重新刷入当前洛书版本'
        return 1
    }
    if ! clone_payload_tree "$_clone_source"; then
        printf '[%s] [SAFE-SWITCH] clone failed source=%s live=%s next=%s\n' \
            "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" \
            "$_clone_source" "$LIVE_PAYLOAD" "$NEXT_PAYLOAD" >> "$LOG_FILE" 2>/dev/null || true
        return 1
    fi
    return 0
}

stage_clear_text_payload() {
    for _part in $(safe_partition_list); do
        rm -rf "$STAGE_PAYLOAD/$_part/fonts" 2>/dev/null || true
        _etc="$STAGE_PAYLOAD/$_part/etc"
        [ -d "$_etc" ] || continue
        rm -f "$_etc/fonts.xml" "$_etc/font_fallback.xml" \
              "$_etc/fonts_customization.xml" "$_etc/font_customization.xml" 2>/dev/null || true
        for _xml in "$_etc"/*.xml; do
            [ -f "$_xml" ] || continue
            grep -a -qE 'LuoShuSlot-|LuoShu-|luoshu' "$_xml" 2>/dev/null && rm -f "$_xml" 2>/dev/null || true
        done
    done
    mkdir -p "$STAGE_PAYLOAD/system/fonts" 2>/dev/null || return 1
}

mirror_existing_targets() {
    _system_fonts="$STAGE_PAYLOAD/system/fonts"
    for _src in "$_system_fonts"/*; do
        [ -f "$_src" ] || continue
        _base="${_src##*/}"
        case "$_base" in *.ttf|*.otf|*.ttc) ;; *) continue ;; esac
        for _part in $(safe_partition_list); do
            [ "$_part" != system ] || continue
            [ -e "/$_part/fonts/$_base" ] || continue
            _dest="$STAGE_PAYLOAD/$_part/fonts/$_base"
            mkdir -p "${_dest%/*}" 2>/dev/null || continue
            if type link_or_copy_font >/dev/null 2>&1; then
                link_or_copy_font "$_src" "$_dest" >/dev/null 2>&1 || true
            else
                ln "$_src" "$_dest" 2>/dev/null || cp -f "$_src" "$_dest" 2>/dev/null || true
                chmod 0644 "$_dest" 2>/dev/null || true
            fi
        done
    done
}

stage_hyperos_complete() {
    [ "${IS_HYPEROS:-false}" = true ] || return 0

    # Use the current HyperOS target inventory to complete the isolated staged tree.
    # This covers current MiSans/Roboto/GoogleSans/NotoSans/Mitype/clock targets across
    # real partitions without ever touching the live payload used by this boot.
    _stage_bridge="$MODDIR/common/hyperos_stage_complete.sh"
    if [ -f "$_stage_bridge" ]; then
        LUOSHU_REAL_MODDIR="$MODDIR" LUOSHU_PUBLIC_DIR="$USER_ROOT" \
            sh "$_stage_bridge" "$STAGE_PAYLOAD" >> "$LOG_FILE" 2>&1 && return 0
    fi

    # A failed modern stage must not be replaced by raw aliases and reported OK.
    return 1
}

stage_coloros_complete() {
    [ "${IS_COLOROS:-false}" = true ] || return 0
    _stage_bridge="$MODDIR/common/coloros_stage_complete.sh"
    [ -f "$_stage_bridge" ] || return 1
    LUOSHU_REAL_MODDIR="$MODDIR" sh "$_stage_bridge" "$STAGE_PAYLOAD" >> "$LOG_FILE" 2>&1
}

stage_verify() {
    _font="$1"
    [ "$_font" = default ] && return 0
    _count=$(find "$STAGE_PAYLOAD" -type f \( -iname '*.ttf' -o -iname '*.otf' -o -iname '*.ttc' \) \
        2>/dev/null | wc -l | tr -d '[:space:]')
    case "$_count" in ''|*[!0-9]*) _count=0 ;; esac
    [ "$_count" -gt 0 ] || return 1
    [ -s "$STAGE_PAYLOAD/system/fonts/.luoshu-font-store/regular.font" ] || \
        [ -s "$STAGE_PAYLOAD/system/fonts/.luoshu-font-store/mix-composite.font" ] || \
        find "$STAGE_PAYLOAD/system/fonts" -maxdepth 1 -type f \( -iname '*.ttf' -o -iname '*.otf' -o -iname '*.ttc' \) \
            -print -quit 2>/dev/null | grep -q .
}

resolve_previous_state() {
    PREVIOUS_FONT=$(head -n1 "$ACTIVE_FONT_CONF" 2>/dev/null | tr -d '\r\n')
    [ -n "$PREVIOUS_FONT" ] || PREVIOUS_FONT=default
    PREVIOUS_LEGACY=false
    [ -f "$LEGACY_MODE_CONF" ] && PREVIOUS_LEGACY=true
    if [ -s "$NEXT_STATE" ]; then
        _queued_previous=$(read_state_value "$NEXT_STATE" previousFont)
        _queued_legacy=$(read_state_value "$NEXT_STATE" previousLegacy)
        [ -n "$_queued_previous" ] && PREVIOUS_FONT="$_queued_previous"
        [ "$_queued_legacy" = true ] && PREVIOUS_LEGACY=true || PREVIOUS_LEGACY=false
    fi
}

prepare_next_payload() {
    _font="$1"; _previous="$2"; _previous_legacy="$3"
    _next_tmp="$LUOSHU_TASK_SCOPE_TMPDIR/font-payload-next-state"
    {
        printf 'state=prepared\nfont=%s\n' "$_font"
        printf 'requestId=%s\n' "${LUOSHU_MIX_REQUEST_ID:-${LUOSHU_SWITCH_REQUEST_ID:-safe-$$-$(date +%s)}}"
        printf 'previousFont=%s\npreviousLegacy=%s\n' "$_previous" "$_previous_legacy"
        if [ "$_font" = mix ]; then
            printf 'cjk=%s\nlatin=%s\ndigit=%s\n' "${LUOSHU_MIX_EXPECTED_CJK:-}" "${LUOSHU_MIX_EXPECTED_LATIN:-}" "${LUOSHU_MIX_EXPECTED_DIGIT:-}"
            printf 'compositeHash=%s\n' "$(read_state_value "${LUOSHU_MIX_MANIFEST:-/dev/null}" compositeHash)"
        fi
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_next_tmp" 2>/dev/null || return 1
    luoshu_next_transaction_begin "$MODDIR" "$STAGE_PAYLOAD" "$_next_tmp" || return 1
    STAGE_PAYLOAD=""
    chmod 0644 "$NEXT_STATE" 2>/dev/null || true
    return 0
}

cancel_next_payload() { luoshu_next_transaction_rollback "$MODDIR"; }

write_runtime_state() {
    _font="$1"
    _tmp_active="${ACTIVE_FONT_CONF}.tmp.$$"
    printf '%s\n' "$_font" > "$_tmp_active" 2>/dev/null && mv -f "$_tmp_active" "$ACTIVE_FONT_CONF" 2>/dev/null || return 1
    chmod 0644 "$ACTIVE_FONT_CONF" 2>/dev/null || true
    _boot_id=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')
    {
        printf 'font=%s\n' "$_font"
        printf 'reason=next-boot-payload-prepared\n'
        printf 'bootId=%s\n' "$_boot_id"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$TEXT_REBOOT_REQUIRED" 2>/dev/null || true
    chmod 0644 "$TEXT_REBOOT_REQUIRED" 2>/dev/null || true

    rm -f "$CONFIG_DIR/font-payload-rebuild-pending.conf" \
          "$CONFIG_DIR/font-payload-reapply-notified.conf" \
          "$CONFIG_DIR/device-font-cache-pending.conf" \
          "$CONFIG_DIR/device-font-engine.conf" \
          "$CONFIG_DIR/device-font-installed.conf" \
          "$CONFIG_DIR/device-font-dynamic-mount.conf" \
          "$CONFIG_DIR/device-font-load-verification.json" \
          "$CONFIG_DIR/native_font_index.json" "$CONFIG_DIR/native_font_index.key" \
          "$CONFIG_DIR/webui_font_list.json" "$CONFIG_DIR/webui_font_list.key" 2>/dev/null || true
    return 0
}

prewarm_start() {
    _font="$1"
    [ -n "$_font" ] && [ "$_font" != default ] || return 0
    _source="$(find_text_font_file "$_font")"
    [ -f "$_source" ] || return 0
    type luoshu_scope_runner >/dev/null 2>&1 || return 0
    _prewarm_identity=$(safe_source_identity "$_source" 2>/dev/null)
    [ -n "$_prewarm_identity" ] || return 0
    _prewarm_key=$({
        printf '%s\n' "$_font"
        printf '%s\n' "$_prewarm_identity"
    } | safe_hash_stream | cut -c1-12)
    [ -n "$_prewarm_key" ] || return 0
    _prewarm_pid="$LUOSHU_TASKS_DIR/font-prewarm-$_prewarm_key.pid"
    _prewarm_task="font-prewarm-$_prewarm_key"
    _prewarm_log="$LUOSHU_LOG_DIR/font-prewarm.log"
    _self="$MODDIR/common/legacy_v14_4/font_switch_safe.sh"
    _prewarm_timeout="${LUOSHU_PREWARM_TIMEOUT:-360}"
    case "$_prewarm_timeout" in ''|*[!0-9]*) _prewarm_timeout=360 ;; esac
    # Prewarming is a finite request, never an idle detached service. Await the
    # supervisor's descendant cleanup and PID removal before returning.
    sh "$(luoshu_scope_runner)" run --pid-file "$_prewarm_pid" \
        --task "$_prewarm_task" --timeout "$_prewarm_timeout" -- \
        env LUOSHU_SAFE_SWITCH_SCOPED=1 \
        sh -c '
            _script="$1"; _family="$2"; _public="$3"
            [ -f "$_script" ] || exit 0
            export LUOSHU_PUBLIC_DIR="$_public"
            if command -v ionice >/dev/null 2>&1 && command -v nice >/dev/null 2>&1; then
                exec ionice -c 3 nice -n 19 sh "$_script" action prewarm "$_family"
            elif command -v nice >/dev/null 2>&1; then
                exec nice -n 19 sh "$_script" action prewarm "$_family"
            fi
            exec sh "$_script" action prewarm "$_family"
        ' font_switch_safe.sh "$_self" "$_font" "$USER_ROOT" >>"$_prewarm_log" 2>&1
    return $?
}

prewarm_font() {
    _font="$1"
    [ -n "$_font" ] && [ "$_font" != default ] || return 0
    [ -s "$CONFIG_DIR/device_font_inventory.json" ] || return 0
    switch_busy && return 0

    prewarm_lock_acquire
    _prewarm_lock_rc=$?
    [ "$_prewarm_lock_rc" -eq 0 ] || return 0
    switch_busy && return 0

    _source="$(find_text_font_file "$_font")"
    [ -f "$_source" ] || return 0
    validate_global "$_source" || return 0
    safe_switch_cache_ready "$_source" "$_font" && return 0

    stage_clone_live || return 0
    stage_clear_text_payload || return 0
    switch_busy && return 0

    PAYLOAD_ROOT="$STAGE_PAYLOAD"
    SYSTEM_FONTS_DIR="$STAGE_PAYLOAD/system/fonts"
    export PAYLOAD_ROOT SYSTEM_FONTS_DIR
    type apply_font_by_rom >/dev/null 2>&1 || return 0
    _prewarm_cache_key=$(safe_switch_cache_key "$_source" "$_font") || _prewarm_cache_key=''
    apply_font_by_rom "$_source" "$SYSTEM_FONTS_DIR" quick "$_font" >> "$LOG_FILE" 2>&1 || return 0
    mirror_existing_targets
    switch_busy && return 0

    if [ "${IS_HYPEROS:-false}" = true ]; then
        stage_hyperos_complete || return 0
    elif [ "${IS_COLOROS:-false}" = true ]; then
        stage_coloros_complete || return 0
    fi
    stage_verify "$_font" || return 0
    safe_switch_cache_store "$_source" "$_font" "$_prewarm_cache_key" >/dev/null 2>&1 || return 0
    printf '[%s] [SAFE-SWITCH] prewarm ready font=%s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$_font" >> "$LOG_FILE" 2>/dev/null || true
    return 0
}

switch_font() {
    _font="$1"
    [ -n "$_font" ] || { safe_error '未指定字体'; return 1; }
    _active_label="${LUOSHU_SWITCH_ACTIVE_LABEL:-$_font}"
    [ -n "$_active_label" ] || _active_label="$_font"

    _source=''
    if [ "$_font" != default ]; then
        safe_timing_phase source_lookup_validation
        progress 6 '正在查找并校验字体文件'
        _source="$(find_text_font_file "$_font")"
        [ -f "$_source" ] || { safe_error "字体 $_font 不存在"; return 1; }
        if ! validate_global "$_source"; then
            safe_error "${FONT_CHECK_ERROR:-字体校验失败}"
            return 1
        fi
        safe_timing_phase prewarm_wait
        progress 14 '正在检查本机字体预热缓存'
        wait_for_prewarm_cache "$_source" "$_font" >/dev/null 2>&1 || true
    fi

    safe_timing_phase lock_recovery
    progress 20 '正在获取字体切换锁'
    lock_acquire || return 1
    luoshu_next_transaction_recover "$MODDIR" || { safe_error '上一字体事务尚未完成清理，请稍后重试'; return 1; }
    cleanup_stale_stages
    resolve_previous_state

    safe_timing_phase clone_payload
    progress 28 '正在保留非字体负载并建立安全暂存区'
    stage_clone_live || { safe_error '无法创建下一启动字体负载'; return 1; }
    safe_timing_phase clear_text_payload
    progress 36 '正在清理暂存区旧文字映射'
    stage_clear_text_payload || { safe_error '无法准备下一启动字体负载'; return 1; }

    if [ "$_font" != default ]; then
        PAYLOAD_ROOT="$STAGE_PAYLOAD"
        SYSTEM_FONTS_DIR="$STAGE_PAYLOAD/system/fonts"
        export PAYLOAD_ROOT SYSTEM_FONTS_DIR
        safe_timing_phase cache_restore
        if safe_switch_cache_restore "$_source" "$_font"; then
            progress 80 '已复用本机字体对齐缓存'
        else
            safe_timing_phase map_rom
            progress 48 '正在生成 ROM 核心字体映射'
            type apply_font_by_rom >/dev/null 2>&1 || { safe_error '缺少 ROM 字体映射器'; return 1; }
            _switch_cache_key=$(safe_switch_cache_key "$_source" "$_font") || _switch_cache_key=''
            if ! apply_font_by_rom "$_source" "$SYSTEM_FONTS_DIR" quick "$_font" >> "$LOG_FILE" 2>&1; then
                safe_error 'ROM 字体映射失败，当前启动字体未被改动'
                return 1
            fi
            safe_timing_phase mirror_targets
            progress 66 '正在补齐系统分区同名字体槽位'
            mirror_existing_targets
            if [ "${IS_HYPEROS:-false}" = true ]; then
                safe_timing_phase complete_hyperos
                progress 76 '正在补齐 HyperOS 状态栏、锁屏和系统 UI 字体槽位'
                stage_hyperos_complete || {
                    safe_error 'HyperOS 字体槽位或度量处理失败，请查看字体切换日志'
                    return 1
                }
            elif [ "${IS_COLOROS:-false}" = true ]; then
                safe_timing_phase complete_coloros
                progress 76 '正在按原厂槽位对齐 ColorOS 字体度量'
                stage_coloros_complete || {
                    safe_error 'ColorOS 字体度量处理失败，请查看字体切换日志'
                    return 1
                }
            fi
            safe_timing_phase cache_store
            progress 82 '正在保存本机字体对齐缓存'
            safe_switch_cache_store "$_source" "$_font" "$_switch_cache_key" >/dev/null 2>&1 || true
        fi
        safe_timing_phase verify_payload
        progress 86 '正在校验下一启动字体负载'
        stage_verify "$_font" || { safe_error '新字体负载校验失败，当前启动字体未被改动'; return 1; }
    fi

    safe_timing_phase prepare_next_payload
    progress 94 '正在提交下一启动字体负载'
    prepare_next_payload "$_active_label" "$PREVIOUS_FONT" "$PREVIOUS_LEGACY" || {
        safe_error '下一启动字体负载提交失败，当前启动字体未被改动'
        return 1
    }
    safe_timing_phase write_state
    progress 98 '正在保存字体选择状态'
    if ! write_runtime_state "$_active_label"; then
        cancel_next_payload
        safe_error '字体状态保存失败，下一启动负载已取消'
        return 1
    fi

    safe_timing_phase commit_transaction
    if ! luoshu_next_transaction_mix_receipt "$MODDIR" || ! luoshu_next_transaction_commit "$MODDIR"; then
        cancel_next_payload
        safe_error '字体事务提交失败，已恢复上次字体选择'
        return 1
    fi
    safe_timing_phase live_mount
    progress 99 '正在挂载当前启动字体；已有字体缓存将在重启后完整更新'
    _live_result=$(MODDIR="$MODDIR" sh "$MODDIR/common/font_live_switch.sh" 2>> "$LOG_FILE")
    _live_applied=false
    _activation=pending-reboot
    if printf '%s\n' "$_live_result" | grep -q '"liveApplied":true'; then
        _live_applied=true
        _activation=live-mounted
    fi
    printf '[LIVE-SWITCH] %s\n' "$_live_result" >> "$LOG_FILE" 2>/dev/null || true
    safe_timing_phase finalize
    printf '%s\n' "$_active_label" > "$CONFIG_DIR/last_switch_result.conf" 2>/dev/null || true
    date '+%Y-%m-%d %H:%M:%S' > "$CONFIG_DIR/last_switch_time.conf" 2>/dev/null || true
    if [ "$_live_applied" = true ]; then
        progress 100 '当前启动已挂载新字体，重启后完整生效'
    else
        progress 100 '字体已准备完成，完整重启后生效'
    fi
    printf '{"status":"ok","data":{"font":"%s","rebootRequired":true,"liveApplied":%s,"activation":"%s","core":"physical-safe-v1","pipeline":"next-boot-stage"}}\n' \
        "$(json_escape "$_active_label")" "$_live_applied" "$_activation"
    return 0
}

case "${1:-}" in
    action)
        case "${2:-}" in
            switch) switch_font "${3:-}"; exit $? ;;
            prewarm) prewarm_font "${3:-}"; exit $? ;;
            prewarm-start) prewarm_start "${3:-}"; exit $? ;;
            *) safe_error '安全切换核心只接管字体应用/预热动作'; exit 2 ;;
        esac
        ;;
    *) safe_error '无效的字体切换命令'; exit 2 ;;
esac
