#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-active-state)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
CFG="$MOD/config"
mkdir -p "$CFG" "$MOD/common" "$TMP/public/fonts"
cp "$ROOT/common/font_active_state.sh" "$MOD/common/font_active_state.sh"
MODDIR="$MOD"
MODULE_DIR="$MOD"
export MODDIR MODULE_DIR

printf 'Demo\n' > "$CFG/active_font.conf"
printf 'state=confirmed\nfont=Demo\n' > "$CFG/font-payload-boot.conf"
printf 'system/fonts/Demo.ttf|hash|1234\n' > "$CFG/font-payload-manifest.conf"
printf 'schema=device-template-v2-baseline-v10-latin-coverage-v1\nfont=Demo\n' > "$CFG/font-payload-schema.conf"
printf 'state=verified\nmode=mount-confirmed\nactiveFont=Demo\n' > "$CFG/device-font-load-verification.conf"
printf 'state=mounted\n' > "$CFG/self-mount.conf"

. "$ROOT/common/font_active_state.sh"
luoshu_active_payload_verified Demo
if luoshu_active_payload_verified Other; then
    echo 'different font reused verified payload' >&2
    exit 1
fi

DIRECT_RESULT=$(MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public" \
    sh "$ROOT/common/font_manager.sh" action switch Demo)
printf '%s\n' "$DIRECT_RESULT" | grep -q '"status":"ok"'
printf '%s\n' "$DIRECT_RESULT" | grep -q '"font":"Demo"'
printf '%s\n' "$DIRECT_RESULT" | grep -q '"reused":true'
test ! -e "$CFG/text_reboot_required.conf"

printf 'state=awaiting-explicit-apply\n' > "$CFG/font-payload-rebuild-pending.conf"
if luoshu_active_payload_verified Demo; then
    echo 'schema rebuild marker was ignored' >&2
    exit 1
fi
rm -f "$CFG/font-payload-rebuild-pending.conf"

printf 'schema=device-template-v2-baseline-v9-rolegraph-v2\nfont=Demo\n' > "$CFG/font-payload-schema.conf"
if luoshu_active_payload_verified Demo; then
    echo 'stale payload schema was reused' >&2
    exit 1
fi
printf 'schema=device-template-v2-baseline-v10-latin-coverage-v1\nfont=Demo\n' > "$CFG/font-payload-schema.conf"

printf 'font=Demo\n' > "$CFG/text_reboot_required.conf"
if luoshu_active_payload_verified Demo; then
    echo 'same-boot reboot marker was ignored' >&2
    exit 1
fi
rm -f "$CFG/text_reboot_required.conf"

printf 'mix\n' > "$CFG/active_font.conf"
printf 'state=confirmed\nfont=mix\n' > "$CFG/font-payload-boot.conf"
printf 'state=verified\nmode=mount-confirmed\nactiveFont=mix\n' > "$CFG/device-font-load-verification.conf"
cat > "$CFG/font_mix.conf" <<'EOF_MIX'
cjk=CJK
latin=Latin
digit=Digit
cjkWeight=400
latinWeight=500
digitWeight=600
cjkAxes=wght=400
latinAxes=wght=500
digitAxes=wght=600
cjkMode=fixed
latinMode=auto
digitMode=fixed
EOF_MIX
luoshu_mix_request_matches_active CJK Latin Digit wght=400 wght=500 wght=600 fixed auto fixed
if luoshu_mix_request_matches_active CJK Latin Other wght=400 wght=500 wght=600 fixed auto fixed; then
    echo 'different composite request reused active payload' >&2
    exit 1
fi

AUTO_RESULT=$(MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public" \
    sh "$ROOT/common/multiweight_mix_task.sh" start CJK Latin Digit \
        wght=400 wght=500 wght=600 fixed auto fixed)
printf '%s\n' "$AUTO_RESULT" | grep -q '"reused":true'
grep -q '^state=success$' "$CFG/axes_task.conf"
grep -q '^percent=100$' "$CFG/axes_task.conf"
grep -q '^reused=true$' "$CFG/axes_task.conf"
AUTO_STATUS=$(MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public" \
    sh "$ROOT/common/weighted_mix_task.sh" status "$(sed -n 's/^task=//p' "$CFG/axes_task.conf")")
printf '%s\n' "$AUTO_STATUS" | grep -q '"reused":true'
test ! -e "$CFG/text_reboot_required.conf"

sed -i 's/^latinMode=auto$/latinMode=fixed/' "$CFG/font_mix.conf"
FIXED_RESULT=$(MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public" \
    sh "$ROOT/common/weighted_mix_task.sh" start CJK Latin Digit wght=400 wght=500 wght=600)
printf '%s\n' "$FIXED_RESULT" | grep -q '"reused":true'
grep -q '^state=success$' "$CFG/axes_task.conf"
grep -q '^reused=true$' "$CFG/axes_task.conf"
test ! -e "$CFG/text_reboot_required.conf"

sh -n "$ROOT/common/font_active_state.sh"
echo 'Verified active font and identical composite requests reuse metadata only.'
