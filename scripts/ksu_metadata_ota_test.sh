#!/bin/sh
# KernelSU override.description, actionIcon metadata and system OTA detection.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d "${TMPDIR:-/tmp}/luoshu-ksumeta.XXXXXX")
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

fail() {
  printf 'ksu metadata/OTA regression: %s\n' "$*" >&2
  exit 1
}

MOD="$TMP/module"
BIN="$TMP/bin"
KSUCFG="$TMP/ksu-config"
mkdir -p "$MOD/common" "$MOD/config" "$MOD/logs" "$BIN" "$KSUCFG"
cp "$ROOT/common/module_status.sh" "$ROOT/common/system_ota_guard.sh" "$MOD/common/"
PROP_TEXT='id=LuoShu
name=洛书
description=static-shipped-description'
printf '%s\n' "$PROP_TEXT" > "$MOD/module.prop"
printf 'Demo\n' > "$MOD/config/active_font.conf"
printf 'state=mounted\nbackend=self-overlay\n' > "$MOD/config/self-mount.conf"

# Fake getprop: build identity comes from the environment.
cat > "$BIN/getprop" <<'EOF'
#!/bin/sh
case "$1" in
  ro.build.fingerprint) printf '%s\n' "${FIXTURE_FP:-}" ;;
  ro.build.version.incremental) printf '%s\n' "${FIXTURE_INC:-}" ;;
  sys.boot_completed) printf '1\n' ;;
esac
EOF
# Fake ksud implementing `module config list|get|set` (documented CLI).
cat > "$BIN/ksud" <<'EOF'
#!/bin/sh
[ "${FIXTURE_KSUD_NO_CONFIG:-0}" = 1 ] && { echo 'error: unrecognized subcommand' >&2; exit 2; }
[ "$1 $2" = "module config" ] || exit 2
[ -n "${KSU_MODULE:-}" ] || { echo 'KSU_MODULE missing' >&2; exit 3; }
dir="$FIXTURE_KSU_CONFIG/$KSU_MODULE"; mkdir -p "$dir"
case "$3" in
  list) ls "$dir" ;;
  get) [ -f "$dir/$4" ] && cat "$dir/$4" ;;
  set) printf '%s\n' "$5" > "$dir/$4"; echo set >> "$FIXTURE_KSU_CONFIG/writes" ;;
  *) exit 2 ;;
esac
EOF
chmod 0755 "$BIN/getprop" "$BIN/ksud"
export PATH="$BIN:$PATH" FIXTURE_KSU_CONFIG="$KSUCFG" FIXTURE_FP=brand/dev:16/A1/100:user/release-keys FIXTURE_INC=100
unset KSU APATCH KSU_MODULE LUOSHU_KSUD 2>/dev/null || true

status() { MODDIR="$MOD" sh "$MOD/common/module_status.sh" "$@" >/dev/null; }
override() { cat "$KSUCFG/LuoShu/override.description" 2>/dev/null; }

# 1. KernelSU with module config: override.description, module.prop untouched.
KSU=true KSU_MODULE=LuoShu LUOSHU_KSUD="$BIN/ksud" status
override | grep -q '当前字体：Demo' || fail 'override.description not set on KernelSU'
[ "$(cat "$MOD/module.prop")" = "$PROP_TEXT" ] || fail 'module.prop rewritten on KernelSU'
writes=$(wc -l < "$KSUCFG/writes")
KSU=true KSU_MODULE=LuoShu LUOSHU_KSUD="$BIN/ksud" status
[ "$(wc -l < "$KSUCFG/writes")" = "$writes" ] || fail 'unchanged description rewritten through ksud'
# KSU_MODULE absent (e.g. manual run): module id comes from module.prop.
KSU=true LUOSHU_KSUD="$BIN/ksud" status Other
override | grep -q '当前字体：Other' || fail 'override not set without KSU_MODULE'

# 2. ksud without module config -> unchanged module.prop behavior.
FIXTURE_KSUD_NO_CONFIG=1 KSU=true KSU_MODULE=LuoShu LUOSHU_KSUD="$BIN/ksud" status
grep -q '^description=Android 全局字体管理，当前字体：Demo$' "$MOD/module.prop" || fail 'no fallback to module.prop'

# 3. APatch (also exports KSU=true) and Magisk keep module.prop path.
printf '%s\n' "$PROP_TEXT" > "$MOD/module.prop"
APATCH=true KSU=true KSU_MODULE=LuoShu LUOSHU_KSUD="$BIN/ksud" status Third
grep -q '当前字体：Third' "$MOD/module.prop" || fail 'APatch did not write module.prop'
override | grep -q 'Third' && fail 'APatch wrote KernelSU override'
printf '%s\n' "$PROP_TEXT" > "$MOD/module.prop"
status Fourth
grep -q '当前字体：Fourth' "$MOD/module.prop" || fail 'Magisk did not write module.prop'

# 4. actionIcon is declared and shipped.
icon=$(sed -n 's/^actionIcon=//p' "$ROOT/module.prop")
[ -n "$icon" ] || fail 'actionIcon missing from module.prop'
[ -s "$ROOT/$icon" ] || fail "actionIcon file missing: $icon"
grep -qx "$icon" "$ROOT/scripts/module_payload_manifest.txt" || fail 'actionIcon not in payload manifest'

# 5. OTA: baseline recorded only after a successful apply.
rm -f "$MOD/config/system-build.conf" "$MOD/config/stock_inventory_scan_pending"
printf 'state=failed\n' > "$MOD/config/self-mount.conf"
status
[ ! -f "$MOD/config/system-build.conf" ] || fail 'baseline recorded without a successful apply'
printf 'default\n' > "$MOD/config/active_font.conf"
printf 'state=idle\n' > "$MOD/config/self-mount.conf"
status
[ ! -f "$MOD/config/system-build.conf" ] || fail 'baseline recorded for default font'
printf 'Demo\n' > "$MOD/config/active_font.conf"
printf 'state=mounted\n' > "$MOD/config/self-mount.conf"
status
grep -qx "fingerprint=$FIXTURE_FP" "$MOD/config/system-build.conf" || fail 'baseline fingerprint not recorded'
grep -qx 'incremental=100' "$MOD/config/system-build.conf" || fail 'baseline incremental not recorded'
[ ! -f "$MOD/config/stock_inventory_scan_pending" ] || fail 'rescan requested without OTA'

# Same build on later boots: nothing requested.
status
[ ! -f "$MOD/config/stock_inventory_scan_pending" ] || fail 'rescan requested on unchanged build'

# 6. OTA boot: rescan marker set, logged once, record moved to the new build.
FIXTURE_FP=brand/dev:16/A1/200:user/release-keys FIXTURE_INC=200 status
[ -f "$MOD/config/stock_inventory_scan_pending" ] || fail 'OTA did not request stock rescan'
grep -q '\[SYSTEM-OTA\].*100 → 200' "$MOD/logs/fontswitch.log" || fail 'OTA not logged'
grep -qx 'fingerprint=brand/dev:16/A1/200:user/release-keys' "$MOD/config/system-build.conf" || fail 'record not updated'
grep -qx 'previousFingerprint=brand/dev:16/A1/100:user/release-keys' "$MOD/config/system-build.conf" || fail 'previous build not kept'
grep -qx 'Demo' "$MOD/config/active_font.conf" || fail 'OTA changed the user selection'
rm -f "$MOD/config/stock_inventory_scan_pending"
FIXTURE_FP=brand/dev:16/A1/200:user/release-keys FIXTURE_INC=200 status
[ ! -f "$MOD/config/stock_inventory_scan_pending" ] || fail 'OTA re-triggered on the same build'
[ "$(grep -c '\[SYSTEM-OTA\]' "$MOD/logs/fontswitch.log")" = 1 ] || fail 'OTA logged more than once'

# 7. No fingerprint available (host, broken getprop): no-op.
FIXTURE_FP='' status
[ ! -f "$MOD/config/stock_inventory_scan_pending" ] || fail 'empty fingerprint treated as OTA'

printf 'KernelSU metadata and system OTA checks passed.\n'
