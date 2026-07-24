#!/system/bin/sh
# LuoShu v2.2 per-device payload runtime.
# Builds a complete device-specific payload after the legacy adapter has prepared
# source weights, then installs the generated systemless tree inside LuoShu's
# existing outer payload transaction. Unsupported sources fail soft and keep the
# legacy mapping; partial v2 trees are never committed.
set +e

_dfpr_module() {
    printf '%s\n' "${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
}

_dfpr_log() {
    _dfpr_level="$1"
    shift
    _dfpr_module_dir="$(_dfpr_module)"
    mkdir -p "$_dfpr_module_dir/logs" 2>/dev/null || true
    printf '[%s] [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$_dfpr_level" "$*" \
        >> "$_dfpr_module_dir/logs/device-font-payload.log" 2>/dev/null || true
}

_dfpr_python() {
    _dfpr_module_dir="$(_dfpr_module)"
    printf '%s/common/python/bin/luoshu-python\n' "$_dfpr_module_dir"
}

_dfpr_exec() {
    _dfpr_module_dir="$(_dfpr_module)"
    _dfpr_python_bin="$(_dfpr_python)"
    [ -x "$_dfpr_python_bin" ] || return 1
    _dfpr_python_root="$_dfpr_module_dir/common/python"
    PYTHONHOME="$_dfpr_python_root" \
    PYTHONPATH="$_dfpr_module_dir/common:$_dfpr_python_root/lib/python3.14:$_dfpr_python_root/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$_dfpr_python_root/lib:$_dfpr_python_root/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$_dfpr_python_bin" "$@"
}

_dfpr_hash() {
    _dfpr_file="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$_dfpr_file" 2>/dev/null | awk '{print $1}'
    elif command -v busybox >/dev/null 2>&1; then
        busybox sha256sum "$_dfpr_file" 2>/dev/null | awk '{print $1}'
    else
        cksum "$_dfpr_file" 2>/dev/null | awk '{print $1 ":" $2}'
    fi
}

_dfpr_size() {
    stat -c '%s' "$1" 2>/dev/null || wc -c < "$1" 2>/dev/null | tr -d '[:space:]'
}

_dfpr_link_or_copy() {
    _dfpr_source="$1"
    _dfpr_target="$2"
    mkdir -p "${_dfpr_target%/*}" 2>/dev/null || return 1
    rm -f "$_dfpr_target" 2>/dev/null || true
    ln "$_dfpr_source" "$_dfpr_target" 2>/dev/null || cp -f "$_dfpr_source" "$_dfpr_target" 2>/dev/null || return 1
    chmod 0644 "$_dfpr_target" 2>/dev/null || true
}

_dfpr_anchor_lines() {
    _dfpr_store="$1"
    for _dfpr_pair in \
        '100:thin' '200:extralight' '300:light' '400:regular' '500:medium' \
        '600:semibold' '700:bold' '800:extrabold' '900:black'; do
        _dfpr_weight=${_dfpr_pair%%:*}
        _dfpr_name=${_dfpr_pair#*:}
        _dfpr_path="$_dfpr_store/${_dfpr_name}.font"
        [ -s "$_dfpr_path" ] && printf '%s|%s\n' "$_dfpr_weight" "$_dfpr_path"
    done
}

_dfpr_nearest_anchor() {
    _dfpr_wanted="$1"
    _dfpr_lines="$2"
    _dfpr_best_path=''
    _dfpr_best_delta=10000
    _dfpr_best_weight=10000
    while IFS='|' read -r _dfpr_weight _dfpr_path; do
        [ -s "$_dfpr_path" ] || continue
        _dfpr_delta=$((_dfpr_weight - _dfpr_wanted))
        [ "$_dfpr_delta" -ge 0 ] || _dfpr_delta=$((-_dfpr_delta))
        if [ "$_dfpr_delta" -lt "$_dfpr_best_delta" ] || \
           { [ "$_dfpr_delta" -eq "$_dfpr_best_delta" ] && [ "$_dfpr_weight" -lt "$_dfpr_best_weight" ]; }; then
            _dfpr_best_delta="$_dfpr_delta"
            _dfpr_best_weight="$_dfpr_weight"
            _dfpr_best_path="$_dfpr_path"
        fi
    done <<EOF_DFPR_ANCHORS
$_dfpr_lines
EOF_DFPR_ANCHORS
    [ -n "$_dfpr_best_path" ] || return 1
    printf '%s\n' "$_dfpr_best_path"
}

_dfpr_prepare_sources() {
    _dfpr_module_dir="$(_dfpr_module)"
    _dfpr_store="$_dfpr_module_dir/system/fonts/.luoshu-font-store"
    _dfpr_output="$_dfpr_module_dir/config/device-font-sources"
    _dfpr_stage="$_dfpr_module_dir/config/.device-font-sources.$$"
    [ -d "$_dfpr_store" ] || return 2
    _dfpr_lines="$(_dfpr_anchor_lines "$_dfpr_store")"
    [ -n "$_dfpr_lines" ] || return 2
    rm -rf "$_dfpr_stage" 2>/dev/null || true
    mkdir -p "$_dfpr_stage" 2>/dev/null || return 1
    for _dfpr_weight in 100 200 300 400 500 600 700 800 900; do
        _dfpr_anchor="$(_dfpr_nearest_anchor "$_dfpr_weight" "$_dfpr_lines")" || {
            rm -rf "$_dfpr_stage" 2>/dev/null || true
            return 2
        }
        _dfpr_link_or_copy "$_dfpr_anchor" "$_dfpr_stage/LuoShu-${_dfpr_weight}.ttf" || {
            rm -rf "$_dfpr_stage" 2>/dev/null || true
            return 1
        }
    done
    rm -rf "$_dfpr_output.previous" 2>/dev/null || true
    [ ! -d "$_dfpr_output" ] || mv "$_dfpr_output" "$_dfpr_output.previous" 2>/dev/null || return 1
    if mv "$_dfpr_stage" "$_dfpr_output" 2>/dev/null; then
        rm -rf "$_dfpr_output.previous" 2>/dev/null || true
        return 0
    fi
    [ ! -d "$_dfpr_output.previous" ] || mv "$_dfpr_output.previous" "$_dfpr_output" 2>/dev/null || true
    rm -rf "$_dfpr_stage" 2>/dev/null || true
    return 1
}

_dfpr_path_allowed() {
    case "$1" in
        system/fonts/*|system/etc/*.xml|system_ext/fonts/*|system_ext/etc/*.xml|product/fonts/*|product/etc/*.xml|\
        vendor/fonts/*|vendor/etc/*.xml|odm/fonts/*|odm/etc/*.xml|oem/fonts/*|oem/etc/*.xml|\
        my_product/fonts/*|my_product/etc/*.xml|my_engineering/fonts/*|my_engineering/etc/*.xml|\
        my_company/fonts/*|my_company/etc/*.xml|my_preload/fonts/*|my_preload/etc/*.xml|\
        my_region/fonts/*|my_region/etc/*.xml|my_stock/fonts/*|my_stock/etc/*.xml|\
        oplus_product/fonts/*|oplus_product/etc/*.xml|oplus_engineering/fonts/*|oplus_engineering/etc/*.xml|\
        oplus_version/fonts/*|oplus_version/etc/*.xml|oplus_region/fonts/*|oplus_region/etc/*.xml|\
        mi_ext/fonts/*|mi_ext/etc/*.xml|cust/fonts/*|cust/etc/*.xml) return 0 ;;
    esac
    return 1
}

_dfpr_remove_installed_files() {
    _dfpr_module_dir="$(_dfpr_module)"
    _dfpr_manifest="$_dfpr_module_dir/config/device-font-installed.conf"
    [ -f "$_dfpr_manifest" ] || return 0
    while IFS='|' read -r _dfpr_kind _dfpr_rel _dfpr_hash_value _dfpr_bytes; do
        [ "$_dfpr_kind" = file ] || continue
        _dfpr_path_allowed "$_dfpr_rel" || continue
        rm -f "$_dfpr_module_dir/$_dfpr_rel" 2>/dev/null || true
    done < "$_dfpr_manifest"
    return 0
}

_dfpr_prepare_dynamic_state() {
    _dfpr_overlay="$1"
    _dfpr_manifest_tmp="$2"
    _dfpr_module_dir="$(_dfpr_module)"
    _dfpr_dynamic_source="$_dfpr_overlay/dynamic/data-fonts-config.xml"
    _dfpr_dynamic_dest="$_dfpr_module_dir/system/etc/.luoshu-data-fonts-config.xml"
    _dfpr_dynamic_state="$_dfpr_module_dir/config/device-font-dynamic-mount.conf"
    # Keep the real target in a dedicated variable. _dfpr_link_or_copy uses shell-global
    # scratch variables named _dfpr_source/_dfpr_target and must never overwrite this path.
    _dfpr_dynamic_target="${LUOSHU_DATA_FONTS_CONFIG_TARGET:-/data/fonts/config/config.xml}"
    if [ ! -s "$_dfpr_dynamic_source" ]; then
        rm -f "$_dfpr_dynamic_dest" "$_dfpr_dynamic_state" 2>/dev/null || true
        return 0
    fi
    [ -s "$_dfpr_dynamic_target" ] || return 2
    _dfpr_link_or_copy "$_dfpr_dynamic_source" "$_dfpr_dynamic_dest" || return 1
    chmod 0600 "$_dfpr_dynamic_dest" 2>/dev/null || true
    if command -v chcon >/dev/null 2>&1; then
        chcon --reference="$_dfpr_dynamic_target" "$_dfpr_dynamic_dest" 2>/dev/null || true
    fi
    _dfpr_target_hash="$(_dfpr_hash "$_dfpr_dynamic_target")"
    _dfpr_source_hash="$(_dfpr_hash "$_dfpr_dynamic_dest")"
    [ -n "$_dfpr_target_hash" ] && [ -n "$_dfpr_source_hash" ] || return 1
    _dfpr_state_tmp="${_dfpr_dynamic_state}.tmp.$$"
    {
        printf 'state=prepared\n'
        printf 'source=system/etc/.luoshu-data-fonts-config.xml\n'
        printf 'target=%s\n' "$_dfpr_dynamic_target"
        printf 'targetSha256=%s\n' "$_dfpr_target_hash"
        printf 'sourceSha256=%s\n' "$_dfpr_source_hash"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_dfpr_state_tmp" 2>/dev/null || return 1
    mv -f "$_dfpr_state_tmp" "$_dfpr_dynamic_state" 2>/dev/null || return 1
    chmod 0600 "$_dfpr_dynamic_state" 2>/dev/null || true
    _dfpr_bytes="$(_dfpr_size "$_dfpr_dynamic_dest")"
    printf 'file|system/etc/.luoshu-data-fonts-config.xml|%s|%s\n' "$_dfpr_source_hash" "$_dfpr_bytes" >> "$_dfpr_manifest_tmp"
    return 0
}

_dfpr_install_overlay() {
    _dfpr_overlay="$1"
    _dfpr_module_dir="$(_dfpr_module)"
    _dfpr_manifest="$_dfpr_module_dir/config/device-font-installed.conf"
    _dfpr_manifest_tmp="${_dfpr_manifest}.tmp.$$"
    _dfpr_list="$_dfpr_module_dir/config/.device-font-overlay-files.$$"
    [ -s "$_dfpr_overlay/overlay-manifest.json" ] || return 1
    _dfpr_remove_installed_files
    : > "$_dfpr_manifest_tmp" 2>/dev/null || return 1
    find "$_dfpr_overlay" -type f 2>/dev/null | LC_ALL=C sort > "$_dfpr_list" 2>/dev/null || {
        rm -f "$_dfpr_manifest_tmp" "$_dfpr_list" 2>/dev/null || true
        return 1
    }
    _dfpr_count=0
    while IFS= read -r _dfpr_source; do
        _dfpr_rel=${_dfpr_source#$_dfpr_overlay/}
        case "$_dfpr_rel" in overlay-manifest.json|dynamic/*) continue ;; esac
        _dfpr_path_allowed "$_dfpr_rel" || {
            rm -f "$_dfpr_manifest_tmp" "$_dfpr_list" 2>/dev/null || true
            return 1
        }
        _dfpr_target="$_dfpr_module_dir/$_dfpr_rel"
        _dfpr_link_or_copy "$_dfpr_source" "$_dfpr_target" || {
            rm -f "$_dfpr_manifest_tmp" "$_dfpr_list" 2>/dev/null || true
            return 1
        }
        _dfpr_hash_value="$(_dfpr_hash "$_dfpr_target")"
        _dfpr_bytes="$(_dfpr_size "$_dfpr_target")"
        [ -n "$_dfpr_hash_value" ] && [ "${_dfpr_bytes:-0}" -ge 1 ] 2>/dev/null || {
            rm -f "$_dfpr_manifest_tmp" "$_dfpr_list" 2>/dev/null || true
            return 1
        }
        printf 'file|%s|%s|%s\n' "$_dfpr_rel" "$_dfpr_hash_value" "$_dfpr_bytes" >> "$_dfpr_manifest_tmp"
        _dfpr_count=$((_dfpr_count + 1))
    done < "$_dfpr_list"
    rm -f "$_dfpr_list" 2>/dev/null || true
    [ "$_dfpr_count" -gt 0 ] || { rm -f "$_dfpr_manifest_tmp" 2>/dev/null || true; return 1; }
    _dfpr_prepare_dynamic_state "$_dfpr_overlay" "$_dfpr_manifest_tmp"
    _dfpr_dynamic_rc=$?
    [ "$_dfpr_dynamic_rc" -ne 1 ] || { rm -f "$_dfpr_manifest_tmp" 2>/dev/null || true; return 1; }
    mv -f "$_dfpr_manifest_tmp" "$_dfpr_manifest" 2>/dev/null || return 1
    chmod 0600 "$_dfpr_manifest" 2>/dev/null || true
    return 0
}

device_font_payload_is_installed() {
    _dfpr_module_dir="$(_dfpr_module)"
    grep -q '^state=installed$' "$_dfpr_module_dir/config/device-font-engine.conf" 2>/dev/null
}

device_font_payload_validate_installed() {
    _dfpr_module_dir="$(_dfpr_module)"
    _dfpr_manifest="$_dfpr_module_dir/config/device-font-installed.conf"
    device_font_payload_is_installed || return 2
    [ -s "$_dfpr_manifest" ] || return 1
    _dfpr_seen=0
    while IFS='|' read -r _dfpr_kind _dfpr_rel _dfpr_expected_hash _dfpr_expected_size; do
        [ "$_dfpr_kind" = file ] || return 1
        _dfpr_path_allowed "$_dfpr_rel" || return 1
        _dfpr_file="$_dfpr_module_dir/$_dfpr_rel"
        [ -f "$_dfpr_file" ] || return 1
        _dfpr_size_now="$(_dfpr_size "$_dfpr_file")"
        [ "$_dfpr_size_now" = "$_dfpr_expected_size" ] || return 1
        _dfpr_hash_now="$(_dfpr_hash "$_dfpr_file")"
        [ "$_dfpr_hash_now" = "$_dfpr_expected_hash" ] || return 1
        _dfpr_seen=$((_dfpr_seen + 1))
    done < "$_dfpr_manifest"
    [ "$_dfpr_seen" -gt 0 ]
}

device_font_payload_clear() {
    _dfpr_module_dir="$(_dfpr_module)"
    _dfpr_remove_installed_files
    rm -f "$_dfpr_module_dir/config/device-font-installed.conf" \
          "$_dfpr_module_dir/config/device-font-engine.conf" \
          "$_dfpr_module_dir/config/device-font-dynamic-mount.conf" \
          "$_dfpr_module_dir/system/etc/.luoshu-data-fonts-config.xml" 2>/dev/null || true
    return 0
}

device_font_payload_build_install() {
    _dfpr_font_id="${1:-custom}"
    _dfpr_module_dir="$(_dfpr_module)"
    _dfpr_template="$_dfpr_module_dir/config/device-font-template.json"
    _dfpr_payload="$_dfpr_module_dir/config/device-font-payload"
    _dfpr_overlay="$_dfpr_module_dir/config/device-font-overlay"
    _dfpr_build="$_dfpr_module_dir/common/device_font_payload_build.py"
    _dfpr_render="$_dfpr_module_dir/common/device_font_payload_overlay.py"
    _dfpr_lock="$_dfpr_module_dir/.device-font-payload.lock"
    [ -x "$(_dfpr_python)" ] && [ -f "$_dfpr_build" ] && [ -f "$_dfpr_render" ] || return 2
    if [ ! -s "$_dfpr_template" ] && [ -f "$_dfpr_module_dir/common/device_font_template.sh" ]; then
        MODDIR="$_dfpr_module_dir" sh "$_dfpr_module_dir/common/device_font_template.sh" ensure >/dev/null 2>&1 || true
    fi
    [ -s "$_dfpr_template" ] || return 2
    if ! mkdir "$_dfpr_lock" 2>/dev/null; then
        _dfpr_log WARN '已有设备专属负载任务在运行'
        return 1
    fi
    trap 'rmdir "'"$_dfpr_lock"'" 2>/dev/null || true' EXIT HUP INT TERM
    _dfpr_prepare_sources
    _dfpr_sources_rc=$?
    if [ "$_dfpr_sources_rc" -ne 0 ]; then
        rmdir "$_dfpr_lock" 2>/dev/null || true
        trap - EXIT HUP INT TERM
        return "$_dfpr_sources_rc"
    fi
    _dfpr_build_result=$(_dfpr_exec "$_dfpr_build" \
        --template "$_dfpr_template" \
        --source-dir "$_dfpr_module_dir/config/device-font-sources" \
        --source-prefix LuoShu \
        --output-dir "$_dfpr_payload" \
        --manifest "$_dfpr_payload/manifest.json" 2>> "$_dfpr_module_dir/logs/device-font-payload.log")
    _dfpr_build_rc=$?
    if [ "$_dfpr_build_rc" -ne 0 ] || [ ! -s "$_dfpr_payload/manifest.json" ]; then
        _dfpr_log WARN "字体 $_dfpr_font_id 暂不支持逐设备生成，保留兼容映射：$_dfpr_build_result"
        rmdir "$_dfpr_lock" 2>/dev/null || true
        trap - EXIT HUP INT TERM
        return 2
    fi
    _dfpr_overlay_result=$(_dfpr_exec "$_dfpr_render" \
        --template "$_dfpr_template" \
        --payload "$_dfpr_payload/manifest.json" \
        --payload-root "$_dfpr_payload" \
        --output-tree "$_dfpr_overlay" 2>> "$_dfpr_module_dir/logs/device-font-payload.log")
    _dfpr_overlay_rc=$?
    if [ "$_dfpr_overlay_rc" -ne 0 ] || [ ! -s "$_dfpr_overlay/overlay-manifest.json" ]; then
        _dfpr_log WARN "字体 $_dfpr_font_id 的设备配置映射未完成，保留兼容映射：$_dfpr_overlay_result"
        rmdir "$_dfpr_lock" 2>/dev/null || true
        trap - EXIT HUP INT TERM
        return 2
    fi
    if ! _dfpr_install_overlay "$_dfpr_overlay"; then
        _dfpr_log ERROR "字体 $_dfpr_font_id 的设备专属负载安装失败"
        rmdir "$_dfpr_lock" 2>/dev/null || true
        trap - EXIT HUP INT TERM
        return 1
    fi
    _dfpr_state="$_dfpr_module_dir/config/device-font-engine.conf"
    {
        printf 'state=installed\n'
        printf 'schema=device-font-payload-v1\n'
        printf 'font=%s\n' "$_dfpr_font_id"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "${_dfpr_state}.tmp.$$" 2>/dev/null || {
        rmdir "$_dfpr_lock" 2>/dev/null || true
        trap - EXIT HUP INT TERM
        return 1
    }
    mv -f "${_dfpr_state}.tmp.$$" "$_dfpr_state" 2>/dev/null || {
        rmdir "$_dfpr_lock" 2>/dev/null || true
        trap - EXIT HUP INT TERM
        return 1
    }
    chmod 0600 "$_dfpr_state" 2>/dev/null || true
    device_font_payload_validate_installed || {
        _dfpr_log ERROR "字体 $_dfpr_font_id 的设备专属负载提交后校验失败"
        rmdir "$_dfpr_lock" 2>/dev/null || true
        trap - EXIT HUP INT TERM
        return 1
    }
    _dfpr_log INFO "字体 $_dfpr_font_id 的设备专属负载已安装：build=$_dfpr_build_result overlay=$_dfpr_overlay_result"
    rmdir "$_dfpr_lock" 2>/dev/null || true
    trap - EXIT HUP INT TERM
    return 0
}

device_font_dynamic_mount_apply() {
    _dfpr_module_dir="$(_dfpr_module)"
    _dfpr_state="$_dfpr_module_dir/config/device-font-dynamic-mount.conf"
    [ -s "$_dfpr_state" ] || return 2
    _dfpr_source_rel=$(sed -n 's/^source=//p' "$_dfpr_state" 2>/dev/null | head -n1)
    _dfpr_target=$(sed -n 's/^target=//p' "$_dfpr_state" 2>/dev/null | head -n1)
    _dfpr_target_hash=$(sed -n 's/^targetSha256=//p' "$_dfpr_state" 2>/dev/null | head -n1)
    _dfpr_source_hash=$(sed -n 's/^sourceSha256=//p' "$_dfpr_state" 2>/dev/null | head -n1)
    case "$_dfpr_source_rel" in system/etc/.luoshu-data-fonts-config.xml) ;; *) return 1 ;; esac
    [ "$_dfpr_target" = "${LUOSHU_DATA_FONTS_CONFIG_TARGET:-/data/fonts/config/config.xml}" ] || return 1
    _dfpr_source="$_dfpr_module_dir/$_dfpr_source_rel"
    [ -s "$_dfpr_source" ] && [ -s "$_dfpr_target" ] || return 2
    [ "$(_dfpr_hash "$_dfpr_source")" = "$_dfpr_source_hash" ] || return 1
    if [ "$(_dfpr_hash "$_dfpr_target")" != "$_dfpr_target_hash" ]; then
        _dfpr_log WARN '动态字体配置已被系统更新，本次启动跳过旧视图挂载'
        return 2
    fi
    awk -v path="$_dfpr_target" '$5 == path { found=1 } END { exit !found }' /proc/self/mountinfo 2>/dev/null && return 0
    mount -o bind "$_dfpr_source" "$_dfpr_target" 2>/dev/null || mount --bind "$_dfpr_source" "$_dfpr_target" 2>/dev/null || {
        _dfpr_log WARN '动态字体配置只读视图挂载失败，保留 ROM 原配置'
        return 2
    }
    mount -o remount,bind,ro "$_dfpr_target" 2>/dev/null || true
    if awk -v path="$_dfpr_target" '$5 == path { found=1 } END { exit !found }' /proc/self/mountinfo 2>/dev/null; then
        _dfpr_log INFO '动态字体配置只读视图已在 FontManagerService 初始化前挂载'
        return 0
    fi
    umount "$_dfpr_target" 2>/dev/null || true
    _dfpr_log WARN '动态字体配置挂载验证失败，已撤销并保留 ROM 原配置'
    return 2
}

if [ "${0##*/}" = device_font_payload_runtime.sh ]; then
    case "${1:-validate}" in
        build-install) shift; device_font_payload_build_install "${1:-custom}" ;;
        validate) device_font_payload_validate_installed ;;
        clear) device_font_payload_clear ;;
        mount-dynamic) device_font_dynamic_mount_apply ;;
        *) echo "Usage: $0 {build-install [font-id]|validate|clear|mount-dynamic}" >&2; exit 2 ;;
    esac
fi
