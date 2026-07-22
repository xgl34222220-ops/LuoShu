#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "baseline-v6-mono-v1"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, found {count}: {old[:100]!r}")
    write(path, text.replace(old, new, 1))


# Central payload schema is written by every successful transaction and checked before Zygote.
replace_once(
    "common/font_safety.sh",
    '''_luoshu_safety_config() {
    printf '%s/config\n' "$(_luoshu_safety_module)"
}

_luoshu_payload_parts() {''',
    f'''_luoshu_safety_config() {{
    printf '%s/config\\n' "$(_luoshu_safety_module)"
}}

LUOSHU_PAYLOAD_SCHEMA_CURRENT="${{LUOSHU_PAYLOAD_SCHEMA_CURRENT:-{SCHEMA}}}"

luoshu_payload_schema_current() {{
    printf '%s\\n' "$LUOSHU_PAYLOAD_SCHEMA_CURRENT"
}}

luoshu_payload_schema_read() {{
    sed -n 's/^schema=//p' "$(_luoshu_safety_config)/font-payload-schema.conf" 2>/dev/null | head -n1 | tr -d '\\r\\n'
}}

luoshu_payload_schema_write() {{
    _lpsw_active="${{1:-default}}"
    _lpsw_config="$(_luoshu_safety_config)"
    _lpsw_tmp="$_lpsw_config/font-payload-schema.conf.tmp.$$"
    mkdir -p "$_lpsw_config" 2>/dev/null || return 1
    {{
        printf 'schema=%s\\n' "$LUOSHU_PAYLOAD_SCHEMA_CURRENT"
        printf 'font=%s\\n' "$_lpsw_active"
        printf 'time=%s\\n' "$(date +%s)"
    }} > "$_lpsw_tmp" 2>/dev/null || return 1
    mv -f "$_lpsw_tmp" "$_lpsw_config/font-payload-schema.conf" 2>/dev/null || return 1
    chmod 0644 "$_lpsw_config/font-payload-schema.conf" 2>/dev/null || true
}}

_luoshu_payload_parts() {{''',
)

text = read("common/font_safety.sh")
text = text.replace("grep -q 'LuoShu-[1-9][0-9][0-9]\\.ttf'", "grep -Eq 'LuoShu(Mono)?-[1-9][0-9][0-9]\\.ttf'")
text = text.replace("grep -q 'LuoShu-'", "grep -Eq 'LuoShu(Mono)?-'")
write("common/font_safety.sh", text)

replace_once(
    "common/font_safety.sh",
    '''    if [ "$_lpa_active" = default ]; then
        rm -f "$_lpa_config/font-payload-boot.conf" "$_lpa_config/font-payload-manifest.conf" 2>/dev/null || true
        return 0
    fi''',
    '''    if [ "$_lpa_active" = default ]; then
        rm -f "$_lpa_config/font-payload-boot.conf" "$_lpa_config/font-payload-manifest.conf" 2>/dev/null || true
        luoshu_payload_schema_write default
        return $?
    fi''',
)
replace_once(
    "common/font_safety.sh",
    '''    mv -f "$_lpa_config/font-payload-boot.conf.tmp.$$" "$_lpa_config/font-payload-boot.conf" 2>/dev/null || return 1
    chmod 0644 "$_lpa_config/font-payload-boot.conf" 2>/dev/null || true
}''',
    '''    mv -f "$_lpa_config/font-payload-boot.conf.tmp.$$" "$_lpa_config/font-payload-boot.conf" 2>/dev/null || return 1
    chmod 0644 "$_lpa_config/font-payload-boot.conf" 2>/dev/null || true
    luoshu_payload_schema_write "$_lpa_active"
}''',
)
replace_once(
    "common/font_safety.sh",
    '''    for _lpt_name in active_font.conf font_mix.conf font-config-overlay.conf font-target-aliases.conf font-target-coverage.conf font-payload-manifest.conf font-payload-boot.conf text_reboot_required.conf; do''',
    '''    for _lpt_name in active_font.conf font_mix.conf font-config-overlay.conf font-target-aliases.conf font-target-coverage.conf font-payload-manifest.conf font-payload-boot.conf font-payload-schema.conf text_reboot_required.conf; do''',
)
replace_once(
    "common/font_safety.sh",
    '''    rm -f "$_lpq_config/font-payload-boot.conf" "$_lpq_config/font-payload-manifest.conf" \\
          "$_lpq_config/font-target-aliases.conf" "$_lpq_config/font-target-coverage.conf" \\
          "$_lpq_config/font-config-overlay.conf" 2>/dev/null || true''',
    '''    rm -f "$_lpq_config/font-payload-boot.conf" "$_lpq_config/font-payload-manifest.conf" \\
          "$_lpq_config/font-payload-schema.conf" "$_lpq_config/font-payload-rebuild-pending.conf" \\
          "$_lpq_config/font-target-aliases.conf" "$_lpq_config/font-target-coverage.conf" \\
          "$_lpq_config/font-config-overlay.conf" 2>/dev/null || true''',
)
replace_once(
    "common/font_safety.sh",
    '''    if [ "$_lbg_active" = default ]; then
        rm -f "$_lbg_config/font-payload-boot.conf" "$_lbg_config/font-payload-manifest.conf" 2>/dev/null || true
        return 0
    fi
    case "$_lbg_state" in''',
    '''    if [ "$_lbg_active" = default ]; then
        rm -f "$_lbg_config/font-payload-boot.conf" "$_lbg_config/font-payload-manifest.conf" 2>/dev/null || true
        return 0
    fi
    _lbg_schema=$(luoshu_payload_schema_read)
    if [ "$_lbg_schema" != "$LUOSHU_PAYLOAD_SCHEMA_CURRENT" ]; then
        _luoshu_safety_log ERROR "字体负载架构过期：${_lbg_schema:-missing} != $LUOSHU_PAYLOAD_SCHEMA_CURRENT"
        luoshu_payload_quarantine
        return 1
    fi
    case "$_lbg_state" in''',
)

# Update migration keeps the old tree as rollback input, but never treats an old schema as current.
state = read("common/module_update_state.sh")
state = state.replace(
    "# 模块更新状态迁移：继承当前字体负载，只清理一次性任务与待重启状态。\n",
    f'''# 模块更新状态迁移：继承当前字体负载，并在引擎架构变化时自动重建。\n\nLUOSHU_PAYLOAD_SCHEMA_CURRENT="${{LUOSHU_PAYLOAD_SCHEMA_CURRENT:-{SCHEMA}}}"\nLUOSHU_UPDATE_ACTIVE=default\nLUOSHU_UPDATE_OLD_SCHEMA=''\nLUOSHU_UPDATE_REBUILD_REQUIRED=false\nLUOSHU_UPDATE_REBUILT=false\nLUOSHU_UPDATE_REBUILD_FAILED=false\n\nluoshu_update_payload_schema() {{\n    sed -n 's/^schema=//p' "$1/config/font-payload-schema.conf" 2>/dev/null | head -n1 | tr -d '\\r\\n'\n}}\n\nluoshu_update_config_value() {{\n    sed -n "s/^${{2}}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\\r\\n'\n}}\n\n''',
    1,
)
state = state.replace("app_install_manual|*.pid", "app_install_manual|font-payload-rebuild-pending.conf|*.pid", 1)
state = state.replace(
    '        "$__never__"',
    '        "$__never__"',
) if '$__never__' in state else state
state = state.replace(
    '        "$__not_present__"',
    '        "$__not_present__"',
) if '$__not_present__' in state else state
state = state.replace(
    '        "$(_unused_)"',
    '        "$(_unused_)"',
) if '$(_unused_)' in state else state
state = state.replace(
    '        "$_module/config/app_install_manual" \\
        "$_module/.font_switch.lock"',
    '        "$_module/config/app_install_manual" \\
        "$_module/config/font-payload-rebuild-pending.conf" \\
        "$_module/.font_switch.lock"',
    1,
)
state = state.replace(
    '''        cache/full-composite-v5 \\
        cache/auto-multiweight-mix/composites-v2 \\
        cache/auto-multiweight-mix/prepared-v2 \\
        cache/auto-multiweight-mix/source-meta-v1; do''',
    '''        cache/full-composite-v6 \\
        cache/auto-multiweight-mix/composites-v3 \\
        cache/auto-multiweight-mix/prepared-v3 \\
        cache/auto-multiweight-mix/source-meta-v1; do''',
    1,
)
state = state.replace(
    '''    _active=$(head -n1 "$_old/config/active_font.conf" 2>/dev/null | tr -d '\\r\\n')
    [ -n "$_active" ] || _active=default''',
    '''    _active=$(head -n1 "$_old/config/active_font.conf" 2>/dev/null | tr -d '\\r\\n')
    [ -n "$_active" ] || _active=default
    _old_schema=$(luoshu_update_payload_schema "$_old")
    LUOSHU_UPDATE_ACTIVE="$_active"
    LUOSHU_UPDATE_OLD_SCHEMA="$_old_schema"
    LUOSHU_UPDATE_REBUILD_REQUIRED=false
    [ "$_active" = default ] || [ "$_old_schema" = "$LUOSHU_PAYLOAD_SCHEMA_CURRENT" ] || LUOSHU_UPDATE_REBUILD_REQUIRED=true''',
    1,
)
state = state.replace(
    '''    luoshu_clear_update_volatile "$_new"
    chmod 0644 "$_new/config"/* 2>/dev/null || true''',
    '''    luoshu_clear_update_volatile "$_new"
    if [ "$LUOSHU_UPDATE_REBUILD_REQUIRED" = true ]; then
        {
            printf 'state=pending\\n'
            printf 'font=%s\\n' "$_active"
            printf 'oldSchema=%s\\n' "${_old_schema:-missing}"
            printf 'newSchema=%s\\n' "$LUOSHU_PAYLOAD_SCHEMA_CURRENT"
            printf 'time=%s\\n' "$(date +%s)"
        } > "$_new/config/font-payload-rebuild-pending.conf" 2>/dev/null || return 1
    fi
    chmod 0644 "$_new/config"/* 2>/dev/null || true''',
    1,
)
state += r'''

luoshu_update_task_failed() {
    _lut_module="$1"
    for _lut_task in axes_task.conf mix_task.conf; do
        _lut_state=$(luoshu_update_config_value "$_lut_module/config/$_lut_task" state)
        [ "$_lut_state" != failed ] || return 0
    done
    return 1
}

luoshu_wait_for_payload_schema() {
    _luw_module="$1"
    _luw_timeout="${2:-${LUOSHU_UPDATE_REBUILD_TIMEOUT:-900}}"
    case "$_luw_timeout" in ''|*[!0-9]*) _luw_timeout=900 ;; esac
    _luw_elapsed=0
    while [ "$_luw_elapsed" -le "$_luw_timeout" ]; do
        _luw_schema=$(luoshu_update_payload_schema "$_luw_module")
        [ "$_luw_schema" != "$LUOSHU_PAYLOAD_SCHEMA_CURRENT" ] || return 0
        luoshu_update_task_failed "$_luw_module" && return 1
        sleep 2
        _luw_elapsed=$((_luw_elapsed + 2))
    done
    return 1
}

luoshu_rebuild_preserved_payload() {
    _lur_module="$1"
    _lur_active="${LUOSHU_UPDATE_ACTIVE:-default}"
    [ -n "$_lur_active" ] || _lur_active=$(head -n1 "$_lur_module/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_lur_active" ] || _lur_active=default
    LUOSHU_UPDATE_REBUILT=false
    LUOSHU_UPDATE_REBUILD_FAILED=false
    rm -f "$_lur_module/config/text_reboot_required.conf" "$_lur_module/.font_switch.lock" \
          "$_lur_module/config/axes_task.conf" "$_lur_module/config/mix_task.conf" \
          "$_lur_module/config/font-payload-schema.conf" 2>/dev/null || true

    if [ "$_lur_active" = default ]; then
        mkdir -p "$_lur_module/config" 2>/dev/null || return 1
        {
            printf 'schema=%s\n' "$LUOSHU_PAYLOAD_SCHEMA_CURRENT"
            printf 'font=default\n'
            printf 'time=%s\n' "$(date +%s)"
        } > "$_lur_module/config/font-payload-schema.conf" 2>/dev/null || return 1
    elif [ "$_lur_active" = mix ]; then
        _lur_conf="$_lur_module/config/axes_mix.conf"
        [ -s "$_lur_conf" ] || _lur_conf="$_lur_module/config/font_mix.conf"
        _lur_cjk=$(luoshu_update_config_value "$_lur_conf" cjk)
        _lur_latin=$(luoshu_update_config_value "$_lur_conf" latin)
        _lur_digit=$(luoshu_update_config_value "$_lur_conf" digit)
        _lur_cjk_axes=$(luoshu_update_config_value "$_lur_conf" cjkAxes)
        _lur_latin_axes=$(luoshu_update_config_value "$_lur_conf" latinAxes)
        _lur_digit_axes=$(luoshu_update_config_value "$_lur_conf" digitAxes)
        [ -n "$_lur_cjk_axes" ] || _lur_cjk_axes="wght=$(luoshu_update_config_value "$_lur_conf" cjkWeight)"
        [ -n "$_lur_latin_axes" ] || _lur_latin_axes="wght=$(luoshu_update_config_value "$_lur_conf" latinWeight)"
        [ -n "$_lur_digit_axes" ] || _lur_digit_axes="wght=$(luoshu_update_config_value "$_lur_conf" digitWeight)"
        case "$_lur_cjk_axes" in wght=) _lur_cjk_axes=wght=400 ;; esac
        case "$_lur_latin_axes" in wght=) _lur_latin_axes=wght=400 ;; esac
        case "$_lur_digit_axes" in wght=) _lur_digit_axes=wght=400 ;; esac
        _lur_cjk_mode=$(luoshu_update_config_value "$_lur_conf" cjkMode); [ -n "$_lur_cjk_mode" ] || _lur_cjk_mode=infer
        _lur_latin_mode=$(luoshu_update_config_value "$_lur_conf" latinMode); [ -n "$_lur_latin_mode" ] || _lur_latin_mode=infer
        _lur_digit_mode=$(luoshu_update_config_value "$_lur_conf" digitMode); [ -n "$_lur_digit_mode" ] || _lur_digit_mode=infer
        _lur_result=$(MODDIR="$_lur_module" sh "$_lur_module/common/font_mix_controller.sh" start \
            "$_lur_cjk" "$_lur_latin" "$_lur_digit" \
            "$_lur_cjk_axes" "$_lur_latin_axes" "$_lur_digit_axes" \
            "$_lur_cjk_mode" "$_lur_latin_mode" "$_lur_digit_mode" 2>&1)
        printf '%s\n' "$_lur_result" >> "$_lur_module/logs/fontswitch.log" 2>/dev/null || true
        printf '%s\n' "$_lur_result" | grep -q '"status":"ok"' || { LUOSHU_UPDATE_REBUILD_FAILED=true; return 1; }
        luoshu_wait_for_payload_schema "$_lur_module" || { LUOSHU_UPDATE_REBUILD_FAILED=true; return 1; }
    else
        _lur_result=$(MODDIR="$_lur_module" sh "$_lur_module/common/font_manager.sh" action switch "$_lur_active" 2>&1)
        printf '%s\n' "$_lur_result" >> "$_lur_module/logs/fontswitch.log" 2>/dev/null || true
        printf '%s\n' "$_lur_result" | grep -q '"status":"ok"' || { LUOSHU_UPDATE_REBUILD_FAILED=true; return 1; }
        luoshu_wait_for_payload_schema "$_lur_module" 30 || { LUOSHU_UPDATE_REBUILD_FAILED=true; return 1; }
    fi

    rm -f "$_lur_module/config/font-payload-rebuild-pending.conf" 2>/dev/null || true
    LUOSHU_UPDATE_REBUILT=true
    return 0
}
'''
write("common/module_update_state.sh", state)

# Cache identities include the new metrics/baseline algorithm.
for path in (
    "common/multiweight_mix_task.sh",
    "scripts/auto_multiweight_engine_test.sh",
    "scripts/check.sh",
    "scripts/stability_test.sh",
):
    text = read(path)
    text = text.replace("composites-v2", "composites-v3")
    text = text.replace("prepared-v2", "prepared-v3")
    text = text.replace("instance-v2", "instance-v3")
    text = text.replace("static-v1", "static-v2")
    text = text.replace("auto-multiweight-v2", "auto-multiweight-v3")
    write(path, text)

# Installer rebuilds stale payloads before it claims one-reboot inheritance.
customize = read("customize.sh")
customize = customize.replace(
    'ui_print "• Emoji、图标和等宽字体默认保持系统原样"',
    'ui_print "• Emoji、图标、衬线与斜体保持系统原样"',
    1,
)
customize = customize.replace(
    '''touch "$MODPATH/magic" 2>/dev/null || true

ui_print "✓ 模块文件已部署"''',
    '''touch "$MODPATH/magic" 2>/dev/null || true

if [ "$UPDATE_PRESERVED" = true ] && [ "${LUOSHU_UPDATE_REBUILD_REQUIRED:-false}" = true ]; then
    ui_print "• 检测到旧版字体负载，正在使用新基线引擎重新生成"
    if type luoshu_rebuild_preserved_payload >/dev/null 2>&1 && luoshu_rebuild_preserved_payload "$MODPATH"; then
        ui_print "✓ 当前字体已按新架构重新生成"
    else
        LUOSHU_UPDATE_REBUILD_FAILED=true
        ui_print "✗ 当前字体自动重建失败；重启时会安全恢复系统默认字体"
        ui_print "• 重启后请在洛书 App 中重新应用一次字体"
    fi
fi

ui_print "✓ 模块文件已部署"''',
    1,
)
customize = customize.replace(
    '''if [ "$UPDATE_PRESERVED" = true ]; then
    _preserved_font=$(head -n1 "$MODPATH/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_preserved_font" ] || _preserved_font=default
    ui_print "✓ 已继承当前字体：$_preserved_font"
    ui_print "✓ 更新后只需重启一次，无需重新应用字体"
else''',
    '''if [ "$UPDATE_PRESERVED" = true ]; then
    _preserved_font=$(head -n1 "$MODPATH/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_preserved_font" ] || _preserved_font=default
    ui_print "✓ 已继承当前字体：$_preserved_font"
    if [ "${LUOSHU_UPDATE_REBUILD_FAILED:-false}" != true ]; then
        ui_print "✓ 更新后只需重启一次，无需重新应用字体"
    fi
else''',
    1,
)
customize = customize.replace(
    '''if [ "$UPDATE_PRESERVED" = true ]; then
    ui_print "请完整重启一次，新版本会继续使用当前字体。"
else''',
    '''if [ "$UPDATE_PRESERVED" = true ] && [ "${LUOSHU_UPDATE_REBUILD_FAILED:-false}" != true ]; then
    ui_print "请完整重启一次，新版基线字体会直接生效。"
elif [ "$UPDATE_PRESERVED" = true ]; then
    ui_print "请重启后在洛书 App 中重新应用字体。"
else''',
    1,
)
write("customize.sh", customize)

print("payload schema migration complete")
