#!/system/bin/sh
# LuoShu v2.2 automatic runtime proof collector.
# The authoritative report is always stored inside the module. Public storage export is
# best-effort only and may fail on devices where /sdcard is not ready in the root service.
set +e

_device_font_report_module() {
    if type _luoshu_safety_module >/dev/null 2>&1; then
        _luoshu_safety_module
    else
        printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
    fi
}

_device_font_report_root() {
    if [ -n "${LUOSHU_RUNTIME_REPORT_ROOT:-}" ]; then
        printf '%s\n' "$LUOSHU_RUNTIME_REPORT_ROOT"
    else
        printf '%s/reports/v2.2-runtime-latest\n' "$(_device_font_report_module)"
    fi
}

_device_font_report_public_root() {
    printf '%s/reports/v2.2-runtime-latest\n' "${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}"
}

_device_font_report_log() {
    _dfr_module="$(_device_font_report_module)"
    mkdir -p "$_dfr_module/logs" 2>/dev/null || true
    printf '[%s] [REPORT] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$*" \
        >> "$_dfr_module/logs/runtime-report.log" 2>/dev/null || true
}

_device_font_report_copy() {
    _dfr_source="$1"
    _dfr_target="$2"
    [ -s "$_dfr_source" ] || return 0
    cp -f "$_dfr_source" "$_dfr_target" 2>/dev/null || return 1
    chmod 0644 "$_dfr_target" 2>/dev/null || true
}

_device_font_report_export_public() {
    _dfr_source_root="$1"
    _dfr_public_root="$(_device_font_report_public_root)"
    [ "$_dfr_source_root" != "$_dfr_public_root" ] || return 0
    [ -d /sdcard ] || return 2
    _dfr_public_stage="${_dfr_public_root}.tmp.$$"
    rm -rf "$_dfr_public_stage" 2>/dev/null || true
    mkdir -p "${_dfr_public_root%/*}" "$_dfr_public_stage" 2>/dev/null || return 2
    cp -R "$_dfr_source_root/." "$_dfr_public_stage/" 2>/dev/null || {
        rm -rf "$_dfr_public_stage" 2>/dev/null || true
        return 2
    }
    find "$_dfr_public_stage" -type f -exec chmod 0644 {} \; 2>/dev/null || true
    rm -rf "$_dfr_public_root" 2>/dev/null || true
    mv -f "$_dfr_public_stage" "$_dfr_public_root" 2>/dev/null || {
        rm -rf "$_dfr_public_stage" 2>/dev/null || true
        return 2
    }
    chmod 0755 "$_dfr_public_root" 2>/dev/null || true
    return 0
}

device_font_runtime_report_collect() {
    _dfr_module="$(_device_font_report_module)"
    _dfr_config="$_dfr_module/config"
    _dfr_root="$(_device_font_report_root)"
    _dfr_active=$(head -n1 "$_dfr_config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_dfr_active" ] || _dfr_active=default
    _dfr_engine=$(sed -n 's/^state=//p' "$_dfr_config/device-font-engine.conf" 2>/dev/null | head -n1)

    _dfr_stage="${_dfr_root}.tmp.$$"
    rm -rf "$_dfr_stage" 2>/dev/null || true
    mkdir -p "$_dfr_stage" 2>/dev/null || {
        _device_font_report_log "无法创建内部报告暂存目录：$_dfr_stage"
        return 1
    }

    {
        printf 'report=device-font-runtime-v2\n'
        printf 'time=%s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)"
        printf 'moduleVersion=%s\n' "$(sed -n 's/^version=//p' "$_dfr_module/module.prop" 2>/dev/null | head -n1)"
        printf 'moduleVersionCode=%s\n' "$(sed -n 's/^versionCode=//p' "$_dfr_module/module.prop" 2>/dev/null | head -n1)"
        printf 'activeFont=%s\n' "$_dfr_active"
        printf 'engineState=%s\n' "${_dfr_engine:-missing}"
        printf 'fingerprint=%s\n' "$(getprop ro.build.fingerprint 2>/dev/null)"
        printf 'incremental=%s\n' "$(getprop ro.build.version.incremental 2>/dev/null)"
        printf 'sdk=%s\n' "$(getprop ro.build.version.sdk 2>/dev/null)"
        printf 'rom=%s\n' "$(getprop ro.build.display.id 2>/dev/null)"
        printf 'rootManager=%s\n' "$(type luoshu_detect_root_manager >/dev/null 2>&1 && luoshu_detect_root_manager || echo unknown)"
    } > "$_dfr_stage/summary.txt" 2>/dev/null || {
        rm -rf "$_dfr_stage" 2>/dev/null || true
        _device_font_report_log '无法写入内部报告摘要'
        return 1
    }

    for _dfr_pair in \
        "device-font-template.json|device-font-template.json" \
        "device-font-template.key|device-font-template.key" \
        "device-font-engine.conf|device-font-engine.conf" \
        "device-font-installed.conf|device-font-installed.conf" \
        "device-font-dynamic-mount.conf|device-font-dynamic-mount.conf" \
        "font-payload-boot.conf|font-payload-boot.conf" \
        "font-payload-schema.conf|font-payload-schema.conf" \
        "font-target-coverage.conf|font-target-coverage.conf"; do
        _dfr_name=${_dfr_pair%%|*}
        _dfr_output=${_dfr_pair#*|}
        _device_font_report_copy "$_dfr_config/$_dfr_name" "$_dfr_stage/$_dfr_output" || true
    done
    _device_font_report_copy "$_dfr_config/device-font-payload/manifest.json" \
        "$_dfr_stage/device-font-payload-manifest.json" || true
    _device_font_report_copy "$_dfr_config/device-font-overlay/overlay-manifest.json" \
        "$_dfr_stage/device-font-overlay-manifest.json" || true
    _device_font_report_copy "$_dfr_module/system/etc/.luoshu-data-fonts-config.xml" \
        "$_dfr_stage/data-fonts-config-view.xml" || true

    if command -v cmd >/dev/null 2>&1; then
        cmd font dump > "$_dfr_stage/font-manager-dump.txt" 2>&1 || \
            cmd font system > "$_dfr_stage/font-manager-dump.txt" 2>&1 || true
    fi
    if [ ! -s "$_dfr_stage/font-manager-dump.txt" ] && command -v dumpsys >/dev/null 2>&1; then
        dumpsys font > "$_dfr_stage/font-manager-dump.txt" 2>&1 || true
    fi
    grep -E '/data/fonts|/(fonts|font_fallback)\.xml' /proc/self/mountinfo 2>/dev/null \
        > "$_dfr_stage/font-mounts.txt" || true
    {
        printf '%s\n' '--- private dynamic view ---'
        sha256sum "$_dfr_module/system/etc/.luoshu-data-fonts-config.xml" 2>/dev/null || true
        printf '%s\n' '--- current /data font config ---'
        sha256sum /data/fonts/config/config.xml 2>/dev/null || true
        printf '%s\n' '--- google/product named families ---'
        grep -Ei 'google[-_ ]?sans|product[-_ ]?sans' "$_dfr_stage/font-manager-dump.txt" 2>/dev/null || true
    } > "$_dfr_stage/dynamic-font-proof.txt"

    find "$_dfr_stage" -type f -exec chmod 0644 {} \; 2>/dev/null || true
    rm -rf "$_dfr_root" 2>/dev/null || true
    mkdir -p "${_dfr_root%/*}" 2>/dev/null || {
        rm -rf "$_dfr_stage" 2>/dev/null || true
        _device_font_report_log "无法创建内部报告目录：${_dfr_root%/*}"
        return 1
    }
    mv -f "$_dfr_stage" "$_dfr_root" 2>/dev/null || {
        rm -rf "$_dfr_stage" 2>/dev/null || true
        _device_font_report_log "无法提交内部报告：$_dfr_root"
        return 1
    }
    chmod 0755 "$_dfr_root" 2>/dev/null || true
    _device_font_report_log "内部报告已生成：$_dfr_root"
    _device_font_report_export_public "$_dfr_root" || \
        _device_font_report_log "共享存储导出失败，内部报告仍保留：$(_device_font_report_public_root)"
    return 0
}

# Preserve the original boot-confirmation contract and collect evidence afterward.
font_config_mark_boot_success() {
    _lmbs_config="$(_luoshu_safety_config)"
    _lmbs_state=$(sed -n 's/^state=//p' "$_lmbs_config/font-payload-boot.conf" 2>/dev/null | head -n1)
    if [ "$_lmbs_state" = booting ]; then
        _lmbs_font=$(sed -n 's/^font=//p' "$_lmbs_config/font-payload-boot.conf" 2>/dev/null | head -n1)
        {
            printf 'state=confirmed\n'
            printf 'font=%s\n' "${_lmbs_font:-unknown}"
            printf 'time=%s\n' "$(date +%s)"
        } > "$_lmbs_config/font-payload-boot.conf.tmp.$$" 2>/dev/null || return 1
        mv -f "$_lmbs_config/font-payload-boot.conf.tmp.$$" \
            "$_lmbs_config/font-payload-boot.conf" 2>/dev/null || return 1
        rm -f "$_lmbs_config/font-boot-failures" \
            "$_lmbs_config/font-payload-quarantine.conf" 2>/dev/null || true
        printf 'time=%s\n' "$(date +%s)" > \
            "$_lmbs_config/font-last-boot-success.conf" 2>/dev/null || true
        chmod 0644 "$_lmbs_config/font-payload-boot.conf" \
            "$_lmbs_config/font-last-boot-success.conf" 2>/dev/null || true
        _luoshu_safety_log INFO 'Android 已完成开机，字体负载事务确认成功'
    fi
    device_font_runtime_report_collect >/dev/null 2>&1 || true
    return 0
}
