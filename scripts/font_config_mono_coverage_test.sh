#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail() { echo "font_config_mono_coverage_test: FAIL - $1" >&2; exit 1; }
python3 - "$ROOT" <<'PY' || fail 'font_config_targets.py no longer protects mono; rewrite this test'
import sys
sys.path.insert(0, sys.argv[1] + "/common")
import font_config_targets as t
assert "mono" in t.PROTECTED_FAMILY_TOKENS
assert "mono" in t.PROTECTED_FILE_TOKENS
PY
cat > "$TMP/fonts.xml" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<familyset>
  <family name="sans-serif"><font weight="400" style="normal">Roboto-Regular.ttf</font></family>
  <family name="monospace"><font weight="400" style="normal">DroidSansMono.ttf</font></family>
</familyset>
XML
python3 - "$ROOT" "$TMP/fonts.xml" <<'PY' || fail 'XML overlay did not rewrite monospace to LuoShuMono'
import sys, xml.etree.ElementTree as ET
sys.path.insert(0, sys.argv[1] + "/common")
from font_config_overlay import rewrite_tree
tree = ET.parse(sys.argv[2])
report = rewrite_tree(tree, "LuoShu", "LuoShuMono")
assert report["changed_mono_families"] == ["monospace"], report
names = {f.attrib.get("name"): [c.text for c in f] for f in tree.getroot()}
assert names["monospace"] == ["LuoShuMono-400.ttf"], names
assert names["sans-serif"] == ["LuoShu-400.ttf"], names
PY

# XML/monospace generation remains implemented and regression-tested in the preserved
# current v4 manager. The App-facing root manager is now only a router, so asking it to
# contain the old generation body would accidentally reconnect final apply to the 94% path.
grep -q 'font_config_enable_for_payload' "$ROOT/common/font_mix.sh" || fail 'font_mix.sh missing XML overlay'
grep -q 'font_config_enable_for_payload' "$ROOT/common/font_manager_v4.sh" || fail 'v4 switch manager missing XML overlay'
grep -q '\[ "\$_font_id" != default \] && type font_config_enable_for_payload' "$ROOT/common/font_manager_v4.sh" || fail 'v4 switch manager missing default guard'
grep -q 'font_config_disable' "$ROOT/common/font_manager_v4.sh" || fail 'v4 manager missing disable path'
grep -q '设备原厂槽位对齐失败' "$ROOT/common/font_manager_v4.sh" || fail 'v4 switch manager missing atomic aligned-payload error'
grep -q 'return 6' "$ROOT/common/font_manager_v4.sh" || fail 'v4 switch manager must reject a partial XML/slot payload'
grep -q '警告：无 Hook XML 未安全启用，已保留文件槽映射' "$ROOT/common/font_manager_v4.sh" && fail 'v4 manager still commits a partial fail-open payload' || true

# Final App apply must stay on the isolated v14.4 physical-file backend and therefore
# must not invoke any XML overlay generator or the v4 device-template/slot pipeline.
grep -q 'legacy_v14_4_switch.sh' "$ROOT/common/font_manager.sh" || fail 'root manager missing legacy switch route'
! grep -q 'font_config_enable_for_payload' "$ROOT/common/font_manager.sh" || fail 'root manager still owns XML generation'
! grep -qE 'font_config_enable_for_payload|font_config_overlay|device_font_template|device_font_slot|device_font_payload_build' \
    "$ROOT/common/legacy_v14_4_switch.sh" || fail 'legacy switch re-entered v4 XML/slot pipeline'

grep -q 'xmlOverlay=false' "$ROOT/common/multiweight_mix_task.sh" && fail 'multiweight still hard-codes xmlOverlay=false' || true
grep -q 'font-config-overlay.conf' "$ROOT/common/multiweight_mix_task.sh" || fail 'multiweight does not read actual XML overlay state'
echo 'font_config_mono_coverage_test: PASS'
