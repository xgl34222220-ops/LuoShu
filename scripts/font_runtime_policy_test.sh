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
_font_store_reset() {
  rm -rf "$1/.luoshu-font-store"
  mkdir -p "$1/.luoshu-font-store"
}
_font_anchor() {
  mkdir -p "$2/.luoshu-font-store"
  cp -f "$1" "$2/.luoshu-font-store/$3.font"
  printf '%s\n' "$2/.luoshu-font-store/$3.font"
}
USER_FONTS_DIR="$TMP/user-fonts"
mkdir -p "$USER_FONTS_DIR"
get_exact_weight_file() {
  case "$1:$2" in
    Demo:regular) printf '%s\n' "$USER_FONTS_DIR/Demo-Regular.ttf" ;;
    Demo:bold) printf '%s\n' "$USER_FONTS_DIR/Demo-Bold.ttf" ;;
    *) return 1 ;;
  esac
}

. "$ROOT/common/font_runtime_policy.sh"
. "$ROOT/common/font_runtime_cleanup.sh"

mkdir -p "$MODDIR/.luoshu-payload/system/fonts" \
  "$MODDIR/.luoshu-payload/product/fonts" \
  "$MODDIR/.luoshu-payload/future_oem/fonts" \
  "$TMP/visible/system/fonts" "$TMP/visible/product/fonts" "$TMP/visible/future_oem/fonts"

# The private tree must be selected dynamically even if it appeared after the
# policy was sourced, matching installation and App-shell namespace handoff.
ok test "$(_lfrp_payload_root)" = "$MODDIR/.luoshu-payload"
SYSTEM_FONTS_DIR="$MODDIR/system/fonts"
# A direct mapper target must preserve the real partition instead of collapsing
# product/vendor/OEM slots into system/fonts.
_lfrp_partitions() { printf '%s\n' 'system product future_oem'; }
_lfrp_visible_font_dirs() {
  case "$1" in
    system) printf '%s\n' "$TMP/visible/system/fonts" ;;
    product) printf '%s\n' "$TMP/visible/product/fonts" ;;
    future_oem) printf '%s\n' "$TMP/visible/future_oem/fonts" ;;
  esac
}

python3 - "$TMP/anchor.ttf" "$USER_FONTS_DIR/Demo-Regular.ttf" "$USER_FONTS_DIR/Demo-Bold.ttf" <<'PY'
from pathlib import Path
import sys
Path(sys.argv[1]).write_bytes((b"LuoShu-runtime-policy" * 512) + b"END")
Path(sys.argv[2]).write_bytes((b"regular-outline" * 900) + b"REG")
Path(sys.argv[3]).write_bytes((b"bold-outline" * 900) + b"BOLD")
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

# A scanner-discovered partition must remain partition-aware all the way to
# the private payload instead of collapsing into system/fonts.
cp "$TMP/anchor.ttf" "$TMP/visible/future_oem/fonts/RobotoFuture-Regular.ttf"
COUNT=$(_lfrp_alias_existing_targets "$TMP/anchor.ttf" RobotoFuture-Regular.ttf)
ok test "$COUNT" -eq 1
ok test -s "$MODDIR/.luoshu-payload/future_oem/fonts/RobotoFuture-Regular.ttf"
no test -e "$MODDIR/.luoshu-payload/system/fonts/RobotoFuture-Regular.ttf"

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

# Foreground staging must keep exact static weights separate and skip a
# missing Medium face instead of copying Regular into a 500 slot.
_font_store_reset "$MODDIR/.luoshu-payload/system/fonts"
REGULAR=$(_lfrp_prepare_family_anchors "$USER_FONTS_DIR/Demo-Regular.ttf" Demo \
  "$MODDIR/.luoshu-payload/system/fonts")
ok test -s "$REGULAR"
ok test -s "$MODDIR/.luoshu-payload/system/fonts/.luoshu-font-store/bold.font"
no test -e "$MODDIR/.luoshu-payload/system/fonts/.luoshu-font-store/medium.font"
ok test "$(_lfrp_target_weight Roboto-Bold.ttf)" -eq 700
ok test "$(_lfrp_target_weight 500.ttf)" -eq 500

_device_font_inventory_entries() {
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    /product/fonts/Roboto-Regular.ttf Roboto-Regular.ttf product TTF 400 normal xml
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    /system/fonts/Roboto-Bold.ttf Roboto-Bold.ttf system TTF 700 normal xml
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    /future_oem/fonts/Roboto-Medium.ttf Roboto-Medium.ttf future_oem TTF 500 normal xml
}
_copy_as_inventory "$USER_FONTS_DIR/Demo-Regular.ttf" "$MODDIR/.luoshu-payload/system/fonts" quick Demo
ok cmp "$MODDIR/.luoshu-payload/product/fonts/Roboto-Regular.ttf" "$USER_FONTS_DIR/Demo-Regular.ttf"
ok cmp "$MODDIR/.luoshu-payload/system/fonts/Roboto-Bold.ttf" "$USER_FONTS_DIR/Demo-Bold.ttf"
no test -e "$MODDIR/.luoshu-payload/future_oem/fonts/Roboto-Medium.ttf"
ok test "${LUOSHU_WEIGHT_PRESERVED_COUNT:-0}" -ge 1

# OriginOS uses several legacy UI files outside the normal family graph,
# including product/vivo/fonts on some builds. The final runtime policy must
# map these only for a complete mixed-script source and record the nested path
# so restoring default removes it again.
ORIGIN_REAL="$TMP/visible/product-vivo"
mkdir -p "$ORIGIN_REAL"
cp "$TMP/anchor.ttf" "$ORIGIN_REAL/VivoFont.ttf"
_luoshu_originos_root_pairs() {
  printf '%s|%s/product/vivo/fonts\n' "$ORIGIN_REAL" "$MODDIR"
}
COUNT=$(_lfrp_alias_originos_critical "$REGULAR" VivoFont.ttf)
ok test "$COUNT" -eq 1
ok test -s "$MODDIR/.luoshu-payload/product/vivo/fonts/VivoFont.ttf"
ok grep -qx 'product/vivo/fonts/VivoFont.ttf' "$MODDIR/config/font-runtime-targets.conf"

# Switching again must remove every old generated alias and generated XML from
# the canonical private payload, not only from the public compatibility view.
mkdir -p "$MODDIR/.luoshu-payload/system/etc"
cp "$TMP/anchor.ttf" "$MODDIR/.luoshu-payload/system/fonts/OldAlias.ttf"
printf '%s\n' '<family><font>LuoShu-400.ttf</font></family>' \
  > "$MODDIR/.luoshu-payload/system/etc/fonts.xml"
clear_managed_text_fonts
no test -e "$MODDIR/.luoshu-payload/product/vivo/fonts/VivoFont.ttf"
no test -e "$MODDIR/.luoshu-payload/system/fonts/OldAlias.ttf"
no test -e "$MODDIR/.luoshu-payload/system/etc/fonts.xml"
ok test -d "$MODDIR/.luoshu-payload/system/fonts"

echo 'font_runtime_policy_test: PASS'
