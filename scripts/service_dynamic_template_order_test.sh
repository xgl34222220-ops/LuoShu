#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SERVICE="$ROOT/service.sh"

release_line=$(grep -n 'device_font_dynamic_mount_release' "$SERVICE" | head -n1 | cut -d: -f1)
template_line=$(grep -n 'device_font_template.sh" ensure' "$SERVICE" | head -n1 | cut -d: -f1)
rebuild_line=$(grep -n 'luoshu_rebuild_preserved_payload "\$MODDIR"' "$SERVICE" | head -n1 | cut -d: -f1)

case "$release_line:$template_line:$rebuild_line" in
    *[!0-9:]*|::*|:*:|:*) echo 'missing service ordering marker' >&2; exit 1 ;;
esac
[ "$release_line" -lt "$template_line" ]
[ "$template_line" -lt "$rebuild_line" ]

grep -q '_device_template_ready=0' "$SERVICE"
grep -q '\[ "\$_device_template_ready" -eq 1 \].*\\' "$SERVICE"
grep -q '本次禁止使用旧模板重建' "$SERVICE"
grep -q '原厂模板未就绪' "$SERVICE"
sh -n "$SERVICE"

echo 'Service releases the dynamic view, refreshes the stock template, then permits rebuild.'
