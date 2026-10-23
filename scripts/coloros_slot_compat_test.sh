#!/bin/sh
# ColorOS slot compatibility mode: default off, no-op on other ROMs / default font,
# writes only unreachable OPlus slots, keeps clock/mono/icon/script slots, restores
# originals on switch-off and rolls back on failure.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SCRIPT="$ROOT/common/coloros_slot_compat.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
fail() { echo "coloros_slot_compat_test: $*" >&2; exit 1; }

sh -n "$SCRIPT" || fail 'syntax'

font() { # name magic-hex filler
    printf "$2" > "$1"
    head -c 4096 /dev/zero | tr '\0' "$3" >> "$1"
}

setup() {
    rm -rf "$TMP/w"
    mkdir -p "$TMP/w/flip" "$TMP/w/sysfonts" "$TMP/w/theme" "$TMP/w/module/common" \
        "$TMP/w/module/config" "$TMP/w/module/system/fonts/.luoshu-font-store"
    cp "$ROOT/common/coloros_flipfont.sh" "$ROOT/common/coloros_slot_compat.sh" "$TMP/w/module/common/"
    font "$TMP/w/theme/Theme-Regular.ttf" '\000\001\000\000' t
    font "$TMP/w/theme/Theme-Mono.ttf" '\000\001\000\000' m
    font "$TMP/w/sysfonts/Roboto-Medium.ttf" '\000\001\000\000' r
    head -c 70000 /dev/zero | tr '\0' b > "$TMP/w/flip/OplusOSUI-Bold.ttf"
    ln -s "$TMP/w/theme/Theme-Regular.ttf" "$TMP/w/flip/OplusOSUI-Regular.ttf"
    ln -s "$TMP/w/sysfonts/Roboto-Medium.ttf" "$TMP/w/flip/OplusOSUI-Medium.ttf"
    ln -s "$TMP/w/theme/Theme-Mono.ttf" "$TMP/w/flip/OplusOSUI-Mono-Regular.ttf"
    ln -s "$TMP/w/theme/Theme-Mono.ttf" "$TMP/w/flip/ColorOSUI-Clock-Regular.ttf"
    ln -s "$TMP/w/theme/Theme-Mono.ttf" "$TMP/w/flip/OplusOSUI-Icon.ttf"
    ln -s "$TMP/w/theme/Theme-Mono.ttf" "$TMP/w/flip/OplusOSUI-Myanmar-Regular.ttf"
    ln -s "$TMP/w/theme/Theme-Mono.ttf" "$TMP/w/flip/OplusOSUI-Italic.ttf"
    font "$TMP/w/module/system/fonts/.luoshu-font-store/regular.font" '\000\001\000\000' R
    font "$TMP/w/module/system/fonts/.luoshu-font-store/bold.font" '\000\001\000\000' B
    printf 'user-font\n' > "$TMP/w/module/config/active_font.conf"
}

run() { # action [rom]
    LUOSHU_REAL_MODDIR="$TMP/w/module" MODDIR="$TMP/w/module" \
    LUOSHU_COLOROS_FLIP_DIR="$TMP/w/flip" LUOSHU_COLOROS_FLIP_SYSTEM_FONTS="$TMP/w/sysfonts" \
    LUOSHU_COLOROS_SLOT_COMPAT_STORE="$TMP/w/store" \
    LUOSHU_COLOROS_SLOT_COMPAT_FORCE_ROM="${2:-coloros}" \
        sh "$TMP/w/module/common/coloros_slot_compat.sh" "$1"
}

snapshot() {
    for _p in "$TMP/w/flip"/* "$TMP/w/flip"/.[!.]*; do
        [ -e "$_p" ] || [ -L "$_p" ] || continue
        if [ -L "$_p" ]; then printf '%s L %s\n' "${_p##*/}" "$(readlink "$_p")"
        else printf '%s F %s\n' "${_p##*/}" "$(cksum < "$_p")"; fi
    done
}

# 1. Default off (no config): nothing written, no store created.
setup; before=$(snapshot)
run sync
[ "$(snapshot)" = "$before" ] || fail 'default off changed flip slots'
[ ! -e "$TMP/w/store" ] || fail 'default off created a store'
run status | grep -qx 'enabled=false' || fail 'status should report disabled'
printf 'enabled=0\n' > "$TMP/w/module/config/coloros_slot_compat.conf"; run sync
[ "$(snapshot)" = "$before" ] || fail 'enabled=0 changed flip slots'
printf 'enabled=true\n' > "$TMP/w/module/config/coloros_slot_compat.conf"; run sync
[ "$(snapshot)" = "$before" ] || fail 'only an exact enabled=1 may turn the mode on'

# 2. Enabled but another ROM, or the system default font: nothing written.
printf 'enabled=1\n' > "$TMP/w/module/config/coloros_slot_compat.conf"
run sync other
[ "$(snapshot)" = "$before" ] || fail 'non-ColorOS ROM changed flip slots'
printf 'default\n' > "$TMP/w/module/config/active_font.conf"; run sync
[ "$(snapshot)" = "$before" ] || fail 'default font changed flip slots'
printf 'user-font\n' > "$TMP/w/module/config/active_font.conf"

# 3. Enabled on ColorOS: unreachable slots take the weight-matched payload font.
run sync
[ -f "$TMP/w/flip/OplusOSUI-Regular.ttf" ] && [ ! -L "$TMP/w/flip/OplusOSUI-Regular.ttf" ] || fail 'external slot not written'
cmp -s "$TMP/w/flip/OplusOSUI-Regular.ttf" "$TMP/w/module/system/fonts/.luoshu-font-store/regular.font" || fail 'regular slot content'
cmp -s "$TMP/w/flip/OplusOSUI-Bold.ttf" "$TMP/w/module/system/fonts/.luoshu-font-store/bold.font" || fail 'bold slot should use bold anchor'
[ "$(readlink "$TMP/w/flip/OplusOSUI-Medium.ttf")" = "$TMP/w/sysfonts/Roboto-Medium.ttf" ] || fail 'overlay-reachable slot touched'
for n in OplusOSUI-Mono-Regular.ttf ColorOSUI-Clock-Regular.ttf OplusOSUI-Icon.ttf OplusOSUI-Myanmar-Regular.ttf OplusOSUI-Italic.ttf; do
    [ "$(readlink "$TMP/w/flip/$n")" = "$TMP/w/theme/Theme-Mono.ttf" ] || fail "protected slot touched: $n"
done
ls -A "$TMP/w/flip" | grep -q '^\.luoshu' && fail 'temp file left in flip dir'
[ "$(wc -l < "$TMP/w/store/manifest.v1" | tr -d ' ')" = 2 ] || fail 'manifest should record exactly two slots'
run status | grep -qx 'writtenSlots=2' || fail 'status writtenSlots'
manifest=$(cat "$TMP/w/store/manifest.v1")

# 4. Idempotent: a second sync keeps the first recorded originals.
run sync
[ "$(cat "$TMP/w/store/manifest.v1")" = "$manifest" ] || fail 'second sync rewrote the manifest'

# 5. Switch off: originals come back exactly.
printf 'enabled=0\n' > "$TMP/w/module/config/coloros_slot_compat.conf"; run sync
[ "$(snapshot)" = "$before" ] || fail 'switch-off did not restore originals'
[ ! -e "$TMP/w/store/manifest.v1" ] || fail 'manifest left after restore'

# 6. Failure part-way rolls every written slot back.
setup; before=$(snapshot)
printf 'enabled=1\n' > "$TMP/w/module/config/coloros_slot_compat.conf"
rm -f "$TMP/w/module/system/fonts/.luoshu-font-store/regular.font"
if run sync; then fail 'missing payload font should fail'; fi
[ "$(snapshot)" = "$before" ] || fail 'failure did not roll back'
[ ! -e "$TMP/w/store/manifest.v1" ] || fail 'manifest left after rollback'

# 7. A collection or non-font never goes into a single-face slot.
setup; before=$(snapshot)
printf 'enabled=1\n' > "$TMP/w/module/config/coloros_slot_compat.conf"
font "$TMP/w/module/system/fonts/.luoshu-font-store/regular.font" 'ttcf' C
font "$TMP/w/module/system/fonts/.luoshu-font-store/bold.font" 'ttcf' C
if run sync; then fail 'collection source should fail'; fi
[ "$(snapshot)" = "$before" ] || fail 'collection source changed slots'

# 8. Uninstall-style restore.
setup; before=$(snapshot)
printf 'enabled=1\n' > "$TMP/w/module/config/coloros_slot_compat.conf"
run sync; run restore
[ "$(snapshot)" = "$before" ] || fail 'restore action did not restore'

# 9. Protected-slot tokens stay in sync with the inventory rules.
python3 - "$ROOT" <<'PY' || fail 'deny tokens drifted from font_inventory.py'
import ast, re, sys
root = sys.argv[1]
src = open(f'{root}/common/font_inventory.py', encoding='utf-8').read()
tree = ast.parse(src)
want = set()
for node in tree.body:
    if isinstance(node, ast.Assign) and any(getattr(t, 'id', '') in ('GENERIC_DENY_FILE_TOKENS', 'GENERIC_DENY_STYLE_TOKENS') for t in node.targets):
        want |= set(ast.literal_eval(node.value))
sh = open(f'{root}/common/coloros_slot_compat.sh', encoding='utf-8').read()
block = re.search(r"_lcsc_deny_tokens\(\) \{\n    printf '%s\\n' '([^']*)'", sh)
have = set(block.group(1).split())
missing = want - have
if missing:
    print('missing tokens:', sorted(missing)); sys.exit(1)
PY

# 10. Wiring: service starts it only when switched on or restore is pending;
#     uninstall restores; App switch goes through luoshu-health.
grep -q "grep -qx 'enabled=1' \"\$MODDIR/config/coloros_slot_compat.conf\"" "$ROOT/service.sh" || fail 'service guard'
grep -q 'coloros_slot_compat.sh" restore' "$ROOT/uninstall.sh" || fail 'uninstall restore'
grep -q 'slot-compat) slot_compat' "$ROOT/system/bin/luoshu-health" || fail 'health action'
grep -qx 'common/coloros_slot_compat.sh' "$ROOT/scripts/module_payload_manifest.txt" || fail 'payload manifest'
echo 'coloros_slot_compat_test: ok'
