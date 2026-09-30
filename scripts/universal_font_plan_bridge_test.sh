#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MOD="$TMP/module"
mkdir -p "$MOD/common" "$MOD/config"
cp "$ROOT/common/universal_font_plan.py" "$MOD/common/"
cp "$ROOT/common/universal_font_plan.sh" "$MOD/common/"

cat > "$MOD/common/font_source_profile.sh" <<'SH'
#!/bin/sh
case "$1" in
  refresh) printf '{"status":"ok"}\n' ;;
  path) printf '%s\n' "$TEST_PROFILE" ;;
  *) exit 2 ;;
esac
SH
chmod 0755 "$MOD/common/font_source_profile.sh"
# Isolated planner-shell contract test; full real cache migration is exercised
# by discovery and mixed pipeline tests, not this source-profile stub fixture.
cat > "$MOD/common/font_topology_snapshot.sh" <<'SH'
#!/bin/sh
[ "$1" = ensure ] || exit 2
printf called > "$MODDIR/config/topology-ensure-called"
SH

cat > "$MOD/config/device_font_topology.json" <<'JSON'
{
  "schema": "device-font-topology-v1",
  "topologyRevision": 3,
  "state": "ready",
  "buildKey": "bridge-test",
  "romKind": "generic",
  "slots": {
    "/system/fonts/Roboto-Regular.ttf": {
      "slotName": "Roboto-Regular.ttf",
      "partition": "system",
      "families": ["sans-serif"],
      "metrics": {
        "weightClass": 400,
        "coverage": {
          "hasHan": false,
          "hanCount": 0,
          "hasLatin": true,
          "latinCount": 52,
          "hasDigits": true,
          "digitCount": 10
        },
        "variationAxes": []
      },
      "xmlRefs": [
        {
          "sourceXml": "/system/etc/fonts.xml",
          "family": "sans-serif",
          "familyAttributes": {},
          "weight": 400,
          "style": "normal",
          "resolvedPath": "/system/fonts/Roboto-Regular.ttf"
        }
      ],
      "runtimeEvidence": {"fontManager": true, "mount": false},
      "legacyReplaceable": true
    }
  }
}
JSON

cat > "$MOD/config/device_font_roles.json" <<'JSON'
{
  "schema": "device-font-roles-v1",
  "roleRevision": 3,
  "state": "ready",
  "buildKey": "bridge-test",
  "romKind": "generic",
  "slots": {
    "/system/fonts/Roboto-Regular.ttf": {
      "role": "latin",
      "confidence": 100,
      "action": "conditional",
      "reasons": ["bridge-test"]
    }
  }
}
JSON

PROFILE="$TMP/profile.json"
cat > "$PROFILE" <<'JSON'
{
  "schema": "source-font-profile-v1",
  "profileRevision": 1,
  "state": "ready",
  "profileId": "sha256:bridge-source",
  "summary": {
    "fileCount": 1,
    "faceCount": 1,
    "familyCount": 1,
    "capabilities": {
      "latinUi": true,
      "cjkUi": false,
      "numeric": true,
      "variable": false,
      "variableWeight": false,
      "colorFont": false,
      "globalUiCandidate": false
    }
  },
  "files": [
    {
      "fileUid": "sha256:bridge-file",
      "sha256": "bridge-file",
      "sourcePath": "/sdcard/LuoShu/fonts/Bridge-Regular.ttf",
      "fileName": "Bridge-Regular.ttf",
      "container": "TTF",
      "requiresSfntConversion": false,
      "faceCount": 1,
      "faces": [
        {
          "uid": "sha256:bridge-file:face:0",
          "fileUid": "sha256:bridge-file",
          "faceIndex": 0,
          "names": {
            "family": "Bridge",
            "familyNormalized": "bridge",
            "subfamily": "Regular",
            "postScriptName": "Bridge-Regular"
          },
          "style": {
            "weight": 400,
            "italic": false,
            "fixedPitch": false
          },
          "variation": {
            "variable": false,
            "axes": []
          },
          "capabilities": {
            "latinUi": true,
            "cjkUi": false,
            "numeric": true,
            "colorFont": false,
            "globalUiCandidate": false
          }
        }
      ]
    }
  ]
}
JSON

export TEST_PROFILE="$PROFILE"

RESULT=$(MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PYTHON=python3 \
  sh "$MOD/common/universal_font_plan.sh" build Bridge-Regular)
printf '%s\n' "$RESULT" | grep -q '"status":"ok"'
printf '%s\n' "$RESULT" | grep -q '"executableNow":false'

PLAN=$(MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PYTHON=python3 \
  sh "$MOD/common/universal_font_plan.sh" path Bridge-Regular)
test -s "$PLAN"

python3 - "$PLAN" <<'PY'
import json, sys
plan = json.load(open(sys.argv[1], encoding='utf-8'))
assert plan['schema'] == 'universal-font-plan-v1'
assert plan['mutatesSystem'] is False
target = plan['targets']['/system/fonts/Roboto-Regular.ttf']
assert target['action'] == 'compile'
assert target['source']['family'] == 'Bridge'
assert 'metrics-normalization' in target['requirements']
PY

VALID=$(MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PYTHON=python3 \
  sh "$MOD/common/universal_font_plan.sh" validate Bridge-Regular)
printf '%s\n' "$VALID" | grep -q '"status":"ok"'

test -s "$MOD/config/topology-ensure-called"
echo "universal_font_plan_bridge_test: PASS"
