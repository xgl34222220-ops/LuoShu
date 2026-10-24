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

# 4. 让出条件：不依赖本次开机的加载验证，只看字体是否已挂载对系统可见。
if grep -q '^faces' "$TOOL.calls"; then fail 'faces built without an active LuoShu font'; fi
grep -qx 'reason=no-active-font' "$MOD/zygisk/runtime/state.conf" || fail 'no-active-font reason missing'
SYS="$TMP/sysroot"
mkdir -p "$SYS/system/fonts"
printf 'MyFont\n' > "$MOD/config/active_font.conf"
# 本次开机验证尚未完成（boot verify 先写 pending/compatibility）。
printf 'state=pending\nmode=compatibility\nactiveFont=MyFont\n' > "$MOD/config/device-font-load-verification.conf"
printf 'luoshu-regular' > "$MOD/system/fonts/LuoShu-400.ttf"
runs() { LUOSHU_NATIVE_FONT_SYSROOT="$SYS" run "$@"; }
# 4a. 未挂载：让出并记录原因。
: > "$TOOL.calls"
runs prepare
if grep -q '^faces' "$TOOL.calls"; then fail 'faces built while the font is not mounted'; fi
grep -qx 'faces=0' "$MOD/zygisk/runtime/state.conf" || fail 'unmounted font reported as faces'
grep -qx 'reason=font-not-mounted' "$MOD/zygisk/runtime/state.conf" || fail 'font-not-mounted reason missing'
runs status | grep -q '"facesReason":"font-not-mounted"' || fail 'reason not in status JSON'
# 4b. 已挂载（/system/fonts 下大小一致）+ 验证 pending → faces=1。
printf 'luoshu-regular' > "$SYS/system/fonts/LuoShu-400.ttf"
: > "$TOOL.calls"
runs prepare
grep -q "^faces --out $MOD/zygisk/runtime/faces.bin.tmp $MOD/system/fonts/LuoShu-400.ttf" "$TOOL.calls" || fail 'mounted faces not built under pending verification'
[ -s "$MOD/zygisk/runtime/faces.bin" ] || fail 'faces.bin missing'
grep -qx 'faces=1' "$MOD/zygisk/runtime/state.conf" || fail 'faces=1 not reported'
grep -qx 'reason=' "$MOD/zygisk/runtime/state.conf" || fail 'stale reason kept'
runs status | grep -q '"faces":true,"facesReason":""' || fail 'status faces not reported'
# 4c. 大小不一致视为未挂载。
printf 'stock' > "$SYS/system/fonts/LuoShu-400.ttf"
runs prepare
grep -qx 'reason=font-not-mounted' "$MOD/zygisk/runtime/state.conf" || fail 'size mismatch treated as mounted'
[ ! -f "$MOD/zygisk/runtime/faces.bin" ] || fail 'stale faces.bin kept'
rm -f "$SYS/system/fonts/LuoShu-400.ttf"
# 4d. 逐文件 bind（附加的 LuoShu-400 不可见）：同一字体的 ColorOS 槽位在 /my_product/fonts 可见。
ln "$MOD/system/fonts/LuoShu-400.ttf" "$MOD/system/fonts/SysSans-Hans-Regular.ttf"
mkdir -p "$MOD/my_product/fonts" "$SYS/my_product/fonts"
ln -s ../../system/fonts/LuoShu-400.ttf "$MOD/my_product/fonts/SysFont-Regular.ttf"
printf 'luoshu-regular' > "$SYS/my_product/fonts/SysFont-Regular.ttf"
: > "$TOOL.calls"
runs prepare
grep -q '^faces' "$TOOL.calls" || fail 'visible slot alias not accepted'
grep -qx 'faces=1' "$MOD/zygisk/runtime/state.conf" || fail 'slot alias faces=0'
rm -f "$SYS/my_product/fonts/SysFont-Regular.ttf"
printf 'stockfont' > "$SYS/system/fonts/SysSans-Hans-Regular.ttf"
runs prepare
grep -qx 'faces=0' "$MOD/zygisk/runtime/state.conf" || fail 'stock slot taken as mounted'
printf 'luoshu-regular' > "$SYS/system/fonts/SysSans-Hans-Regular.ttf"
runs prepare
grep -qx 'faces=1' "$MOD/zygisk/runtime/state.conf" || fail 'system slot alias not accepted'
rm -rf "$SYS/system/fonts/SysSans-Hans-Regular.ttf" "$MOD/system/fonts/SysSans-Hans-Regular.ttf" "$MOD/my_product"
printf 'luoshu-regular' > "$SYS/system/fonts/LuoShu-400.ttf"
# 4e. 私有负载 .luoshu-payload/system/fonts 同样识别。
mkdir -p "$MOD/.luoshu-payload/system/fonts"
mv "$MOD/system/fonts/LuoShu-400.ttf" "$MOD/.luoshu-payload/system/fonts/LuoShu-400.ttf"
: > "$TOOL.calls"
runs prepare
grep -q "^faces --out .* $MOD/.luoshu-payload/system/fonts/LuoShu-400.ttf" "$TOOL.calls" || fail 'private payload faces not built'
mv "$MOD/.luoshu-payload/system/fonts/LuoShu-400.ttf" "$MOD/system/fonts/LuoShu-400.ttf"
rm -rf "$MOD/.luoshu-payload"
# 4f. 上次验证明确 failed → 让出。
printf 'state=failed\nmode=compatibility\nactiveFont=MyFont\n' > "$MOD/config/device-font-load-verification.conf"
: > "$TOOL.calls"
runs prepare
if grep -q '^faces' "$TOOL.calls"; then fail 'faces built after a failed verification'; fi
grep -qx 'reason=verify-failed' "$MOD/zygisk/runtime/state.conf" || fail 'verify-failed reason missing'
printf 'state=verified\nactiveFont=MyFont\nmode=aligned\n' > "$MOD/config/device-font-load-verification.conf"
runs prepare
grep -qx 'faces=1' "$MOD/zygisk/runtime/state.conf" || fail 'verified mounted font not built'
# 4g. 待重启时让出。
printf 'pending\n' > "$MOD/config/text_reboot_required.conf"
: > "$TOOL.calls"
runs prepare
if grep -q '^faces' "$TOOL.calls"; then fail 'faces built while a reboot is pending'; fi
[ ! -f "$MOD/zygisk/runtime/faces.bin" ] || fail 'stale faces.bin kept'
grep -qx 'reason=reboot-required' "$MOD/zygisk/runtime/state.conf" || fail 'reboot-required reason missing'
rm -f "$MOD/config/text_reboot_required.conf"

# 4h. ROM 槽位布局（模块里没有 LuoShu-NNN，正文直接写成 ROM 槽位文件）。
# mkfont FILE WEIGHT TAG：最小 sfnt，只有一张 OS/2 表（usWeightClass=WEIGHT），TAG 让内容各不相同。
mkfont() {
  _hi=$(( $2 / 256 )); _lo=$(( $2 % 256 ))
  # shellcheck disable=SC2059
  { printf '\000\001\000\000\000\001\000\000\000\000\000\000OS/2\000\000\000\000\000\000\000\034\000\000\000\010'
    printf "\000\004\001\364\\$(printf '%o' "$_hi")\\$(printf '%o' "$_lo")\000\005"
    printf '%s' "$3"; } > "$1"
}
rm -f "$MOD/system/fonts/LuoShu-400.ttf" "$SYS/system/fonts/LuoShu-400.ttf"
rm -rf "$MOD/system/fonts" "$MOD/my_product" "$MOD/.luoshu-payload" "$SYS"
mkdir -p "$SYS/system/fonts" "$SYS/my_product/fonts"
# 4h-1. 什么都没有：no-luoshu-faces，并写明找过的目录。
: > "$TOOL.calls"
runs prepare
grep -qx 'reason=no-luoshu-faces' "$MOD/zygisk/runtime/state.conf" || fail 'no-luoshu-faces reason missing'
grep -q '^reason_detail=.*system/fonts' "$MOD/zygisk/runtime/state.conf" || fail 'searched dirs not reported'
runs status | grep -q '"facesDetail":".*fonts' || fail 'facesDetail not in status JSON'
# 4h-2. ColorOS（PLK110 布局）：/system/fonts 与 /my_product/fonts 下的 SysSans/SysFont 槽位。
mkdir -p "$MOD/system/fonts/.luoshu-font-store" "$MOD/my_product/fonts"
mkfont "$MOD/system/fonts/.luoshu-font-store/regular.font" 400 luoshu-regular
ln "$MOD/system/fonts/.luoshu-font-store/regular.font" "$MOD/system/fonts/SysSans-Hans-Regular.ttf"
ln "$MOD/system/fonts/.luoshu-font-store/regular.font" "$MOD/system/fonts/SysFont-Hans-Regular.ttf"
ln "$MOD/system/fonts/.luoshu-font-store/regular.font" "$MOD/system/fonts/SysSans-En-Regular.ttf"
ln "$MOD/system/fonts/.luoshu-font-store/regular.font" "$MOD/system/fonts/DroidSansMono.ttf"
ln "$MOD/system/fonts/.luoshu-font-store/regular.font" "$MOD/system/fonts/AndroidClock.ttf"
mkfont "$MOD/system/fonts/SysSans-Hans-Bold.ttf" 700 luoshu-bold
mkfont "$MOD/system/fonts/SysFont-Hans-Bold.ttf" 700 luoshu-bold-copy
printf 'no-os2-medium' > "$MOD/my_product/fonts/SysFont-Hans-Medium.ttf"
mkfont "$MOD/system/fonts/SysSans-Hans-Light-Italic.ttf" 300 italic
# OS/2 usWeightClass 优先于文件名（Heavy 名字但 OS/2=850）。
mkfont "$MOD/system/fonts/SysSans-Hans-Heavy.ttf" 850 luoshu-heavy
# 未挂载：让出。
: > "$TOOL.calls"
runs prepare
grep -qx 'reason=font-not-mounted' "$MOD/zygisk/runtime/state.conf" || fail 'coloros slots taken as mounted'
cp "$MOD/my_product/fonts/SysFont-Hans-Medium.ttf" "$SYS/my_product/fonts/SysFont-Hans-Medium.ttf"
: > "$TOOL.calls"
runs prepare
grep -qx 'faces=1' "$MOD/zygisk/runtime/state.conf" || fail "coloros slot layout faces=0: $(cat "$MOD/zygisk/runtime/state.conf")"
call=$(grep '^faces' "$TOOL.calls")
for w in 400 500 700 850; do
  printf '%s' "$call" | grep -q "$MOD/zygisk/runtime/faces/LuoShu-$w.ttf" || fail "coloros weight $w missing: $call"
done
[ "$(printf '%s' "$call" | tr ' ' '\n' | grep -c 'LuoShu-')" = 4 ] || fail "coloros faces not deduped by weight: $call"
[ "$(stat -c %i "$MOD/zygisk/runtime/faces/LuoShu-400.ttf")" = "$(stat -c %i "$MOD/system/fonts/SysSans-Hans-Regular.ttf")" ] || fail 'regular face not linked to the slot file'
cmp -s "$MOD/zygisk/runtime/faces/LuoShu-700.ttf" "$MOD/system/fonts/SysSans-Hans-Bold.ttf" || fail 'SysSans bold not preferred over SysFont'
cmp -s "$MOD/zygisk/runtime/faces/LuoShu-500.ttf" "$MOD/my_product/fonts/SysFont-Hans-Medium.ttf" || fail 'my_product slot not used'
grep -qx 'reason=' "$MOD/zygisk/runtime/state.conf" || fail 'stale reason after coloros faces'
# 槽位大小与系统真实路径不一致视为未挂载。
printf 'stock' > "$SYS/my_product/fonts/SysFont-Hans-Medium.ttf"
runs prepare
grep -qx 'reason=font-not-mounted' "$MOD/zygisk/runtime/state.conf" || fail 'stock my_product slot taken as mounted'
[ ! -f "$MOD/zygisk/runtime/faces.bin" ] || fail 'stale faces.bin kept (coloros)'
cp "$MOD/system/fonts/SysFont-Hans-Bold.ttf" "$SYS/system/fonts/SysFont-Hans-Bold.ttf"
runs prepare
grep -qx 'faces=1' "$MOD/zygisk/runtime/state.conf" || fail 'system slot visibility not accepted'
rm -rf "$MOD/system/fonts" "$MOD/my_product" "$SYS" "$MOD/zygisk/runtime/faces"
mkdir -p "$SYS/system/fonts"
# 4h-3. HyperOS（私有负载，seed 同名换内容）：MiSansVF + 数字字重槽；Roboto/拉丁/Overlay 不取。
P="$MOD/.luoshu-payload/system/fonts"
mkdir -p "$P" "$MOD/.luoshu-payload/mi_ext/fonts"
mkfont "$P/MiSansVF.ttf" 400 luoshu-vf
ln "$P/MiSansVF.ttf" "$P/400.ttf"
mkfont "$P/700.ttf" 700 luoshu-700
mkfont "$P/MiSansLatinVF.ttf" 400 latin
mkfont "$P/MiSansVF_Overlay.ttf" 400 overlay
mkfont "$P/Roboto-Medium.ttf" 500 roboto
mkfont "$P/RobotoMono-Regular.ttf" 400 mono
mkfont "$MOD/.luoshu-payload/mi_ext/fonts/MiSansVF.ttf" 400 luoshu-vf-mi-ext
: > "$TOOL.calls"
runs prepare
grep -qx 'reason=font-not-mounted' "$MOD/zygisk/runtime/state.conf" || fail 'hyperos seed slots taken as mounted'
printf 'stock-vf' > "$SYS/system/fonts/MiSansVF.ttf"
cp "$P/700.ttf" "$SYS/system/fonts/700.ttf"
: > "$TOOL.calls"
runs prepare
grep -qx 'faces=1' "$MOD/zygisk/runtime/state.conf" || fail "hyperos slot layout faces=0: $(cat "$MOD/zygisk/runtime/state.conf")"
call=$(grep '^faces' "$TOOL.calls")
printf '%s' "$call" | grep -q "$MOD/zygisk/runtime/faces/LuoShu-400.ttf" || fail "hyperos 400 missing: $call"
printf '%s' "$call" | grep -q "$MOD/zygisk/runtime/faces/LuoShu-700.ttf" || fail "hyperos 700 missing: $call"
[ "$(printf '%s' "$call" | tr ' ' '\n' | grep -c 'LuoShu-')" = 2 ] || fail "hyperos picked extra slots: $call"
cmp -s "$MOD/zygisk/runtime/faces/LuoShu-400.ttf" "$P/MiSansVF.ttf" || fail 'hyperos regular face is not MiSansVF'
rm -rf "$MOD/.luoshu-payload" "$MOD/zygisk/runtime/faces" "$SYS"
mkdir -p "$MOD/system/fonts" "$SYS/system/fonts"
printf 'luoshu-regular' > "$MOD/system/fonts/LuoShu-400.ttf"
printf 'luoshu-regular' > "$SYS/system/fonts/LuoShu-400.ttf"
runs prepare
grep -qx 'faces=1' "$MOD/zygisk/runtime/state.conf" || fail 'LuoShu-NNN path regressed'
[ ! -e "$MOD/zygisk/runtime/faces" ] || fail 'slot aliases kept for LuoShu-NNN layout'

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
grep -qx 'reason=config-build-failed' "$MOD/zygisk/runtime/state.conf" || fail 'config failure reason missing'
[ -f "$MOD/zygisk/runtime/config.bin" ] || fail 'disabled fallback config.bin missing'
rm -f "$TOOL.fail"

# 8. App 桥接入口。
grep -q 'native_font_status|native_font_set)' "$ROOT/common/app_bridge.sh" || fail 'app bridge entry missing'

printf 'Native font (Zygisk) config checks passed.\n'
