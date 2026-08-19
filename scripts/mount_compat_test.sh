#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/assert.sh"
CASE='挂载兼容'
CASE_NAME="${1:-all}"
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-mount)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

new_module() {
    MODULE="$TMP/$1/modules/LuoShu"
    META="$TMP/$1/meta"
    VISIBLE="$TMP/$1/visible"
    mkdir -p "$MODULE/common" "$MODULE/system/fonts" "$MODULE/product/fonts" \
        "$MODULE/config" "$MODULE/logs" "$META" "$VISIBLE"
    cp "$ROOT/common/mount_compat.sh" "$MODULE/common/mount_compat.sh"
    cp "$ROOT/common/mount_compat_base.sh" "$MODULE/common/mount_compat_base.sh"
    cp "$ROOT/common/mount_self_fallback.sh" "$MODULE/common/mount_self_fallback.sh"
    cp "$ROOT/common/mount_compat_policy.sh" "$MODULE/common/mount_compat_policy.sh"
    printf 'id=LuoShu\nversion=v2.2.7\nversionCode=20207\n' > "$MODULE/module.prop"
    printf 'font-a' > "$MODULE/system/fonts/Roboto-Regular.ttf"
    printf 'product-a' > "$MODULE/product/fonts/Test.ttf"
}

sync_dual() {
    MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=meta-overlayfs \
    LUOSHU_META_TEST_ROOT="$META" sh -c '
        . "$MODDIR/common/mount_compat.sh"
        luoshu_sync_mount_payload Demo
    '
}

case_dual_sync() {
    new_module dual-sync
    sync_dual
    ok test -f "$META/LuoShu/system/fonts/Roboto-Regular.ttf"
    ok test -f "$META/LuoShu/product/fonts/Test.ttf"
    ok test -f "$META/LuoShu/system/etc/luoshu/mount-probe.conf"
    ok test -f "$META/LuoShu/product/etc/luoshu/mount-probe.conf"
    ok grep -q '^engine=meta-overlayfs$' "$MODULE/config/mount_compat.conf"
    ok grep -q '^state=prepared$' "$MODULE/config/mount_compat.conf"
    ok grep -q '^partitions=system,product$' "$MODULE/config/mount_compat.conf"
}

case_dual_replace() {
    new_module dual-replace
    sync_dual
    rm -f "$MODULE/system/fonts/Roboto-Regular.ttf"
    printf stale > "$META/LuoShu/system/fonts/Old.ttf"
    sync_dual
    no test -e "$META/LuoShu/system/fonts/Old.ttf"
    no test -e "$META/LuoShu/system/fonts/Roboto-Regular.ttf"
    ok test -s "$META/LuoShu/system/etc/luoshu/mount-probe.conf"
}

case_dual_verify() {
    new_module dual-verify
    sync_dual
    mkdir -p "$VISIBLE/system/etc/luoshu" "$VISIBLE/product/etc/luoshu"
    cp "$MODULE/system/etc/luoshu/mount-probe.conf" "$VISIBLE/system/etc/luoshu/mount-probe.conf"
    cp "$MODULE/product/etc/luoshu/mount-probe.conf" "$VISIBLE/product/etc/luoshu/mount-probe.conf"
    MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=meta-overlayfs \
    LUOSHU_META_TEST_ROOT="$META" LUOSHU_VISIBLE_PROBE_ROOT="$VISIBLE" sh -c '
        . "$MODDIR/common/mount_compat.sh"
        luoshu_mount_verify_active Demo
    '
    ok grep -q '^state=verified$' "$MODULE/config/mount_compat.conf"
    ok grep -q '^verifiedPartitions=system,product$' "$MODULE/config/mount_compat.conf"
    rm -f "$VISIBLE/product/etc/luoshu/mount-probe.conf"
    if MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=meta-overlayfs \
       LUOSHU_META_TEST_ROOT="$META" LUOSHU_VISIBLE_PROBE_ROOT="$VISIBLE" sh -c '
        . "$MODDIR/common/mount_compat.sh"
        luoshu_mount_verify_active Demo
    '; then
        echo 'partition verification unexpectedly passed with product missing' >&2
        exit 1
    fi
    ok grep -q '^state=unverified$' "$MODULE/config/mount_compat.conf"
    ok grep -q '^failedPartitions=product$' "$MODULE/config/mount_compat.conf"
}

case_dual_unsupported() {
    new_module dual-unsupported
    mkdir -p "$MODULE/my_product/fonts"
    printf vendor-font > "$MODULE/my_product/fonts/Oem.ttf"
    if sync_dual; then
        echo 'unsupported meta-overlayfs partition unexpectedly succeeded' >&2
        exit 1
    fi
    ok grep -q 'my_product' "$MODULE/config/mount_compat.conf"
    MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=meta-overlayfs \
    LUOSHU_META_TEST_ROOT="$META" LUOSHU_META_EXTRA_PARTITIONS=my_product sh -c '
        . "$MODDIR/common/mount_compat.sh"
        luoshu_sync_mount_payload Demo
    '
    ok test -f "$META/LuoShu/my_product/fonts/Oem.ttf"
}

case_direct_source() {
    new_module direct

    rm -rf "$META/LuoShu"
    MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=mountify \
    LUOSHU_META_TEST_ROOT="$META" sh -c '
        . "$MODDIR/common/mount_compat.sh"
        luoshu_sync_mount_payload Demo
    '
    no test -e "$META/LuoShu"
    ok grep -q '^engine=mountify$' "$MODULE/config/mount_compat.conf"
    ok grep -q '^system|' "$MODULE/config/mount-probes-expected.conf"
    no grep -q '^product|' "$MODULE/config/mount-probes-expected.conf"

    MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=hybrid-mount \
    LUOSHU_META_TEST_BACKEND=kasumi sh -c '
        . "$MODDIR/common/mount_compat.sh"
        luoshu_sync_mount_payload Demo
    '
    ok grep -q '^engine=hybrid-mount$' "$MODULE/config/mount_compat.conf"
    ok grep -q '^backend=kasumi$' "$MODULE/config/mount_compat.conf"

    touch "$MODULE/skip_mount" "$MODULE/mount_error"
    MAGIC_CONFIG="$TMP/direct/magic-mount-config.toml"
    printf 'mountsource = "KSU"\numount = false\npartitions = [\n  "vendor", # keep existing\n]\n' > "$MAGIC_CONFIG"
    MAGIC_BEFORE=$(cksum "$MAGIC_CONFIG")
    MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=magic-mount \
    LUOSHU_MAGIC_MOUNT_CONFIG="$MAGIC_CONFIG" sh -c '
        . "$MODDIR/common/mount_compat.sh"
        luoshu_sync_mount_payload Demo
    '
    no test -e "$MODULE/skip_mount"
    no test -e "$MODULE/mount_error"
    ok test "$(cksum "$MAGIC_CONFIG")" = "$MAGIC_BEFORE"
    ok grep -q '"vendor"' "$MAGIC_CONFIG"
    no grep -q '"product"' "$MAGIC_CONFIG"
    no test -e "$MAGIC_CONFIG.luoshu.bak"
    no test -e "$MAGIC_CONFIG.luoshu.lock"

    touch "$MODULE/disable"
    printf '2\n' > "$MODULE/config/font-boot-failures"
    MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=magic-mount \
    LUOSHU_MAGIC_MOUNT_CONFIG="$MAGIC_CONFIG" sh -c '
        . "$MODDIR/common/mount_compat.sh"
        luoshu_sync_mount_payload FontA
    '
    no test -e "$MODULE/disable"
    no test -e "$MODULE/config/font-boot-failures"
    touch "$MODULE/remove"
    if MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=magic-mount \
       LUOSHU_MAGIC_MOUNT_CONFIG="$MAGIC_CONFIG" sh -c '
        . "$MODDIR/common/mount_compat.sh"
        luoshu_sync_mount_payload FontA
    '; then
        echo 'remove marker was unexpectedly cleared' >&2
        exit 1
    fi
    ok test -e "$MODULE/remove"
}

case_timeout() {
    new_module timeout
    SLOWBIN="$TMP/timeout/slowbin"
    mkdir -p "$SLOWBIN" "$TMP/timeout/source/system" "$TMP/timeout/dest/system"
    printf new > "$TMP/timeout/source/system/new.ttf"
    printf old > "$TMP/timeout/dest/system/old.ttf"
    cat > "$SLOWBIN/cp" <<'EOS'
#!/bin/sh
sleep 10
exit 1
EOS
    chmod 0755 "$SLOWBIN/cp"
    if PATH="$SLOWBIN:$PATH" MODDIR="$MODULE" MODULE_DIR="$MODULE" \
       LUOSHU_MOUNT_TIMEOUT=2 LUOSHU_META_TEST_ENGINE=native-module-mount sh -c '
        . "$MODDIR/common/mount_compat.sh"
        luoshu_mount_budget_begin
        luoshu_copy_partition_atomic "$1" "$2"
    ' sh "$TMP/timeout/source/system" "$TMP/timeout/dest/system"; then
        echo 'slow copy unexpectedly succeeded' >&2
        exit 1
    fi
    ok test -f "$TMP/timeout/dest/system/old.ttf"
    no test -e "$TMP/timeout/dest/system/new.ttf"
}

case_diagnostics() {
    new_module diagnostics
    MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=mountify \
    LUOSHU_META_TEST_CANDIDATES="mountify magic-mount" sh -c '
        . "$MODDIR/common/mount_compat.sh"
        luoshu_sync_mount_payload Demo
        luoshu_mount_status_json > "$MODDIR/config/mount_status.json"
    '
    ok grep -q '^warning=检测到多个已启用挂载模块：mountify、magic-mount$' "$MODULE/config/mount_compat.conf"
    ok grep -q '"backend":"mountify"' "$MODULE/config/mount_status.json"
    ok grep -q '"warning":"检测到多个已启用挂载模块：mountify、magic-mount"' "$MODULE/config/mount_status.json"
}

case_static_contracts() {
    ok grep -q 'for _enable_dir in "$MODPATH" "$OLD_MOD"' "$ROOT/customize.sh"
    ok grep -q 'rm -f "$_enable_dir/disable"' "$ROOT/customize.sh"
    ok grep -q 'common/mount_compat.sh' "$ROOT/common/font_mix.sh"
    ok grep -q 'luoshu_sync_mount_payload' "$ROOT/common/font_mix.sh"
    no grep -q 'luoshu_sync_mount_payload' "$ROOT/post-fs-data.sh"
    no grep -q 'luoshu_sync_mount_payload' "$ROOT/service.sh"
    no grep -q 'prepare_mount_compat.sh' "$ROOT/scripts/build.sh"

    STAGE="$TMP/static-stage"
    mkdir -p "$STAGE"
    cp -R "$ROOT/." "$STAGE/"
    rm -rf "$STAGE/.git" "$STAGE/dist" "$STAGE/common/python" 2>/dev/null || true
    ! find "$STAGE" -type f \( -name skip_mount -o -name skip_mountify \) | grep -q .
    sh -n "$ROOT/common/mount_compat.sh"
    sh -n "$ROOT/common/mount_compat_base.sh"
    sh -n "$ROOT/common/mount_compat_policy.sh"
    sh -n "$ROOT/common/mount_self_fallback.sh"
    sh -n "$ROOT/common/font_mix.sh"
    sh -n "$ROOT/common/app_bridge.sh"
    sh -n "$ROOT/post-fs-data.sh"
    sh -n "$ROOT/service.sh"
}

run_case() {
    case "$1" in
        dual-sync) case_dual_sync ;;
        dual-replace) case_dual_replace ;;
        dual-verify) case_dual_verify ;;
        dual-unsupported) case_dual_unsupported ;;
        direct) case_direct_source ;;
        timeout) case_timeout ;;
        diagnostics) case_diagnostics ;;
        static) case_static_contracts ;;
        *) echo "unknown test case: $1" >&2; exit 2 ;;
    esac
    printf 'mount compatibility case passed: %s\n' "$1"
}

if [ "$CASE_NAME" = all ]; then
    for _case in dual-sync dual-replace dual-verify dual-unsupported direct timeout diagnostics static; do
        run_case "$_case"
    done
else
    run_case "$CASE_NAME"
fi

echo 'LuoShu metamodule compatibility checks passed.'
