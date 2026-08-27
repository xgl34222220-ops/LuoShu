from pathlib import Path

path = Path("scripts/check.sh")
text = path.read_text(encoding="utf-8")

old = """find \"$ROOT/common\" -maxdepth 1 -type f -printf 'common/%f\\n' | sort > /tmp/luoshu-common-files.txt
grep '^common/' \"$PAYLOAD_MANIFEST\" | grep -v '^common/python$' | sort > /tmp/luoshu-manifest-common.txt
cmp -s /tmp/luoshu-common-files.txt /tmp/luoshu-manifest-common.txt"""
new = """find \"$ROOT/common\" -maxdepth 1 -type f -printf 'common/%f\\n' | sort > /tmp/luoshu-common-files.txt
: > /tmp/luoshu-manifest-common.txt
while IFS= read -r payload || [ -n \"$payload\" ]; do
  case \"$payload\" in
    common/*)
      [ -f \"$ROOT/$payload\" ] || continue
      case \"${payload#common/}\" in */*) continue ;; esac
      printf '%s\\n' \"$payload\" >> /tmp/luoshu-manifest-common.txt
      ;;
  esac
done < \"$PAYLOAD_MANIFEST\"
sort -o /tmp/luoshu-manifest-common.txt /tmp/luoshu-manifest-common.txt
cmp -s /tmp/luoshu-common-files.txt /tmp/luoshu-manifest-common.txt"""
assert old in text, "manifest audit block not found"
text = text.replace(old, new, 1)

old = """! grep -RInE --exclude-dir=python '(^|[^0-9])v1[34](\\.|[^0-9])|Beta[[:space:]]*[0-9]|Hotfix' \\
  \"$ROOT/common\" \"$ROOT/customize.sh\" \"$ROOT/post-fs-data.sh\" \"$ROOT/service.sh\" \"$ROOT/uninstall.sh\" >/dev/null 2>&1"""
new = """! grep -RInE --exclude-dir=python --exclude-dir=legacy_v14_4 \\
  --exclude=legacy_v14_4_switch.sh --exclude=font_manager.sh \\
  '(^|[^0-9])v1[34](\\.|[^0-9])|Beta[[:space:]]*[0-9]|Hotfix' \\
  \"$ROOT/common\" \"$ROOT/customize.sh\" \"$ROOT/post-fs-data-v4.sh\" \"$ROOT/service_v4.sh\" \"$ROOT/uninstall.sh\" >/dev/null 2>&1"""
assert old in text, "historical runtime audit block not found"
text = text.replace(old, new, 1)

old = """! grep -RInE 'webui_font_list|WebUI' \"$ROOT/common\" --exclude=module_update_state.sh >/dev/null 2>&1"""
new = """! grep -RInE 'webui_font_list|WebUI' \"$ROOT/common\" --exclude=module_update_state.sh --exclude-dir=legacy_v14_4 >/dev/null 2>&1"""
assert old in text, "WebUI audit block not found"
text = text.replace(old, new, 1)

old = """  scripts/stability_test.sh scripts/native_zip_import_test.sh scripts/native_preview_source_test.sh scripts/app_bridge_status_test.sh scripts/font_boot_state_test.sh \\
"""
new = """  scripts/stability_test.sh scripts/legacy_switch_core_test.sh scripts/native_zip_import_test.sh scripts/native_preview_source_test.sh scripts/app_bridge_status_test.sh scripts/font_boot_state_test.sh \\
"""
assert old in text, "active test source list anchor not found"
text = text.replace(old, new, 1)

old = 'sh "$ROOT/scripts/font_switch_performance_test.sh"'
new = old + '\nsh "$ROOT/scripts/legacy_switch_core_test.sh"'
assert old in text, "test execution anchor not found"
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
