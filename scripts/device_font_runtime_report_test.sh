#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-runtime-report)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
REPORT="$TMP/report"
BIN="$TMP/bin"
mkdir -p "$MOD/config/device-font-payload" "$MOD/config/device-font-overlay" "$MOD/system/etc" "$BIN"

cat > "$MOD/module.prop" <<'EOF_PROP'
id=LuoShu
name=洛书
version=v2.2.0 Alpha 1
versionCode=20191
EOF_PROP
printf 'Fixture Font\n' > "$MOD/config/active_font.conf"
printf 'state=installed\n' > "$MOD/config/device-font-engine.conf"
printf 'state=booting\nfont=Fixture Font\ntime=1\n' > "$MOD/config/font-payload-boot.conf"
printf 'schema=device-template-v1\n' > "$MOD/config/font-payload-schema.conf"
printf '{"schema":"device-font-template-v1","slots":[]}' > "$MOD/config/device-font-template.json"
printf '{"schema":"device-font-payload-v1"}' > "$MOD/config/device-font-payload/manifest.json"
printf '{"schema":"device-font-overlay-v1"}' > "$MOD/config/device-font-overlay/overlay-manifest.json"
printf '<fontConfig><family name="emoji"/></fontConfig>\n' > "$MOD/system/etc/.luoshu-data-fonts-config.xml"
printf 'file|system/fonts/LuoShuSlot-fixture.ttf|hash|2048\n' > "$MOD/config/device-font-installed.conf"
printf 'state=prepared\nsource=system/etc/.luoshu-data-fonts-config.xml\ntarget=/data/fonts/config/config.xml\n' > "$MOD/config/device-font-dynamic-mount.conf"

cat > "$BIN/getprop" <<'EOF_GETPROP'
#!/bin/sh
case "$1" in
  ro.build.fingerprint) echo fixture/fingerprint ;;
  ro.build.version.incremental) echo fixture-incremental ;;
  ro.build.version.sdk) echo 36 ;;
  ro.build.display.id) echo FixtureOS ;;
esac
EOF_GETPROP
cat > "$BIN/cmd" <<'EOF_CMD'
#!/bin/sh
if [ "${1:-}" = font ] && [ "${2:-}" = dump ]; then
  echo 'google-sans-text -> /system/fonts/LuoShuSlot-fixture.ttf'
  exit 0
fi
exit 1
EOF_CMD
chmod 0755 "$BIN/getprop" "$BIN/cmd"

_luoshu_safety_module() { printf '%s\n' "$MOD"; }
_luoshu_safety_config() { printf '%s/config\n' "$MOD"; }
_luoshu_safety_log() { :; }
luoshu_detect_root_manager() { printf 'KernelSU\n'; }
export LUOSHU_RUNTIME_REPORT_ROOT="$REPORT"
export PATH="$BIN:$PATH"
# shellcheck disable=SC1090
. "$ROOT/common/device_font_runtime_report.sh"

font_config_mark_boot_success

grep -q '^state=confirmed$' "$MOD/config/font-payload-boot.conf"
grep -q '^moduleVersion=v2.2.0 Alpha 1$' "$REPORT/summary.txt"
grep -q '^activeFont=Fixture Font$' "$REPORT/summary.txt"
grep -q '^engineState=installed$' "$REPORT/summary.txt"
grep -q 'google-sans-text.*LuoShuSlot-fixture.ttf' "$REPORT/font-manager-dump.txt"
grep -q 'google-sans-text.*LuoShuSlot-fixture.ttf' "$REPORT/dynamic-font-proof.txt"
test -s "$REPORT/device-font-template.json"
test -s "$REPORT/device-font-payload-manifest.json"
test -s "$REPORT/device-font-overlay-manifest.json"
test -s "$REPORT/device-font-installed.conf"

# Reporting remains repeatable after the boot transaction is already confirmed.
rm -rf "$REPORT"
font_config_mark_boot_success
test -s "$REPORT/font-manager-dump.txt"

echo 'device font runtime report tests passed'
