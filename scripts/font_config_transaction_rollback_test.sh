#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
MOD="$TMP/module"
mkdir -p "$MOD/config" "$MOD/system/etc" "$MOD/system/fonts"
printf 'mode=enabled\nfamily=OldFamily\n' > "$MOD/config/font-config-overlay.conf"
printf '<familyset><family name="monospace"><font>OldMono.ttf</font></family></familyset>\n' > "$MOD/system/etc/fonts.xml"
printf 'old-font\n' > "$MOD/system/fonts/Old.ttf"
MODULE_DIR="$MOD"
MODDIR="$MOD"
. "$ROOT/common/font_safety.sh"
set -eu
# Keep the harness intentionally small and deterministic.
_luoshu_payload_parts() { printf '%s\n' system; }
luoshu_payload_transaction_begin || { echo 'font_config_transaction_rollback_test: FAIL - begin' >&2; exit 1; }
# This represents XML enable having succeeded, followed by payload validation failing.
printf 'mode=enabled\nfamily=NewFamily\n' > "$MOD/config/font-config-overlay.conf"
printf '<familyset><family name="monospace"><font>LuoShuMono-400.ttf</font></family></familyset>\n' > "$MOD/system/etc/fonts.xml"
printf 'new-font\n' > "$MOD/system/fonts/New.ttf"
rm -f "$MOD/system/fonts/Old.ttf"
luoshu_payload_transaction_abort
[ "$(sed -n 's/^family=//p' "$MOD/config/font-config-overlay.conf")" = OldFamily ] || { echo 'font_config_transaction_rollback_test: FAIL - overlay state not restored' >&2; exit 1; }
grep -q 'OldMono.ttf' "$MOD/system/etc/fonts.xml" || { echo 'font_config_transaction_rollback_test: FAIL - XML not restored' >&2; exit 1; }
[ -f "$MOD/system/fonts/Old.ttf" ] || { echo 'font_config_transaction_rollback_test: FAIL - old payload not restored' >&2; exit 1; }
[ ! -e "$MOD/system/fonts/New.ttf" ] || { echo 'font_config_transaction_rollback_test: FAIL - failed payload survived rollback' >&2; exit 1; }
[ -z "${LUOSHU_PAYLOAD_TXN:-}" ] || { echo 'font_config_transaction_rollback_test: FAIL - transaction not cleared' >&2; exit 1; }
echo 'font_config_transaction_rollback_test: PASS'
