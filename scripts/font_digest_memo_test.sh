#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/assert.sh"

TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-digest)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE_DIR="$TMP/module"
MODDIR="$MODULE_DIR"
LUOSHU_DIGEST_MEMO="$TMP/digest.memo"
export MODULE_DIR MODDIR LUOSHU_DIGEST_MEMO
mkdir -p "$MODULE_DIR/config" "$TMP/bin"

REAL_SHA256SUM=$(command -v sha256sum)
SHA_CALLS="$TMP/sha.calls"
export REAL_SHA256SUM SHA_CALLS
cat > "$TMP/bin/sha256sum" <<'EOF'
#!/bin/sh
printf '1\n' >> "$SHA_CALLS"
exec "$REAL_SHA256SUM" "$@"
EOF
chmod +x "$TMP/bin/sha256sum"
PATH="$TMP/bin:$PATH"
export PATH

. "$ROOT/common/font_safety.sh"
. "$ROOT/common/rom_adapters.sh"

SRC="$TMP/source.ttf"
python3 - "$SRC" <<'PY'
from pathlib import Path
import sys
Path(sys.argv[1]).write_bytes(b"A" * 4096)
PY

CASE='字体摘要同身份只计算一次'
first=$(_font_source_digest "$SRC")
second=$(_font_source_digest "$SRC")
eq "$second" "$first"
eq "$(wc -l < "$SHA_CALLS" | tr -d '[:space:]')" 1

# Rewrite to different bytes with exactly the same size immediately. Whole-second mtime/ctime keys
# can collide here; the identity must include the sub-second timestamps exposed by stat/toybox stat.
before_id=$(_font_source_identity "$SRC")
python3 - "$SRC" <<'PY'
from pathlib import Path
import os, sys
p = Path(sys.argv[1])
st = p.stat()
p.write_bytes(b"B" * st.st_size)
# Keep the rewrite in the same integer mtime second while forcing a different nanosecond component.
now = p.stat()
sec = now.st_mtime_ns // 1_000_000_000
nsec = (now.st_mtime_ns + 1234567) % 1_000_000_000
os.utime(p, ns=(now.st_atime_ns, sec * 1_000_000_000 + nsec))
PY
after_id=$(_font_source_identity "$SRC")
CASE='同大小快速替换必须使摘要缓存失效'
ne "$after_id" "$before_id"
third=$(_font_source_digest "$SRC")
ne "$third" "$first"
eq "$(wc -l < "$SHA_CALLS" | tr -d '[:space:]')" 2

printf 'Font digest memoization tests passed.\n'
