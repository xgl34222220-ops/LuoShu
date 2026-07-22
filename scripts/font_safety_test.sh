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

# Transaction rollback must restore partition payload, configuration and the previous schema marker.
dd if=/dev/zero of="$MODDIR/system/fonts/Test.ttf" bs=2048 count=1 2>/dev/null
printf 'old\n' >"$MODDIR/config/active_font.conf"
printf 'schema=legacy-v1\n' >"$MODDIR/config/font-payload-schema.conf"
luoshu_payload_transaction_begin
printf 'changed' >>"$MODDIR/system/fonts/Test.ttf"
printf 'new\n' >"$MODDIR/config/active_font.conf"
luoshu_payload_arm Demo
[ "$(luoshu_payload_schema_read)" = "$LUOSHU_PAYLOAD_SCHEMA_CURRENT" ]
luoshu_payload_transaction_abort
[ "$(wc -c <"$MODDIR/system/fonts/Test.ttf" | tr -d ' ')" = 2048 ]
[ "$(cat "$MODDIR/config/active_font.conf")" = old ]
[ "$(luoshu_payload_schema_read)" = legacy-v1 ]

# A prepared current-schema payload is allowed for one boot, then quarantined if boot never confirms.
luoshu_payload_arm Demo
[ "$(sed -n 's/^state=//p' "$MODDIR/config/font-payload-boot.conf")" = prepared ]
[ "$(luoshu_payload_schema_read)" = "$LUOSHU_PAYLOAD_SCHEMA_CURRENT" ]
font_config_boot_guard Demo
[ "$(sed -n 's/^state=//p' "$MODDIR/config/font-payload-boot.conf")" = booting ]
if font_config_boot_guard Demo; then
    echo 'stale boot marker was not rejected' >&2
    exit 1
fi
[ ! -d "$MODDIR/system/fonts" ]
[ "$(cat "$MODDIR/config/active_font.conf")" = default ]
[ ! -e "$MODDIR/config/font-payload-schema.conf" ]
[ ! -e "$MODDIR/disable" ]
[ -s "$MODDIR/config/font-payload-quarantine.conf" ]

# Repeated recoverable font failures must never disable the entire module.
mkdir -p "$MODDIR/system/fonts"
dd if=/dev/zero of="$MODDIR/system/fonts/Test.ttf" bs=2048 count=1 2>/dev/null
printf 'Demo\n' >"$MODDIR/config/active_font.conf"
luoshu_payload_quarantine
[ "$(cat "$MODDIR/config/font-boot-failures")" -ge 2 ]
[ ! -e "$MODDIR/disable" ]

# A completed boot keeps the current schema and resets failure history.
mkdir -p "$MODDIR/system/fonts"
dd if=/dev/zero of="$MODDIR/system/fonts/Test.ttf" bs=2048 count=1 2>/dev/null
luoshu_payload_arm Demo
font_config_boot_guard Demo
font_config_mark_boot_success
[ "$(sed -n 's/^state=//p' "$MODDIR/config/font-payload-boot.conf")" = confirmed ]
font_config_boot_guard Demo
[ "$(sed -n 's/^state=//p' "$MODDIR/config/font-payload-boot.conf")" = confirmed ]
[ "$(luoshu_payload_schema_read)" = "$LUOSHU_PAYLOAD_SCHEMA_CURRENT" ]
[ -s "$MODDIR/config/font-last-boot-success.conf" ]

# Even a structurally valid old payload is rejected before Zygote when its engine schema is stale.
printf 'schema=legacy-v1\n' >"$MODDIR/config/font-payload-schema.conf"
if font_config_boot_guard Demo; then
    echo 'legacy payload schema was not rejected' >&2
    exit 1
fi
[ "$(cat "$MODDIR/config/active_font.conf")" = default ]
[ ! -e "$MODDIR/config/font-payload-schema.conf" ]

echo 'font safety and payload schema tests passed'
