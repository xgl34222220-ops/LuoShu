#!/bin/sh
# A1：卸载在开机早期执行时 pm/settings 不可用。模拟这种失败，确认：
#   1. 根 uninstall.sh 不中止，v2.2.7 清理照常完成；
#   2. Google 字体恢复记录保留，单次恢复脚本放到模块目录之外；
#   3. 单次脚本在开机完成后用 pm 恢复原状态、复核、删除记录并删除自己；
#   4. 身份不符 / pm 不可用 / 开机未完成 / 已重新安装 / 超过重试次数时都不乱改。
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT INT TERM
COMPONENT=com.google.android.gms/com.google.android.gms.fonts.provider.FontsProvider

BIN="$TMP/bin"
mkdir -p "$BIN"
# getprop：sys.boot_completed 由 TEST_BOOT_COMPLETED 决定。
cat > "$BIN/getprop" <<'EOF'
#!/bin/sh
printf '%s\n' "${TEST_BOOT_COMPLETED:-0}"
EOF
# dumpsys：状态文件不存在时模拟 system_server 未启动。
cat > "$BIN/dumpsys" <<'EOF'
#!/bin/sh
[ -f "$TEST_STATE" ] || { echo "Can't find service: package"; exit 0; }
state=$(cat "$TEST_STATE")
cat <<DUMP
Activity Resolver Table:
  Non-Data Actions:
      com.google.android.gms/com.google.android.gms.fonts.provider.FontsProvider filter 1234
Packages:
  Package [com.android.other] (1111):
    appId=10001
    User 0: ceDataInode=1 installed=true hidden=false enabled=0
  Package [com.google.android.gms] (abcd):
    appId=10123
    versionCode=243
    firstInstallTime=${TEST_FIRST:-2024-01-01 00:00:00}
    User 0: ceDataInode=2 installed=true hidden=false suspended=false enabled=0
DUMP
if [ "$state" = 2 ]; then
cat <<DUMP
      disabledComponents:
        com.google.android.gms.fonts.provider.FontsProvider
DUMP
elif [ "$state" = 1 ]; then
cat <<DUMP
      enabledComponents:
        com.google.android.gms.fonts.provider.FontsProvider
DUMP
fi
cat <<DUMP

Hidden system packages:
  Package [com.google.android.gms] (old):
    appId=10123
    User 0: installed=true enabled=0
      disabledComponents:
        com.google.android.gms.fonts.provider.FontsProvider
DUMP
EOF
cat > "$BIN/pm" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "$TEST_PM_LOG"
[ -f "$TEST_STATE" ] || { echo "cmd: Can't find service: package"; exit 255; }
case "$1" in default-state) echo 0 > "$TEST_STATE" ;; enable) echo 1 > "$TEST_STATE" ;; *) exit 1 ;; esac
EOF
chmod 0755 "$BIN/getprop" "$BIN/dumpsys" "$BIN/pm"

new_case() {
    CASE="$TMP/$1"
    rm -rf "$CASE"
    STORE="$CASE/adb/luoshu/google-font-fallback"
    SERVICE_D="$CASE/adb/service.d"
    SCRIPT="$SERVICE_D/luoshu-uninstall-restore.sh"
    mkdir -p "$STORE" "$SERVICE_D" "$CASE/modules" "$CASE/modules_update"
    chmod 0700 "$STORE"
    : > "$STORE/operation.lock"
    chmod 0600 "$STORE/operation.lock"
    cat > "$STORE/user-0.json" <<EOF
{
  "user": 0,
  "appId": 10123,
  "versionCode": 243,
  "firstInstallTime": "2024-01-01 00:00:00",
  "packageState": 0,
  "component": "$COMPONENT",
  "componentState": 0,
  "declared": true,
  "schema": "luoshu-google-font-fallback-v1",
  "original": ${2:-0}
}
EOF
    chmod 0600 "$STORE/user-0.json"
    cp "$ROOT/common/google_font_deferred_restore.sh" "$SCRIPT"
    chmod 0755 "$SCRIPT"
    PM_LOG="$CASE/pm.log"
    : > "$PM_LOG"
    STATE="$CASE/component-state"
}

run_deferred() {
    PATH="$BIN:$PATH" TEST_STATE="$STATE" TEST_PM_LOG="$PM_LOG" \
    LUOSHU_DEFERRED_RESTORE_FOREGROUND=1 \
    LUOSHU_DEFERRED_RESTORE_WAIT="${WAIT:-4}" \
    LUOSHU_GOOGLE_FALLBACK_STORE="$STORE" \
    LUOSHU_GOOGLE_FALLBACK_LEGACY_STORE="$CASE/adb/luoshu-google-font-fallback" \
    LUOSHU_MODULES_DIR="$CASE/modules" \
    LUOSHU_MODULES_UPDATE_DIR="$CASE/modules_update" \
        sh "$SCRIPT"
}

# --- 1. 真实根 uninstall.sh：开机早期（未完成开机），pm 不可用 ---------------
new_case wrapper
MODDIR="$CASE/modules/LuoShu"
mkdir -p "$MODDIR/common" "$MODDIR/config" "$MODDIR/.luoshu-runtime/compat/v227" \
    "$CASE/adb/luoshu/self-mount" "$CASE/adb/luoshu/private-payload"
rm -f "$SCRIPT"
cp "$ROOT/uninstall.sh" "$MODDIR/uninstall.sh"
cp "$ROOT/common/private_payload.sh" "$ROOT/common/google_font_deferred_restore.sh" "$MODDIR/common/"
cp "$ROOT/.luoshu-runtime/compat/v227/uninstall.sh" "$MODDIR/.luoshu-runtime/compat/v227/uninstall.sh"
printf 'version=v-test\n' > "$MODDIR/module.prop"
: > "$CASE/adb/luoshu/private-payload/module-view.mounts"
cat > "$MODDIR/common/google_font_fallback.sh" <<'EOF'
#!/bin/sh
echo called >> "$TEST_PM_LOG"
exit 1
EOF
PATH="$BIN:$PATH" TEST_BOOT_COMPLETED=0 TEST_STATE="$STATE" TEST_PM_LOG="$PM_LOG" \
LUOSHU_GOOGLE_FALLBACK_STORE="$STORE" \
LUOSHU_GOOGLE_FALLBACK_LEGACY_STORE="$CASE/adb/luoshu-google-font-fallback" \
LUOSHU_SERVICE_D="$SERVICE_D" \
LUOSHU_PRIVATE_STATE_ROOT="$CASE/adb/luoshu/private-payload" \
LUOSHU_SELF_MOUNT_STATE="$CASE/adb/luoshu/self-mount" \
LUOSHU_MODULES_DIR="$CASE/modules" \
LUOSHU_MODULES_UPDATE_DIR="$CASE/modules_update" \
LUOSHU_METAMODULE_MNT="$CASE/metamodule" \
LUOSHU_MAGIC_MOUNT_CONFIG="$CASE/magic_mount/config.toml" \
    sh "$MODDIR/uninstall.sh" > "$CASE/out.log" 2>&1
[ ! -e "$MODDIR" ]                                  # v2.2.7 清理没有被跳过
[ ! -e "$CASE/adb/luoshu/self-mount" ]
[ ! -e "$CASE/adb/luoshu/private-payload" ]         # C1
[ -f "$STORE/user-0.json" ]                         # 恢复记录保留
[ ! -s "$PM_LOG" ]                                  # 未开机完成时不尝试 pm
[ -x "$SCRIPT" ]
grep -q '开机完成后自动恢复' "$CASE/out.log"
# 同一次开机稍后：开机完成，组件仍是洛书设置的“停用”。
echo 2 > "$STATE"
TEST_BOOT_COMPLETED=1 run_deferred
grep -qx "default-state --user 0 $COMPONENT" "$PM_LOG"
[ "$(cat "$STATE")" = 0 ]
[ ! -e "$STORE" ]
[ ! -e "$CASE/adb/luoshu" ]
[ ! -e "$SCRIPT" ]

# --- 2. 原状态为“启用” ------------------------------------------------------------
new_case original-enabled 1
echo 2 > "$STATE"
TEST_BOOT_COMPLETED=1 run_deferred
grep -qx "enable --user 0 $COMPONENT" "$PM_LOG"
[ "$(cat "$STATE")" = 1 ]
[ ! -e "$SCRIPT" ]
[ ! -e "$STORE" ]

# --- 3. 组件已经回到原状态：只清理记录，不调用 pm ---------------------------------
new_case already-restored
echo 0 > "$STATE"
TEST_BOOT_COMPLETED=1 run_deferred
[ ! -s "$PM_LOG" ]
[ ! -e "$STORE" ]
[ ! -e "$SCRIPT" ]

# --- 4. GMS 被重装（安装身份不同）：不覆盖，保留记录和脚本 ------------------------
new_case reinstalled-gms
echo 2 > "$STATE"
TEST_FIRST='2025-05-05 00:00:00' TEST_BOOT_COMPLETED=1 run_deferred
[ ! -s "$PM_LOG" ]
[ -f "$STORE/user-0.json" ]
[ -x "$SCRIPT" ]

# --- 5. 组件被其他人改成“启用”：不碰 -------------------------------------------
new_case foreign-change
echo 1 > "$STATE"
TEST_BOOT_COMPLETED=1 run_deferred
[ ! -s "$PM_LOG" ]
[ -f "$STORE/user-0.json" ]
[ -x "$SCRIPT" ]

# --- 6. 开机一直没完成（等待有上限）：不改，下次开机再试 --------------------------
new_case boot-never-completes
echo 2 > "$STATE"
WAIT=0 TEST_BOOT_COMPLETED=0 run_deferred
[ ! -s "$PM_LOG" ]
[ -f "$STORE/user-0.json" ]
[ -x "$SCRIPT" ]
[ "$(cat "$CASE/adb/luoshu/.uninstall-restore-attempts")" = 1 ]

# --- 7. pm/dumpsys 不可用：保留 ------------------------------------------------
new_case services-missing
TEST_BOOT_COMPLETED=1 run_deferred
[ ! -s "$PM_LOG" ]
[ -f "$STORE/user-0.json" ]
[ -x "$SCRIPT" ]

# --- 8. 超过重试次数：删除自己，保留记录（重新安装后可在 App 恢复） ---------------
new_case max-boots
echo 3 > "$CASE/adb/luoshu/.uninstall-restore-attempts"
echo 2 > "$STATE"
TEST_BOOT_COMPLETED=1 run_deferred
[ ! -s "$PM_LOG" ]
[ -f "$STORE/user-0.json" ]
[ ! -e "$SCRIPT" ]
[ ! -e "$CASE/adb/luoshu/.uninstall-restore-attempts" ]

# --- 9. 用户已重新安装洛书：交给新模块，脚本删除自己 -------------------------------
new_case reinstalled-luoshu
mkdir -p "$CASE/modules_update/LuoShu"
echo 2 > "$STATE"
TEST_BOOT_COMPLETED=1 run_deferred
[ ! -s "$PM_LOG" ]
[ -f "$STORE/user-0.json" ]
[ ! -e "$SCRIPT" ]

# --- 10. 记录不安全（组可写 / 被篡改的组件名）：不执行 -----------------------------
new_case unsafe-record
chmod 0664 "$STORE/user-0.json"
echo 2 > "$STATE"
TEST_BOOT_COMPLETED=1 run_deferred
[ ! -s "$PM_LOG" ]
[ -f "$STORE/user-0.json" ]
new_case forged-component
sed -i 's#FontsProvider"#FontsProvider; reboot"#' "$STORE/user-0.json"
echo 2 > "$STATE"
TEST_BOOT_COMPLETED=1 run_deferred
[ ! -s "$PM_LOG" ]
[ -f "$STORE/user-0.json" ]

# 后台模式立即返回，不阻塞管理器的 service 阶段。
new_case background
echo 2 > "$STATE"
PATH="$BIN:$PATH" TEST_STATE="$STATE" TEST_PM_LOG="$PM_LOG" TEST_BOOT_COMPLETED=0 \
LUOSHU_DEFERRED_RESTORE_WAIT=1 LUOSHU_GOOGLE_FALLBACK_STORE="$STORE" \
LUOSHU_GOOGLE_FALLBACK_LEGACY_STORE="$CASE/legacy" \
LUOSHU_MODULES_DIR="$CASE/modules" LUOSHU_MODULES_UPDATE_DIR="$CASE/modules_update" \
    timeout 5 sh "$SCRIPT"
sleep 3

sh -n "$ROOT/common/google_font_deferred_restore.sh"
! grep -q 'exit 1' "$ROOT/uninstall.sh" || ! grep -q '未继续卸载' "$ROOT/uninstall.sh"
echo 'LuoShu deferred Google font restore checks passed.'
