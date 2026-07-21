#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "${0%/*}/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MODDIR="$TMP/module"
MODULE_DIR="$MODDIR"
export MODDIR MODULE_DIR
mkdir -p "$MODDIR/common" "$MODDIR/config" "$MODDIR/system/fonts"
cp "$ROOT/common/font_safety.sh" "$MODDIR/common/font_safety.sh"
. "$MODDIR/common/font_safety.sh"

# Transaction rollback must restore both partition payload and configuration.
dd if=/dev/zero of="$MODDIR/system/fonts/Test.ttf" bs=2048 count=1 2>/dev/null
printf 'old\n' > "$MODDIR/config/active_font.conf"
luoshu_payload_transaction_begin
printf 'changed' >> "$MODDIR/system/fonts/Test.ttf"
printf 'new\n' > "$MODDIR/config/active_font.conf"
luoshu_payload_transaction_abort
[ "$(wc -c < "$MODDIR/system/fonts/Test.ttf" | tr -d ' ')" = 2048 ]
[ "$(cat "$MODDIR/config/active_font.conf")" = old ]

# A prepared payload is allowed for one boot, then must be quarantined if boot success was never marked.
luoshu_payload_arm Demo
[ "$(sed -n 's/^state=//p' "$MODDIR/config/font-payload-boot.conf")" = prepared ]
font_config_boot_guard Demo
[ "$(sed -n 's/^state=//p' "$MODDIR/config/font-payload-boot.conf")" = booting ]
if font_config_boot_guard Demo; then
    echo 'stale boot marker was not rejected' >&2
    exit 1
fi
[ ! -d "$MODDIR/system/fonts" ]
[ "$(cat "$MODDIR/config/active_font.conf")" = default ]

# A completed boot clears the marker and resets failure history.
mkdir -p "$MODDIR/system/fonts"
dd if=/dev/zero of="$MODDIR/system/fonts/Test.ttf" bs=2048 count=1 2>/dev/null
luoshu_payload_arm Demo
font_config_boot_guard Demo
font_config_mark_boot_success
[ ! -e "$MODDIR/config/font-payload-boot.conf" ]
[ -s "$MODDIR/config/font-last-boot-success.conf" ]

echo 'font safety tests passed'
