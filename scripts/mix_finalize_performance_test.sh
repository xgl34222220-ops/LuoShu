#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-mix-finalize)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

# Hard-linked aliases must be checksummed once, not once per path.
MODULE="$TMP/module"
mkdir -p "$MODULE/common" "$MODULE/config" "$MODULE/system/fonts" "$TMP/bin"
cp "$ROOT/common/font_safety.sh" "$MODULE/common/font_safety.sh"
printf 'font payload\n' > "$MODULE/system/fonts/LuoShu-400.ttf"
# Make the test file large enough for payload validation and add aliases to the same inode.
dd if=/dev/zero bs=1024 count=4 >> "$MODULE/system/fonts/LuoShu-400.ttf" 2>/dev/null
ln "$MODULE/system/fonts/LuoShu-400.ttf" "$MODULE/system/fonts/Roboto-Regular.ttf"
ln "$MODULE/system/fonts/LuoShu-400.ttf" "$MODULE/system/fonts/GoogleSans-Regular.ttf"
REAL_CKSUM=$(command -v cksum)
printf '0\n' > "$TMP/cksum-count"
cat > "$TMP/bin/cksum" <<'EOS'
#!/bin/sh
count=$(cat "$LUOSHU_CKSUM_COUNT" 2>/dev/null || printf '0')
printf '%s\n' "$((count + 1))" > "$LUOSHU_CKSUM_COUNT"
exec "$LUOSHU_REAL_CKSUM" "$@"
EOS
chmod 0755 "$TMP/bin/cksum"
PATH="$TMP/bin:$PATH" LUOSHU_REAL_CKSUM="$REAL_CKSUM" LUOSHU_CKSUM_COUNT="$TMP/cksum-count" \
MODULE_DIR="$MODULE" MODDIR="$MODULE" sh -c '
    . "$1/common/font_safety.sh"
    luoshu_payload_build_manifest
' sh "$MODULE"
test "$(cat "$TMP/cksum-count")" -eq 1
test "$(wc -l < "$MODULE/config/font-payload-manifest.conf" | tr -d '[:space:]')" -eq 3

# Finalization progress must reserve space after glyph generation and expose real stages.
grep -q '完整复合字体已生成", 80' "$ROOT/common/composite_font.py"
grep -q "mix_stage mount-sync '正在同步元模块字体负载' 96" "$ROOT/common/font_mix.sh"
grep -q "mix_stage manifest '正在生成安全启动清单' 98" "$ROOT/common/font_mix.sh"
! grep -q 'cp -af "$SYSTEM_FONTS_DIR/." "$PAYLOAD_STAGE/"' "$ROOT/common/font_mix.sh"
grep -q '_progress_message=' "$ROOT/common/v142_weighted_mix.sh"
grep -q '完整复合字体后台进程已退出' "$ROOT/common/v142_weighted_mix.sh"

# The import action must fit the full Chinese label on one line.
grep -q 'else -> 148.dp' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportOverlay.kt"
grep -q 'softWrap = false' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportOverlay.kt"
grep -q 'modifier = modifier.fillMaxWidth()' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportOverlay.kt"

echo 'Mix finalization reuses hard-link checksums, reports real stages, and keeps the full import label.'
