#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"missing anchor in {path}: {old[:100]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_pattern(path: str, pattern: str, replacement: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    match = re.search(pattern, text, flags=re.S)
    if match is None:
        raise SystemExit(f"missing pattern in {path}: {pattern[:100]!r}")
    file.write_text(text[: match.start()] + replacement + text[match.end() :], encoding="utf-8")


def patch_runtime() -> None:
    path = Path("common/font_config_runtime.sh")
    text = path.read_text(encoding="utf-8")
    old = '''        [ -s "$_lfc_backup" ] && _luoshu_font_config_validate "$_lfc_backup" && continue
        # Never snapshot our own overlay as the device source of truth.
        grep -q 'LuoShu-[1-9][0-9][0-9]\\.ttf' "$_lfc_real" 2>/dev/null && continue
'''
    new = '''        _lfc_backup_valid=0
        if [ -s "$_lfc_backup" ] && _luoshu_font_config_validate "$_lfc_backup"; then
            _lfc_backup_valid=1
            command -v cmp >/dev/null 2>&1 && cmp -s "$_lfc_real" "$_lfc_backup" 2>/dev/null && continue
        fi
        # Never snapshot our own upper-layer document. Keep a valid previous source when mounted.
        if grep -q 'LuoShu-[1-9][0-9][0-9]\\.ttf' "$_lfc_real" 2>/dev/null; then
            continue
        fi
'''
    if old not in text:
        raise SystemExit("missing source refresh anchor")
    text = text.replace(old, new, 1)
    start = text.index("_luoshu_font_config_generate_base() {")
    end = text.index("\n_luoshu_font_config_boot_guard_base() {", start)
    body = text[start:end].replace("font_config_disable", "_luoshu_font_config_disable_base")
    path.write_text(text[:start] + body + text[end:], encoding="utf-8")


def patch_safety() -> None:
    replace_once(
        "common/font_safety.sh",
        '''_luoshu_checksum() {
    _lsc_file="$1"
    if command -v cksum >/dev/null 2>&1; then
        cksum "$_lsc_file" 2>/dev/null | awk '{print $1 "|" $2}'
    elif command -v toybox >/dev/null 2>&1; then
        toybox cksum "$_lsc_file" 2>/dev/null | awk '{print $1 "|" $2}'
    else
        wc -c < "$_lsc_file" 2>/dev/null | awk '{print "0|" $1}'
    fi
}
''',
        '''_luoshu_checksum() {
    _lsc_file="$1"
    if command -v cksum >/dev/null 2>&1; then
        cksum "$_lsc_file" 2>/dev/null | awk '{print $1 "|" $2}'
    elif command -v toybox >/dev/null 2>&1; then
        toybox cksum "$_lsc_file" 2>/dev/null | awk '{print $1 "|" $2}'
    else
        wc -c < "$_lsc_file" 2>/dev/null | awk '{print "0|" $1}'
    fi
}

_luoshu_filesize() {
    _lfs_file="$1"
    if command -v stat >/dev/null 2>&1; then
        stat -c '%s' "$_lfs_file" 2>/dev/null && return 0
    fi
    if command -v toybox >/dev/null 2>&1; then
        toybox stat -c '%s' "$_lfs_file" 2>/dev/null && return 0
    fi
    wc -c < "$_lfs_file" 2>/dev/null | tr -d '[:space:]'
}
''',
    )

    replace_pattern(
        "common/font_safety.sh",
        r"luoshu_payload_validate_manifest\(\) \{.*?\n\}\n\nluoshu_payload_arm\(\) \{",
        '''luoshu_payload_validate_manifest_full() {
    _lpvm_module="$(_luoshu_safety_module)"
    _lpvm_manifest="$(_luoshu_safety_config)/font-payload-manifest.conf"
    [ -s "$_lpvm_manifest" ] || return 1
    _lpvm_seen=0
    while IFS='|' read -r _lpvm_rel _lpvm_sum _lpvm_size; do
        case "$_lpvm_rel" in */fonts/*|*/etc/*.xml) ;; *) return 1 ;; esac
        _lpvm_file="$_lpvm_module/$_lpvm_rel"
        [ -f "$_lpvm_file" ] || return 1
        _lpvm_now=$(_luoshu_checksum "$_lpvm_file")
        [ "$_lpvm_now" = "$_lpvm_sum|$_lpvm_size" ] || return 1
        _lpvm_seen=$((_lpvm_seen + 1))
    done < "$_lpvm_manifest"
    [ "$_lpvm_seen" -gt 0 ]
}

# Early boot only checks font size metadata and tiny XML checksums. Full file checksums are generated
# during the App-side transaction, never before Zygote.
luoshu_payload_validate_manifest_fast() {
    _lpvf_module="$(_luoshu_safety_module)"
    _lpvf_manifest="$(_luoshu_safety_config)/font-payload-manifest.conf"
    [ -s "$_lpvf_manifest" ] || return 1
    _lpvf_seen=0
    while IFS='|' read -r _lpvf_rel _lpvf_sum _lpvf_size; do
        case "$_lpvf_size" in ''|*[!0-9]*) return 1 ;; esac
        _lpvf_file="$_lpvf_module/$_lpvf_rel"
        [ -f "$_lpvf_file" ] || return 1
        case "$_lpvf_rel" in
            */fonts/*)
                _lpvf_now=$(_luoshu_filesize "$_lpvf_file")
                case "$_lpvf_now" in ''|*[!0-9]*) return 1 ;; esac
                [ "$_lpvf_now" -ge 1024 ] && [ "$_lpvf_now" = "$_lpvf_size" ] || return 1
                ;;
            */etc/*.xml)
                _lpvf_now=$(_luoshu_checksum "$_lpvf_file")
                [ "$_lpvf_now" = "$_lpvf_sum|$_lpvf_size" ] || return 1
                ;;
            *) return 1 ;;
        esac
        _lpvf_seen=$((_lpvf_seen + 1))
    done < "$_lpvf_manifest"
    [ "$_lpvf_seen" -gt 0 ]
}

luoshu_payload_arm() {''',
    )

    replace_once(
        "common/font_safety.sh",
        '''                cp -af "$_lpt_src" "$LUOSHU_PAYLOAD_TXN/tree/$_lpt_rel" 2>/dev/null || {
                    mkdir -p "$LUOSHU_PAYLOAD_TXN/tree/$_lpt_rel" 2>/dev/null || return 1
                    cp -rfp "$_lpt_src/." "$LUOSHU_PAYLOAD_TXN/tree/$_lpt_rel/" 2>/dev/null || return 1
                }
''',
        '''                cp -al "$_lpt_src" "$LUOSHU_PAYLOAD_TXN/tree/$_lpt_rel" 2>/dev/null ||
                cp -af "$_lpt_src" "$LUOSHU_PAYLOAD_TXN/tree/$_lpt_rel" 2>/dev/null || {
                    mkdir -p "$LUOSHU_PAYLOAD_TXN/tree/$_lpt_rel" 2>/dev/null || return 1
                    cp -rfp "$_lpt_src/." "$LUOSHU_PAYLOAD_TXN/tree/$_lpt_rel/" 2>/dev/null || return 1
                }
''',
    )

    replace_once(
        "common/font_safety.sh",
        '''luoshu_payload_transaction_abort() {
    [ -z "$LUOSHU_PAYLOAD_TXN" ] || luoshu_payload_transaction_rollback
}
''',
        '''luoshu_payload_transaction_abort() {
    _lpta_had=0
    if [ -n "$LUOSHU_PAYLOAD_TXN" ]; then
        _lpta_had=1
        luoshu_payload_transaction_rollback
    fi
    if [ "$_lpta_had" -eq 1 ] && type luoshu_sync_mount_payload >/dev/null 2>&1; then
        luoshu_sync_mount_payload >/dev/null 2>&1 ||
            _luoshu_safety_log ERROR '本地旧字体已恢复，但元模块旧负载回写失败；开机守卫将撤销覆盖'
    fi
}
''',
    )

    replace_pattern(
        "common/font_safety.sh",
        r"font_config_boot_guard\(\) \{.*?\n\}\n\nfont_config_mark_boot_success\(\) \{.*?\n\}\s*$",
        '''font_config_boot_guard() {
    _lbg_active="${1:-default}"
    _lbg_config="$(_luoshu_safety_config)"
    _lbg_state=$(sed -n 's/^state=//p' "$_lbg_config/font-payload-boot.conf" 2>/dev/null | head -n1)
    if [ "$_lbg_active" = default ]; then
        rm -f "$_lbg_config/font-payload-boot.conf" "$_lbg_config/font-payload-manifest.conf" 2>/dev/null || true
        return 0
    fi
    case "$_lbg_state" in
        booting)
            luoshu_payload_quarantine
            return 1
            ;;
        prepared)
            luoshu_payload_validate_manifest_fast || { luoshu_payload_quarantine; return 1; }
            {
                printf 'state=booting\n'
                printf 'font=%s\n' "$_lbg_active"
                printf 'time=%s\n' "$(date +%s)"
            } > "$_lbg_config/font-payload-boot.conf.tmp.$$" 2>/dev/null || { luoshu_payload_quarantine; return 1; }
            mv -f "$_lbg_config/font-payload-boot.conf.tmp.$$" "$_lbg_config/font-payload-boot.conf" 2>/dev/null || { luoshu_payload_quarantine; return 1; }
            _luoshu_safety_log INFO '新字体负载轻量校验通过，等待 Android 完成开机确认'
            ;;
        confirmed)
            luoshu_payload_validate_manifest_fast || { luoshu_payload_quarantine; return 1; }
            ;;
        *)
            # An older engine has no trusted transaction manifest. Restore the ROM font once instead
            # of parsing or hashing large payloads before Zygote.
            luoshu_payload_quarantine
            return 1
            ;;
    esac
    return 0
}

font_config_mark_boot_success() {
    _lmbs_config="$(_luoshu_safety_config)"
    _lmbs_state=$(sed -n 's/^state=//p' "$_lmbs_config/font-payload-boot.conf" 2>/dev/null | head -n1)
    [ "$_lmbs_state" = booting ] || return 0
    _lmbs_font=$(sed -n 's/^font=//p' "$_lmbs_config/font-payload-boot.conf" 2>/dev/null | head -n1)
    {
        printf 'state=confirmed\n'
        printf 'font=%s\n' "${_lmbs_font:-unknown}"
        printf 'time=%s\n' "$(date +%s)"
    } > "$_lmbs_config/font-payload-boot.conf.tmp.$$" 2>/dev/null || return 1
    mv -f "$_lmbs_config/font-payload-boot.conf.tmp.$$" "$_lmbs_config/font-payload-boot.conf" 2>/dev/null || return 1
    rm -f "$_lmbs_config/font-boot-failures" 2>/dev/null || true
    printf 'time=%s\n' "$(date +%s)" > "$_lmbs_config/font-last-boot-success.conf" 2>/dev/null || true
    chmod 0644 "$_lmbs_config/font-payload-boot.conf" "$_lmbs_config/font-last-boot-success.conf" 2>/dev/null || true
    _luoshu_safety_log INFO 'Android 已完成开机，字体负载事务确认成功'
}
''',
    )


def patch_manager_and_mix() -> None:
    replace_once(
        "common/font_manager.sh",
        '''    printf '%s\n' "$_font_id" > "$ACTIVE_FONT_CONF"
    chmod 0644 "$ACTIVE_FONT_CONF" "$SYSTEM_FONTS_DIR"/* 2>/dev/null || true
''',
        '''    if ! type luoshu_payload_validate_current >/dev/null 2>&1 || ! luoshu_payload_validate_current "$_font_id"; then
        echo '错误：字体负载覆盖校验失败，已恢复上一个字体' >&2
        return 6
    fi
    printf '%s\n' "$_font_id" > "$ACTIVE_FONT_CONF" || {
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
''',
    )

    replace_once(
        "common/font_mix.sh",
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
    replace_once(
        "common/font_mix.sh",
        '''    echo $$ > "$LOCK_FILE"
    trap cleanup_mix_process EXIT INT TERM

    _cjk_src=$(find_family_file "$_cjk")
''',
        '''    echo $$ > "$LOCK_FILE"
    trap cleanup_mix_process EXIT INT TERM
    if ! type luoshu_payload_transaction_begin >/dev/null 2>&1 || ! luoshu_payload_transaction_begin; then
        set_mix_error '无法创建字体负载安全快照'
        return 4
    fi

    _cjk_src=$(find_family_file "$_cjk")
''',
    )
    replace_once(
        "common/font_mix.sh",
        '''    type luoshu_sync_mount_payload >/dev/null 2>&1 && luoshu_sync_mount_payload 2>/dev/null || true
    rm -f "$LOCK_FILE" 2>/dev/null || true
''',
        '''    if ! type luoshu_payload_validate_current >/dev/null 2>&1 || ! luoshu_payload_validate_current mix; then
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
''',
    )


def patch_tests_and_ci() -> None:
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
        '''font_config_mark_boot_success
[ ! -e "$MODDIR/config/font-payload-boot.conf" ]
[ -s "$MODDIR/config/font-last-boot-success.conf" ]
''',
        '''font_config_mark_boot_success
[ "$(sed -n 's/^state=//p' "$MODDIR/config/font-payload-boot.conf")" = confirmed ]
font_config_boot_guard Demo
[ "$(sed -n 's/^state=//p' "$MODDIR/config/font-payload-boot.conf")" = confirmed ]
[ -s "$MODDIR/config/font-last-boot-success.conf" ]
''',
    )
    no_hook = Path("scripts/no_hook_bootstrap_test.sh")
    text = no_hook.read_text(encoding="utf-8").replace(
        "system system_ext product my_product vendor odm oem",
        "system system_ext product vendor odm oem my_product",
    )
    no_hook.write_text(text, encoding="utf-8")

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
    patch_runtime()
    patch_safety()
    patch_manager_and_mix()
    patch_tests_and_ci()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
