#!/bin/sh
# 改了字体引擎却复用旧缓存，表现就是"补丁打了但设备没变"。这一类事故此前发生过两次，两次都
# 因为缓存键里是手写的版本字面量，而改引擎的人没记得去递增它。键必须由引擎文件内容派生。
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/assert.sh"
CASE='引擎变更必须让缓存失效'

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
mkdir -p "$MOD/common"
for f in composite_font.py font_metrics_normalize.py font_instance.py; do
    cp "$ROOT/common/$f" "$MOD/common/$f"
done

export MODDIR="$MOD" MODULE_DIR="$MOD"
composite_hash_file() {
    sha256sum "$1" | awk '{print $1}'
}
# Pull in just the key builder from font_mix.sh without running the whole switch machinery.
eval "$(sed -n '/^composite_engine_key() {/,/^}/p' "$ROOT/common/font_mix.sh")"
ok type composite_engine_key >/dev/null

CASE='引擎不变时键稳定'
BEFORE=$(composite_engine_key)
ok test -n "$BEFORE"
eq "$(composite_engine_key)" "$BEFORE"

CASE='改度量引擎必须换键'
printf '\n# metric contract changed\n' >> "$MOD/common/font_metrics_normalize.py"
AFTER=$(composite_engine_key)
ne "$AFTER" "$BEFORE"

CASE='改合成引擎必须换键'
cp "$ROOT/common/font_metrics_normalize.py" "$MOD/common/font_metrics_normalize.py"
eq "$(composite_engine_key)" "$BEFORE"
printf '\n# composite changed\n' >> "$MOD/common/composite_font.py"
ne "$(composite_engine_key)" "$BEFORE"

CASE='归一化缓存版本同样由引擎内容派生'
# rom_adapters.sh must not carry a hand-maintained literal any more.
no grep -qE '^LUOSHU_NORMALIZER_VERSION="[0-9]+"$' "$ROOT/common/rom_adapters.sh"
ok grep -q '_luoshu_normalizer_version()' "$ROOT/common/rom_adapters.sh"

cp "$ROOT/common/font_metrics_normalize.py" "$MOD/common/font_metrics_normalize.py"
V1=$(sh -c 'MODULE_DIR="'"$MOD"'"; . "'"$ROOT"'/common/rom_adapters.sh" 2>/dev/null; printf %s "$LUOSHU_NORMALIZER_VERSION"')
printf '\n# again\n' >> "$MOD/common/font_metrics_normalize.py"
V2=$(sh -c 'MODULE_DIR="'"$MOD"'"; . "'"$ROOT"'/common/rom_adapters.sh" 2>/dev/null; printf %s "$LUOSHU_NORMALIZER_VERSION"')
ok test -n "$V1"
ne "$V2" "$V1"

CASE='复合缓存键确实带上了引擎'
ok grep -q 'engine:\$(composite_engine_key)' "$ROOT/common/font_mix.sh"

CASE='旧世代的归一化缓存必须被回收'
# config/metrics_cache is never emptied by anything else -- switching fonts clears
# .luoshu-font-store, not this. Each entry is a whole normalized font, so superseded generations
# would otherwise pile up until the module is uninstalled.
ok grep -q 'for _fa_stale in "\$_fa_cache/\${_fa_sha}_\${key}_v"\*' "$ROOT/common/rom_adapters.sh"

CACHE="$TMP/metrics_cache"
mkdir -p "$CACHE"
: > "$CACHE/abc123_regular_v6_inv.font"
: > "$CACHE/abc123_regular_v6-oldhash_inv.font"
: > "$CACHE/abc123_bold_v6_inv.font"
: > "$CACHE/other_regular_v6_inv.font"
KEEP="$CACHE/abc123_regular_v6-newhash_inv.font"
# Same shape as the pruning loop in _font_anchor.
for stale in "$CACHE/abc123_regular_v"*; do
    [ -e "$stale" ] || continue
    [ "$stale" != "$KEEP" ] || continue
    rm -f "$stale"
done
: > "$KEEP"
ok test -e "$KEEP"
no test -e "$CACHE/abc123_regular_v6_inv.font"
no test -e "$CACHE/abc123_regular_v6-oldhash_inv.font"
# A different weight and a different source font must survive: only this pair is superseded.
ok test -e "$CACHE/abc123_bold_v6_inv.font"
ok test -e "$CACHE/other_regular_v6_inv.font"

printf 'Engine cache invalidation tests passed.\n'
