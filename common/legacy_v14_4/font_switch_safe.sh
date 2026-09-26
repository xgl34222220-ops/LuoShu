#!/system/bin/sh
# LuoShu safe physical font switch core.
# Foreground switching never renames, deletes or rewrites the payload used by the
# current Android boot. It builds .luoshu-payload-next off-line; post-fs-data activates
# that tree before LuoShu mounts fonts on the following complete boot.
set +e

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
CONFIG_DIR="$MODDIR/config"
LEGACY_DIR="$MODDIR/common/legacy_v14_4"
USER_ROOT="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}"
USER_FONTS_DIR="$USER_ROOT/fonts"
LIVE_PAYLOAD="$MODDIR/.luoshu-payload"
STAGE_PAYLOAD="$MODDIR/.luoshu-payload-stage.$$"
NEXT_PAYLOAD="$MODDIR/.luoshu-payload-next"
NEXT_STATE="$CONFIG_DIR/font-payload-next.conf"
ACTIVE_FONT_CONF="$CONFIG_DIR/active_font.conf"
LEGACY_MODE_CONF="$CONFIG_DIR/font_runtime_legacy_v14_4.conf"
TEXT_REBOOT_REQUIRED="$CONFIG_DIR/text_reboot_required.conf"
LOG_FILE="$MODDIR/logs/fontswitch.log"
COVERAGE_REMEDIATE_HELPER="$MODDIR/common/coverage_payload_remediate.sh"
INVENTORY_STAGE_HELPER="$MODDIR/common/inventory_font_stage.sh"
SWITCH_LOCK="$MODDIR/.font_switch.lock"
PROGRESS_FILE="${LUOSHU_SWITCH_PROGRESS_FILE:-}"
SWITCH_CACHE_ROOT="$CONFIG_DIR/safe-switch-cache"
SWITCH_VALIDATION_CACHE_ROOT="$CONFIG_DIR/safe-switch-validation"
SWITCH_CACHE_SCHEMA="safe-switch-inventory-v6-tree-manifest"
SWITCH_CACHE_MAX_ENTRIES="${LUOSHU_SWITCH_CACHE_MAX_ENTRIES:-3}"
SWITCH_CACHE_MAX_KB="${LUOSHU_SWITCH_CACHE_MAX_KB:-786432}"
case "$SWITCH_CACHE_MAX_ENTRIES" in ''|*[!0-9]*) SWITCH_CACHE_MAX_ENTRIES=3 ;; esac
case "$SWITCH_CACHE_MAX_KB" in ''|*[!0-9]*) SWITCH_CACHE_MAX_KB=786432 ;; esac
[ "$SWITCH_CACHE_MAX_ENTRIES" -ge 1 ] 2>/dev/null || SWITCH_CACHE_MAX_ENTRIES=1
[ "$SWITCH_CACHE_MAX_KB" -ge 131072 ] 2>/dev/null || SWITCH_CACHE_MAX_KB=131072
PREWARM_LOCK="$MODDIR/.safe-switch-prewarm.lock"
LOCK_HELD=false
PREWARM_LOCK_HELD=false

export MODULE_DIR LUOSHU_PUBLIC_DIR="$USER_ROOT"
[ -f "$LEGACY_DIR/util_functions.sh" ] && . "$LEGACY_DIR/util_functions.sh"
[ -f "$LEGACY_DIR/font_check.sh" ] && . "$LEGACY_DIR/font_check.sh"
[ -f "$MODDIR/common/font_switch_lock.sh" ] && . "$MODDIR/common/font_switch_lock.sh"
[ -f "$MODDIR/common/background_task.sh" ] && . "$MODDIR/common/background_task.sh"
[ -f "$MODDIR/common/font_provenance.sh" ] && . "$MODDIR/common/font_provenance.sh"
[ -f "$LEGACY_DIR/payload_clone.sh" ] && . "$LEGACY_DIR/payload_clone.sh"

type ensure_public_storage >/dev/null 2>&1 && ensure_public_storage
mkdir -p "$CONFIG_DIR" "$MODDIR/logs" "$USER_FONTS_DIR" 2>/dev/null || true

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

read_state_value() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

safe_hash_stream() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum | awk '{print $1}'
    elif command -v busybox >/dev/null 2>&1; then
        busybox sha256sum | awk '{print $1}'
    else
        cksum | awk '{print $1 "-" $2}'
    fi
}

safe_source_identity() {
    _ssi_file="$1"
    if command -v stat >/dev/null 2>&1; then
        stat -L -c '%d:%i:%s:%y:%z' "$_ssi_file" 2>/dev/null && return 0
    fi
    if command -v toybox >/dev/null 2>&1; then
        toybox stat -L -c '%d:%i:%s:%y:%z' "$_ssi_file" 2>/dev/null && return 0
    fi
    return 1
}

safe_source_family_identity() (
    # The inventory engine may select another face from this directory. Include
    # all candidate identities in one stat call; do not parse/hash large fonts on
    # each cache lookup. Broad invalidation also handles renamed/new family faces.
    # SourcePool resolves a user symlink before discovering sibling faces.
    if command -v readlink >/dev/null 2>&1; then
        _ssfi_source=$(readlink -f "$1" 2>/dev/null) || return 1
    elif command -v toybox >/dev/null 2>&1; then
        _ssfi_source=$(toybox readlink -f "$1" 2>/dev/null) || return 1
    else
        [ ! -L "$1" ] || return 1
        _ssfi_directory=$(CDPATH= cd -P -- "${1%/*}" 2>/dev/null && pwd -P) || return 1
        _ssfi_source="$_ssfi_directory/${1##*/}"
    fi
    _ssfi_directory="${_ssfi_source%/*}"
    LC_ALL=C; export LC_ALL
    set --
    for _ssfi_file in "$_ssfi_directory"/* "$_ssfi_directory"/.[!.]* "$_ssfi_directory"/..?*; do
        [ -f "$_ssfi_file" ] || continue
        case "$_ssfi_file" in
            *.[tT][tT][fF]|*.[oO][tT][fF]|*.[tT][tT][cC]|*.[oO][tT][cC]|*.[fF][oO][nN][tT])
                set -- "$@" "$_ssfi_file" ;;
        esac
    done
    [ "$#" -gt 0 ] || return 1
    if command -v stat >/dev/null 2>&1; then
        _ssfi_rows=$(stat -L -c '%d:%i:%s:%y:%z:%n' "$@" 2>/dev/null) || return 1
    elif command -v toybox >/dev/null 2>&1; then
        _ssfi_rows=$(toybox stat -L -c '%d:%i:%s:%y:%z:%n' "$@" 2>/dev/null) || return 1
    else
        return 1
    fi
    [ -n "$_ssfi_rows" ] || return 1
    printf '%s\n' "$_ssfi_rows" | safe_hash_stream
)

safe_inventory_identity() (
    # Partition routing is part of the installed scan result, not just the JSON.
    set --
    for _sii_file in "$CONFIG_DIR/device_font_inventory.json" \
                     "$CONFIG_DIR/device_font_partitions.conf" \
                     "$CONFIG_DIR/device_font_roots.conf"; do
        [ ! -f "$_sii_file" ] || set -- "$@" "$_sii_file"
    done
    if [ "$#" -eq 0 ]; then printf 'no-inventory\n'; return 0; fi
    safe_checksum_files "$@"
)

safe_checksum_files() (
    # One process for the complete small-file set; never hash the font payload.
    # A read failure is a cache miss, not a successful fingerprint of partial data.
    if command -v cksum >/dev/null 2>&1; then
        _scf_rows=$(cksum "$@" 2>/dev/null) || return 1
    elif command -v busybox >/dev/null 2>&1; then
        _scf_rows=$(busybox cksum "$@" 2>/dev/null) || return 1
    else
        return 1
    fi
    [ -n "$_scf_rows" ] || return 1
    printf '%s\n' "$_scf_rows" | safe_hash_stream
)

safe_mapper_identity() (
    # Include transitive helpers, not just the three shell entry points. A
    # generator/metrics/coverage fix must invalidate previously aligned output.
    # Globs cover shipped source only, not common/python's large runtime tree.
    LC_ALL=C; export LC_ALL
    set --
    for _smi_file in "$MODDIR"/common/*.sh "$MODDIR"/common/*.py \
                     "$LEGACY_DIR"/*.sh "$LEGACY_DIR"/*.py \
                     "$MODDIR"/common/python/lib/python*/site-packages/fontTools/__init__.py; do
        [ ! -f "$_smi_file" ] || set -- "$@" "$_smi_file"
    done
    [ "$#" -gt 0 ] || return 1
    safe_checksum_files "$@"
)

safe_stage_begin() {
    # Pin before generation. Never stamp output with a key recomputed only after
    # the source, installed inventory or engine has changed under a worker.
    SAFE_STAGE_ENGINE=$(safe_mapper_identity) || return 1
    SAFE_STAGE_KEY=$(safe_switch_cache_key "$1" "$2") || return 1
    [ -n "$SAFE_STAGE_KEY" ]
}

safe_stage_unchanged() {
    [ -n "${SAFE_STAGE_KEY:-}" ] || return 1
    _ssu_engine=$(safe_mapper_identity) || return 1
    [ "$_ssu_engine" = "$SAFE_STAGE_ENGINE" ] || return 1
    _ssu_key=$(safe_switch_cache_key "$1" "$2") || return 1
    [ "$_ssu_key" = "$SAFE_STAGE_KEY" ]
}

safe_inventory_ready() {
    [ -f "$INVENTORY_STAGE_HELPER" ] || return 1
    LUOSHU_REAL_MODDIR="$MODDIR" LUOSHU_PUBLIC_DIR="$USER_ROOT" \
        sh "$INVENTORY_STAGE_HELPER" --ensure-inventory >> "$LOG_FILE" 2>&1
}

stage_inventory_map() {
    [ -f "$INVENTORY_STAGE_HELPER" ] || return 1
    # A new stage must include the entire inventory even when the caller arrived
    # through an explicit repair request. An existing cache uses the plan below.
    LUOSHU_REAL_MODDIR="$MODDIR" LUOSHU_PUBLIC_DIR="$USER_ROOT" LUOSHU_COVERAGE_PLAN= \
        sh "$INVENTORY_STAGE_HELPER" "$STAGE_PAYLOAD" direct "$2" "$1" >> "$LOG_FILE" 2>&1
}

safe_partition_list() {
    luoshu_payload_partitions "$MODDIR"
}

safe_font_roots() {
    for _sfr_part in $(safe_partition_list); do
        printf '%s/fonts\n' "$_sfr_part"
    done
    # Use the same scanner manifest as staging and mounting. A cache containing
    # only /<partition>/fonts loses OEM trees after the next cache hit.
    luoshu_payload_nested_font_roots "$MODDIR" | while IFS='|' read -r _sfr_part _sfr_rel; do
        [ -n "$_sfr_part" ] && [ -n "$_sfr_rel" ] || continue
        printf '%s/%s\n' "$_sfr_part" "$_sfr_rel"
    done
}

safe_validation_key() {
    _svk_file="$1"
    _svk_identity=$(safe_source_identity "$_svk_file") || return 1
    _svk_engine=${SAFE_STAGE_ENGINE:-$(safe_mapper_identity)}
    [ -n "$_svk_engine" ] || return 1
    {
        printf 'safe-validation-v2\n'
        printf '%s\n' "$_svk_file"
        printf '%s\n' "$_svk_identity"
        printf '%s\n' "$_svk_engine"
    } | safe_hash_stream
}

safe_validation_restore() {
    _svr_file="$1"
    _svr_key=$(safe_validation_key "$_svr_file") || return 1
    _svr_conf="$SWITCH_VALIDATION_CACHE_ROOT/$_svr_key.conf"
    [ -s "$_svr_conf" ] || return 1
    _svr_identity=$(safe_source_identity "$_svr_file") || return 1
    [ "$(read_state_value "$_svr_conf" valid)" = true ] || return 1
    [ "$(read_state_value "$_svr_conf" identity)" = "$_svr_identity" ] || return 1
    return 0
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
    _sck_family=$(safe_source_family_identity "$_sck_file") || return 1
    _sck_inventory=$(safe_inventory_identity) || return 1
    _sck_mapper=${SAFE_STAGE_ENGINE:-$(safe_mapper_identity)}
    [ -n "$_sck_mapper" ] || return 1
    {
        printf '%s\n' "$SWITCH_CACHE_SCHEMA"
        printf '%s\n' "$_sck_font"
        printf '%s\n' "$_sck_file"
        printf '%s\n' "$_sck_identity"
        printf '%s\n' "$_sck_family"
        printf '%s\n' "$_sck_inventory"
        printf '%s\n' "$_sck_mapper"
    } | safe_hash_stream
}

safe_cache_tree_manifest() (
    # Verify the complete saved tree using metadata in one batched stat process.
    # Missing/truncated OEM aliases must cause a rebuild, without hashing each
    # hard-linked large CJK font again during the foreground switch.
    cd "$1" 2>/dev/null || return 1
    _sctm_rows=$(find . -type f -exec stat -c '%s %y %n' {} + 2>/dev/null) || return 1
    [ -n "$_sctm_rows" ] || return 1
    printf '%s\n' "$_sctm_rows" | LC_ALL=C sort
)

safe_switch_cache_restore() {
    _scr_file="$1"; _scr_font="$2"
    _scr_key=$(safe_switch_cache_key "$_scr_file" "$_scr_font") || return 1
    _scr_root="$SWITCH_CACHE_ROOT/$_scr_key"
    _scr_conf="$_scr_root/cache.conf"
    [ -s "$_scr_conf" ] && [ -d "$_scr_root/tree" ] || return 1
    [ "$(read_state_value "$_scr_conf" schema)" = "$SWITCH_CACHE_SCHEMA" ] || return 1
    [ "$(read_state_value "$_scr_conf" font)" = "$_scr_font" ] || return 1
    [ "$(read_state_value "$_scr_conf" sourceIdentity)" = "$(safe_source_identity "$_scr_file")" ] || return 1
    [ "$(read_state_value "$_scr_conf" inventoryIdentity)" = "$(safe_inventory_identity)" ] || return 1
    [ "$(read_state_value "$_scr_conf" mapperIdentity)" = "${SAFE_STAGE_ENGINE:-$(safe_mapper_identity)}" ] || return 1

    [ -s "$_scr_root/tree.manifest" ] || return 1
    _scr_manifest=$(safe_cache_tree_manifest "$_scr_root/tree") || return 1
    [ "$_scr_manifest" = "$(cat "$_scr_root/tree.manifest" 2>/dev/null)" ] || return 1

    _scr_restored=0
    while IFS= read -r _scr_rel; do
        _scr_src="$_scr_root/tree/$_scr_rel"
        [ -d "$_scr_src" ] || continue
        _scr_dest="$STAGE_PAYLOAD/$_scr_rel"
        mkdir -p "${_scr_dest%/*}" 2>/dev/null || return 1
        rm -rf "$_scr_dest" 2>/dev/null || return 1
        if ! cp -al "$_scr_src" "$_scr_dest" 2>/dev/null; then
            # cp can leave a partial destination behind. Remove it before the
            # fallback, otherwise cp may create fonts/fonts and retain stale data.
            rm -rf "$_scr_dest" 2>/dev/null || return 1
            cp -af "$_scr_src" "$_scr_dest" 2>/dev/null || return 1
        fi
        _scr_restored=$((_scr_restored + 1))
    done <<EOF_SAFE_CACHE_ROOTS
$(safe_font_roots)
EOF_SAFE_CACHE_ROOTS
    [ "$_scr_restored" -gt 0 ] || return 1
    for _scr_meta in .luoshu-metrics-report.json .luoshu-metrics-covered.lst \
        .luoshu-coverage-remediation.conf .luoshu-coverage-preserved.tsv \
        .luoshu-coverage-summary.conf .luoshu-inventory-output-manifest.json; do
        [ ! -f "$_scr_root/tree/$_scr_meta" ] || \
            cp -f "$_scr_root/tree/$_scr_meta" "$STAGE_PAYLOAD/$_scr_meta" 2>/dev/null || return 1
    done
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
    safe_stage_unchanged "$_scs_file" "$_scs_font" || return 1
    _scs_key=$(safe_switch_cache_key "$_scs_file" "$_scs_font") || return 1
    _scs_root="$SWITCH_CACHE_ROOT/$_scs_key"
    _scs_stage="$SWITCH_CACHE_ROOT/.stage.$_scs_key.$$"
    rm -rf "$_scs_stage" 2>/dev/null || true
    mkdir -p "$_scs_stage/tree" 2>/dev/null || return 1
    _scs_saved=0
    while IFS= read -r _scs_rel; do
        _scs_src="$STAGE_PAYLOAD/$_scs_rel"
        [ -d "$_scs_src" ] || continue
        find "$_scs_src" -type f -print -quit 2>/dev/null | grep -q . || continue
        _scs_dest="$_scs_stage/tree/$_scs_rel"
        mkdir -p "${_scs_dest%/*}" 2>/dev/null || { rm -rf "$_scs_stage"; return 1; }
        if ! cp -al "$_scs_src" "$_scs_dest" 2>/dev/null; then
            rm -rf "$_scs_dest" 2>/dev/null || { rm -rf "$_scs_stage"; return 1; }
            cp -af "$_scs_src" "$_scs_dest" 2>/dev/null || {
                rm -rf "$_scs_stage" 2>/dev/null || true
                return 1
            }
        fi
        _scs_saved=$((_scs_saved + 1))
    done <<EOF_SAFE_CACHE_ROOTS
$(safe_font_roots)
EOF_SAFE_CACHE_ROOTS
    [ "$_scs_saved" -gt 0 ] || { rm -rf "$_scs_stage" 2>/dev/null || true; return 1; }
    for _scs_meta in .luoshu-metrics-report.json .luoshu-metrics-covered.lst \
        .luoshu-coverage-remediation.conf .luoshu-coverage-preserved.tsv \
        .luoshu-coverage-summary.conf .luoshu-inventory-output-manifest.json; do
        [ ! -f "$STAGE_PAYLOAD/$_scs_meta" ] || \
            cp -f "$STAGE_PAYLOAD/$_scs_meta" "$_scs_stage/tree/$_scs_meta" 2>/dev/null || {
                rm -rf "$_scs_stage" 2>/dev/null || true
                return 1
            }
    done
    safe_cache_tree_manifest "$_scs_stage/tree" > "$_scs_stage/tree.manifest" || {
        rm -rf "$_scs_stage" 2>/dev/null || true
        return 1
    }
    _scs_identity=$(safe_source_identity "$_scs_file") || { rm -rf "$_scs_stage"; return 1; }
    {
        printf 'schema=%s\n' "$SWITCH_CACHE_SCHEMA"
        printf 'font=%s\n' "$_scs_font"
        printf 'sourceIdentity=%s\n' "$_scs_identity"
        printf 'inventoryIdentity=%s\n' "$(safe_inventory_identity)"
        printf 'mapperIdentity=%s\n' "${SAFE_STAGE_ENGINE:-$(safe_mapper_identity)}"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_scs_stage/cache.conf" 2>/dev/null || { rm -rf "$_scs_stage"; return 1; }
    mkdir -p "$SWITCH_CACHE_ROOT" 2>/dev/null || { rm -rf "$_scs_stage"; return 1; }
    safe_stage_unchanged "$_scs_file" "$_scs_font" || { rm -rf "$_scs_stage"; return 1; }
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
    [ "$(read_state_value "$_scrd_conf" schema)" = "$SWITCH_CACHE_SCHEMA" ] || return 1
    [ "$(read_state_value "$_scrd_conf" font)" = "$_scrd_font" ] || return 1
    [ "$(read_state_value "$_scrd_conf" sourceIdentity)" = "$(safe_source_identity "$_scrd_file")" ] || return 1
    [ "$(read_state_value "$_scrd_conf" inventoryIdentity)" = "$(safe_inventory_identity)" ] || return 1
    [ "$(read_state_value "$_scrd_conf" mapperIdentity)" = "${SAFE_STAGE_ENGINE:-$(safe_mapper_identity)}" ] || return 1
    safe_verify_inventory_tree "$_scrd_root/tree"
}

wait_for_prewarm_cache() {
    _wfpc_file="$1"; _wfpc_font="$2"
    safe_switch_cache_ready "$_wfpc_file" "$_wfpc_font" && return 0
    type luoshu_font_lock_active >/dev/null 2>&1 || return 1
    luoshu_font_lock_active "$PREWARM_LOCK" >/dev/null 2>&1 || return 1
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
    rm -rf "$STAGE_PAYLOAD" 2>/dev/null || true
}

cleanup_stale_stages() {
    for _stale_stage in "$MODDIR"/.luoshu-payload-stage.*; do
        [ -e "$_stale_stage" ] || continue
        [ "$_stale_stage" = "$STAGE_PAYLOAD" ] && continue
        rm -rf "$_stale_stage" 2>/dev/null || true
    done
}

trap 'cleanup_stage; prewarm_lock_cleanup; lock_cleanup' EXIT
trap 'cleanup_stage; prewarm_lock_cleanup; lock_cleanup; exit 129' HUP
trap 'cleanup_stage; prewarm_lock_cleanup; lock_cleanup; exit 130' INT
trap 'cleanup_stage; prewarm_lock_cleanup; lock_cleanup; exit 143' TERM

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
    rm -f "$STAGE_PAYLOAD/.luoshu-metrics-report.json" \
          "$STAGE_PAYLOAD/.luoshu-metrics-covered.lst" \
          "$STAGE_PAYLOAD/.luoshu-coverage-preserved.tsv" \
          "$STAGE_PAYLOAD/.luoshu-coverage-remediation.conf" \
          "$STAGE_PAYLOAD/.luoshu-coverage-summary.conf" \
          "$STAGE_PAYLOAD/.luoshu-inventory-output-manifest.json" 2>/dev/null || return 1
    while IFS= read -r _sctp_rel; do
        rm -rf "$STAGE_PAYLOAD/$_sctp_rel" 2>/dev/null || return 1
    done <<EOF_SAFE_CLEAR_ROOTS
$(safe_font_roots)
EOF_SAFE_CLEAR_ROOTS
    for _part in $(safe_partition_list); do
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

safe_verify_inventory_tree() {
    _svit_tree="$1"
    _svit_manifest="$_svit_tree/.luoshu-metrics-covered.lst"
    [ -s "$_svit_manifest" ] || return 1
    _svit_seen=0
    while IFS= read -r _svit_slot || [ -n "$_svit_slot" ]; do
        case "$_svit_slot" in
            /*) ;;
            *) return 1 ;;
        esac
        case "$_svit_slot" in *'/../'*|*'/./'*|*'//'*) return 1 ;; esac
        [ -f "$_svit_tree$_svit_slot" ] && [ -s "$_svit_tree$_svit_slot" ] || return 1
        _svit_seen=$((_svit_seen + 1))
    done < "$_svit_manifest"
    [ "$_svit_seen" -gt 0 ]
}

stage_verify() {
    [ "$1" = default ] && return 0
    # The inventory owns paths and formats, including nested directories, OTC
    # and XML fonts with no filename extension. Verify its complete output list.
    safe_verify_inventory_tree "$STAGE_PAYLOAD"
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
    _font="$1"; _previous="$2"; _previous_legacy="$3"; _source="${4:-}"
    _next_tmp="${NEXT_STATE}.tmp.$$"
    # An orphaned auto-weight child can outlive its controller. It must not
    # replace the current request's queued payload even if its font is valid.
    if [ "$_font" = mix ] && [ -n "${LUOSHU_MIX_REQUEST_ID:-}" ]; then
        [ "$(read_state_value "$CONFIG_DIR/mix-stage-next.conf" requestId)" = "$LUOSHU_MIX_REQUEST_ID" ] || return 1
    fi
    _direct_proof=''
    if [ "$_font" != default ] && [ "$_font" != mix ] && [ -f "$_source" ]; then
        type luoshu_provenance_direct_proof >/dev/null 2>&1 || return 1
        _direct_proof=$(luoshu_provenance_direct_proof "$_source" "$_font") || return 1
        [ -n "$_direct_proof" ] || return 1
    fi
    rm -rf "$NEXT_PAYLOAD" 2>/dev/null || true
    rm -f "$NEXT_STATE" 2>/dev/null || true
    if ! mv "$STAGE_PAYLOAD" "$NEXT_PAYLOAD" 2>/dev/null; then
        return 1
    fi
    STAGE_PAYLOAD="$MODDIR/.luoshu-payload-stage.committed.$$"
    {
        printf 'state=prepared\n'
        printf 'font=%s\n' "$_font"
        printf 'previousFont=%s\n' "$_previous"
        printf 'previousLegacy=%s\n' "$_previous_legacy"
        # Composite generation already builds the complete next-boot tree through
        # this safe switch. Stamp the originating mix request so the compatibility
        # router can recognize this exact payload and must not rebuild/"补齐" it
        # a second time during prepare-finalize.
        if [ "$_font" = mix ] && [ -n "${LUOSHU_MIX_REQUEST_ID:-}" ]; then
            printf 'requestId=%s\n' "$LUOSHU_MIX_REQUEST_ID"
        fi
        if [ -n "$_direct_proof" ]; then
            printf 'provenanceSchema=font-provenance-v1\n'
            printf 'proofKind=direct\n'
            printf 'directProof=%s\n' "$_direct_proof"
        fi
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_next_tmp" 2>/dev/null || {
        rm -rf "$NEXT_PAYLOAD" 2>/dev/null || true
        return 1
    }
    mv -f "$_next_tmp" "$NEXT_STATE" 2>/dev/null || {
        rm -rf "$NEXT_PAYLOAD" "$_next_tmp" 2>/dev/null || true
        return 1
    }
    chmod 0644 "$NEXT_STATE" 2>/dev/null || true
    return 0
}

cancel_next_payload() {
    rm -rf "$NEXT_PAYLOAD" 2>/dev/null || true
    rm -f "$NEXT_STATE" 2>/dev/null || true
}

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
    type luoshu_start_detached >/dev/null 2>&1 || return 0
    _prewarm_identity=$(safe_source_identity "$_source" 2>/dev/null)
    [ -n "$_prewarm_identity" ] || return 0
    _prewarm_key=$({
        printf '%s\n' "$_font"
        printf '%s\n' "$_prewarm_identity"
    } | safe_hash_stream | cut -c1-12)
    [ -n "$_prewarm_key" ] || return 0
    _prewarm_pid="$CONFIG_DIR/font-prewarm-$_prewarm_key.pid"
    _prewarm_log="$MODDIR/logs/font-prewarm.log"
    _self="$MODDIR/common/legacy_v14_4/font_switch_safe.sh"
    luoshu_start_detached "$_prewarm_pid" font_switch_safe.sh "$_prewarm_log" \
        sh -c '
            sleep 1
            _script="$1"; _family="$2"; _public="$3"
            [ -f "$_script" ] || exit 0
            export LUOSHU_PUBLIC_DIR="$_public"
            if command -v ionice >/dev/null 2>&1 && command -v nice >/dev/null 2>&1; then
                exec ionice -c 3 nice -n 19 sh "$_script" action prewarm "$_family"
            elif command -v nice >/dev/null 2>&1; then
                exec nice -n 19 sh "$_script" action prewarm "$_family"
            fi
            exec sh "$_script" action prewarm "$_family"
        ' font_switch_safe.sh "$_self" "$_font" "$USER_ROOT" >/dev/null 2>&1 || true
    return 0
}

prewarm_font() {
    _font="$1"
    [ -n "$_font" ] && [ "$_font" != default ] || return 0
    switch_busy && return 0

    prewarm_lock_acquire
    _prewarm_lock_rc=$?
    [ "$_prewarm_lock_rc" -eq 0 ] || return 0
    switch_busy && return 0

    _source="$(find_text_font_file "$_font")"
    [ -f "$_source" ] || return 0
    safe_inventory_ready || return 0
    safe_stage_begin "$_source" "$_font" || return 0
    validate_global "$_source" || return 0
    safe_switch_cache_ready "$_source" "$_font" && return 0

    stage_clone_live || return 0
    stage_clear_text_payload || return 0
    switch_busy && return 0

    stage_inventory_map "$_source" "$_font" || return 0
    switch_busy && return 0
    stage_verify "$_font" || return 0
    safe_switch_cache_store "$_source" "$_font" >/dev/null 2>&1 || return 0
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
        progress 6 '正在查找并校验字体文件'
        _source="$(find_text_font_file "$_font")"
        [ -f "$_source" ] || { safe_error "字体 $_font 不存在"; return 1; }
        progress 10 '正在验证本机通用字体清单'
        safe_inventory_ready || {
            safe_error '本机字体清单不可用，自动检测未能完成；当前启动字体未被改动'
            return 1
        }
        safe_stage_begin "$_source" "$_font" || {
            safe_error '无法核验本机字体清单或生成引擎，请重新检测后应用'
            return 1
        }
        if ! validate_global "$_source"; then
            safe_error "${FONT_CHECK_ERROR:-字体校验失败}"
            return 1
        fi
        progress 14 '正在检查本机字体预热缓存'
        wait_for_prewarm_cache "$_source" "$_font" >/dev/null 2>&1 || true
    fi

    progress 20 '正在获取字体切换锁'
    lock_acquire || return 1
    cleanup_stale_stages
    resolve_previous_state

    progress 28 '正在保留非字体负载并建立安全暂存区'
    stage_clone_live || { safe_error '无法创建下一启动字体负载'; return 1; }
    progress 36 '正在清理暂存区旧文字映射'
    stage_clear_text_payload || { safe_error '无法准备下一启动字体负载'; return 1; }

    if [ "$_font" != default ]; then
        PAYLOAD_ROOT="$STAGE_PAYLOAD"
        SYSTEM_FONTS_DIR="$STAGE_PAYLOAD/system/fonts"
        export PAYLOAD_ROOT SYSTEM_FONTS_DIR
        _cache_restored=false
        if safe_switch_cache_restore "$_source" "$_font"; then
            _cache_restored=true
            progress 80 '已复用本机字体对齐缓存'
        else
            # A failed restore may already have populated several partitions.
            stage_clear_text_payload || { safe_error '无法清理未完成的缓存恢复'; return 1; }
            progress 48 '正在按本机扫描清单映射全部可替换字体槽位'
            if ! stage_inventory_map "$_source" "$_font"; then
                safe_error '按本机清单生成字体失败，当前启动字体未被改动'
                return 1
            fi
        fi
        # A cache miss has already generated every eligible slot in one pass.
        # Only a restored complete tree needs the requested incremental repair.
        if [ "${LUOSHU_COVERAGE_REMEDIATE:-0}" = 1 ] && [ "$_cache_restored" = true ]; then
            progress 82 '正在按补齐计划重建本机安全字体槽位'
            if [ ! -f "$COVERAGE_REMEDIATE_HELPER" ]; then
                safe_error '字体覆盖补齐组件缺失，当前启动字体未被改动'
                return 1
            fi
            if ! LUOSHU_REAL_MODDIR="$MODDIR" LUOSHU_PUBLIC_DIR="$USER_ROOT" \
                sh "$COVERAGE_REMEDIATE_HELPER" "$STAGE_PAYLOAD" direct "$_font" >> "$LOG_FILE" 2>&1; then
                safe_error '按补齐计划重建字体槽位失败，当前启动字体未被改动'
                return 1
            fi
        elif [ "$_cache_restored" = true ]; then
            progress 82 '已复用完整本机字体槽位缓存'
        fi
        progress 86 '正在校验下一启动字体负载'
        stage_verify "$_font" || { safe_error '新字体负载校验失败，当前启动字体未被改动'; return 1; }
        if [ "$_cache_restored" != true ] || [ "${LUOSHU_COVERAGE_REMEDIATE:-0}" = 1 ]; then
            progress 90 '正在保存已校验的本机字体对齐缓存'
            safe_switch_cache_store "$_source" "$_font" >/dev/null 2>&1 || true
        fi
    fi

    if [ "$_font" != default ] && ! safe_stage_unchanged "$_source" "$_font"; then
        safe_error '字体源、本机扫描清单或生成引擎在处理中发生变化，请重新应用'
        return 1
    fi
    progress 94 '正在提交下一启动字体负载'
    prepare_next_payload "$_active_label" "$PREVIOUS_FONT" "$PREVIOUS_LEGACY" "$_source" || {
        safe_error '下一启动字体负载提交失败，当前启动字体未被改动'
        return 1
    }
    progress 98 '正在保存字体选择状态'
    if ! write_runtime_state "$_active_label"; then
        cancel_next_payload
        safe_error '字体状态保存失败，下一启动负载已取消'
        return 1
    fi

    printf '%s\n' "$_active_label" > "$CONFIG_DIR/last_switch_result.conf" 2>/dev/null || true
    date '+%Y-%m-%d %H:%M:%S' > "$CONFIG_DIR/last_switch_time.conf" 2>/dev/null || true
    progress 100 '字体已准备完成，完整重启后生效'
    printf '{"status":"ok","data":{"font":"%s","rebootRequired":true,"core":"physical-safe-v1","pipeline":"next-boot-stage"}}\n' \
        "$(json_escape "$_active_label")"
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
