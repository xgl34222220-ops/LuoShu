#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MOD="$TMP/module"
mkdir -p "$MOD/common/python/bin" "$MOD/config" "$MOD/system/fonts/.luoshu-font-store"
: > "$MOD/common/font_config_targets.py"

COUNT="$TMP/python-count"
cat > "$MOD/common/python/bin/luoshu-python" <<'EOF_PY'
#!/bin/sh
printf '1\n' >> "${LUOSHU_SPEED_TEST_COUNT:?}"
if [ "${2:-}" = --input ]; then
    printf 'Roboto-Regular.ttf|400|sans-serif\n'
fi
EOF_PY
chmod 0755 "$MOD/common/python/bin/luoshu-python"

MODULE_DIR="$MOD"
MODDIR="$MOD"
CONFIG_DIR="$MOD/config"
LUOSHU_SPEED_TEST_COUNT="$COUNT"
export MODULE_DIR MODDIR CONFIG_DIR LUOSHU_SPEED_TEST_COUNT

. "$ROOT/common/font_config_runtime.sh"
. "$ROOT/common/font_switch_speed_hotfix.sh"

INPUT="$TMP/fonts.xml"
printf '<familyset><family><font>Roboto-Regular.ttf</font></family></familyset>\n' > "$INPUT"
_luoshu_font_config_exec "$MOD/common/font_config_targets.py" --input "$INPUT" > "$TMP/first"
_luoshu_font_config_exec "$MOD/common/font_config_targets.py" --input "$INPUT" > "$TMP/second"
cmp "$TMP/first" "$TMP/second"
test "$(wc -l < "$COUNT" | tr -d '[:space:]')" -eq 1

# Changing XML content invalidates the persistent target-discovery cache.
printf '<familyset><family><font>Roboto-Medium.ttf</font></family></familyset>\n' > "$INPUT"
_luoshu_font_config_exec "$MOD/common/font_config_targets.py" --input "$INPUT" > "$TMP/third"
test "$(wc -l < "$COUNT" | tr -d '[:space:]')" -eq 2

PREP="$TMP/prepare-count"
printf 'payload-a\n' > "$MOD/system/fonts/.luoshu-font-store/regular.font"
font_config_prepare_payload_weights() {
    printf '1\n' >> "$PREP"
    return 0
}
device_font_payload_build_install() { return 0; }
font_config_disable() { :; }

font_config_enable_for_payload 'Demo Family'
test "$LUOSHU_DEVICE_PAYLOAD_RESULT" = device
font_config_enable_for_payload 'Demo Family'
test "$LUOSHU_DEVICE_PAYLOAD_RESULT" = device
test "$(wc -l < "$PREP" | tr -d '[:space:]')" -eq 1

# A changed source token must rebuild rather than reusing a stale prepared payload.
printf 'payload-b-more-data\n' >> "$MOD/system/fonts/.luoshu-font-store/regular.font"
font_config_enable_for_payload 'Demo Family'
test "$(wc -l < "$PREP" | tr -d '[:space:]')" -eq 2

printf 'Font switch speed hotfix tests passed.\n'
