#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-builder-update)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

LUOSHU_PAYLOAD_SCHEMA_CURRENT=builder-update-test-schema
export LUOSHU_PAYLOAD_SCHEMA_CURRENT
. "$ROOT/common/module_update_state.sh"

BUILDERS='common/hyperos_physical_policy.py common/hyperos_metrics_batch.py common/coloros_metrics_batch.py common/legacy_v14_4/hyperos_full_coverage.sh'
GENERATED_CACHES='cache/full-composite-v12 cache/full-composite-v7 cache/auto-multiweight-mix/composites-v9 cache/auto-multiweight-mix/composites-v3 cache/auto-multiweight-mix/prepared-v8'
COPY_TRACE="$TMP/copies.log"
cp() {
    printf '%s\n' "$@" >> "$COPY_TRACE"
    command cp "$@"
}

make_install() {
    mkdir -p "$1/config" "$1/system/fonts" "$1/common"
    printf 'id=LuoShu\nversion=v4.2.0\nversionCode=40200\n' > "$1/module.prop"
    for _fixture_builder in $BUILDERS; do
        mkdir -p "$1/${_fixture_builder%/*}"
        printf '# builder policy before update\n' > "$1/$_fixture_builder"
    done
}

OLD="$TMP/old"
NEW="$TMP/new"
make_install "$OLD"
printf 'mix\n' > "$OLD/config/active_font.conf"
printf 'cjk=CJK\nlatin=Latin\ndigit=Digit\n' > "$OLD/config/font_mix.conf"
# Reproduce customize.sh's same-schema migration even when builders changed.
printf 'schema=%s\n' "$LUOSHU_PAYLOAD_SCHEMA_CURRENT" > "$OLD/config/font-payload-schema.conf"
printf 'working font payload must remain mounted\n' > "$OLD/system/fonts/Roboto-Regular.ttf"
mkdir -p "$OLD/config/device-font-cache/current" "$OLD/config/metrics_cache"
printf 'derived old font\n' > "$OLD/config/device-font-cache/current/font.ttf"
printf 'original metric values\n' > "$OLD/config/metrics_cache/source.json"
mkdir -p "$OLD/cache/auto-multiweight-mix/source-meta-v1" "$OLD/fonts/user"
printf 'source metadata\n' > "$OLD/cache/auto-multiweight-mix/source-meta-v1/source.json"
printf 'original user font\n' > "$OLD/fonts/user/CJK.ttf"
for _cache in $GENERATED_CACHES; do
    mkdir -p "$OLD/$_cache"
    printf 'old generated font\n' > "$OLD/$_cache/font.ttf"
done

# Ordinary updates preserve their payload and reusable device cache.
make_install "$NEW"
luoshu_migrate_active_install "$OLD" "$NEW"
[ "$LUOSHU_UPDATE_REBUILD_REQUIRED" = false ]
[ ! -e "$NEW/config/font-payload-rebuild-pending.conf" ]
cmp -s "$OLD/system/fonts/Roboto-Regular.ttf" "$NEW/system/fonts/Roboto-Regular.ttf"
cmp -s "$OLD/config/device-font-cache/current/font.ttf" "$NEW/config/device-font-cache/current/font.ttf"
for _cache in $GENERATED_CACHES; do
    cmp -s "$OLD/$_cache/font.ttf" "$NEW/$_cache/font.ttf"
done

# Each physical-font builder can independently invalidate derived output. The
# live font, selection, mix sources and source metrics survive without rebuild.
for _changed_builder in $BUILDERS; do
    rm -rf "$NEW"
    make_install "$NEW"
    printf '# narrowed routing or corrected physical metrics\n' > "$NEW/$_changed_builder"
    mkdir -p "$NEW/config/device-font-cache/packaged-stale"
    printf 'stale target cache\n' > "$NEW/config/device-font-cache/packaged-stale/font.ttf"
    for _cache in $GENERATED_CACHES; do
        mkdir -p "$NEW/$_cache"
        printf 'stale staged cache\n' > "$NEW/$_cache/font.ttf"
    done
    : > "$COPY_TRACE"
    luoshu_migrate_active_install "$OLD" "$NEW"
    [ "$LUOSHU_UPDATE_REBUILD_REQUIRED" = true ]
    grep -q '^reason=font-builder-changed$' "$NEW/config/font-payload-rebuild-pending.conf"
    grep -q '^mode=preserve-current$' "$NEW/config/font-payload-rebuild-pending.conf"
    grep -q '^font=mix$' "$NEW/config/font-payload-rebuild-pending.conf"
    [ "$(cat "$NEW/config/active_font.conf")" = mix ]
    cmp -s "$OLD/config/font_mix.conf" "$NEW/config/font_mix.conf"
    cmp -s "$OLD/system/fonts/Roboto-Regular.ttf" "$NEW/system/fonts/Roboto-Regular.ttf"
    cmp -s "$OLD/config/metrics_cache/source.json" "$NEW/config/metrics_cache/source.json"
    cmp -s "$OLD/cache/auto-multiweight-mix/source-meta-v1/source.json" "$NEW/cache/auto-multiweight-mix/source-meta-v1/source.json"
    [ ! -d "$NEW/config/device-font-cache" ]
    [ -s "$OLD/config/device-font-cache/current/font.ttf" ]
    [ "$(cat "$OLD/fonts/user/CJK.ttf")" = 'original user font' ]
    for _cache in $GENERATED_CACHES; do
        [ ! -e "$NEW/$_cache" ]
        [ -s "$OLD/$_cache/font.ttf" ]
        # Absence alone would miss copying the full cache and deleting it later.
        ! grep -Fq "$OLD/$_cache/" "$COPY_TRACE"
    done
    ! grep -Fq "$OLD/config/device-font-cache/" "$COPY_TRACE"
done

# Boot confirmation only confirms the preserved payload. Even a much newer
# timestamp with matching font, schema and manifest cannot complete migration.
printf 'system/fonts/Roboto-Regular.ttf|hash|1234\n' > "$NEW/config/font-payload-manifest.conf"
cat > "$NEW/config/font-payload-boot.conf" <<'EOF_BOOT'
state=confirmed
font=mix
time=4000000000
EOF_BOOT
if MODDIR="$NEW" sh "$ROOT/common/font_boot_state.sh" reconcile-rebuild; then
    echo 'boot confirmation incorrectly cleared builder migration' >&2
    exit 1
fi
[ -s "$NEW/config/font-payload-rebuild-pending.conf" ]

# A same-font request must not reuse this old confirmed payload while the new
# builder is pending. Check a complete proof first to exclude unrelated guards.
printf 'state=verified\nmode=aligned\nactiveFont=mix\n' > "$NEW/config/device-font-load-verification.conf"
mv "$NEW/config/font-payload-rebuild-pending.conf" "$TMP/pending.conf"
MODULE_DIR="$NEW" sh -c '. "$1/common/font_active_state.sh"; luoshu_active_payload_verified mix' sh "$ROOT"
mv "$TMP/pending.conf" "$NEW/config/font-payload-rebuild-pending.conf"
if MODULE_DIR="$NEW" sh -c '. "$1/common/font_active_state.sh"; luoshu_active_payload_verified mix' sh "$ROOT"; then
    echo 'same-font apply incorrectly reused a payload from the old builder' >&2
    exit 1
fi

# A same-build reinstall before reapplying still requires explicit application.
NEXT="$TMP/next"
make_install "$NEXT"
cp -af "$NEW/common/." "$NEXT/common/"
luoshu_migrate_active_install "$NEW" "$NEXT"
[ "$LUOSHU_UPDATE_REBUILD_REQUIRED" = true ]
grep -q '^reason=font-builder-changed$' "$NEXT/config/font-payload-rebuild-pending.conf"
cmp -s "$OLD/system/fonts/Roboto-Regular.ttf" "$NEXT/system/fonts/Roboto-Regular.ttf"

# Existing commit paths consume the pending marker after applying successfully;
# the next unchanged update can then reuse its freshly generated device cache.
rm -f "$NEXT/config/font-payload-rebuild-pending.conf"
mkdir -p "$NEXT/config/device-font-cache/current"
printf 'new compact font\n' > "$NEXT/config/device-font-cache/current/font.ttf"
FINAL="$TMP/final"
make_install "$FINAL"
cp -af "$NEXT/common/." "$FINAL/common/"
luoshu_migrate_active_install "$NEXT" "$FINAL"
[ "$LUOSHU_UPDATE_REBUILD_REQUIRED" = false ]
[ ! -e "$FINAL/config/font-payload-rebuild-pending.conf" ]
cmp -s "$NEXT/config/device-font-cache/current/font.ttf" "$FINAL/config/device-font-cache/current/font.ttf"

# The default system font needs no user reapplication, even after policy changes.
printf 'default\n' > "$OLD/config/active_font.conf"
rm -rf "$NEW"
make_install "$NEW"
printf '# changed\n' > "$NEW/common/hyperos_physical_policy.py"
luoshu_migrate_active_install "$OLD" "$NEW"
[ "$LUOSHU_UPDATE_REBUILD_REQUIRED" = false ]
[ ! -e "$NEW/config/font-payload-rebuild-pending.conf" ]
[ ! -d "$NEW/config/device-font-cache" ]

echo 'Builder update policy preserves live fonts and invalidates only stale generated caches.'
