#!/bin/sh
# 全局字体增强（Zygisk）配置层：默认关闭、新旧路径、让出条件、失败保守。
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SCRIPT="$ROOT/common/native_font.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

fail() {
  printf 'native font test failed: %s\n' "$*" >&2
  exit 1
}

MOD="$TMP/LuoShu"
LEGACY="$TMP/legacy"
mkdir -p "$MOD/config" "$MOD/zygisk/defaults" "$MOD/system/fonts"
printf 'com.android.systemui\n' > "$MOD/zygisk/defaults/exclude.list"
printf 'bootid-1\n' > "$TMP/boot_id"
: > "$MOD/zygisk/arm64-v8a.so"

# Fake config tool: records its arguments; "build" writes the output file.
TOOL="$TMP/lsnf-config"
cat > "$TOOL" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "${0}.calls"
[ ! -f "${0}.fail" ] || [ "$1" != build ] || case "$*" in *"--enabled 0 --verbose 0 --java-font 0"*) ;; *) exit 3 ;; esac
out=''
prev=''
for a in "$@"; do
  [ "$prev" = --out ] && out="$a"
  prev="$a"
done
[ -z "$out" ] || printf 'x' > "$out"
EOF
chmod 0755 "$TOOL"

run() {
  LUOSHU_NATIVE_FONT_MODDIR="$MOD" LUOSHU_NATIVE_FONT_LEGACY_DIR="$LEGACY" LUOSHU_NATIVE_FONT_BOOT_ID="$TMP/boot_id" \
    LUOSHU_NATIVE_FONT_ABI=arm64-v8a LUOSHU_NATIVE_FONT_TOOL="$TOOL" sh "$SCRIPT" "$@"
}

# 1. 默认关闭，未加载。
out=$(run status)
printf '%s' "$out" | grep -q '"enabled":false' || fail "default must be off: $out"
printf '%s' "$out" | grep -q '"library":true' || fail "library not detected: $out"
printf '%s' "$out" | grep -q '"zygiskLoaded":false' || fail "loaded before prepare: $out"

# 2. prepare 默认关闭：写 enabled=0 的配置，不生成 faces。
run prepare
grep -q -- '--enabled 0' "$TOOL.calls" || fail 'prepare did not build a disabled config'
if grep -q '^faces' "$TOOL.calls"; then fail 'faces built while disabled'; fi
grep -q -- "--exclude $MOD/zygisk/defaults/exclude.list" "$TOOL.calls" || fail 'built-in exclude list missing'
[ -f "$MOD/zygisk/runtime/config.bin" ] || fail 'config.bin missing'
grep -qx 'boot_id=bootid-1' "$MOD/zygisk/runtime/state.conf" || fail 'state.conf not stamped'
run status | grep -q '"zygiskLoaded":true' || fail 'loaded state not reported'

# 3. 旧路径只读兼容：新配置不存在时读取 /data/adb/luoshu_native_font。
mkdir -p "$LEGACY"
: > "$LEGACY/enabled"
printf 'com.legacy.app\n' > "$LEGACY/exclude.list"
run status | grep -q '"legacyConfig":true' || fail 'legacy config not reported'
run status | grep -q '"enabled":true' || fail 'legacy enabled not honoured'
: > "$TOOL.calls"
run prepare
grep -q -- '--enabled 1' "$TOOL.calls" || fail 'legacy enabled not compiled'
grep -q -- "--exclude $LEGACY/exclude.list" "$TOOL.calls" || fail 'legacy exclude list not read'

# 4. 主模块字体未验证生效时让出：不写 faces。
if grep -q '^faces' "$TOOL.calls"; then fail 'faces built without a verified LuoShu font'; fi
printf 'MyFont\n' > "$MOD/config/active_font.conf"
printf 'state=verified\nactiveFont=MyFont\nmode=aligned\n' > "$MOD/config/device-font-load-verification.conf"
: > "$MOD/system/fonts/LuoShu-400.ttf"
: > "$TOOL.calls"
run prepare
grep -q "^faces --out $MOD/zygisk/runtime/faces.bin $MOD/system/fonts/LuoShu-400.ttf" "$TOOL.calls" || fail 'verified faces not built'
printf 'pending\n' > "$MOD/config/text_reboot_required.conf"
: > "$TOOL.calls"
run prepare
if grep -q '^faces' "$TOOL.calls"; then fail 'faces built while a reboot is pending'; fi
[ ! -f "$MOD/zygisk/runtime/faces.bin" ] || fail 'stale faces.bin kept'
rm -f "$MOD/config/text_reboot_required.conf"

# 5. App 写开关：迁到主模块 config，带走旧名单；之后只读新配置。
out=$(run set enabled 0)
printf '%s' "$out" | grep -q '"enabled":false' || fail "set enabled 0 failed: $out"
grep -qx 'enabled=0' "$MOD/config/native-font.conf" || fail 'native-font.conf not written'
grep -qx 'java_font=1' "$MOD/config/native-font.conf" || fail 'java_font default lost'
grep -qx 'com.legacy.app' "$MOD/config/native-font-exclude.list" || fail 'legacy exclude list not migrated'
run status | grep -q '"legacyConfig":false' || fail 'legacy still reported after migration'
run set enabled 1 | grep -q '"enabled":true' || fail 'set enabled 1 failed'
run set java_font 0 | grep -q '"status":"error"' || fail 'unknown key accepted'
run set enabled 2 | grep -q '"status":"error"' || fail 'bad value accepted'

# 6. 模块被禁用时整体关闭。
: > "$MOD/disable"
: > "$TOOL.calls"
run prepare
grep -q -- '--enabled 0' "$TOOL.calls" || fail 'disabled module still enabled'
rm -f "$MOD/disable"

# 7. 配置编译失败时写关闭状态的配置（失败保守）。
: > "$TOOL.fail"
: > "$TOOL.calls"
run prepare
grep -q -- '--enabled 0 --verbose 0 --java-font 0' "$TOOL.calls" || fail 'no disabled fallback config'
[ ! -f "$MOD/zygisk/runtime/faces.bin" ] || fail 'faces kept after failure'
grep -qx 'enabled=0' "$MOD/zygisk/runtime/state.conf" || fail 'failure not reported as disabled'
rm -f "$TOOL.fail"

# 8. App 桥接入口。
grep -q 'native_font_status|native_font_set)' "$ROOT/common/app_bridge.sh" || fail 'app bridge entry missing'

printf 'Native font (Zygisk) config checks passed.\n'
