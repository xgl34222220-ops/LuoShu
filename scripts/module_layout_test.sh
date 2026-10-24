#!/bin/sh
# Keep LuoShu's shipped module layout intentionally small and comprehensible.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
MANIFEST="$ROOT/scripts/module_payload_manifest.txt"

fail() {
  printf 'module layout regression: %s\n' "$*" >&2
  exit 1
}

# Root-manager entrypoints are the only runtime shell entrypoints allowed at module root.
for path in customize.sh post-fs-data.sh post-mount.sh service.sh uninstall.sh action.sh boot-completed.sh late-load.sh emulated-soft-reboot.sh; do
  [ -f "$ROOT/$path" ] || fail "missing root hook: $path"
done
for obsolete in post-fs-data-v4.sh post-mount-v4.sh service_v4.sh; do
  [ ! -e "$ROOT/$obsolete" ] || fail "versioned internal core leaked back to module root: $obsolete"
done

# Internal implementation has exactly two layers: current core and explicit compatibility.
for path in \
  .luoshu-runtime/core/post-fs-data.sh \
  .luoshu-runtime/core/post-mount.sh \
  .luoshu-runtime/core/service.sh \
  .luoshu-runtime/core/emulated-soft-reboot.sh \
  .luoshu-runtime/compat/v227/customize.sh \
  .luoshu-runtime/compat/v227/post-fs-data.sh \
  .luoshu-runtime/compat/v227/uninstall.sh; do
  [ -f "$ROOT/$path" ] || fail "missing organized runtime core: $path"
done
for obsolete in \
  .luoshu-runtime/customize-v227.sh \
  .luoshu-runtime/post-fs-data-v227.sh \
  .luoshu-runtime/uninstall-v227.sh; do
  [ ! -e "$ROOT/$obsolete" ] || fail "old compatibility location still exists: $obsolete"
done

# The stock scanner has one canonical implementation. Version suffixes caused v2/v3/v4
# routing ambiguity and are not allowed to return.
[ -f "$ROOT/common/font_inventory_scan.py" ] || fail "canonical font scanner missing"
[ ! -e "$ROOT/common/font_inventory_scan_v3.py" ] || fail "versioned font scanner returned"
grep -q 'SCANNER_REVISION = 5' "$ROOT/common/font_inventory_scan.py" || fail "canonical scanner is not v5"

# Exact copies formerly carried inside legacy_v14_4 must stay deduplicated.
for duplicate in luoshu_composite.sh font_role_check.sh font_role_check.py; do
  [ ! -e "$ROOT/common/legacy_v14_4/$duplicate" ] || fail "duplicate legacy helper returned: $duplicate"
done
grep -q 'REALMOD/common/luoshu_composite.sh' "$ROOT/common/legacy_v14_4/mix_router.sh" || fail "legacy router does not reuse canonical composite helper"
grep -q 'REALMOD/common/font_role_check.sh' "$ROOT/common/legacy_v14_4/mix_router.sh" || fail "legacy router does not reuse canonical role checker"

# Release payload is allowlisted, never a dump of repository state.
[ -s "$MANIFEST" ] || fail "payload manifest missing"
awk 'NF && $1 !~ /^#/ { if (seen[$0]++) { print $0; bad=1 } } END { exit bad }' "$MANIFEST" >/dev/null || fail "duplicate payload manifest entries"
! grep -qx 'config' "$MANIFEST" || fail "entire repository config directory must not ship"
grep -qx 'config/active_font.conf' "$MANIFEST" || fail "active font default missing"
grep -qx 'config/version_notes.conf' "$MANIFEST" || fail "version notes default missing"
grep -qx '.luoshu-runtime' "$MANIFEST" || fail "internal runtime directory missing"
for unwanted in README.txt 兼容与目录说明.txt post-fs-data-v4.sh post-mount-v4.sh service_v4.sh common/font_inventory_scan_v3.py; do
  ! grep -qx "$unwanted" "$MANIFEST" || fail "obsolete payload entry: $unwanted"
done

# All moved shell cores must remain syntactically valid.
for path in \
  customize.sh post-fs-data.sh post-mount.sh service.sh uninstall.sh late-load.sh emulated-soft-reboot.sh \
  .luoshu-runtime/core/post-fs-data.sh \
  .luoshu-runtime/core/post-mount.sh \
  .luoshu-runtime/core/service.sh \
  .luoshu-runtime/core/emulated-soft-reboot.sh \
  .luoshu-runtime/compat/v227/customize.sh \
  .luoshu-runtime/compat/v227/post-fs-data.sh \
  .luoshu-runtime/compat/v227/uninstall.sh; do
  sh -n "$ROOT/$path" || fail "shell syntax: $path"
done

# 全局字体增强：主模块只有一个 Zygisk 入口（zygisk/<abi>.so，四个 ABI），由 build.sh 从同一份
# 源码构建；不再有独立伴随模块。Hook 只在开关开启时由 Zygisk 库安装，默认关闭。
grep -qx 'common/native_font.sh' "$MANIFEST" || fail "native font config layer not shipped"
! grep -q '^zygisk' "$MANIFEST" || fail "zygisk payload must be built, never copied from the repository"
grep -q 'build_zygisk.sh' "$ROOT/scripts/build.sh" || fail "build.sh does not build the Zygisk library"
grep -q "ZYGISK_ABIS='arm64-v8a armeabi-v7a x86_64 x86'" "$ROOT/scripts/build.sh" || fail "Zygisk ABI list changed"
[ ! -e "$ROOT/zygisk-native-font/module" ] || fail "standalone Zygisk module packaging returned"
[ "$(grep -rl 'REGISTER_ZYGISK_MODULE(' "$ROOT/zygisk-native-font/src" | wc -l | tr -d ' ')" = 1 ] || fail "exactly one Zygisk entry expected"
sh -n "$ROOT/common/native_font.sh" || fail "shell syntax: common/native_font.sh"

printf 'Module layout cleanup checks passed.\n'
