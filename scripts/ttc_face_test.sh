#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHONPATH_DIR="$ROOT/common/python/lib/python3.14/site-packages"
REGULAR=$(find /usr/share/fonts -type f -iname 'DejaVuSans.ttf' -print -quit 2>/dev/null || true)
BOLD=$(find /usr/share/fonts -type f -iname 'DejaVuSans-Bold.ttf' -print -quit 2>/dev/null || true)
if [ ! -s "$REGULAR" ] || [ ! -s "$BOLD" ]; then
  echo 'TTC face test skipped: DejaVu Sans test fonts are unavailable.'
  exit 0
fi
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
PYTHONPATH="$PYTHONPATH_DIR" python3 -S - "$REGULAR" "$BOLD" "$TMP/input.ttc" <<'PY'
import sys
from fontTools.ttLib import TTCollection, TTFont
regular, bold, output = sys.argv[1:]
fonts = [TTFont(regular, lazy=False), TTFont(bold, lazy=False)]
try:
    collection = TTCollection()
    collection.fonts = fonts
    collection.save(output)
finally:
    for font in fonts:
        font.close()
PY
PYTHONPATH="$PYTHONPATH_DIR" python3 -S "$ROOT/common/font_extract_faces.py" \
  --input "$TMP/input.ttc" --output-dir "$TMP/out" --label 'LuoShu-CI' > "$TMP/result.json"
PYTHONPATH="$PYTHONPATH_DIR:$ROOT/common" python3 -S - "$TMP/result.json" "$TMP/out" <<'PY'
import json
import sys
from pathlib import Path
import font_metadata
result_path, output_dir = sys.argv[1:]
result = json.loads(Path(result_path).read_text(encoding='utf-8'))
assert result['status'] == 'ok', result
faces = result['data']['faces']
assert result['data']['faceCount'] == 2, result
assert result['data']['imported'] == 2, result
assert len(faces) == 2, result
assert len({face['sourceUid'] for face in faces}) == 2, result
files = sorted(Path(output_dir).glob('*.*'))
assert len(files) == 2, files
for path in files:
    inspected = font_metadata.inspect(path)
    assert inspected['status'] == 'ok', inspected
    assert inspected['data']['faceCount'] == 1, inspected
print('TTC face extraction smoke test passed.')
PY
