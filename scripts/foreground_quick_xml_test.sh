#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

export MODULE_DIR="$TMP/module" MODDIR="$TMP/module"
PAYLOAD="$MODULE_DIR/.luoshu-payload"
mkdir -p "$MODULE_DIR/config" "$MODULE_DIR/logs" \
    "$PAYLOAD/system/fonts/.luoshu-font-store" "$PAYLOAD/system/etc"

dd if=/dev/zero of="$PAYLOAD/system/fonts/.luoshu-font-store/regular.font" \
    bs=2048 count=1 2>/dev/null

. "$ROOT/common/font_config_runtime.sh"
. "$ROOT/common/font_config_weights.sh"
. "$ROOT/common/device_font_payload_policy.sh"
# Runtime libraries deliberately use permissive Android-shell semantics. Restore
# strict test semantics so a failed policy call cannot be printed as PASS.
set -eu

_lfrp_payload_root() { printf '%s\n' "$PAYLOAD"; }
_luoshu_font_config_specs() {
    printf 'system/fonts.xml|%s|%s|%s\n' \
        "$TMP/stock-fonts.xml" "$PAYLOAD/system/etc/fonts.xml" "$PAYLOAD/system/fonts"
}
_luoshu_font_config_generate_base() {
    printf 'generate\n' >> "$TMP/generator.calls"
    printf '<family><font>LuoShu-400.ttf</font></family>\n' > "$PAYLOAD/system/etc/fonts.xml"
    printf 'mode=enabled\nfamily=%s\nconfigs=1\ntime=1\n' "$1" \
        > "$MODULE_DIR/config/font-config-overlay.conf"
}
device_font_payload_build_install() {
    printf '%s\n' "$1" >> "$TMP/final-builder.calls"
    for prefix in LuoShu LuoShuMono; do
        for weight in 100 200 300 400 500 600 700 800 900; do
            ln "$PAYLOAD/system/fonts/.luoshu-font-store/regular.font" \
                "$PAYLOAD/system/fonts/${prefix}-${weight}.ttf"
        done
    done
    [ -s "$PAYLOAD/system/etc/fonts.xml" ] || _luoshu_font_config_generate_base "$1"
    return 0
}
device_font_cache_schedule() { : > "$TMP/cache.schedule"; return 99; }

IS_COLOROS=false
LUOSHU_FOREGROUND_QUICK_SWITCH=1
export IS_COLOROS LUOSHU_FOREGROUND_QUICK_SWITCH

font_config_enable_for_payload First
test "$LUOSHU_DEVICE_PAYLOAD_RESULT" = device
test "$(wc -l < "$TMP/generator.calls" | tr -d '[:space:]')" -eq 1
test ! -e "$TMP/cache.schedule"
test "$(wc -l < "$TMP/final-builder.calls" | tr -d '[:space:]')" -eq 1

for prefix in LuoShu LuoShuMono; do
    for weight in 100 200 300 400 500 600 700 800 900; do
        test -s "$PAYLOAD/system/fonts/${prefix}-${weight}.ttf"
    done
done

# A later font-to-font switch repoints aliases but reuses the already validated, font-independent
# XML document. The generator must not run a second time.
dd if=/dev/zero bs=3072 count=1 of="$TMP/next.font" 2>/dev/null
rm -f "$PAYLOAD/system/fonts/.luoshu-font-store/regular.font"
ln "$TMP/next.font" "$PAYLOAD/system/fonts/.luoshu-font-store/regular.font"
rm -f "$PAYLOAD/system/fonts"/LuoShu-*.ttf "$PAYLOAD/system/fonts"/LuoShuMono-*.ttf
font_config_enable_for_payload Second
test "$LUOSHU_DEVICE_PAYLOAD_RESULT" = device
test "$(wc -l < "$TMP/generator.calls" | tr -d '[:space:]')" -eq 1
test "$(wc -c < "$PAYLOAD/system/fonts/LuoShu-400.ttf" | tr -d '[:space:]')" -eq 3072
test "$(wc -l < "$TMP/final-builder.calls" | tr -d '[:space:]')" -eq 2

echo 'foreground_quick_xml_test: PASS'
