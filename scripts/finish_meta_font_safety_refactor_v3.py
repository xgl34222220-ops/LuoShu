#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"missing anchor in {path}: {old[:120]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_font_manager() -> None:
    replace_once(
        "common/font_manager.sh",
        """    printf '%s\\n' "$_font_id" > "$ACTIVE_FONT_CONF"
    chmod 0644 "$ACTIVE_FONT_CONF" "$SYSTEM_FONTS_DIR"/* 2>/dev/null || true
""",
        """    if ! type luoshu_payload_validate_current >/dev/null 2>&1 || ! luoshu_payload_validate_current "$_font_id"; then
        echo '错误：字体负载覆盖校验失败，已恢复上一个字体' >&2
        return 6
    fi
    printf '%s\\n' "$_font_id" > "$ACTIVE_FONT_CONF" || {
        echo '错误：无法保存当前字体状态' >&2
        return 7
    }
    chmod 0644 "$ACTIVE_FONT_CONF" "$SYSTEM_FONTS_DIR"/* 2>/dev/null || true
    if type luoshu_sync_mount_payload >/dev/null 2>&1 && ! luoshu_sync_mount_payload; then
        echo '错误：元模块真实挂载目录同步失败，已恢复上一个字体' >&2
        return 7
    fi
    if ! luoshu_payload_transaction_commit "$_font_id"; then
        echo '错误：无法提交字体负载事务，已恢复上一个字体' >&2
        return 7
    fi
""",
    )


def patch_font_mix() -> None:
    replace_once(
        "common/font_mix.sh",
        """cleanup_mix_process() {
    payload_stage_abort
    payload_stage_rollback
    rm -f "$LOCK_FILE" 2>/dev/null || true
}
""",
        """cleanup_mix_process() {
    payload_stage_abort
    payload_stage_rollback
    type luoshu_payload_transaction_abort >/dev/null 2>&1 && luoshu_payload_transaction_abort
    rm -f "$LOCK_FILE" 2>/dev/null || true
}
""",
    )
    replace_once(
        "common/font_mix.sh",
        """    echo $$ > "$LOCK_FILE"
    trap cleanup_mix_process EXIT INT TERM

    _cjk_src=$(find_family_file "$_cjk")
""",
        """    echo $$ > "$LOCK_FILE"
    trap cleanup_mix_process EXIT INT TERM
    if ! type luoshu_payload_transaction_begin >/dev/null 2>&1 || ! luoshu_payload_transaction_begin; then
        set_mix_error '无法创建字体负载安全快照'
        return 4
    fi

    _cjk_src=$(find_family_file "$_cjk")
""",
    )
    replace_once(
        "common/font_mix.sh",
        """    type luoshu_sync_mount_payload >/dev/null 2>&1 && luoshu_sync_mount_payload 2>/dev/null || true
    rm -f "$LOCK_FILE" 2>/dev/null || true
""",
        """    if ! type luoshu_payload_validate_current >/dev/null 2>&1 || ! luoshu_payload_validate_current mix; then
        set_mix_error '复合字体负载覆盖校验失败，已恢复旧字体'
        return 7
    fi
    if type luoshu_sync_mount_payload >/dev/null 2>&1 && ! luoshu_sync_mount_payload; then
        set_mix_error '元模块真实挂载目录同步失败，已恢复旧字体'
        return 7
    fi
    if ! luoshu_payload_transaction_commit mix; then
        set_mix_error '无法提交复合字体负载事务，已恢复旧字体'
        return 7
    fi
    rm -f "$LOCK_FILE" 2>/dev/null || true
""",
    )


def patch_tests() -> None:
    replace_once("service.sh", '"$WAITED" -lt 90', '"$WAITED" -lt 600')

    replace_once(
        "scripts/font_config_runtime_test.sh",
        'cp -f "$ROOT/common/font_config_partitions.sh" "$MOD/common/font_config_partitions.sh"\n',
        'cp -f "$ROOT/common/font_config_partitions.sh" "$MOD/common/font_config_partitions.sh"\n'
        'cp -f "$ROOT/common/font_config_targets.py" "$MOD/common/font_config_targets.py"\n'
        'cp -f "$ROOT/common/font_safety.sh" "$MOD/common/font_safety.sh"\n',
    )
    replace_once(
        "scripts/font_config_runtime_test.sh",
        '# Regeneration repairs every partition alias from the validated system weight set.\nfont_config_generate DemoFamily\n',
        '# Regeneration repairs every partition alias from the validated system weight set.\n'
        'mkdir -p "$MOD/system/fonts"\n'
        'for weight in 100 200 300 400 500 600 700 800 900; do\n'
        '    dd if=/dev/zero of="$MOD/system/fonts/LuoShu-${weight}.ttf" bs=2048 count=1 2>/dev/null\n'
        'done\n'
        'font_config_generate DemoFamily\n',
    )
    replace_once(
        "scripts/font_safety_test.sh",
        """font_config_mark_boot_success
[ ! -e "$MODDIR/config/font-payload-boot.conf" ]
[ -s "$MODDIR/config/font-last-boot-success.conf" ]
""",
        """font_config_mark_boot_success
[ "$(sed -n 's/^state=//p' "$MODDIR/config/font-payload-boot.conf")" = confirmed ]
font_config_boot_guard Demo
[ "$(sed -n 's/^state=//p' "$MODDIR/config/font-payload-boot.conf")" = confirmed ]
[ -s "$MODDIR/config/font-last-boot-success.conf" ]
""",
    )

    no_hook = Path("scripts/no_hook_bootstrap_test.sh")
    no_hook.write_text(
        no_hook.read_text(encoding="utf-8").replace(
            "system system_ext product my_product vendor odm oem",
            "system system_ext product vendor odm oem my_product",
        ),
        encoding="utf-8",
    )


def patch_ci() -> None:
    workflow = Path(".github/workflows/no-hook-font-engine.yml")
    text = workflow.read_text(encoding="utf-8")
    text = text.replace(
        '      - common/font_config_overlay.py\n',
        '      - common/font_config_overlay.py\n      - common/font_config_targets.py\n      - common/font_safety.sh\n',
        1,
    )
    text = text.replace(
        '      - scripts/font_config_overlay_test.py\n',
        '      - scripts/font_config_overlay_test.py\n      - scripts/font_config_targets_test.py\n      - scripts/font_safety_test.sh\n      - scripts/meta_module_sync_test.sh\n',
        1,
    )
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
    text = text.replace(
        "          grep -q 'font_config_boot_guard' post-fs-data.sh\n",
        "          grep -q 'font_config_boot_guard' post-fs-data.sh\n"
        "          grep -q 'font_config_mark_boot_success' service.sh\n"
        "          grep -q 'luoshu_payload_transaction_begin' common/font_manager.sh\n"
        "          grep -q 'luoshu_payload_transaction_begin' common/font_mix.sh\n"
        "          grep -q 'font_config_targets.py' common/font_safety.sh\n",
        1,
    )
    workflow.write_text(text, encoding="utf-8")


def main() -> int:
    patch_font_manager()
    patch_font_mix()
    patch_tests()
    patch_ci()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
