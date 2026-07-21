#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"missing anchor in {path}: {old[:120]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


def regex_once(path: str, pattern: str, replacement: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"pattern matched {count} times in {path}: {pattern[:120]!r}")
    file.write_text(text, encoding="utf-8")


def patch_runtime() -> None:
    path = Path("common/font_config_runtime.sh")
    text = path.read_text(encoding="utf-8")
    old = r'''        [ -s "$_lfc_backup" ] && _luoshu_font_config_validate "$_lfc_backup" && continue
        # Never snapshot our own overlay as the device source of truth.
        grep -q 'LuoShu-[1-9][0-9][0-9]\.ttf' "$_lfc_real" 2>/dev/null && continue
'''
    new = r'''        _lfc_backup_valid=0
        if [ -s "$_lfc_backup" ] && _luoshu_font_config_validate "$_lfc_backup"; then
            _lfc_backup_valid=1
            command -v cmp >/dev/null 2>&1 && cmp -s "$_lfc_real" "$_lfc_backup" 2>/dev/null && continue
        fi
        # Never snapshot our own upper-layer document. A valid previous source remains the only safe
        # source in that case; otherwise the document is skipped instead of guessing after an OTA.
        if grep -q 'LuoShu-[1-9][0-9][0-9]\.ttf' "$_lfc_real" 2>/dev/null; then
            [ "$_lfc_backup_valid" -eq 1 ] && continue
            continue
        fi
'''
    if old not in text:
        raise SystemExit("missing capture-original refresh anchor")
    text = text.replace(old, new, 1)

    start = text.index("_luoshu_font_config_generate_base() {")
    end = text.index("\n_luoshu_font_config_boot_guard_base() {", start)
    body = text[start:end].replace("font_config_disable", "_luoshu_font_config_disable_base")
    text = text[:start] + body + text[end:]
    path.write_text(text, encoding="utf-8")


def patch_font_safety() -> None:
    path = "common/font_safety.sh"
    replace_once(
        path,
        r'''_luoshu_checksum() {
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
        r'''_luoshu_checksum() {
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

    regex_once(
        path,
        r'''luoshu_payload_validate_manifest\(\) \{.*?\n\}\n\nluoshu_payload_arm\(\) \{''',
        r'''luoshu_payload_validate_manifest_full() {
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

# post-fs-data must not stream every large font before Zygote. Font contents and XML structure are
# fully validated when the App commits the transaction; early boot verifies immutable size metadata
# for fonts and checksums only the tiny XML documents.
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

    # Prefer hard-link snapshots on /data. Switching removes/replaces targets rather than modifying
    # them in place, so this is both safe and dramatically cheaper for large CJK payloads.
    replace_once(
        path,
        r'''                cp -af "$_lpt_src" "$LUOSHU_PAYLOAD_TXN/tree/$_lpt_rel" 2>/dev/null || {
                    mkdir -p "$LUOSHU_PAYLOAD_TXN/tree/$_lpt_rel" 2>/dev/null || return 1
                    cp -rfp "$_lpt_src/." "$LUOSHU_PAYLOAD_TXN/tree/$_lpt_rel/" 2>/dev/null || return 1
                }
''',
        r'''                cp -al "$_lpt_src" "$LUOSHU_PAYLOAD_TXN/tree/$_lpt_rel" 2>/dev/null ||
                cp -af "$_lpt_src" "$LUOSHU_PAYLOAD_TXN/tree/$_lpt_rel" 2>/dev/null || {
                    mkdir -p "$LUOSHU_PAYLOAD_TXN/tree/$_lpt_rel" 2>/dev/null || return 1
                    cp -rfp "$_lpt_src/." "$LUOSHU_PAYLOAD_TXN/tree/$_lpt_rel/" 2>/dev/null || return 1
                }
''',
    )

    replace_once(
        path,
        r'''luoshu_payload_transaction_abort() {
    [ -z "$LUOSHU_PAYLOAD_TXN" ] || luoshu_payload_transaction_rollback
}
''',
        r'''luoshu_payload_transaction_abort() {
    _lpta_had=0
    if [ -n "$LUOSHU_PAYLOAD_TXN" ]; then
        _lpta_had=1
        luoshu_payload_transaction_rollback
    fi
    # A failed switch may already have mirrored the candidate into a meta-module staging root. After
    # restoring the local snapshot, mirror the old payload back; mount sync itself preserves the last
    # complete destination when a copy fails.
    if [ "$_lpta_had" -eq 1 ] && type luoshu_sync_mount_payload >/dev/null 2>&1; then
        luoshu_sync_mount_payload >/dev/null 2>&1 ||
            _luoshu_safety_log ERROR '旧字体已在模块目录恢复，但元模块回写失败；下次开机守卫将撤销覆盖'
    fi
}
''',
    )

    regex_once(
        path,
        r'''font_config_boot_guard\(\) \{.*?\n\}\n\nfont_config_mark_boot_success\(\) \{.*?\n\}\s*$''',
        r'''font_config_boot_guard() {
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
            _luoshu_safety_log INFO '新字体负载轻量启动校验通过，等待系统完成开机确认'
            ;;
        confirmed)
            luoshu_payload_validate_manifest_fast || { luoshu_payload_quarantine; return 1; }
            ;;
        *)
            # Payloads created by an older engine have no trustworthy transaction manifest. Failing
            # open to the ROM font once is safer than attempting Python/XML work before Zygote.
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
    _luoshu_safety_log INFO '系统已完成开机，字体负载事务确认成功'
}
''',
    )


def patch_font_manager() -> None:
    path = "common/font_manager.sh"
    replace_once(
        path,
        r'''    printf '%s\n' "$_font_id" > "$ACTIVE_FONT_CONF"
    chmod 0644 "$ACTIVE_FONT_CONF" "$SYSTEM_FONTS_DIR"/* 2>/dev/null || true
''',
        r'''    if ! type luoshu_payload_validate_current >/dev/null 2>&1 || ! luoshu_payload_validate_current "$_font_id"; then
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


def patch_font_mix() -> None:
    path = "common/font_mix.sh"
    replace_once(
        path,
        r'''cleanup_mix_process() {
    payload_stage_abort
    payload_stage_rollback
    rm -f "$LOCK_FILE" 2>/dev/null || true
}
''',
        r'''cleanup_mix_process() {
    payload_stage_abort
    payload_stage_rollback
    type luoshu_payload_transaction_abort >/dev/null 2>&1 && luoshu_payload_transaction_abort
    rm -f "$LOCK_FILE" 2>/dev/null || true
}
''',
    )
    replace_once(
        path,
        r'''    echo $$ > "$LOCK_FILE"
    trap cleanup_mix_process EXIT INT TERM

    _cjk_src=$(find_family_file "$_cjk")
''',
        r'''    echo $$ > "$LOCK_FILE"
    trap cleanup_mix_process EXIT INT TERM
    if ! type luoshu_payload_transaction_begin >/dev/null 2>&1 || ! luoshu_payload_transaction_begin; then
        set_mix_error '无法创建字体负载安全快照'
        return 4
    fi

    _cjk_src=$(find_family_file "$_cjk")
''',
    )
    replace_once(
        path,
        r'''    type luoshu_sync_mount_payload >/dev/null 2>&1 && luoshu_sync_mount_payload 2>/dev/null || true
    rm -f "$LOCK_FILE" 2>/dev/null || true
''',
        r'''    if ! type luoshu_payload_validate_current >/dev/null 2>&1 || ! luoshu_payload_validate_current mix; then
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


def patch_service() -> None:
    replace_once("service.sh", '"$WAITED" -lt 90', '"$WAITED" -lt 600')


def patch_tests() -> None:
    path = "scripts/font_config_runtime_test.sh"
    replace_once(
        path,
        'cp -f "$ROOT/common/font_config_partitions.sh" "$MOD/common/font_config_partitions.sh"\n',
        'cp -f "$ROOT/common/font_config_partitions.sh" "$MOD/common/font_config_partitions.sh"\n'
        'cp -f "$ROOT/common/font_config_targets.py" "$MOD/common/font_config_targets.py"\n'
        'cp -f "$ROOT/common/font_safety.sh" "$MOD/common/font_safety.sh"\n',
    )
    replace_once(
        path,
        '# Regeneration repairs every partition alias from the validated system weight set.\nfont_config_generate DemoFamily\n',
        '# Regeneration repairs every partition alias from the validated system weight set.\n'
        'mkdir -p "$MOD/system/fonts"\n'
        'for weight in 100 200 300 400 500 600 700 800 900; do\n'
        '    dd if=/dev/zero of="$MOD/system/fonts/LuoShu-${weight}.ttf" bs=2048 count=1 2>/dev/null\n'
        'done\n'
        'font_config_generate DemoFamily\n',
    )

    path = "scripts/font_safety_test.sh"
    replace_once(
        path,
        r'''font_config_mark_boot_success
[ ! -e "$MODDIR/config/font-payload-boot.conf" ]
[ -s "$MODDIR/config/font-last-boot-success.conf" ]
''',
        r'''font_config_mark_boot_success
[ "$(sed -n 's/^state=//p' "$MODDIR/config/font-payload-boot.conf")" = confirmed ]
font_config_boot_guard Demo
[ "$(sed -n 's/^state=//p' "$MODDIR/config/font-payload-boot.conf")" = confirmed ]
[ -s "$MODDIR/config/font-last-boot-success.conf" ]
''',
    )

    path = Path("scripts/no_hook_bootstrap_test.sh")
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "grep -q 'system system_ext product my_product vendor odm oem' \"$ROOT/common/mount_compat.sh\"",
        "grep -q 'system system_ext product vendor odm oem my_product' \"$ROOT/common/mount_compat.sh\"",
    )
    path.write_text(text, encoding="utf-8")


def patch_ci() -> None:
    path = Path(".github/workflows/no-hook-font-engine.yml")
    text = path.read_text(encoding="utf-8")
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
    path.write_text(text, encoding="utf-8")


def main() -> int:
    patch_runtime()
    patch_font_safety()
    patch_font_manager()
    patch_font_mix()
    patch_service()
    patch_tests()
    patch_ci()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
