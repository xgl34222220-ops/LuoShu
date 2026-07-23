#!/system/bin/sh
# LuoShu persistent per-device alignment cache.
# Foreground application only activates a ready cache or writes a tiny pending request.
# Expensive generation starts at low priority after active_font.conf is committed; boot
# service resumes the same request when Android kills or reboots during the background job.
set +e

_dfcache_module() {
    printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
}

_dfcache_log() {
    _dfc_module="$(_dfcache_module)"
    mkdir -p "$_dfc_module/logs" 2>/dev/null || true
    printf '[%s] [CACHE] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$*" \
        >> "$_dfc_module/logs/device-font-cache.log" 2>/dev/null || true
}

_dfcache_hash_stream() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum | awk '{print $1}'
    elif command -v busybox >/dev/null 2>&1; then
        busybox sha256sum | awk '{print $1}'
    else
        cksum | awk '{print $1 ":" $2}'
    fi
}

_dfcache_template_key() {
    _dfc_module="$(_dfcache_module)"
    _dfc_template="$_dfc_module/common/device_font_template.sh"
    [ -f "$_dfc_template" ] || return 1
    MODDIR="$_dfc_module" sh "$_dfc_template" trusted >/dev/null 2>&1 || return 1
    _dfc_key=$(cat "$_dfc_module/config/device-font-template.key" 2>/dev/null)
    [ -n "$_dfc_key" ] || return 1
    printf '%s\n' "$_dfc_key"
}

# Metadata-only identity keeps the App click fast. Reimporting or rebuilding a font changes
# inode/size/mtime and automatically selects a different cache directory.
_dfcache_source_key() {
    _dfc_module="$(_dfcache_module)"
    _dfc_store="$_dfc_module/system/fonts/.luoshu-font-store"
    [ -d "$_dfc_store" ] || return 1
    _dfc_files=$(find "$_dfc_store" -maxdepth 1 -type f -name '*.font' -print 2>/dev/null | LC_ALL=C sort)
    [ -n "$_dfc_files" ] || return 1
    {
        printf 'source-contract-v2\n'
        while IFS= read -r _dfc_file; do
            [ -f "$_dfc_file" ] || continue
            stat -c '%n|%d|%i|%s|%Y' "$_dfc_file" 2>/dev/null || ls -ln "$_dfc_file" 2>/dev/null
        done <<EOF_DFCACHE_FILES
$_dfc_files
EOF_DFCACHE_FILES
    } | _dfcache_hash_stream
}

_dfcache_id() {
    _dfc_font="$1"
    _dfc_template_key="$2"
    _dfc_source_key="$3"
    printf 'alignment-cache-v2|%s|%s|%s\n' "$_dfc_font" "$_dfc_template_key" "$_dfc_source_key" | _dfcache_hash_stream
}

_dfcache_root_for() {
    _dfc_font="$1"
    _dfc_template_key="$2"
    _dfc_source_key="$3"
    _dfc_id=$(_dfcache_id "$_dfc_font" "$_dfc_template_key" "$_dfc_source_key") || return 1
    printf '%s/config/device-font-cache/%s\n' "$(_dfcache_module)" "$_dfc_id"
}

_dfcache_ready_matches() {
    _dfc_root="$1"
    _dfc_font="$2"
    _dfc_template_key="$3"
    _dfc_source_key="$4"
    _dfc_conf="$_dfc_root/cache.conf"
    [ -s "$_dfc_conf" ] && [ -s "$_dfc_root/payload/manifest.json" ] && [ -s "$_dfc_root/overlay/overlay-manifest.json" ] || return 1
    [ "$(sed -n 's/^state=//p' "$_dfc_conf" 2>/dev/null | head -n1)" = ready ] || return 1
    [ "$(sed -n 's/^font=//p' "$_dfc_conf" 2>/dev/null | head -n1)" = "$_dfc_font" ] || return 1
    [ "$(sed -n 's/^templateKey=//p' "$_dfc_conf" 2>/dev/null | head -n1)" = "$_dfc_template_key" ] || return 1
    [ "$(sed -n 's/^sourceKey=//p' "$_dfc_conf" 2>/dev/null | head -n1)" = "$_dfc_source_key" ] || return 1
    return 0
}

device_font_cache_lookup() {
    _dfc_font="${1:-custom}"
    _dfc_template_key=$(_dfcache_template_key) || return 2
    _dfc_source_key=$(_dfcache_source_key) || return 2
    _dfc_root=$(_dfcache_root_for "$_dfc_font" "$_dfc_template_key" "$_dfc_source_key") || return 2
    _dfcache_ready_matches "$_dfc_root" "$_dfc_font" "$_dfc_template_key" "$_dfc_source_key" || return 2
    printf '%s\n' "$_dfc_root"
    return 0
}

_dfcache_autostart_pending() {
    _dfc_font="$1"
    _dfc_module="$(_dfcache_module)"
    _dfc_script="$_dfc_module/common/device_font_cache.sh"
    [ "${LUOSHU_CACHE_AUTOSTART:-1}" != 0 ] || return 0
    [ -f "$_dfc_script" ] || return 0
    (
        _dfc_waited=0
        while [ "$_dfc_waited" -lt 60 ]; do
            _dfc_active=$(head -n1 "$_dfc_module/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
            [ "$_dfc_active" = "$_dfc_font" ] && break
            sleep 1
            _dfc_waited=$((_dfc_waited + 1))
        done
        [ "$_dfc_active" = "$_dfc_font" ] || exit 0
        sleep 2
        MODDIR="$_dfc_module"
        MODULE_DIR="$_dfc_module"
        export MODDIR MODULE_DIR
        if command -v ionice >/dev/null 2>&1 && command -v nice >/dev/null 2>&1; then
            ionice -c 3 nice -n 10 sh "$_dfc_script" service >> "$_dfc_module/logs/device-font-cache.log" 2>&1
        elif command -v nice >/dev/null 2>&1; then
            nice -n 10 sh "$_dfc_script" service >> "$_dfc_module/logs/device-font-cache.log" 2>&1
        else
            sh "$_dfc_script" service >> "$_dfc_module/logs/device-font-cache.log" 2>&1
        fi
    ) &
    return 0
}

device_font_cache_schedule() {
    _dfc_font="${1:-custom}"
    _dfc_module="$(_dfcache_module)"
    _dfc_pending="$_dfc_module/config/device-font-cache-pending.conf"
    _dfc_template_key=$(_dfcache_template_key) || {
        _dfcache_log '无法安排对齐缓存：可信原厂模板尚未建立'
        return 2
    }
    _dfc_source_key=$(_dfcache_source_key) || {
        _dfcache_log '无法安排对齐缓存：当前字体源锚点不存在'
        return 2
    }
    _dfc_id=$(_dfcache_id "$_dfc_font" "$_dfc_template_key" "$_dfc_source_key") || return 1
    mkdir -p "$_dfc_module/config" 2>/dev/null || return 1
    {
        printf 'state=pending\n'
        printf 'font=%s\n' "$_dfc_font"
        printf 'cacheId=%s\n' "$_dfc_id"
        printf 'templateKey=%s\n' "$_dfc_template_key"
        printf 'sourceKey=%s\n' "$_dfc_source_key"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "${_dfc_pending}.tmp.$$" 2>/dev/null || return 1
    mv -f "${_dfc_pending}.tmp.$$" "$_dfc_pending" 2>/dev/null || return 1
    chmod 0600 "$_dfc_pending" 2>/dev/null || true
    _dfcache_log "已安排后台生成设备对齐缓存：$_dfc_font"
    _dfcache_autostart_pending "$_dfc_font"
    return 0
}

_dfcache_write_engine_state() {
    _dfc_font="$1"
    _dfc_template_key="$2"
    _dfc_source_key="$3"
    _dfc_cache_id="$4"
    _dfc_module="$(_dfcache_module)"
    _dfc_state="$_dfc_module/config/device-font-engine.conf"
    {
        printf 'state=installed\n'
        printf 'schema=device-font-payload-v2\n'
        printf 'font=%s\n' "$_dfc_font"
        printf 'templateKey=%s\n' "$_dfc_template_key"
        printf 'sourceKey=%s\n' "$_dfc_source_key"
        printf 'cacheId=%s\n' "$_dfc_cache_id"
        printf 'planRevision=2\n'
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "${_dfc_state}.tmp.$$" 2>/dev/null || return 1
    mv -f "${_dfc_state}.tmp.$$" "$_dfc_state" 2>/dev/null || return 1
    chmod 0600 "$_dfc_state" 2>/dev/null || true
}

device_font_cache_activate() {
    _dfc_font="${1:-custom}"
    _dfc_module="$(_dfcache_module)"
    _dfc_template_key=$(_dfcache_template_key) || return 2
    _dfc_source_key=$(_dfcache_source_key) || return 2
    _dfc_cache_id=$(_dfcache_id "$_dfc_font" "$_dfc_template_key" "$_dfc_source_key") || return 2
    _dfc_root="$_dfc_module/config/device-font-cache/$_dfc_cache_id"
    _dfcache_ready_matches "$_dfc_root" "$_dfc_font" "$_dfc_template_key" "$_dfc_source_key" || return 2
    type _dfpr_install_overlay >/dev/null 2>&1 || return 1
    _dfpr_install_overlay "$_dfc_root/overlay" || return 1
    _dfcache_write_engine_state "$_dfc_font" "$_dfc_template_key" "$_dfc_source_key" "$_dfc_cache_id" || return 1
    if type device_font_payload_validate_installed >/dev/null 2>&1; then
        device_font_payload_validate_installed || return 1
    fi
    rm -f "$_dfc_module/config/device-font-cache-pending.conf" 2>/dev/null || true
    _dfcache_log "设备对齐缓存已激活：$_dfc_font cache=$_dfc_cache_id"
    return 0
}

_dfcache_runtime_ready() {
    type _dfpr_exec >/dev/null 2>&1 && type _dfpr_prepare_sources >/dev/null 2>&1 && type _dfpr_install_overlay >/dev/null 2>&1 && return 0
    _dfc_module="$(_dfcache_module)"
    [ -f "$_dfc_module/common/device_font_payload_runtime.sh" ] || return 1
    . "$_dfc_module/common/device_font_payload_runtime.sh"
    type _dfpr_exec >/dev/null 2>&1 && type _dfpr_prepare_sources >/dev/null 2>&1 && type _dfpr_install_overlay >/dev/null 2>&1
}

_dfcache_notify() {
    _dfc_message="$1"
    command -v cmd >/dev/null 2>&1 || return 0
    cmd notification post -S bigtext -t '洛书' luoshu-font-cache "$_dfc_message" >/dev/null 2>&1 || \
        cmd notification post -t '洛书' luoshu-font-cache "$_dfc_message" >/dev/null 2>&1 || true
}

_dfcache_prune() {
    _dfc_keep="$1"
    _dfc_module="$(_dfcache_module)"
    _dfc_base="$_dfc_module/config/device-font-cache"
    [ -d "$_dfc_base" ] || return 0
    _dfc_seen=0
    for _dfc_dir in $(ls -1dt "$_dfc_base"/* 2>/dev/null); do
        [ -d "$_dfc_dir" ] || continue
        [ "$_dfc_dir" = "$_dfc_keep" ] && continue
        _dfc_seen=$((_dfc_seen + 1))
        [ "$_dfc_seen" -le 1 ] || rm -rf "$_dfc_dir" 2>/dev/null || true
    done
}

device_font_cache_build_pending() {
    _dfc_module="$(_dfcache_module)"
    _dfc_pending="$_dfc_module/config/device-font-cache-pending.conf"
    _dfc_lock="$_dfc_module/.device-font-cache.lock"
    [ -s "$_dfc_pending" ] || return 2
    if ! mkdir "$_dfc_lock" 2>/dev/null; then
        _dfcache_log '后台对齐缓存任务已经在运行'
        return 2
    fi
    trap 'rmdir "'"$_dfc_lock"'" 2>/dev/null || true' EXIT HUP INT TERM

    _dfc_font=$(sed -n 's/^font=//p' "$_dfc_pending" 2>/dev/null | head -n1)
    _dfc_cache_id=$(sed -n 's/^cacheId=//p' "$_dfc_pending" 2>/dev/null | head -n1)
    _dfc_expected_template=$(sed -n 's/^templateKey=//p' "$_dfc_pending" 2>/dev/null | head -n1)
    _dfc_expected_source=$(sed -n 's/^sourceKey=//p' "$_dfc_pending" 2>/dev/null | head -n1)
    _dfc_active=$(head -n1 "$_dfc_module/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_dfc_font" ] && [ "$_dfc_font" != default ] && [ "$_dfc_active" = "$_dfc_font" ] || {
        _dfcache_log "取消过期缓存任务：pending=$_dfc_font active=$_dfc_active"
        rm -f "$_dfc_pending" 2>/dev/null || true
        return 2
    }
    _dfc_template_key=$(_dfcache_template_key) || return 2
    _dfc_source_key=$(_dfcache_source_key) || return 2
    [ "$_dfc_template_key" = "$_dfc_expected_template" ] && [ "$_dfc_source_key" = "$_dfc_expected_source" ] || {
        _dfcache_log '缓存任务源指纹已经变化，等待下次明确应用重新安排'
        rm -f "$_dfc_pending" 2>/dev/null || true
        return 2
    }
    _dfc_root="$_dfc_module/config/device-font-cache/$_dfc_cache_id"
    if _dfcache_ready_matches "$_dfc_root" "$_dfc_font" "$_dfc_template_key" "$_dfc_source_key"; then
        _dfcache_log "后台缓存已经存在：$_dfc_font"
    else
        _dfcache_runtime_ready || return 1
        _dfpr_prepare_sources || {
            _dfcache_log '后台缓存无法准备九档源锚点'
            return 1
        }
        _dfc_stage="$_dfc_module/config/device-font-cache/.stage.${_dfc_cache_id}.$$"
        rm -rf "$_dfc_stage" 2>/dev/null || true
        mkdir -p "$_dfc_stage" 2>/dev/null || return 1
        _dfc_build="$_dfc_module/common/device_font_payload_build.py"
        _dfc_render="$_dfc_module/common/device_font_payload_overlay.py"
        _dfc_verify="$_dfc_module/common/device_font_payload_verify.py"
        _dfc_template="$_dfc_module/config/device-font-template.json"
        _dfc_build_result=$(_dfpr_exec "$_dfc_build" \
            --template "$_dfc_template" \
            --source-dir "$_dfc_module/config/device-font-sources" \
            --source-prefix LuoShu \
            --output-dir "$_dfc_stage/payload" \
            --manifest "$_dfc_stage/payload/manifest.json" 2>> "$_dfc_module/logs/device-font-cache.log")
        _dfc_rc=$?
        if [ "$_dfc_rc" -ne 0 ] || [ ! -s "$_dfc_stage/payload/manifest.json" ]; then
            rm -rf "$_dfc_stage" 2>/dev/null || true
            _dfcache_log "后台生成设备对齐字体失败：$_dfc_build_result"
            return 1
        fi
        _dfc_verify_result=$(_dfpr_exec "$_dfc_verify" --manifest "$_dfc_stage/payload/manifest.json" --root "$_dfc_stage/payload" 2>> "$_dfc_module/logs/device-font-cache.log")
        [ $? -eq 0 ] || {
            rm -rf "$_dfc_stage" 2>/dev/null || true
            _dfcache_log "后台字体负载验证失败：$_dfc_verify_result"
            return 1
        }
        _dfc_overlay_result=$(_dfpr_exec "$_dfc_render" \
            --template "$_dfc_template" \
            --payload "$_dfc_stage/payload/manifest.json" \
            --payload-root "$_dfc_stage/payload" \
            --output-tree "$_dfc_stage/overlay" 2>> "$_dfc_module/logs/device-font-cache.log")
        if [ $? -ne 0 ] || [ ! -s "$_dfc_stage/overlay/overlay-manifest.json" ]; then
            rm -rf "$_dfc_stage" 2>/dev/null || true
            _dfcache_log "后台设备字体映射失败：$_dfc_overlay_result"
            return 1
        fi
        {
            printf 'state=ready\n'
            printf 'font=%s\n' "$_dfc_font"
            printf 'cacheId=%s\n' "$_dfc_cache_id"
            printf 'templateKey=%s\n' "$_dfc_template_key"
            printf 'sourceKey=%s\n' "$_dfc_source_key"
            printf 'engine=script-anchor-v2\n'
            printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
        } > "$_dfc_stage/cache.conf" 2>/dev/null || {
            rm -rf "$_dfc_stage" 2>/dev/null || true
            return 1
        }
        mkdir -p "${_dfc_root%/*}" 2>/dev/null || return 1
        rm -rf "${_dfc_root}.previous" 2>/dev/null || true
        [ ! -d "$_dfc_root" ] || mv "$_dfc_root" "${_dfc_root}.previous" 2>/dev/null || return 1
        if mv "$_dfc_stage" "$_dfc_root" 2>/dev/null; then
            rm -rf "${_dfc_root}.previous" 2>/dev/null || true
        else
            [ ! -d "${_dfc_root}.previous" ] || mv "${_dfc_root}.previous" "$_dfc_root" 2>/dev/null || true
            rm -rf "$_dfc_stage" 2>/dev/null || true
            return 1
        fi
        _dfcache_log "后台设备对齐缓存生成完成：font=$_dfc_font verify=$_dfc_verify_result"
    fi

    _dfc_txn=0
    if type luoshu_payload_transaction_begin >/dev/null 2>&1; then
        luoshu_payload_transaction_begin || return 1
        _dfc_txn=1
    fi
    if device_font_cache_activate "$_dfc_font" && \
       { ! type luoshu_sync_mount_payload >/dev/null 2>&1 || luoshu_sync_mount_payload; } && \
       { [ "$_dfc_txn" -eq 0 ] || luoshu_payload_transaction_commit "$_dfc_font"; }; then
        printf 'font=%s\ntime=%s\n' "$_dfc_font" "$(date +%s 2>/dev/null || echo 0)" > "$_dfc_module/config/text_reboot_required.conf" 2>/dev/null || true
        rm -f "$_dfc_pending" 2>/dev/null || true
        _dfcache_prune "$_dfc_root"
        _dfcache_notify '设备对齐字体已在后台生成完成，请完整重启一次加载校准结果。'
        _dfcache_log "后台设备对齐缓存已提交，等待重启：$_dfc_font"
        rmdir "$_dfc_lock" 2>/dev/null || true
        trap - EXIT HUP INT TERM
        return 0
    fi
    [ "$_dfc_txn" -eq 0 ] || luoshu_payload_transaction_abort >/dev/null 2>&1 || true
    _dfcache_log "后台设备对齐缓存激活失败：$_dfc_font"
    return 1
}

if [ "${0##*/}" = device_font_cache.sh ]; then
    case "${1:-service}" in
        service|build-pending) device_font_cache_build_pending ;;
        schedule) device_font_cache_schedule "${2:-custom}" ;;
        activate) device_font_cache_activate "${2:-custom}" ;;
        lookup) device_font_cache_lookup "${2:-custom}" ;;
        source-key) _dfcache_source_key ;;
        *) echo 'Usage: device_font_cache.sh {service|schedule FONT|activate FONT|lookup FONT|source-key}' >&2; exit 2 ;;
    esac
fi