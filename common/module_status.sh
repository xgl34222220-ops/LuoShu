#!/system/bin/sh
# 洛书 v14：在 Root 管理器中显示简洁的当前字体状态。
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
    else
        MODDIR="/data/adb/modules/LuoShu"
    fi
fi

PROP="$MODDIR/module.prop"
ACTIVE="${1:-}"
[ -n "$ACTIVE" ] || ACTIVE=$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
[ -n "$ACTIVE" ] || ACTIVE="default"

case "$ACTIVE" in
    default) DISPLAY="系统默认字体" ;;
    *) DISPLAY=$(printf '%s' "$ACTIVE" | tr '\r\n' '  ') ;;
esac

DESCRIPTION="Android 全局字体管理，当前字体：$DISPLAY"
[ -f "$PROP" ] || exit 0
TMP="$PROP.tmp.$$"
awk -v description="$DESCRIPTION" '
BEGIN { replaced=0 }
/^description=/ { print "description=" description; replaced=1; next }
{ print }
END { if (!replaced) print "description=" description }
' "$PROP" > "$TMP" 2>/dev/null && mv -f "$TMP" "$PROP" 2>/dev/null
chmod 0644 "$PROP" 2>/dev/null || true
printf '%s\n' "$DESCRIPTION"
exit 0
