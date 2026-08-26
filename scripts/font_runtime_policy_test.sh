#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/assert.sh"
CASE='运行时策略'
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

MODDIR="$TMP/module"
MODULE_DIR="$MODDIR"
mkdir -p "$MODDIR/common" "$MODDIR/config"

# Minimal helpers used by the final runtime policy.
_log_step() { :; }
_font_alias() {
  rm -f "$2"
  ln "$1" "$2" 2>/dev/null || cp -f "$1" "$2"
}
_verify_font_copy() {
  test -s "$1"
  test "$(wc -c < "$1" | tr -d '[:space:]')" -ge 1024
}

. "$ROOT/common/font_runtime_policy.sh"
. "$ROOT/common/font_runtime_cleanup.sh"

mkdir -p "$MODDIR/.luoshu-payload/system/fonts" \
  "$MODDIR/.luoshu-payload/product/fonts" \
  "$TMP/visible/system/fonts" "$TMP/visible/product/fonts"

# The private tree must be selected dynamically even if it appeared after the
# policy was sourced, matching installation and App-shell namespace handoff.
ok test "$(_lfrp_payload_root)" = "$MODDIR/.luoshu-payload"
SYSTEM_FONTS_DIR="$MODDIR/system/fonts"
# A direct mapper target must preserve the real partition instead of collapsing
# product/vendor/OEM slots into system/fonts.
_lfrp_partitions() { printf '%s\n' 'system product'; }
_lfrp_visible_font_dirs() {
  case "$1" in
    system) printf '%s\n' "$TMP/visible/system/fonts" ;;
    product) printf '%s\n' "$TMP/visible/product/fonts" ;;
  esac
}

python3 - "$TMP/anchor.ttf" <<'PY'
from pathlib import Path
import sys
Path(sys.argv[1]).write_bytes((b"LuoShu-runtime-policy" * 512) + b"END")
PY
cp "$TMP/anchor.ttf" "$TMP/visible/product/fonts/Roboto-Regular.ttf"

LUOSHU_FONT_HAS_CJK=false
LUOSHU_FONT_HAS_LATIN=true
LUOSHU_FONT_HAS_MIXED=false
export LUOSHU_FONT_HAS_CJK LUOSHU_FONT_HAS_LATIN LUOSHU_FONT_HAS_MIXED

COUNT=$(_lfrp_alias_existing_targets "$TMP/anchor.ttf" Roboto-Regular.ttf)
ok test "$COUNT" -eq 1
ok test -s "$MODDIR/.luoshu-payload/product/fonts/Roboto-Regular.ttf"
no test -e "$MODDIR/.luoshu-payload/system/fonts/Roboto-Regular.ttf"

# A Latin-only font must not replace CJK or mixed fallback slots, which is the
# architectural fix for the Telegram/System Settings tofu-box failure.
_lfrp_target_allowed Roboto-Regular.ttf
! _lfrp_target_allowed NotoSansSC-Regular.otf
! _lfrp_target_allowed MiSansVF.ttf
! _lfrp_target_allowed NotoColorEmoji.ttf
_lfrp_target_allowed 400.ttf
_lfrp_target_allowed MitypeMonoVF.ttf
! _lfrp_target_allowed RobotoMono-Regular.ttf

# A complete HyperOS font must drive the CJK, Latin, numeric and Xiaomi clock slots from the same
# source inode so no page can silently fall back to stock English/digits.
rm -f "$TMP/visible/product/fonts/Roboto-Regular.ttf"
for NAME in MiSansVF.ttf Roboto-Regular.ttf 400.ttf MitypeMonoVF.ttf; do
  cp "$TMP/anchor.ttf" "$TMP/visible/system/fonts/$NAME"
done
LUOSHU_FONT_HAS_CJK=true
LUOSHU_FONT_HAS_LATIN=true
LUOSHU_FONT_HAS_MIXED=true
export LUOSHU_FONT_HAS_CJK LUOSHU_FONT_HAS_LATIN LUOSHU_FONT_HAS_MIXED
for NAME in MiSansVF.ttf Roboto-Regular.ttf 400.ttf MitypeMonoVF.ttf; do
  COUNT=$(_lfrp_alias_existing_targets "$TMP/anchor.ttf" "$NAME")
  ok test "$COUNT" -eq 1
  ok test "$(stat -c '%d:%i' "$MODDIR/.luoshu-payload/system/fonts/$NAME")" = \
    "$(stat -c '%d:%i' "$TMP/anchor.ttf")"
done

# Switching again must remove every old generated alias and generated XML from
# the canonical private payload, not only from the public compatibility view.
mkdir -p "$MODDIR/.luoshu-payload/system/etc"
cp "$TMP/anchor.ttf" "$MODDIR/.luoshu-payload/system/fonts/OldAlias.ttf"
printf '%s\n' '<family><font>LuoShu-400.ttf</font></family>' \
  > "$MODDIR/.luoshu-payload/system/etc/fonts.xml"
clear_managed_text_fonts
no test -e "$MODDIR/.luoshu-payload/system/fonts/OldAlias.ttf"
no test -e "$MODDIR/.luoshu-payload/system/etc/fonts.xml"
ok test -d "$MODDIR/.luoshu-payload/system/fonts"

echo 'font_runtime_policy_test: PASS'
