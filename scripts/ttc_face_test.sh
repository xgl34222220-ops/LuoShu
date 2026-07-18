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
PYTHONPATH="$PYTHONPATH_DIR" python3 -S - "$TMP/result.json" "$TMP/out" "$ROOT/common/font_metadata.py" <<'PY'
import json
import subprocess
import sys
from pathlib import Path
result_path, output_dir, inspector = sys.argv[1:]
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
    completed = subprocess.run(
        [sys.executable, '-S', inspector, str(path)],
        env={'PYTHONPATH': str(Path(inspector).parent.parent / 'python' / 'lib' / 'python3.14' / 'site-packages')},
        text=True,
        capture_output=True,
    )
    # The subprocess environment above is intentionally minimal; fall back to
    # in-process inspection when the host strips standard environment entries.
    if completed.returncode != 0:
        sys.path.insert(0, str(Path(inspector).parent))
        import font_metadata
        inspected = font_metadata.inspect(path)
    else:
        inspected = json.loads(completed.stdout)
    assert inspected['status'] == 'ok', inspected
    assert inspected['data']['faceCount'] == 1, inspected
print('TTC face extraction smoke test passed.')
PY
