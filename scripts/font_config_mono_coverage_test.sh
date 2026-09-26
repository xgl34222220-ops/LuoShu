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

# The legacy XML helper above keeps its regression fixture, while every active
# App/backend mutation now maps the measured inventory without rewriting full XML.
grep -q 'inventory_font_stage.sh' "$ROOT/common/legacy_v14_4/mix_router.sh" || fail 'composite missing inventory mapping'
grep -q 'font_switch_safe.sh' "$ROOT/common/font_manager.sh" || fail 'root manager missing universal switch route'
for _entry in "$ROOT/common/font_mix.sh" "$ROOT/common/legacy_v14_4/mix_router.sh" \
              "$ROOT/common/font_manager.sh" "$ROOT/common/font_manager_v4.sh" \
              "$ROOT/common/legacy_v14_4_switch.sh"; do
    ! grep -qE 'font_config_enable_for_payload|font_config_overlay|device_font_template|device_font_slot|device_font_payload_build|apply_font_by_rom' \
        "$_entry" || fail 'active entry re-entered the retired XML/ROM mapper'
done
grep -q 'action switch "$1"' "$ROOT/common/font_manager_v4.sh" || fail 'active font deletion bypasses safe reset'

grep -q 'xmlOverlay=false' "$ROOT/common/multiweight_mix_task.sh" && fail 'multiweight still hard-codes xmlOverlay=false' || true
grep -q 'font-config-overlay.conf' "$ROOT/common/multiweight_mix_task.sh" || fail 'multiweight does not read actual XML overlay state'
echo 'font_config_mono_coverage_test: PASS'
