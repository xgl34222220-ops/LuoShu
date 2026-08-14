#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
MOD="$TMP/module"; HIST="$MOD/config/switch_history"
mkdir -p "$MOD/config" "$MOD/common"
cat > "$MOD/common/font_switch_task.sh" <<'EOF'
#!/bin/sh
printf '{"status":"ok","kind":"direct","font":"%s"}\n' "$2"
EOF
cat > "$MOD/common/font_mix_controller.sh" <<'EOF'
#!/bin/sh
printf '{"status":"ok","kind":"mix","cjk":"%s","latin":"%s","digit":"%s"}\n' "$2" "$3" "$4"
EOF
chmod +x "$MOD/common/"*.sh
MODDIR="$MOD" LUOSHU_HISTORY_DIR="$HIST" sh "$ROOT/system/bin/luoshu-history" record-direct A
MODDIR="$MOD" LUOSHU_HISTORY_DIR="$HIST" sh "$ROOT/system/bin/luoshu-history" record-direct A
[ "$(find "$HIST" -type f | wc -l)" -eq 1 ]
cat > "$MOD/config/axes_task.conf" <<EOF
state=success
EOF
cat > "$MOD/config/font_mix.conf" <<EOF
cjk=CJK
latin=LAT
digit=NUM
cjkAxes=wght=410
latinAxes=wght=420
digitAxes=wght=430
EOF
MODDIR="$MOD" LUOSHU_HISTORY_DIR="$HIST" sh "$ROOT/system/bin/luoshu-history" record-mix
OUT=$(MODDIR="$MOD" LUOSHU_HISTORY_DIR="$HIST" sh "$ROOT/system/bin/luoshu-history" list)
printf '%s' "$OUT" | grep -q '"type":"mix"'
printf '%s' "$OUT" | grep -q '"type":"direct"'
MIX_ID=$(ls -1t "$HIST"/*mix.conf | head -n1 | xargs basename .conf 2>/dev/null || true)
# basename suffix portability
MIX_ID=$(basename "$(ls -1t "$HIST"/*mix.conf | head -n1)" .conf)
RESTORED=$(MODDIR="$MOD" LUOSHU_HISTORY_DIR="$HIST" sh "$ROOT/system/bin/luoshu-history" restore "$MIX_ID")
printf '%s' "$RESTORED" | grep -q '"kind":"mix"'
echo 'switch history tests passed'
