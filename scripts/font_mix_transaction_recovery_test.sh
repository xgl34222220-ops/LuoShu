#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

new_module() {
    _n="$1"; _mod="$TMP/$_n"
    mkdir -p "$_mod/system/fonts" "$_mod/config" "$_mod/common"
    cat > "$_mod/common/util_functions.sh" <<'EOF_UTIL'
luoshu_payload_validate_manifest_fast() {
    [ -f "$MODDIR/config/manifest-valid" ]
}
luoshu_payload_transaction_rollback() {
    [ -n "${LUOSHU_PAYLOAD_TXN:-}" ] && [ -d "$LUOSHU_PAYLOAD_TXN" ] || return 1
    rm -rf "$MODDIR/system/fonts"
    cp -a "$LUOSHU_PAYLOAD_TXN/system-fonts" "$MODDIR/system/fonts"
    cp -f "$LUOSHU_PAYLOAD_TXN/active_font.conf" "$MODDIR/config/active_font.conf"
    rm -rf "$LUOSHU_PAYLOAD_TXN"
    LUOSHU_PAYLOAD_TXN=''
}
EOF_UTIL
    printf '%s\n' old > "$_mod/system/fonts/payload.txt"
    printf '%s\n' "$_mod"
}

write_journal() {
    _mod="$1"; _state="$2"; _stage="$3"; _backup="$4"; _outer="${5:-}"
    {
        printf 'version=1\nstate=%s\n' "$_state"
        printf 'stage=%s\nbackup=%s\nouter=%s\n' "$_stage" "$_backup" "$_outer"
        printf 'target=%s/system/fonts\n' "$_mod"
    } > "$_mod/.font-payload-transaction.state"
}

recover() {
    MODDIR="$1" sh "$ROOT/common/font_mix.sh" recover >/dev/null
}

# Crash while only the empty staging tree exists: keep the live payload.
MOD=$(new_module prepared)
STAGE="$MOD/.font-payload-stage.101"; BACKUP="$MOD/.font-payload-backup.101"
mkdir -p "$STAGE"
write_journal "$MOD" PREPARED "$STAGE" "$BACKUP"
recover "$MOD"
test "$(cat "$MOD/system/fonts/payload.txt")" = old
test ! -e "$STAGE"; test ! -e "$MOD/.font-payload-transaction.state"

# Crash after the directory swap: restore the only known-good backup.
MOD=$(new_module swapped)
BACKUP="$MOD/.font-payload-backup.102"
mv "$MOD/system/fonts" "$BACKUP"; mkdir -p "$MOD/system/fonts"
printf '%s\n' new > "$MOD/system/fonts/payload.txt"
write_journal "$MOD" PAYLOAD_SWAPPED "" "$BACKUP"
recover "$MOD"
test "$(cat "$MOD/system/fonts/payload.txt")" = old
test ! -e "$BACKUP"; test ! -e "$MOD/.font-payload-transaction.state"

# A config commit without a valid prepared boot manifest is still incomplete.
MOD=$(new_module config-incomplete)
BACKUP="$MOD/.font-payload-backup.103"
mv "$MOD/system/fonts" "$BACKUP"; mkdir -p "$MOD/system/fonts"
printf '%s\n' new > "$MOD/system/fonts/payload.txt"
write_journal "$MOD" CONFIG_COMMITTED "" "$BACKUP"
recover "$MOD"
test "$(cat "$MOD/system/fonts/payload.txt")" = old

# The outer transaction snapshot restores config and secondary payload state, not only system/fonts.
MOD=$(new_module outer-snapshot)
OUTER="$MOD/.payload-transaction.105"; mkdir -p "$OUTER/system-fonts"
printf '%s\n' old > "$OUTER/system-fonts/payload.txt"
printf '%s\n' old-active > "$OUTER/active_font.conf"
printf '%s\n' new > "$MOD/system/fonts/payload.txt"
printf '%s\n' new-active > "$MOD/config/active_font.conf"
write_journal "$MOD" CONFIG_COMMITTED "" "" "$OUTER"
recover "$MOD"
test "$(cat "$MOD/system/fonts/payload.txt")" = old
test "$(cat "$MOD/config/active_font.conf")" = old-active
test ! -e "$OUTER"

# The prepared manifest is the durable evidence that the outer safety transaction committed.
MOD=$(new_module config-committed)
BACKUP="$MOD/.font-payload-backup.104"
mv "$MOD/system/fonts" "$BACKUP"; mkdir -p "$MOD/system/fonts"
printf '%s\n' new > "$MOD/system/fonts/payload.txt"
printf 'state=prepared\nfont=mix\n' > "$MOD/config/font-payload-boot.conf"
: > "$MOD/config/manifest-valid"
write_journal "$MOD" CONFIG_COMMITTED "" "$BACKUP"
recover "$MOD"
test "$(cat "$MOD/system/fonts/payload.txt")" = new
test ! -e "$BACKUP"; test ! -e "$MOD/.font-payload-transaction.state"

# Journal paths are never allowed to escape the module directory.
MOD=$(new_module invalid-path)
OUTSIDE="$TMP/outside-backup"; mkdir -p "$OUTSIDE"; printf safe > "$OUTSIDE/sentinel"
write_journal "$MOD" PAYLOAD_SWAPPED "" "$OUTSIDE"
recover "$MOD"
test "$(cat "$OUTSIDE/sentinel")" = safe
test -f "$MOD/.font-payload-transaction.state"

echo 'Persistent composite payload transaction recovery tests passed.'
