#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
mkdir -p "$MOD/common" "$MOD/config/universal-font-plans" "$MOD/config/minimal-xml-route-plans" "$MOD/config/universal-font-artifact-manifests"
cp "$ROOT/common/universal_font_deployment.sh" "$ROOT/common/payload_commit_lock.sh" "$MOD/common/"
cp "$ROOT/common/universal_next_boot.sh" "$MOD/common/"

cat > "$MOD/common/universal_font_plan.sh" <<'SH'
#!/bin/sh
P="$CONFIG_DIR/universal-font-plans/test.json"
case "$1" in path) printf "%s\n" "$P" ;; *) exit 2 ;; esac
SH
cat > "$MOD/common/minimal_xml_router.sh" <<'SH'
#!/bin/sh
P="$CONFIG_DIR/minimal-xml-route-plans/test.json"
case "$1" in path) printf "%s\n" "$P" ;; *) exit 2 ;; esac
SH
cat > "$MOD/common/universal_font_compiler.sh" <<'SH'
#!/bin/sh
M="$CONFIG_DIR/universal-font-artifact-manifests/test.json"
case "$1" in
  compile) printf '{"status":"ok"}\n' ;;
  manifest) printf "%s\n" "$M" ;;
  *) exit 2 ;;
esac
SH
chmod 0755 "$MOD/common/universal_font_plan.sh" "$MOD/common/minimal_xml_router.sh" "$MOD/common/universal_font_compiler.sh"

cat > "$MOD/common/universal_font_deployment.py" <<'PY'
#!/usr/bin/env python3
import argparse,json,sys
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument("--font-plan")
p.add_argument("--route-plan")
p.add_argument("--artifact-manifest")
p.add_argument("--payload-root")
p.add_argument("--manifest")
p.add_argument("--validate")
p.add_argument("--validate-payload-only")
p.add_argument("--validate-dynamic-generation", action="store_true")
a=p.parse_args()
if a.validate_payload_only:
    m=json.load(open(a.validate_payload_only,encoding="utf-8"))
    assert Path(a.payload_root,".luoshu-runtime/deployment/deployment.json").is_file()
    print(json.dumps({"status":"ok","deploymentId":m["deploymentId"]}))
    raise SystemExit(0)
if a.validate:
    assert Path(a.validate).is_file()
    print('{"status":"ok"}')
    raise SystemExit(0)
root=Path(a.payload_root)
(root/".luoshu-runtime/deployment").mkdir(parents=True,exist_ok=True)
(root/"system/fonts").mkdir(parents=True,exist_ok=True)
(root/"system/fonts/Fake.ttf").write_bytes(b"fake-font")
m={
  "schema":"universal-font-deployment-v1",
  "deploymentRevision":1,
  "state":"prepared",
  "mutatesSystem":False,
  "backendNeutral":True,
  "deploymentId":"sha256:test-deployment",
  "payloadDigest":"sha256:test-payload",
  "summary":{"activationReady":True}
}
Path(a.manifest).write_text(json.dumps(m),encoding="utf-8")
(root/".luoshu-runtime/deployment/deployment.json").write_text(json.dumps(m),encoding="utf-8")
print('{"status":"ok","deploymentId":"sha256:test-deployment"}')
PY
chmod 0755 "$MOD/common/universal_font_deployment.py"
printf '{}\n' > "$MOD/config/universal-font-plans/test.json"
printf '{}\n' > "$MOD/config/minimal-xml-route-plans/test.json"
printf '{}\n' > "$MOD/config/universal-font-artifact-manifests/test.json"

export MODDIR="$MOD"
export MODULE_DIR="$MOD"
export CONFIG_DIR="$MOD/config"
export LUOSHU_PYTHON=python3

echo "PHASE7_BRIDGE prepare"
PREP=$(sh "$MOD/common/universal_font_deployment.sh" prepare DemoFamily)
printf "%s\n" "$PREP" | grep -q '"status":"ok"'
MANIFEST=$(sh "$MOD/common/universal_font_deployment.sh" manifest DemoFamily)
PAYLOAD=$(sh "$MOD/common/universal_font_deployment.sh" payload DemoFamily)
test -s "$MANIFEST"
test -s "$PAYLOAD/system/fonts/Fake.ttf"

echo "PHASE7_BRIDGE stage-next"
STAGED=$(sh "$MOD/common/universal_font_deployment.sh" stage-next DemoFamily)
printf "%s\n" "$STAGED" | grep -q '"state":"staged-next-boot"'
test -d "$MOD/.luoshu-payload-next"
test -s "$MOD/config/universal-font-next.conf"
test "$(cat "$MOD/config/active_font.conf")" = DemoFamily
grep -q '^font=DemoFamily$' "$MOD/config/text_reboot_required.conf"
grep -q '^reason=universal-next-boot-prepared$' "$MOD/config/text_reboot_required.conf"

echo "PHASE7_BRIDGE activate"
MODDIR="$MOD" MODULE_DIR="$MOD" sh -c '. "$1"; universal_font_next_boot_activate' sh "$MOD/common/universal_next_boot.sh"
test -d "$MOD/.luoshu-payload"
test ! -e "$MOD/.luoshu-payload-next"
test -s "$MOD/config/universal-font-runtime.conf"
grep -q '^pipeline=universal-font-deployment-v1$' "$MOD/config/universal-font-runtime.conf"
grep -q '^deploymentId=sha256:test-deployment$' "$MOD/config/universal-font-runtime.conf"
test "$(cat "$MOD/config/active_font.conf")" = DemoFamily
test ! -e "$MOD/config/font_runtime_legacy_v14_4.conf"

echo "PHASE7_BRIDGE assertions-ok"
echo "universal_font_deployment_bridge_test: PASS"
