#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MOD="$TMP/module"
mkdir -p "$MOD/common" "$MOD/config/universal-font-plans" "$MOD/config/minimal-xml-route-plans"
cp "$ROOT/common/universal_font_compiler.sh" "$MOD/common/"

cat > "$MOD/common/universal_font_plan.sh" <<'SH'
#!/bin/sh
P="$CONFIG_DIR/universal-font-plans/test.json"
case "$1" in
  path) printf "%s\n" "$P" ;;
  exclusions) printf "%s\n" "$CONFIG_DIR/universal-font-exclusions/test.json" ;;
  *) exit 2 ;;
esac
SH
chmod 0755 "$MOD/common/universal_font_plan.sh"

cat > "$MOD/common/minimal_xml_router.sh" <<'SH'
#!/bin/sh
P="$CONFIG_DIR/minimal-xml-route-plans/test.json"
case "$1" in
  build)
    echo build >> "$CONFIG_DIR/route-builds"
    mkdir -p "${P%/*}"
    printf '{"schema":"minimal-xml-route-plan-v1","state":"planned"}\n' > "$P"
    printf '{"status":"ok"}\n'
    ;;
  path) printf "%s\n" "$P" ;;
  *) exit 2 ;;
esac
SH
chmod 0755 "$MOD/common/minimal_xml_router.sh"

cat > "$MOD/common/universal_font_compiler.py" <<'PY'
#!/usr/bin/env python3
import argparse, json
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument("--font-plan", required=True)
p.add_argument("--route-plan", required=True)
p.add_argument("--output-dir")
p.add_argument("--manifest")
p.add_argument("--validate")
p.add_argument("--stock-map")
p.add_argument("--allow-live-stock", action="store_true")
p.add_argument("--exclusions-out")
a=p.parse_args()
import os, sys
if a.exclusions_out and os.environ.get("FAKE_REPLAN") and (
    os.environ["FAKE_REPLAN"] == "always" or not Path(a.exclusions_out).exists()
):
    Path(a.exclusions_out).write_text('{"targets":{"/system/fonts/Extra.ttf":"x"}}')
    print('{"status":"retry"}')
    sys.exit(3)
assert Path(a.font_plan).is_file()
assert Path(a.route_plan).is_file()
if a.validate:
    assert Path(a.validate).is_file()
    print('{"status":"ok","schema":"universal-font-artifacts-v1"}')
else:
    out=Path(a.output_dir); out.mkdir(parents=True, exist_ok=True)
    artifact=out/"fake.ttf"; artifact.write_bytes(b"font-artifact")
    manifest=Path(a.manifest); manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({
      "schema":"universal-font-artifacts-v1",
      "compilerRevision":1,
      "state":"compiled",
      "mutatesSystem":False,
      "manifestId":"sha256:test",
      "fontPlanId":"sha256:test",
      "routeId":"sha256:test",
      "summary":{"artifactCount":1,"readyCount":1,"blockedCount":0,"deferredDynamicTargetCount":0,"deploymentReady":True,"executableNow":False},
      "deferredDynamicTargets":[],
      "artifactMap":{"ufc:test":"fake.ttf"},
      "physicalTargetMap":{},
      "artifacts":[]
    }), encoding="utf-8")
    print('{"status":"ok","schema":"universal-font-artifacts-v1"}')
PY
chmod 0755 "$MOD/common/universal_font_compiler.py"

cat > "$MOD/config/universal-font-plans/test.json" <<'JSON'
{"schema":"universal-font-plan-v1","state":"planned"}
JSON

export MODDIR="$MOD"
export MODULE_DIR="$MOD"
export CONFIG_DIR="$MOD/config"
export LUOSHU_PYTHON=python3
export LUOSHU_COMPILER_CACHE="$MOD/cache/compiler"

BUILD=$(sh "$MOD/common/universal_font_compiler.sh" compile DemoFamily)
printf "%s\n" "$BUILD" | grep -q '"status":"ok"'

MANIFEST=$(sh "$MOD/common/universal_font_compiler.sh" manifest DemoFamily)
test -s "$MANIFEST"
OUTDIR=$(sh "$MOD/common/universal_font_compiler.sh" output-dir DemoFamily)
test -s "$OUTDIR/fake.ttf"

VALID=$(sh "$MOD/common/universal_font_compiler.sh" validate DemoFamily)
printf "%s\n" "$VALID" | grep -q '"status":"ok"'

# Only non-core slots failed: keep them stock and re-plan once.
rm -f "$CONFIG_DIR/route-builds"
mkdir -p "$LUOSHU_COMPILER_CACHE/stale-family"
REPLAN=$(FAKE_REPLAN=once sh "$MOD/common/universal_font_compiler.sh" compile DemoFamily)
printf "%s\n" "$REPLAN" | grep -q '"status":"ok"'
test "$(wc -l < "$CONFIG_DIR/route-builds")" -eq 2
test -s "$CONFIG_DIR/universal-font-exclusions/test.json"
test ! -e "$LUOSHU_COMPILER_CACHE/stale-family"
test -s "$OUTDIR/fake.ttf"

# A fresh switch starts without the previous exclusions; a loop is bounded.
rm -f "$CONFIG_DIR/route-builds"
if LOOP=$(FAKE_REPLAN=always sh "$MOD/common/universal_font_compiler.sh" compile DemoFamily); then
    printf "%s\n" "$LOOP" | grep -q '"status":"error"'
fi
printf "%s\n" "$LOOP" | grep -q '多次保留原厂后仍有字体无法替换'
test "$(wc -l < "$CONFIG_DIR/route-builds")" -eq 4

# Compiler bridge must stay private: no system or payload tree is created.
test ! -e "$MOD/system"
test ! -e "$MOD/.luoshu-payload"

echo "universal_font_compiler_bridge_test: PASS"
