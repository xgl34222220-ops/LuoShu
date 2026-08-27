#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SERVICE="$ROOT/service_v4.sh"
ROUTER="$ROOT/service.sh"

# The preserved v4 service keeps its original ordering and non-mutating guarantees.
release_line=$(grep -n 'device_font_dynamic_mount_release' "$SERVICE" | head -n1 | cut -d: -f1)
template_line=$(grep -n 'device_font_template.sh" ensure' "$SERVICE" | head -n1 | cut -d: -f1)
pending_line=$(grep -n '_pending_font=.*font-payload-rebuild-pending.conf' "$SERVICE" | head -n1 | cut -d: -f1)

case "$release_line:$template_line:$pending_line" in
    *[!0-9:]*|::*|:*:|:*) echo 'missing v4 service ordering marker' >&2; exit 1 ;;
esac
[ "$release_line" -lt "$template_line" ]
[ "$template_line" -lt "$pending_line" ]

! grep -q 'luoshu_rebuild_preserved_payload' "$SERVICE"
! grep -q 'font_manager.sh.*action switch' "$SERVICE"
grep -q '后台服务绝不改写 active_font' "$SERVICE"
grep -q 'font-payload-reapply-notified.conf' "$SERVICE"

# The root service is now a compatibility router: legacy mode must never enter that v4 chain.
grep -q 'font_runtime_legacy_v14_4.conf' "$ROUTER"
grep -q 'service_v4.sh' "$ROUTER"
! grep -q 'device_font_template.sh" ensure' "$ROUTER"
! grep -q 'font-payload-rebuild-pending.conf' "$ROUTER"
sh -n "$SERVICE"
sh -n "$ROUTER"

echo 'v4 service ordering is preserved and legacy-v14.4 boot bypasses all rebuild paths.'
