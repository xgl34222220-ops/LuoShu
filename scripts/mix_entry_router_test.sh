#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
mkdir -p "$MOD/common/legacy_v14_4"
# Loading an obsolete initializer is a failure even when the backend succeeds.
printf 'exit 91\n' > "$MOD/common/util_functions.sh"
printf 'exit 92\n' > "$MOD/common/font_check.sh"
cat > "$MOD/common/legacy_v14_4/mix_router.sh" <<'EOF_BACKEND'
printf '%s\n' "${1:-config}" "${2:-}" "${3:-}"
exit 0
EOF_BACKEND
MODDIR="$MOD" sh "$ROOT/common/font_mix_controller.sh" start 'Font A' '中文 B' > "$TMP/result"
printf 'start\nFont A\n中文 B\n' > "$TMP/expected"
cmp "$TMP/result" "$TMP/expected"
MODDIR="$MOD" sh "$ROOT/common/font_mix_controller.sh" > "$TMP/default"
head -n1 "$TMP/default" | grep -qx config
rm "$MOD/common/legacy_v14_4/mix_router.sh"
if MODDIR="$MOD" sh "$ROOT/common/font_mix_controller.sh" status task > "$TMP/missing"; then
    echo 'Missing backend must not run a dormant fallback' >&2
    exit 1
fi
grep -q '缺少字体组合核心' "$TMP/missing"
echo 'Composite entry delegates immediately, preserves arguments and reports a missing core.'
