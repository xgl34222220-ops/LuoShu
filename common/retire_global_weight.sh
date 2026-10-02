#!/system/bin/sh
# One-time retirement, never overwrite a later user/system setting.
set +e
MODDIR="${1:-${MODDIR:-/data/adb/modules/LuoShu}}"
CONFIG="$MODDIR/config"
SAVED="$CONFIG/font_weight.conf"
ORIGINAL="$CONFIG/font_weight_original.conf"
[ -f "$SAVED" ] || exit 0
command -v settings >/dev/null 2>&1 || exit 1
saved=$(sed -n 's/^adjustment=//p' "$SAVED" | head -n1)
original=$(sed -n 's/^adjustment=//p' "$ORIGINAL" 2>/dev/null | head -n1)
valid_int() { case "$1" in ''|*[!0-9-]*|--*|*-*-*) return 1 ;; esac; [ "$1" -ge -1000 ] 2>/dev/null && [ "$1" -le 1000 ] 2>/dev/null; }
# Without a recorded original, do not invent a reset value.
valid_int "$saved" && valid_int "$original" || exit 1
current=$(settings --user current get secure font_weight_adjustment 2>/dev/null)
valid_int "$current" || current=$(settings get secure font_weight_adjustment 2>/dev/null)
valid_int "$current" || exit 1
if [ "$current" = "$saved" ]; then
    settings --user current put secure font_weight_adjustment "$original" >/dev/null 2>&1 || \
        settings put secure font_weight_adjustment "$original" >/dev/null 2>&1 || exit 1
fi
# Keep a reversible small backup, outside all active configuration readers.
archive="$CONFIG/recovery/retired-global-weight"
mkdir -p "$archive" || exit 1
cp -p "$SAVED" "$archive/font_weight.conf" || exit 1
cp -p "$ORIGINAL" "$archive/font_weight_original.conf" || exit 1
cmp -s "$SAVED" "$archive/font_weight.conf" && cmp -s "$ORIGINAL" "$archive/font_weight_original.conf" || exit 1
rm -f "$SAVED" "$ORIGINAL" "$CONFIG/font_weight_reboot_required.conf"
exit 0
