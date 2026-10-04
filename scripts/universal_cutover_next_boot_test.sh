#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

cat > "$TMP/fake-python" <<'SH'
#!/bin/sh
case "$1" in
  */luoshu_payload.py)
    [ "${FAKE_VALIDATE:-ok}" = ok ] || exit 1
    exit 0
    ;;
  -)
    case "$3" in
      deploymentId) printf 'new-deployment\n' ;;
      payloadDigest) printf 'new-digest\n' ;;
      *) printf '\n' ;;
    esac
    ;;
  *) exit 1 ;;
esac
SH
chmod +x "$TMP/fake-python"

# Universal activation records the exact previous production identity and clears stale states.
MOD="$TMP/universal"
mkdir -p "$MOD/common" "$MOD/config" "$MOD/.luoshu-payload/old" \
         "$MOD/.luoshu-payload-next/.luoshu-runtime/deployment"
printf '# fake\n' > "$MOD/common/luoshu_payload.py"
printf 'old\n' > "$MOD/.luoshu-payload/old/file"
printf '{}\n' > "$MOD/.luoshu-payload-next/.luoshu-runtime/deployment/deployment.json"
printf 'OldFont\n' > "$MOD/config/active_font.conf"
printf 'enabled=true\n' > "$MOD/config/font_runtime_legacy_v14_4.conf"
printf 'schema=legacy\n' > "$MOD/config/font-payload-schema.conf"
printf 'pending\n' > "$MOD/config/text_reboot_required.conf"
printf 'grade=PASS\n' > "$MOD/config/universal-font-runtime-verification.conf"
printf '{}\n' > "$MOD/config/universal-font-runtime-verification.json"
printf 'state=mounted\n' > "$MOD/config/universal-font-mount.conf"
printf 'state=staged\n' > "$MOD/config/universal-font-rollback.conf"
cat > "$MOD/config/universal-font-next.conf" <<'EOF'
state=prepared
font=NewFont
deploymentId=new-deployment
payloadDigest=new-digest
previousFont=OldFont
previousMode=legacy
previousLegacy=true
recovery=false
EOF

MODDIR="$MOD"; MODULE_DIR="$MOD"; LUOSHU_PYTHON="$TMP/fake-python"
export MODDIR MODULE_DIR LUOSHU_PYTHON
. "$ROOT/common/universal_next_boot.sh"
universal_font_next_boot_activate

grep -q '^font=NewFont$' "$MOD/config/universal-font-runtime.conf"
grep -q '^recovery=false$' "$MOD/config/universal-font-runtime.conf"
grep -q '^NewFont$' "$MOD/config/active_font.conf"
grep -q '^previousFont=OldFont$' "$MOD/config/universal-font-activated.conf"
grep -q '^previousMode=legacy$' "$MOD/config/universal-font-activated.conf"
grep -q '^previousLegacy=true$' "$MOD/config/universal-font-activated.conf"
[ ! -f "$MOD/config/font_runtime_legacy_v14_4.conf" ]
[ ! -f "$MOD/config/font-payload-schema.conf" ]
[ ! -f "$MOD/config/text_reboot_required.conf" ]
[ ! -f "$MOD/config/universal-font-runtime-verification.conf" ]
[ ! -f "$MOD/config/universal-font-runtime-verification.json" ]
[ ! -f "$MOD/config/universal-font-mount.conf" ]
[ ! -f "$MOD/config/universal-font-rollback.conf" ]
[ ! -f "$MOD/config/universal-font-next.conf" ]
RETIRED="$(sed -n 's/^retired=//p' "$MOD/config/universal-font-activated.conf")"
[ -f "$RETIRED/old/file" ]

# Classic recovery from a failed Universal boot must leave Universal mode completely.
MOD2="$TMP/classic"
mkdir -p "$MOD2/config" "$MOD2/.luoshu-payload/current" "$MOD2/.luoshu-payload-next/classic"
printf 'failed universal\n' > "$MOD2/.luoshu-payload/current/file"
printf 'classic payload\n' > "$MOD2/.luoshu-payload-next/classic/file"
printf 'BadFont\n' > "$MOD2/config/active_font.conf"
printf 'state=active\nfont=BadFont\n' > "$MOD2/config/universal-font-runtime.conf"
printf 'grade=FAIL\n' > "$MOD2/config/universal-font-runtime-verification.conf"
printf '{}\n' > "$MOD2/config/universal-font-runtime-verification.json"
printf 'state=failed\n' > "$MOD2/config/universal-font-mount.conf"
printf 'state=staged\n' > "$MOD2/config/universal-font-rollback.conf"
printf 'pending\n' > "$MOD2/config/text_reboot_required.conf"
cat > "$MOD2/config/font-payload-next.conf" <<'EOF'
state=prepared
font=ClassicFont
previousFont=BadFont
previousLegacy=false
targetMode=classic
recovery=true
EOF

MODDIR="$MOD2"; MODULE_DIR="$MOD2"
export MODDIR MODULE_DIR
. "$ROOT/common/next_boot_payload.sh"
luoshu_next_boot_activate

grep -q '^ClassicFont$' "$MOD2/config/active_font.conf"
[ ! -f "$MOD2/config/font_runtime_legacy_v14_4.conf" ]
[ ! -f "$MOD2/config/universal-font-runtime.conf" ]
[ ! -f "$MOD2/config/universal-font-runtime-verification.conf" ]
[ ! -f "$MOD2/config/universal-font-runtime-verification.json" ]
[ ! -f "$MOD2/config/universal-font-mount.conf" ]
[ ! -f "$MOD2/config/universal-font-rollback.conf" ]
[ ! -f "$MOD2/config/text_reboot_required.conf" ]
grep -q '^targetMode=classic$' "$MOD2/config/font-payload-activated.conf"
[ -f "$MOD2/.luoshu-payload/classic/file" ]

# Legacy recovery still restores the physical-safe runtime mode.
MOD3="$TMP/legacy"
mkdir -p "$MOD3/config" "$MOD3/.luoshu-payload/current" "$MOD3/.luoshu-payload-next/legacy"
printf 'failed universal\n' > "$MOD3/.luoshu-payload/current/file"
printf 'legacy payload\n' > "$MOD3/.luoshu-payload-next/legacy/file"
printf 'BadFont\n' > "$MOD3/config/active_font.conf"
printf 'state=active\nfont=BadFont\n' > "$MOD3/config/universal-font-runtime.conf"
cat > "$MOD3/config/font-payload-next.conf" <<'EOF'
state=prepared
font=LegacyFont
previousFont=BadFont
previousLegacy=false
targetMode=legacy
recovery=true
EOF

MODDIR="$MOD3"; MODULE_DIR="$MOD3"
export MODDIR MODULE_DIR
. "$ROOT/common/next_boot_payload.sh"
luoshu_next_boot_activate

grep -q '^LegacyFont$' "$MOD3/config/active_font.conf"
grep -q '^enabled=true$' "$MOD3/config/font_runtime_legacy_v14_4.conf"
grep -q '^font=LegacyFont$' "$MOD3/config/font_runtime_legacy_v14_4.conf"
[ ! -f "$MOD3/config/universal-font-runtime.conf" ]
grep -q '^targetMode=legacy$' "$MOD3/config/font-payload-activated.conf"

# A Universal payload rejected before swap keeps the previous live payload and
# restores the configured selection to the font that is actually still running.
MOD4="$TMP/rejected"
mkdir -p "$MOD4/common" "$MOD4/config" "$MOD4/.luoshu-payload/old" \
         "$MOD4/.luoshu-payload-next/.luoshu-runtime/deployment"
printf '# fake\n' > "$MOD4/common/luoshu_payload.py"
printf 'still-live\n' > "$MOD4/.luoshu-payload/old/file"
printf '{}\n' > "$MOD4/.luoshu-payload-next/.luoshu-runtime/deployment/deployment.json"
printf 'NewConfigured\n' > "$MOD4/config/active_font.conf"
printf 'enabled=true\nfont=OldLive\n' > "$MOD4/config/font_runtime_legacy_v14_4.conf"
printf 'pending\n' > "$MOD4/config/text_reboot_required.conf"
cat > "$MOD4/config/universal-font-next.conf" <<'EOF'
state=prepared
font=NewConfigured
deploymentId=new-deployment
payloadDigest=new-digest
previousFont=OldLive
previousMode=legacy
previousLegacy=true
recovery=false
EOF

MODDIR="$MOD4"; MODULE_DIR="$MOD4"; LUOSHU_PYTHON="$TMP/fake-python"; FAKE_VALIDATE=fail
export MODDIR MODULE_DIR LUOSHU_PYTHON FAKE_VALIDATE
. "$ROOT/common/universal_next_boot.sh"
universal_font_next_boot_activate >/dev/null 2>&1 || true
unset FAKE_VALIDATE

[ -f "$MOD4/.luoshu-payload/old/file" ]
[ ! -e "$MOD4/.luoshu-payload-next" ]
[ ! -f "$MOD4/config/universal-font-next.conf" ]
[ ! -f "$MOD4/config/text_reboot_required.conf" ]
grep -q '^OldLive$' "$MOD4/config/active_font.conf"
grep -q '^reason=payload-validation-failed$' "$MOD4/config/universal-font-next.failed.conf"
grep -q '^font=OldLive$' "$MOD4/config/font_runtime_legacy_v14_4.conf"

echo "universal_cutover_next_boot_test: PASS"
