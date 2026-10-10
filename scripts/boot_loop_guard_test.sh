#!/bin/sh
# Boot-loop guard (卡开机保护) and KernelSU late-load regression.
# Drives the real frozen routers (post-fs-data.sh, post-mount.sh,
# boot-completed.sh) with stub mount backends and a simulated boot_id.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d "${TMPDIR:-/tmp}/luoshu-bootguard.XXXXXX")
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

fail() {
  printf 'boot loop guard regression: %s\n' "$*" >&2
  exit 1
}

MOD="$TMP/module"
MOUNTS="$TMP/mounts"
BIN="$TMP/bin"
mkdir -p "$MOD/common" "$MOD/config" "$MOD/logs" "$BIN"
for file in post-fs-data.sh post-mount.sh boot-completed.sh late-load.sh action.sh; do
  cp "$ROOT/$file" "$MOD/$file"
done
for file in util_functions.sh util_functions_core.sh font_settings_policy.sh \
  boot_loop_guard.sh next_boot_payload.sh module_status.sh; do
  cp "$ROOT/common/$file" "$MOD/common/$file"
done
printf 'id=LuoShu\nname=洛书\ndescription=Android 全局字体管理，当前字体：Demo\n' > "$MOD/module.prop"
printf 'Demo\n' > "$MOD/config/active_font.conf"
printf 'enabled=true\nfont=Demo\n' > "$MOD/config/font_runtime_legacy_v14_4.conf"
cat > "$MOD/common/private_payload.sh" <<'EOF'
luoshu_private_mount_module_view() { :; }
luoshu_private_unmount_module_view() { printf 'hidden:%s\n' "${0##*/}" >> "$FIXTURE_MOUNTS"; }
EOF
cat > "$MOD/common/mount_compat.sh" <<'EOF'
luoshu_detect_root_manager() { printf '%s\n' "$FIXTURE_MANAGER"; }
luoshu_self_mount_stage_for_manager() {
  case "$1" in Magisk) printf 'post-fs-data\n' ;; *) printf 'post-mount\n' ;; esac
}
luoshu_private_self_mount_ensure() { printf 'mounted:%s\n' "${0##*/}" >> "$FIXTURE_MOUNTS"; }
luoshu_text_reboot_reconcile() { return 0; }
EOF
# module_status.sh is the Magisk boot-completed point; fake getprop.
cat > "$BIN/getprop" <<'EOF'
#!/bin/sh
[ "$1" = sys.boot_completed ] && printf '%s\n' "${FIXTURE_BOOT_COMPLETED:-0}"
EOF
chmod 0755 "$BIN/getprop"

export FIXTURE_MOUNTS="$MOUNTS" PATH="$BIN:$PATH"
unset KSU_LATE_LOAD MODDIR MODULE_DIR 2>/dev/null || true

stage() { # stage BOOT_ID MANAGER SCRIPT
  : > "$MOUNTS"
  LUOSHU_BOOTLOOP_BOOT_ID="$1" FIXTURE_MANAGER="$2" sh "$MOD/$3" >/dev/null 2>&1 || fail "$3 returned non-zero"
}
counter() { sed -n 's/^count=//p' "$MOD/config/boot-loop-guard.conf" 2>/dev/null | head -n1; }
mounted() { grep -q "^mounted:" "$MOUNTS"; }
safe() { [ -f "$MOD/config/boot-loop-safe-mode.conf" ]; }

# 1. Magisk: each started boot counts once; repeated post-fs-data is idempotent.
stage boot-a Magisk post-fs-data.sh
mounted || fail 'first boot must mount'
[ "$(counter)" = 1 ] || fail "boot-a counter=$(counter)"
stage boot-a Magisk post-fs-data.sh
[ "$(counter)" = 1 ] || fail 'same boot_id counted twice'

# 2. A completed boot (Magisk: module_status after sys.boot_completed=1) clears it.
FIXTURE_BOOT_COMPLETED=0 LUOSHU_BOOTLOOP_BOOT_ID=boot-a MODDIR="$MOD" sh "$MOD/common/module_status.sh" >/dev/null
[ "$(counter)" = 1 ] || fail 'module_status cleared counter before boot completed'
FIXTURE_BOOT_COMPLETED=1 LUOSHU_BOOTLOOP_BOOT_ID=boot-a MODDIR="$MOD" sh "$MOD/common/module_status.sh" >/dev/null
[ "$(counter)" = 0 ] || fail 'completed boot did not clear counter'

# 3. Two consecutive unfinished boots -> third boot enters safe mode, no mount.
stage boot-b Magisk post-fs-data.sh
mounted || fail 'boot-b (first unfinished) must still mount'
stage boot-c Magisk post-fs-data.sh
mounted || fail 'boot-c (one unfinished before) must still mount'
! safe || fail 'safe mode entered after only one unfinished boot'
stage boot-d Magisk post-fs-data.sh
! mounted || fail 'safe mode boot still mounted in post-fs-data'
safe || fail 'safe mode marker missing after two unfinished boots'
[ "$(counter)" = 3 ] || fail "boot-d counter=$(counter)"
grep -q '^state=failed$' "$MOD/config/self-mount.conf" || fail 'self-mount.conf not marked failed'
grep -q '^failed=boot-loop-safe-mode' "$MOD/config/self-mount.conf" || fail 'safe mode reason missing from self-mount.conf'
grep -q '\[BOOT-GUARD\].*卡开机保护' "$MOD/logs/fontswitch.log" || fail 'safe mode log line missing'
[ -f "$MOD/skip_mount" ] || fail 'skip_mount not kept in safe mode'
grep -qx 'Demo' "$MOD/config/active_font.conf" || fail 'safe mode must keep the user selection'

# 4. KernelSU/APatch stages in safe mode: post-mount and boot-completed never mount.
stage boot-d KernelSU post-mount.sh
! mounted || fail 'safe mode boot still mounted in post-mount'
stage boot-d KernelSU boot-completed.sh
! mounted || fail 'safe mode boot still mounted in boot-completed'
[ "$(counter)" = 0 ] || fail 'boot-completed did not clear counter'
safe || fail 'safe mode must stay until the user re-enables'
FIXTURE_BOOT_COMPLETED=1 LUOSHU_BOOTLOOP_BOOT_ID=boot-d MODDIR="$MOD" sh "$MOD/common/module_status.sh" >/dev/null
grep -q '^description=.*卡开机保护' "$MOD/module.prop" || fail 'module description does not show safe mode'

# 5. Sticky: the next (successful) boot stays in safe mode.
stage boot-e KernelSU post-fs-data.sh
stage boot-e KernelSU post-mount.sh
! mounted || fail 'safe mode not sticky across boots'

# 6. Re-enable through the Root manager action button.
out=$(LUOSHU_BOOTLOOP_BOOT_ID=boot-e sh "$MOD/action.sh" 2>&1) || fail "action.sh re-enable failed: $out"
printf '%s\n' "$out" | grep -q '卡开机保护已解除' || fail 'action.sh did not report re-enable'
! safe || fail 'action.sh did not clear safe mode'
[ "$(counter)" = 0 ] || fail 'action.sh did not reset counter'
stage boot-f KernelSU post-fs-data.sh
grep -q '^hidden:post-fs-data.sh$' "$MOUNTS" || fail 'KernelSU post-fs-data no longer hides payload'
stage boot-f KernelSU post-mount.sh
mounted || fail 're-enabled boot did not mount'
stage boot-f KernelSU boot-completed.sh

# 7. Default font: LuoShu mounts nothing, so boots are not counted.
printf 'default\n' > "$MOD/config/active_font.conf"
for boot in boot-g boot-h boot-i boot-j; do stage "$boot" Magisk post-fs-data.sh; done
[ "$(counter)" = 0 ] || fail 'default font boots were counted'
! safe || fail 'default font entered safe mode'
printf 'Demo\n' > "$MOD/config/active_font.conf"

# 8. App bridge style reset helper.
(
  MODDIR="$MOD"; . "$MOD/common/boot_loop_guard.sh"
  luoshu_bootloop_enter_safe_mode 3 >/dev/null
  luoshu_bootloop_safe_mode_active || exit 1
  luoshu_bootloop_reset
  ! luoshu_bootloop_safe_mode_active
) || fail 'luoshu_bootloop_reset did not leave safe mode'

# 9. KernelSU late-load.
: > "$MOUNTS"
LUOSHU_BOOTLOOP_BOOT_ID=boot-k FIXTURE_MANAGER=KernelSU sh "$MOD/late-load.sh" >/dev/null 2>&1
[ ! -s "$MOUNTS" ] || fail 'late-load.sh ran without KSU_LATE_LOAD=1'
# normal boot already ran post-fs-data -> late-load must not repeat it.
stage boot-k KernelSU post-fs-data.sh
: > "$MOUNTS"
KSU_LATE_LOAD=1 LUOSHU_BOOTLOOP_BOOT_ID=boot-k FIXTURE_MANAGER=KernelSU sh "$MOD/late-load.sh" >/dev/null 2>&1
[ ! -s "$MOUNTS" ] || fail 'late-load repeated post-fs-data on a normal boot'
before=$(counter)
: > "$MOUNTS"
KSU_LATE_LOAD=1 LUOSHU_BOOTLOOP_BOOT_ID=boot-late FIXTURE_MANAGER=KernelSU sh "$MOD/late-load.sh" >/dev/null 2>&1
grep -q '^hidden:post-fs-data.sh$' "$MOUNTS" || fail 'late-load did not run the post-fs-data pipeline'
[ "$(counter)" = "$before" ] || fail 'late-load counted a boot'
: > "$MOUNTS"
KSU_LATE_LOAD=1 LUOSHU_BOOTLOOP_BOOT_ID=boot-late FIXTURE_MANAGER=KernelSU sh "$MOD/late-load.sh" >/dev/null 2>&1
[ ! -s "$MOUNTS" ] || fail 'second late-load in the same boot ran again'
KSU_LATE_LOAD=1 LUOSHU_BOOTLOOP_BOOT_ID=boot-late FIXTURE_MANAGER=KernelSU sh "$MOD/post-mount.sh" >/dev/null 2>&1
grep -q '^mounted:post-mount.sh$' "$MOUNTS" || fail 'late-load post-mount did not mount'

# 10. A host shell that merely sources util_functions.sh is never affected.
(
  MODDIR="$MOD"; MODULE_DIR="$MOD"
  . "$MOD/common/util_functions.sh"
  type luoshu_bootloop_stage_hook >/dev/null 2>&1
) || fail 'util_functions.sh did not load the guard'

printf 'Boot loop guard and KernelSU late-load checks passed.\n'
