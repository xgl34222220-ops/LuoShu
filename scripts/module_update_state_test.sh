#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-update-state)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
SCHEMA=device-template-v2-baseline-v9-rolegraph-v2
LUOSHU_PAYLOAD_SCHEMA_CURRENT="$SCHEMA"
export LUOSHU_PAYLOAD_SCHEMA_CURRENT
OEM_PARTITIONS='my_engineering my_company my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust hw_product'

OLD="$TMP/old"
NEW="$TMP/new"
mkdir -p \
    "$OLD/config" "$OLD/system/fonts/.luoshu-font-store" "$OLD/system/etc" "$OLD/product/fonts" \
    "$OLD/cache/full-composite-v5" "$OLD/cache/auto-multiweight-mix/composites-v2" \
    "$OLD/config/device-font-cache/stale" \
    "$NEW/config" "$NEW/system/bin"
for partition in $OEM_PARTITIONS; do
    mkdir -p "$OLD/$partition/fonts"
    printf '%s payload\n' "$partition" >"$OLD/$partition/fonts/LuoShu-OEM.ttf"
done

printf 'id=LuoShu\nversion=old\n' >"$OLD/module.prop"
printf 'Qsal\n' >"$OLD/config/active_font.conf"
printf 'Twemoji\n' >"$OLD/config/active_emoji.conf"
printf 'cjk=Qsal\nlatin=Qsal\ndigit=Qsal\n' >"$OLD/config/font_mix.conf"
printf 'old notes\n' >"$OLD/config/version_notes.conf"
printf 'state=running\n' >"$OLD/config/switch_task.conf"
printf 'font=Qsal\n' >"$OLD/config/text_reboot_required.conf"
printf '123\n' >"$OLD/config/axes_worker.pid"
printf '2\n' >"$OLD/config/font-boot-failures"
printf 'state=quarantined\n' >"$OLD/config/font-payload-quarantine.conf"
printf 'state=degraded\n' >"$OLD/config/self-mount.conf"
printf '/old/source|/system/fonts|overlay\n' >"$OLD/config/self-mount-required.conf"
printf 'state=verified\nactiveFont=Qsal\n' >"$OLD/config/device-font-load-verification.conf"
printf 'Qsal payload\n' >"$OLD/system/fonts/Qsal-Regular.ttf"
printf 'anchor\n' >"$OLD/system/fonts/.luoshu-font-store/qsal.font"
printf '<familyset/>\n' >"$OLD/system/etc/fonts.xml"
printf 'OEM payload\n' >"$OLD/product/fonts/OEM-Regular.ttf"
printf 'cached composite\n' >"$OLD/cache/full-composite-v5/test.otf"
printf 'cached auto composite\n' >"$OLD/cache/auto-multiweight-mix/composites-v2/test.font"
printf 'state=ready\n' >"$OLD/config/device-font-cache/stale/cache.conf"

printf 'new notes\n' >"$NEW/config/version_notes.conf"
printf '#!/bin/sh\n' >"$NEW/system/bin/洛书"

# Test the exact production update chain: customize.sh loads module_update_state.sh first,
# then the v4 override before calling luoshu_migrate_active_install.
. "$ROOT/common/module_update_state.sh"
. "$ROOT/common/module_update_hotfix_v4.sh"

RECOVERY_OLD="$TMP/recovery-old"
RECOVERY_NEW="$TMP/recovery-new"
mkdir -p "$RECOVERY_OLD" "$RECOVERY_NEW"
printf 'id=LuoShu\nversionCode=30303\n' > "$RECOVERY_OLD/module.prop"
printf 'id=LuoShu\nversionCode=30304\n' > "$RECOVERY_NEW/module.prop"
luoshu_runtime_recovery_required "$RECOVERY_OLD" "$RECOVERY_NEW"
printf 'id=LuoShu\nversionCode=30304\n' > "$RECOVERY_OLD/module.prop"
if luoshu_runtime_recovery_required "$RECOVERY_OLD" "$RECOVERY_NEW"; then
    echo 'same-version recovery reinstall unexpectedly reset its payload' >&2
    exit 1
fi
printf 'id=LuoShu\nversionCode=30305\n' > "$RECOVERY_NEW/module.prop"
if luoshu_runtime_recovery_required "$RECOVERY_OLD" "$RECOVERY_NEW"; then
    echo 'post-recovery upgrade unexpectedly reset its clean payload' >&2
    exit 1
fi
printf 'id=LuoShu\nversionCode=30303\n' > "$RECOVERY_OLD/module.prop"
luoshu_runtime_recovery_required "$RECOVERY_OLD" "$RECOVERY_NEW"

# Missing/old schema: keep selection/config, but never inherit generated payload from a
# different engine schema. customize.sh will rebuild the same selected font before commit.
luoshu_migrate_active_install "$OLD" "$NEW"

test "$(cat "$NEW/config/active_font.conf")" = Qsal
test "$(cat "$NEW/config/active_emoji.conf")" = Twemoji
grep -q '^cjk=Qsal$' "$NEW/config/font_mix.conf"
test "$(cat "$NEW/config/version_notes.conf")" = 'new notes'
test ! -e "$NEW/system/fonts/Qsal-Regular.ttf"
test ! -e "$NEW/system/fonts/.luoshu-font-store/qsal.font"
test ! -e "$NEW/system/etc/fonts.xml"
test ! -e "$NEW/product/fonts/OEM-Regular.ttf"
for partition in $OEM_PARTITIONS; do
    test ! -e "$NEW/$partition/fonts/LuoShu-OEM.ttf"
done
test ! -e "$NEW/cache/full-composite-v5/test.otf"
test ! -e "$NEW/cache/auto-multiweight-mix/composites-v2/test.font"
test ! -e "$NEW/config/device-font-cache/stale/cache.conf"
test -f "$NEW/system/bin/洛书"
test ! -e "$NEW/config/switch_task.conf"
test ! -e "$NEW/config/text_reboot_required.conf"
test ! -e "$NEW/config/axes_worker.pid"
test ! -e "$NEW/config/font-boot-failures"
test ! -e "$NEW/config/font-payload-quarantine.conf"
test ! -e "$NEW/config/self-mount.conf"
test ! -e "$NEW/config/self-mount-required.conf"
test ! -e "$NEW/config/device-font-load-verification.conf"
test "$LUOSHU_UPDATE_ACTIVE" = Qsal
test "$LUOSHU_UPDATE_REBUILD_REQUIRED" = true
grep -q '^state=install-rebuild-required$' "$NEW/config/font-payload-rebuild-pending.conf"
grep -q '^mode=preserve-selection$' "$NEW/config/font-payload-rebuild-pending.conf"
grep -q '^reason=schema-mismatch$' "$NEW/config/font-payload-rebuild-pending.conf"
grep -q '^oldSchema=missing$' "$NEW/config/font-payload-rebuild-pending.conf"
grep -q "^newSchema=$SCHEMA$" "$NEW/config/font-payload-rebuild-pending.conf"

# Current-schema updates preserve the already validated payload and current cache generations.
CURRENT="$TMP/current"
CURRENT_NEW="$TMP/current-new"
mkdir -p "$CURRENT/config" "$CURRENT/system/fonts" \
    "$CURRENT/cache/full-composite-v12" "$CURRENT/cache/full-composite-v7" \
    "$CURRENT/cache/auto-multiweight-mix/composites-v9" "$CURRENT/cache/auto-multiweight-mix/composites-v3" \
    "$CURRENT/cache/auto-multiweight-mix/prepared-v8" "$CURRENT/config/device-font-cache/current/payload" \
    "$CURRENT/config/device-font-cache/current/overlay" "$CURRENT/config/metrics_cache" "$CURRENT_NEW/config"
printf 'id=LuoShu\nversion=current\n' >"$CURRENT/module.prop"
printf 'mix\n' >"$CURRENT/config/active_font.conf"
printf 'cjk=Qsal\nlatin=Latin\ndigit=Digit\n' >"$CURRENT/config/font_mix.conf"
printf 'schema=%s\nfont=mix\n' "$SCHEMA" >"$CURRENT/config/font-payload-schema.conf"
printf 'payload\n' >"$CURRENT/system/fonts/Qsal-Regular.ttf"
printf 'v11\n' >"$CURRENT/cache/full-composite-v12/current.font"
printf 'v5\n' >"$CURRENT/cache/full-composite-v7/current.font"
printf 'v8\n' >"$CURRENT/cache/auto-multiweight-mix/composites-v9/current.font"
printf 'v1\n' >"$CURRENT/cache/auto-multiweight-mix/composites-v3/current.font"
printf 'prepared\n' >"$CURRENT/cache/auto-multiweight-mix/prepared-v8/current.font"
for _stale_cache in full-composite-v11 full-composite-v5 \
    auto-multiweight-mix/composites-v8 auto-multiweight-mix/composites-v1; do
    mkdir -p "$CURRENT/cache/$_stale_cache"
    printf 'old glyph metric variations\n' >"$CURRENT/cache/$_stale_cache/stale.font"
done
printf '{}\n' >"$CURRENT/config/device-font-cache/current/payload/manifest.json"
printf '{}\n' >"$CURRENT/config/device-font-cache/current/overlay/overlay-manifest.json"
printf 'state=ready\nfont=mix\n' >"$CURRENT/config/device-font-cache/current/cache.conf"
printf 'metric\n' >"$CURRENT/config/metrics_cache/current.font"
luoshu_migrate_active_install "$CURRENT" "$CURRENT_NEW"
test "$LUOSHU_UPDATE_REBUILD_REQUIRED" = false
test "$(cat "$CURRENT_NEW/config/active_font.conf")" = mix
grep -q '^cjk=Qsal$' "$CURRENT_NEW/config/font_mix.conf"
test -f "$CURRENT_NEW/system/fonts/Qsal-Regular.ttf"
test -f "$CURRENT_NEW/cache/full-composite-v12/current.font"
test -f "$CURRENT_NEW/cache/full-composite-v7/current.font"
test -f "$CURRENT_NEW/cache/auto-multiweight-mix/composites-v9/current.font"
test -f "$CURRENT_NEW/cache/auto-multiweight-mix/composites-v3/current.font"
test -f "$CURRENT_NEW/cache/auto-multiweight-mix/prepared-v8/current.font"
for _stale_cache in full-composite-v11 full-composite-v5 \
    auto-multiweight-mix/composites-v8 auto-multiweight-mix/composites-v1; do
    test ! -e "$CURRENT_NEW/cache/$_stale_cache/stale.font"
done
test -f "$CURRENT_NEW/config/device-font-cache/current/cache.conf"
test -f "$CURRENT_NEW/config/device-font-cache/current/payload/manifest.json"
test -f "$CURRENT_NEW/config/metrics_cache/current.font"
test ! -e "$CURRENT_NEW/config/font-payload-rebuild-pending.conf"

# A valid current-schema payload may live only in an OEM partition and must be retained.
OPLUS_ONLY="$TMP/oplus-only"
OPLUS_ONLY_NEW="$TMP/oplus-only-new"
mkdir -p "$OPLUS_ONLY/config" "$OPLUS_ONLY/oplus_product/fonts" "$OPLUS_ONLY_NEW/config"
printf 'id=LuoShu\nversion=oplus-only\n' >"$OPLUS_ONLY/module.prop"
printf 'Qsal\n' >"$OPLUS_ONLY/config/active_font.conf"
printf 'schema=%s\nfont=Qsal\n' "$SCHEMA" >"$OPLUS_ONLY/config/font-payload-schema.conf"
printf 'oplus-only payload\n' >"$OPLUS_ONLY/oplus_product/fonts/OPPOSans-Regular.ttf"
luoshu_migrate_active_install "$OPLUS_ONLY" "$OPLUS_ONLY_NEW"
test -f "$OPLUS_ONLY_NEW/oplus_product/fonts/OPPOSans-Regular.ttf"
test "$LUOSHU_UPDATE_REBUILD_REQUIRED" = false

# A selected font with no compatible generated payload is kept as selection state and marked for
# install-time rebuild. If its source font is really unavailable, customize.sh aborts before commit.
INVALID="$TMP/invalid"
TARGET="$TMP/invalid-target"
mkdir -p "$INVALID/config" "$TARGET/config"
printf 'id=LuoShu\n' >"$INVALID/module.prop"
printf 'MissingFont\n' >"$INVALID/config/active_font.conf"
luoshu_migrate_active_install "$INVALID" "$TARGET"
test "$(cat "$TARGET/config/active_font.conf")" = MissingFont
test "$LUOSHU_UPDATE_REBUILD_REQUIRED" = true
grep -q '^mode=preserve-selection$' "$TARGET/config/font-payload-rebuild-pending.conf"

# HyperOS/ColorOS physical payloads carry their stage metrics report (compiled
# CJK collections, preservedCollections reasons) across an update. Without it,
# or after a builder change, the inherited payload keeps working this boot but
# is marked for one explicit apply. The previous switch log is carried too.
hyper_fixture() {
    _hf="$1"
    mkdir -p "$_hf/config" "$_hf/system/fonts" "$_hf/product/fonts" "$_hf/common" "$_hf/logs"
    printf 'id=LuoShu\nversion=hyper\n' >"$_hf/module.prop"
    printf 'mix\n' >"$_hf/config/active_font.conf"
    printf 'cjk=Qsal\nlatin=Latin\ndigit=Digit\n' >"$_hf/config/font_mix.conf"
    printf 'schema=%s\nfont=mix\n' "$SCHEMA" >"$_hf/config/font-payload-schema.conf"
    printf 'payload\n' >"$_hf/system/fonts/MiSansVF.ttf"
    printf 'payload\n' >"$_hf/product/fonts/MiSansVF.ttf"
    printf 'builder\n' >"$_hf/common/composite_collection_build.py"
    printf '[SAFE-TIMING] task=t event=begin phase=source_lookup_validation uptime=1.00\n' >"$_hf/logs/fontswitch.log"
}
HYPER="$TMP/hyper"; HYPER_NEW="$TMP/hyper-new"
hyper_fixture "$HYPER"
mkdir -p "$HYPER/.luoshu-payload" "$HYPER_NEW/config" "$HYPER_NEW/common"
printf 'builder\n' >"$HYPER_NEW/common/composite_collection_build.py"
printf '{"schema":"luoshu-slot-metrics-v1","collections":[]}\n' >"$HYPER/.luoshu-payload/.luoshu-metrics-report.json"
luoshu_migrate_active_install "$HYPER" "$HYPER_NEW"
test "$LUOSHU_UPDATE_REBUILD_REQUIRED" = false
test -f "$HYPER_NEW/system/fonts/MiSansVF.ttf"
grep -q luoshu-slot-metrics-v1 "$HYPER_NEW/.luoshu-payload/.luoshu-metrics-report.json"
test ! -e "$HYPER_NEW/config/font-payload-rebuild-pending.conf"
grep -q 'phase=source_lookup_validation' "$HYPER_NEW/logs/fontswitch.log"
grep -q '\[UPDATE\] module updated' "$HYPER_NEW/logs/fontswitch.log"

# A migration view (symlinked partitions only) reads the report from the real module.
VIEW="$TMP/hyper-view"; VIEW_NEW="$TMP/hyper-view-new"
mkdir -p "$VIEW/config" "$VIEW_NEW/config" "$VIEW_NEW/common"
cp "$HYPER/module.prop" "$VIEW/module.prop"; cp "$HYPER/config/"* "$VIEW/config/"
ln -s "$HYPER/system" "$VIEW/system"; ln -s "$HYPER/product" "$VIEW/product"
printf 'builder\n' >"$VIEW_NEW/common/composite_collection_build.py"
LUOSHU_UPDATE_REAL_OLD_MOD="$HYPER" luoshu_migrate_active_install "$VIEW" "$VIEW_NEW"
test "$LUOSHU_UPDATE_REBUILD_REQUIRED" = false
test -f "$VIEW_NEW/.luoshu-payload/.luoshu-metrics-report.json"

NOREPORT="$TMP/hyper-noreport"; NOREPORT_NEW="$TMP/hyper-noreport-new"
hyper_fixture "$NOREPORT"
mkdir -p "$NOREPORT_NEW/config" "$NOREPORT_NEW/common"
printf 'builder\n' >"$NOREPORT_NEW/common/composite_collection_build.py"
luoshu_migrate_active_install "$NOREPORT" "$NOREPORT_NEW"
test "$LUOSHU_UPDATE_REBUILD_REQUIRED" = true
test -f "$NOREPORT_NEW/system/fonts/MiSansVF.ttf"
grep -q '^state=awaiting-explicit-apply$' "$NOREPORT_NEW/config/font-payload-rebuild-pending.conf"
grep -q '^mode=preserve-current$' "$NOREPORT_NEW/config/font-payload-rebuild-pending.conf"
grep -q '^reason=font-builder-changed$' "$NOREPORT_NEW/config/font-payload-rebuild-pending.conf"
grep -q '^detail=metrics-report-missing$' "$NOREPORT_NEW/config/font-payload-rebuild-pending.conf"

CHANGED="$TMP/hyper-changed"; CHANGED_NEW="$TMP/hyper-changed-new"
hyper_fixture "$CHANGED"
mkdir -p "$CHANGED/.luoshu-payload" "$CHANGED_NEW/config" "$CHANGED_NEW/common"
printf '{}\n' >"$CHANGED/.luoshu-payload/.luoshu-metrics-report.json"
printf 'faster builder\n' >"$CHANGED_NEW/common/composite_collection_build.py"
luoshu_migrate_active_install "$CHANGED" "$CHANGED_NEW"
test "$LUOSHU_UPDATE_REBUILD_REQUIRED" = true
test -f "$CHANGED_NEW/system/fonts/MiSansVF.ttf"
test ! -e "$CHANGED_NEW/.luoshu-payload/.luoshu-metrics-report.json"
grep -q '^detail=builder-files-changed$' "$CHANGED_NEW/config/font-payload-rebuild-pending.conf"

FRESH="$TMP/fresh"
mkdir -p "$FRESH"
set +e
luoshu_migrate_active_install "$TMP/not-installed" "$FRESH"
FRESH_CODE=$?
set -e
test "$FRESH_CODE" -eq 2

# An unconfirmed stop must keep identity evidence and block both the canonical
# migrator and its supported old CLI override; later successful writes cannot
# mask the cleanup error.
for migrator in canonical compatibility; do
    (
        . "$ROOT/common/module_update_state.sh"
        if [ "$migrator" = compatibility ]; then
            . "$ROOT/common/module_update_hotfix_v4.sh"
        fi
        luoshu_stop_module_tasks() { return 125; }
        BLOCKED="$TMP/blocked-$migrator"
        mkdir -p "$BLOCKED/config"
        printf 'identity-evidence\n' > "$BLOCKED/config/axes_worker.pid.owner.json"
        if luoshu_clear_update_volatile "$BLOCKED"; then
            echo 'Unknown cleanup unexpectedly erased task identity' >&2
            exit 1
        fi
        grep -qx identity-evidence "$BLOCKED/config/axes_worker.pid.owner.json"
        if luoshu_migrate_active_install "$CURRENT" "$BLOCKED"; then
            echo 'Migration unexpectedly succeeded without confirmed cleanup' >&2
            exit 1
        fi
        grep -qx identity-evidence "$BLOCKED/config/axes_worker.pid.owner.json"
    )
done

# Content-addressed collection and prepared-instance caches survive even a
# builder-incompatible update, including when cache/ is the .luoshu-state link.
CACHED="$TMP/cached"
CACHED_NEW="$TMP/cached-new"
mkdir -p "$CACHED/.luoshu-state/cache/hyperos-collections-v1" \
    "$CACHED/.luoshu-state/cache/axes-mix/prepared-v1" "$CACHED_NEW"
ln -s .luoshu-state/cache "$CACHED/cache"
printf 'ttc\n' >"$CACHED/cache/hyperos-collections-v1/abc-NotoSansCJK-Regular.ttc"
printf '{}\n' >"$CACHED/cache/hyperos-collections-v1/abc-NotoSansCJK-Regular.ttc.json"
printf 'inst\n' >"$CACHED/cache/axes-mix/prepared-v1/k.font"
printf 'sha\n' >"$CACHED/cache/axes-mix/prepared-v1/k.font.sha256"
luoshu_migrate_update_cache "$CACHED" "$CACHED_NEW" false false
grep -qx ttc "$CACHED_NEW/cache/hyperos-collections-v1/abc-NotoSansCJK-Regular.ttc"
test -f "$CACHED_NEW/cache/hyperos-collections-v1/abc-NotoSansCJK-Regular.ttc.json"
grep -qx inst "$CACHED_NEW/cache/axes-mix/prepared-v1/k.font"
test -f "$CACHED_NEW/cache/axes-mix/prepared-v1/k.font.sha256"
test ! -L "$CACHED_NEW/cache"
# A state directory without the compatibility link is still found.
rm -f "$CACHED/cache"
CACHED_NEW2="$TMP/cached-new2"
mkdir -p "$CACHED_NEW2"
luoshu_migrate_update_cache "$CACHED" "$CACHED_NEW2" true
grep -qx ttc "$CACHED_NEW2/cache/hyperos-collections-v1/abc-NotoSansCJK-Regular.ttc"
grep -qx inst "$CACHED_NEW2/cache/axes-mix/prepared-v1/k.font"

echo 'Module updates preserve selection, reject incompatible generated payloads, and rebuild before commit.'
