#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
mkdir -p "$MOD/common" "$MOD/config/device-font-sources" "$MOD/logs"
cp "$ROOT/common/google_font_provider_bridge.sh" "$MOD/common/"
cp "$ROOT/common/google_font_provider_patch.py" "$MOD/common/"
printf 'fixture\n' > "$MOD/config/active_font.conf"
SOURCE=$(find /usr/share/fonts -type f -iname 'DejaVuSans.ttf' -print -quit)
TARGET_SOURCE=$(find /usr/share/fonts -type f -iname 'DejaVuSans-Bold.ttf' -print -quit)
[ -s "$SOURCE" ] && [ -s "$TARGET_SOURCE" ]
TARGET="$TMP/Google_Sans-700-100_0-0_0.ttf"
cp "$SOURCE" "$MOD/config/device-font-sources/LuoShu-700.ttf"
cp "$TARGET_SOURCE" "$TARGET"
LUOSHU_GOOGLE_FONT_PYTHON="$(command -v python3)" \
LUOSHU_GOOGLE_FONT_TARGETS="$TARGET" \
LUOSHU_GOOGLE_FONT_DRY_RUN=1 \
MODDIR="$MOD" \
    sh "$MOD/common/google_font_provider_bridge.sh" apply
[ -s "$MOD/config/google-font-provider-mounts.conf" ]
OUTPUT=$(awk -F'|' 'NR==1 {print $2}' "$MOD/config/google-font-provider-mounts.conf")
[ -s "$OUTPUT" ]
python3 - "$TARGET" "$OUTPUT" <<'PY'
from pathlib import Path
import sys
from fontTools.ttLib import TTFont

def values(path: Path, name_id: int) -> set[str]:
    font = TTFont(str(path), lazy=True)
    try:
        return {record.toUnicode() for record in font['name'].names if record.nameID == name_id}
    finally:
        font.close()

target = Path(sys.argv[1])
output = Path(sys.argv[2])
for name_id in (1, 4, 6, 16, 17):
    expected = values(target, name_id)
    if expected:
        assert expected <= values(output, name_id), (name_id, expected, values(output, name_id))
font = TTFont(str(output), lazy=True)
try:
    assert int(font['OS/2'].usWeightClass) == 700
finally:
    font.close()
PY
grep -q 'provider bridge：发现=1 生成=1 挂载=1 失败=0' "$MOD/logs/google-font-provider.log"
echo 'google_font_provider_bridge_test: PASS'
