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
grep -q 'font_config_enable_for_payload' "$ROOT/common/font_mix.sh" || fail 'font_mix.sh missing XML overlay'
grep -q 'font_config_enable_for_payload' "$ROOT/common/font_manager.sh" || fail 'switch_font missing XML overlay'
grep -q '\[ "\$_font_id" != default \] && type font_config_enable_for_payload' "$ROOT/common/font_manager.sh" || fail 'switch_font missing default guard'
grep -q 'font_config_disable' "$ROOT/common/font_manager.sh" || fail 'font_manager missing disable path'
grep -q '警告：无 Hook XML 未安全启用，已保留文件槽映射' "$ROOT/common/font_manager.sh" || fail 'switch_font XML path is not fail-open'
grep -q 'xmlOverlay=false' "$ROOT/common/multiweight_mix_task.sh" && fail 'multiweight still hard-codes xmlOverlay=false' || true
grep -q 'font-config-overlay.conf' "$ROOT/common/multiweight_mix_task.sh" || fail 'multiweight does not read actual XML overlay state'
echo 'font_config_mono_coverage_test: PASS'
