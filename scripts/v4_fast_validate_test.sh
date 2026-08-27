#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-v4-validate)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
mkdir -p "$MOD/system/fonts/.luoshu-font-store" "$MOD/system/etc" "$MOD/config"
dd if=/dev/zero of="$MOD/system/fonts/.luoshu-font-store/mix-composite.font" bs=2048 count=1 2>/dev/null
ln "$MOD/system/fonts/.luoshu-font-store/mix-composite.font" "$MOD/system/fonts/LuoShu-400.ttf"

# 120 aliases share one inode. The foreground validator must use metadata only.
: > "$MOD/config/font-target-aliases.conf"
i=1
while [ "$i" -le 120 ]; do
    name=$(printf 'Alias%03d.ttf' "$i")
    ln "$MOD/system/fonts/.luoshu-font-store/mix-composite.font" "$MOD/system/fonts/$name"
    printf 'system/fonts/%s|system/fonts.xml|400|Test\n' "$name" >> "$MOD/config/font-target-aliases.conf"
    i=$((i + 1))
done
cat > "$MOD/config/font-target-coverage.conf" <<'EOF'
targets=120
mapped=120
status=full
EOF
cat > "$MOD/system/etc/fonts.xml" <<'EOF'
<familyset><family name="sans"><font weight="400">LuoShu-400.ttf</font></family></familyset>
EOF
printf 'mix\n' > "$MOD/config/active_font.conf"

MODULE_DIR="$MOD"
MODDIR="$MOD"
export MODULE_DIR MODDIR
_luoshu_safety_module() { printf '%s\n' "$MOD"; }
_luoshu_safety_config() { printf '%s/config\n' "$MOD"; }
_luoshu_payload_parts() { printf '%s\n' system; }
_luoshu_font_config_specs() {
    printf 'system/fonts.xml|/system/etc/fonts.xml|%s/system/etc/fonts.xml|%s/system/fonts\n' "$MOD" "$MOD"
}
_luoshu_fast_font_ok() {
    [ -f "$1" ] || return 1
    size=$(stat -c '%s' "$1" 2>/dev/null || wc -c < "$1")
    [ "$size" -ge 1024 ]
}
_luoshu_safety_log() { :; }
luoshu_meta_content_roots() { return 0; }
# Old 94% code invoked this embedded-Python path for every XML. Any call is a failure here.
_luoshu_font_config_validate() { echo 'heavy XML validator was called' >&2; return 99; }

. "$ROOT/common/font_validate_fast_v4.sh"
luoshu_payload_validate_current mix
[ "$LUOSHU_PAYLOAD_VALIDATED_ACTIVE" = mix ]

# Quarantine removes generated payload but keeps selection instead of relabeling it default.
printf 'mix\n' > "$MOD/config/active_font.conf"
luoshu_payload_quarantine
[ "$(cat "$MOD/config/active_font.conf")" = mix ]
grep -q '^selectedFont=mix$' "$MOD/config/font-payload-quarantine.conf"
grep -q '^effectiveFont=stock$' "$MOD/config/font-payload-quarantine.conf"

echo 'v4 fast validate test: ok'
