from pathlib import Path

path = Path("scripts/check.sh")
text = path.read_text(encoding="utf-8")

replacements = [
    (
        "grep '^common/' \"$PAYLOAD_MANIFEST\" | grep -v '^common/python$' | sort > /tmp/luoshu-manifest-common.txt",
        "grep '^common/' \"$PAYLOAD_MANIFEST\" | grep -v '^common/python$' | grep -v '^common/legacy_v14_4$' | sort > /tmp/luoshu-manifest-common.txt",
    ),
    (
        "! grep -RInE --exclude-dir=python '(^|[^0-9])v1[34](\\.|[^0-9])|Beta[[:space:]]*[0-9]|Hotfix' \\\n  \"$ROOT/common\" \"$ROOT/customize.sh\" \"$ROOT/post-fs-data.sh\" \"$ROOT/service.sh\" \"$ROOT/uninstall.sh\" >/dev/null 2>&1",
        "! grep -RInE --exclude-dir=python --exclude-dir=legacy_v14_4 --exclude=legacy_v14_4_switch.sh --exclude=font_manager.sh \\\n  '(^|[^0-9])v1[34](\\.|[^0-9])|Beta[[:space:]]*[0-9]|Hotfix' \\\n  \"$ROOT/common\" \"$ROOT/customize.sh\" \"$ROOT/post-fs-data-v4.sh\" \"$ROOT/service_v4.sh\" \"$ROOT/uninstall.sh\" >/dev/null 2>&1",
    ),
    (
        "! grep -RInE 'webui_font_list|WebUI' \"$ROOT/common\" --exclude=module_update_state.sh >/dev/null 2>&1",
        "! grep -RInE 'webui_font_list|WebUI' \"$ROOT/common\" --exclude=module_update_state.sh --exclude-dir=legacy_v14_4 >/dev/null 2>&1",
    ),
    (
        "! grep -RInE --exclude-dir=python '洛书 v1[34]\\.|LuoShu v1[34]\\.' \\\n  \"$ROOT/common\" \"$ROOT/customize.sh\" \"$ROOT/post-fs-data.sh\" \"$ROOT/service.sh\" \"$ROOT/uninstall.sh\" >/dev/null 2>&1",
        "! grep -RInE --exclude-dir=python --exclude-dir=legacy_v14_4 --exclude=legacy_v14_4_switch.sh --exclude=font_manager.sh \\\n  '洛书 v1[34]\\.|LuoShu v1[34]\\.' \\\n  \"$ROOT/common\" \"$ROOT/customize.sh\" \"$ROOT/post-fs-data-v4.sh\" \"$ROOT/service_v4.sh\" \"$ROOT/uninstall.sh\" >/dev/null 2>&1",
    ),
    (
        "  scripts/stability_test.sh scripts/native_zip_import_test.sh scripts/native_preview_source_test.sh scripts/app_bridge_status_test.sh scripts/font_boot_state_test.sh \\",
        "  scripts/stability_test.sh scripts/legacy_switch_core_test.sh scripts/native_zip_import_test.sh scripts/native_preview_source_test.sh scripts/app_bridge_status_test.sh scripts/font_boot_state_test.sh \\",
    ),
    (
        'sh "$ROOT/scripts/font_switch_performance_test.sh"\nsh "$ROOT/scripts/font_validation_cache_test.sh"',
        'sh "$ROOT/scripts/font_switch_performance_test.sh"\nsh "$ROOT/scripts/legacy_switch_core_test.sh"\nsh "$ROOT/scripts/font_validation_cache_test.sh"',
    ),
]

for old, new in replacements:
    if old not in text:
        raise SystemExit(f"check.sh patch anchor missing: {old[:100]!r}")
    text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
