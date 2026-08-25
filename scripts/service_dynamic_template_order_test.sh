#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SERVICE="$ROOT/service.sh"

release_line=$(grep -n 'device_font_dynamic_mount_release' "$SERVICE" | head -n1 | cut -d: -f1)
template_line=$(grep -n 'device_font_template.sh" ensure' "$SERVICE" | head -n1 | cut -d: -f1)
pending_line=$(grep -n '_pending_font=.*font-payload-rebuild-pending.conf' "$SERVICE" | head -n1 | cut -d: -f1)

case "$release_line:$template_line:$pending_line" in
    *[!0-9:]*|::*|:*:|:*) echo 'missing service ordering marker' >&2; exit 1 ;;
esac
[ "$release_line" -lt "$template_line" ]
[ "$template_line" -lt "$pending_line" ]

! grep -q 'luoshu_rebuild_preserved_payload' "$SERVICE"
! grep -q 'font_manager.sh.*action switch' "$SERVICE"
grep -q '后台服务绝不改写 active_font' "$SERVICE"
grep -q 'font-payload-reapply-notified.conf' "$SERVICE"
sh -n "$SERVICE"

echo 'Service releases the dynamic view, validates the stock template, and never mutates a preserved font.'
