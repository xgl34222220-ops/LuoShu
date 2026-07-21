#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path


def must_replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if text.count(old) < count:
        raise SystemExit(f"missing patch anchor in {path}: {old!r}")
    file.write_text(text.replace(old, new, count), encoding="utf-8")


def patch_runtime() -> None:
    path = Path("common/font_config_runtime.sh")
    text = path.read_text(encoding="utf-8")
    for old, new in (
        ("\nfont_config_disable() {\n", "\n_luoshu_font_config_disable_base() {\n"),
        ("\nfont_config_generate() {\n", "\n_luoshu_font_config_generate_base() {\n"),
        ("\nfont_config_boot_guard() {\n", "\n_luoshu_font_config_boot_guard_base() {\n"),
    ):
        if old not in text:
            raise SystemExit(f"missing runtime function anchor: {old!r}")
        text = text.replace(old, new, 1)
    if "common/font_safety.sh" not in text:
        text = text.rstrip() + """

# Load the fail-open transaction and boot-confirmation layer for every runtime caller.
_luoshu_font_safety="$(_luoshu_font_config_module)/common/font_safety.sh"
[ -f "$_luoshu_font_safety" ] && . "$_luoshu_font_safety"
"""
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def patch_overlay() -> None:
    path = Path("common/font_config_overlay.py")
    text = path.read_text(encoding="utf-8")
    constants = '''SAFE_EXACT_FAMILIES = {
    "sans", "sans-serif", "sans-serif-condensed", "default", "default-sans",
    "system-ui", "ui-sans-serif", "roboto", "roboto-flex", "roboto-static",
    "google-sans", "google-sans-text", "google-sans-flex", "source-sans",
    "source-sans-pro", "noto-sans", "noto-sans-cjk", "miui", "mipro",
    "misans", "mi-sans", "sysfont", "sys-font", "sys-sans", "sys-sans-en",
    "op-sans", "op-sans-en", "oplus-sans", "oppo-sans", "opposans",
    "coloros-sans", "oneplus-sans", "realme-sans", "vivo-sans",
    "origin-sans", "honor-sans", "harmonyos-sans",
}
SAFE_PREFIXES = (
    "sans-serif-", "roboto-", "google-sans-", "source-sans-", "noto-sans-",
    "miui-", "mipro-", "misans-", "mi-sans-", "sysfont-", "sys-font-",
    "sys-sans-", "op-sans-", "oplus-sans-", "oppo-sans-", "opposans-",
    "coloros-sans-", "oneplus-sans-", "realme-sans-", "vivo-sans-",
    "origin-sans-", "honor-sans-", "harmonyos-sans-",
)
PROTECTED_FAMILY_TOKENS = (
    "emoji", "symbol", "icon", "material", "dingbat", "mono", "serif",
    "clock", "mitype", "math", "music", "braille", "barcode", "qrcode",
    "fallback", "legacy",
)
PROTECTED_FILE_TOKENS = PROTECTED_FAMILY_TOKENS
FONT_SUFFIXES = (".ttf", ".otf", ".ttc")
WEIGHTS = (100, 200, 300, 400, 500, 600, 700, 800, 900)
MIN_FONT_BYTES = 1024'''
    text, changed = re.subn(
        r"SAFE_EXACT_FAMILIES = \{.*?MIN_FONT_BYTES = 1024",
        constants,
        text,
        count=1,
        flags=re.S,
    )
    if changed != 1:
        raise SystemExit("failed to replace overlay family policy")
    helpers = '''def is_safe_family(name: str) -> bool:
    normalized = normalize_family(name)
    if not normalized:
        return False
    safe = normalized in SAFE_EXACT_FAMILIES or normalized.startswith(SAFE_PREFIXES)
    return safe and not any(token in normalized for token in PROTECTED_FAMILY_TOKENS)


def is_locale_specific_family(family: ET.Element) -> bool:
    return any(
        family.attrib.get(key)
        for key in ("lang", "variant", "fallbackFor", "fallbackfor")
    )


def is_protected_file(value: str) -> bool:
    filename = os.path.basename(value.strip()).lower()
    return not filename.endswith(FONT_SUFFIXES) or any(
        token in filename for token in PROTECTED_FILE_TOKENS
    )


def nearest_weight'''
    text, changed = re.subn(
        r"def is_safe_family\(name: str\) -> bool:.*?def nearest_weight",
        helpers,
        text,
        count=1,
        flags=re.S,
    )
    if changed != 1:
        raise SystemExit("failed to replace overlay helper policy")
    old = '''        family_name = family.attrib.get("name", "")
        if not is_safe_family(family_name):
            continue
'''
    new = '''        family_name = family.attrib.get("name", "")
        if is_locale_specific_family(family) or not is_safe_family(family_name):
            continue
'''
    if old not in text:
        raise SystemExit("missing overlay family loop anchor")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_boot_scripts() -> None:
    must_replace(
        "post-fs-data.sh",
        '[ -f "$MODDIR/common/font_config_partitions.sh" ] && . "$MODDIR/common/font_config_partitions.sh"\n',
        '[ -f "$MODDIR/common/font_config_partitions.sh" ] && . "$MODDIR/common/font_config_partitions.sh"\n'
        '[ -f "$MODDIR/common/mount_compat.sh" ] && . "$MODDIR/common/mount_compat.sh"\n',
    )
    must_replace(
        "post-fs-data.sh",
        '    "$MODDIR/common/font_name_normalize.py" 2>/dev/null || true\n',
        '    "$MODDIR/common/font_name_normalize.py" "$MODDIR/common/font_config_targets.py" 2>/dev/null || true\n',
    )
    must_replace(
        "post-fs-data.sh",
        'for _partition in system product system_ext my_product vendor odm; do\n',
        'for _partition in system system_ext product vendor odm oem my_product my_engineering my_company my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust; do\n',
    )
    must_replace(
        "post-fs-data.sh",
        '[ -f "$MODDIR/common/module_status.sh" ] && MODDIR="$MODDIR" sh "$MODDIR/common/module_status.sh" "$ACTIVE_TEXT" >/dev/null 2>&1 || true\n',
        '',
    )
    must_replace(
        "service.sh",
        '[ -n "$MODULE_VERSION" ] || MODULE_VERSION="unknown"\n',
        '[ -n "$MODULE_VERSION" ] || MODULE_VERSION="unknown"\n'
        'MODULE_DIR="$MODDIR"\n'
        '[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"\n'
        '[ -f "$MODDIR/common/font_config_runtime.sh" ] && . "$MODDIR/common/font_config_runtime.sh"\n'
        '[ -f "$MODDIR/common/font_config_partitions.sh" ] && . "$MODDIR/common/font_config_partitions.sh"\n'
        '[ -f "$MODDIR/common/mount_compat.sh" ] && . "$MODDIR/common/mount_compat.sh"\n',
    )
    must_replace(
        "service.sh",
        '    done\n\n    LOG_FILE="$MODDIR/logs/fontswitch.log"\n',
        '    done\n\n'
        '    # A timeout is not proof that Android completed boot; never confirm in that case.\n'
        '    [ "$(getprop sys.boot_completed 2>/dev/null)" = "1" ] || exit 0\n\n'
        '    LOG_FILE="$MODDIR/logs/fontswitch.log"\n',
    )
    must_replace(
        "service.sh",
        '    log_service "INFO" "服务脚本开始执行 ($MODULE_VERSION)"\n',
        '    log_service "INFO" "服务脚本开始执行 ($MODULE_VERSION)"\n'
        '    type font_config_mark_boot_success >/dev/null 2>&1 && font_config_mark_boot_success\n',
    )


def patch_font_manager() -> None:
    path = "common/font_manager.sh"
    must_replace(
        path,
        '[ -f "$MODULE_DIR/common/font_config_weights.sh" ] && . "$MODULE_DIR/common/font_config_weights.sh"\n',
        '[ -f "$MODULE_DIR/common/font_config_weights.sh" ] && . "$MODULE_DIR/common/font_config_weights.sh"\n'
        '[ -f "$MODULE_DIR/common/mount_compat.sh" ] && . "$MODULE_DIR/common/mount_compat.sh"\n',
    )
    must_replace(
        path,
        "    trap 'rm -f \"$MODULE_DIR/.font_switch.lock\" 2>/dev/null' EXIT HUP INT TERM\n",
        "    trap 'type luoshu_payload_transaction_abort >/dev/null 2>&1 && luoshu_payload_transaction_abort; rm -f \"$MODULE_DIR/.font_switch.lock\" 2>/dev/null' EXIT HUP INT TERM\n",
    )
    must_replace(
        path,
        '    clear_managed_text_fonts\n',
        '    if ! type luoshu_payload_transaction_begin >/dev/null 2>&1 || ! luoshu_payload_transaction_begin; then\n'
        "        echo '错误：无法创建字体负载安全快照' >&2\n"
        '        return 5\n'
        '    fi\n'
        '    clear_managed_text_fonts\n',
    )
    must_replace(
        path,
        '''    printf '%s\n' "$_font_id" > "$ACTIVE_FONT_CONF"
    chmod 0644 "$ACTIVE_FONT_CONF" "$SYSTEM_FONTS_DIR"/* 2>/dev/null || true
''',
        '''    if ! type luoshu_payload_validate_current >/dev/null 2>&1 || ! luoshu_payload_validate_current "$_font_id"; then
        echo '错误：字体负载覆盖校验失败，已恢复上一个字体' >&2
        return 6
    fi
    if type luoshu_sync_mount_payload >/dev/null 2>&1 && ! luoshu_sync_mount_payload; then
        echo '错误：元模块真实挂载目录同步失败，已恢复上一个字体' >&2
        return 7
    fi
    printf '%s\n' "$_font_id" > "$ACTIVE_FONT_CONF" || {
        echo '错误：无法保存当前字体状态' >&2
        return 7
    }
    chmod 0644 "$ACTIVE_FONT_CONF" "$SYSTEM_FONTS_DIR"/* 2>/dev/null || true
    if ! luoshu_payload_transaction_commit "$_font_id"; then
        echo '错误：无法提交字体负载事务，已恢复上一个字体' >&2
        return 7
    fi
''',
    )


def patch_font_mix() -> None:
    path = "common/font_mix.sh"
    must_replace(
        path,
        '''cleanup_mix_process() {
    payload_stage_abort
    payload_stage_rollback
    rm -f "$LOCK_FILE" 2>/dev/null || true
}
''',
        '''cleanup_mix_process() {
    payload_stage_abort
    payload_stage_rollback
    type luoshu_payload_transaction_abort >/dev/null 2>&1 && luoshu_payload_transaction_abort
    rm -f "$LOCK_FILE" 2>/dev/null || true
}
''',
    )
    must_replace(
        path,
        '    trap cleanup_mix_process EXIT INT TERM\n\n    _cjk_src=',
        '    trap cleanup_mix_process EXIT INT TERM\n'
        "    if ! type luoshu_payload_transaction_begin >/dev/null 2>&1 || ! luoshu_payload_transaction_begin; then set_mix_error '无法创建字体负载安全快照'; return 4; fi\n\n"
        '    _cjk_src=',
    )
    must_replace(
        path,
        '    type luoshu_sync_mount_payload >/dev/null 2>&1 && luoshu_sync_mount_payload 2>/dev/null || true\n'
        '    rm -f "$LOCK_FILE" 2>/dev/null || true\n',
        "    if ! type luoshu_payload_validate_current >/dev/null 2>&1 || ! luoshu_payload_validate_current mix; then set_mix_error '复合字体负载覆盖校验失败，已恢复旧字体'; return 7; fi\n"
        "    if type luoshu_sync_mount_payload >/dev/null 2>&1 && ! luoshu_sync_mount_payload; then set_mix_error '元模块真实挂载目录同步失败，已恢复旧字体'; return 7; fi\n"
        "    if ! luoshu_payload_transaction_commit mix; then set_mix_error '无法提交复合字体负载事务，已恢复旧字体'; return 7; fi\n"
        '    rm -f "$LOCK_FILE" 2>/dev/null || true\n',
    )


def patch_tests_and_ci() -> None:
    path = "scripts/font_config_runtime_test.sh"
    must_replace(
        path,
        'cp -f "$ROOT/common/font_config_partitions.sh" "$MOD/common/font_config_partitions.sh"\n',
        'cp -f "$ROOT/common/font_config_partitions.sh" "$MOD/common/font_config_partitions.sh"\n'
        'cp -f "$ROOT/common/font_config_targets.py" "$MOD/common/font_config_targets.py"\n'
        'cp -f "$ROOT/common/font_safety.sh" "$MOD/common/font_safety.sh"\n',
    )
    must_replace(
        path,
        '# Regeneration repairs every partition alias from the validated system weight set.\nfont_config_generate DemoFamily\n',
        '# Regeneration repairs every partition alias from the validated system weight set.\n'
        'mkdir -p "$MOD/system/fonts"\n'
        'for weight in 100 200 300 400 500 600 700 800 900; do\n'
        '    dd if=/dev/zero of="$MOD/system/fonts/LuoShu-${weight}.ttf" bs=2048 count=1 2>/dev/null\n'
        'done\n'
        'font_config_generate DemoFamily\n',
    )

    workflow = Path(".github/workflows/no-hook-font-engine.yml")
    text = workflow.read_text(encoding="utf-8")
    if "common/font_config_targets.py" not in text:
        text = text.replace(
            '      - common/font_config_overlay.py\n',
            '      - common/font_config_overlay.py\n      - common/font_config_targets.py\n      - common/font_safety.sh\n',
            1,
        )
    if "scripts/font_config_targets_test.py" not in text:
        text = text.replace(
            '      - scripts/font_config_overlay_test.py\n',
            '      - scripts/font_config_overlay_test.py\n      - scripts/font_config_targets_test.py\n      - scripts/font_safety_test.sh\n      - scripts/meta_module_sync_test.sh\n',
            1,
        )
    if "Run dynamic target discovery tests" not in text:
        text = text.replace(
            '      - name: Run static font identity tests\n',
            '      - name: Run dynamic target discovery tests\n'
            '        run: python3 scripts/font_config_targets_test.py\n'
            '      - name: Run payload transaction and boot guard tests\n'
            '        run: sh -x scripts/font_safety_test.sh\n'
            '      - name: Run meta-module synchronization tests\n'
            '        run: sh -x scripts/meta_module_sync_test.sh\n'
            '      - name: Run static font identity tests\n',
            1,
        )
    if "font_config_mark_boot_success" not in text:
        text = text.replace(
            "          grep -q 'font_config_boot_guard' post-fs-data.sh\n",
            "          grep -q 'font_config_boot_guard' post-fs-data.sh\n"
            "          grep -q 'font_config_mark_boot_success' service.sh\n"
            "          grep -q 'luoshu_payload_transaction_begin' common/font_manager.sh\n"
            "          grep -q 'font_config_targets.py' common/font_safety.sh\n",
            1,
        )
    workflow.write_text(text, encoding="utf-8")


def main() -> int:
    patch_runtime()
    patch_overlay()
    patch_boot_scripts()
    patch_font_manager()
    patch_font_mix()
    patch_tests_and_ci()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
