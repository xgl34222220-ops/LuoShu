#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ROUTER="$ROOT/common/legacy_v14_4/mix_router.sh"
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-mix-finalize)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE="$TMP/module"
mkdir -p "$MODULE/.luoshu-mix-stage/system/fonts" "$MODULE/config" "$MODULE/common" "$MODULE/logs"
cp "$ROOT/common/background_task.sh" "$MODULE/common/background_task.sh"
chmod 0755 "$MODULE/common/background_task.sh"
cat > "$MODULE/common/inventory_font_stage.sh" <<'EOF_INVENTORY_STAGE'
#!/bin/sh
[ "$2" = mix ] || exit 1
[ -s "$1/system/fonts/MiSansVF.ttf" ] || exit 1
printf 'mapped\n' >> "$LUOSHU_REAL_MODDIR/inventory-stage-calls"
EOF_INVENTORY_STAGE
printf 'module\n' > "$MODULE/module.prop"
printf 'new-composite\n' > "$MODULE/.luoshu-mix-stage/system/fonts/MiSansVF.ttf"
printf 'default\n' > "$MODULE/config/active_font.conf"
cat > "$MODULE/config/mix-stage-next.conf" <<'EOF_STATE'
requestId=request-a
cjk=CjkA
latin=LatinA
digit=DigitA
previousFont=default
previousLegacy=false
time=1
EOF_STATE
cat > "$MODULE/.luoshu-mix-stage/.luoshu-mix-generation.conf" <<'EOF_MANIFEST_A'
requestId=request-a
cjk=CjkA
latin=LatinA
digit=DigitA
cjkHash=cjk-a
latinHash=latin-a
digitHash=digit-a
compositeHash=composite-a
EOF_MANIFEST_A

# App polling and the outer weighted task may observe child success at the same
# time. Every caller must see the same idempotent success; none may race between
# the stage rename and state-file commit.
for index in 1 2 3 4 5 6; do
    MODDIR="$MODULE" sh "$ROUTER" finalize > "$TMP/finalize-$index.out" 2>&1 &
done
wait
for output in "$TMP"/finalize-*.out; do
    grep -q '"status":"ok"' "$output"
done
test -s "$MODULE/.luoshu-payload-next/system/fonts/MiSansVF.ttf"
grep -q '^font=mix$' "$MODULE/config/font-payload-next.conf"
grep -q '^requestId=request-a$' "$MODULE/config/font-payload-next.conf"
grep -q '^compositeHash=composite-a$' "$MODULE/config/font-payload-next.conf"
test ! -e "$MODULE/.mix-stage-finalize.lock"
test "$(wc -l < "$MODULE/inventory-stage-calls" | tr -d '[:space:]')" = 1

# The monitor can commit and remove stage metadata before the outer weighted
# worker reaches prepare-finalize. The worker's inherited request identity must
# recognize its own completed tree, without accepting an unrelated/old task.
test ! -e "$MODULE/config/mix-stage-next.conf"
MODDIR="$MODULE" LUOSHU_MIX_REQUEST_ID=request-a sh "$ROUTER" prepare-finalize > "$TMP/prepare-after-commit.out" 2>&1
grep -q '"status":"ok"' "$TMP/prepare-after-commit.out"
if MODDIR="$MODULE" LUOSHU_MIX_REQUEST_ID=request-other sh "$ROUTER" prepare-finalize > "$TMP/prepare-wrong-request.out" 2>&1; then
    echo 'A different request reused the already committed mix' >&2
    exit 1
fi
if MODDIR="$MODULE" LUOSHU_MIX_REQUEST_ID= sh "$ROUTER" prepare-finalize > "$TMP/prepare-no-request.out" 2>&1; then
    echo 'A caller without generation identity reused the already committed mix' >&2
    exit 1
fi
grep -q '^requestId=request-a$' "$MODULE/config/font-payload-next.conf"

# Recover the narrow interrupted state: directory rename completed, state write
# did not. The preserved stage metadata is sufficient to finish without rebuild.
rm -f "$MODULE/config/font-payload-next.conf"
cat > "$MODULE/config/mix-stage-next.conf" <<'EOF_RECOVER'
requestId=request-a
cjk=CjkA
latin=LatinA
digit=DigitA
previousFont=mix
previousLegacy=true
time=2
EOF_RECOVER
MODDIR="$MODULE" sh "$ROUTER" finalize > "$TMP/recover.out" 2>&1
grep -q '"status":"ok"' "$TMP/recover.out"
grep -q '^font=mix$' "$MODULE/config/font-payload-next.conf"
grep -q '^requestId=request-a$' "$MODULE/config/font-payload-next.conf"

# A later selection is a different generation even though both payloads are named
# `mix`.  It must replace the already prepared generation instead of returning the
# old English/digit composite as an idempotent success.
mkdir -p "$MODULE/.luoshu-mix-stage/system/fonts"
printf 'newer-composite\n' > "$MODULE/.luoshu-mix-stage/system/fonts/MiSansVF.ttf"
cat > "$MODULE/config/mix-stage-next.conf" <<'EOF_STATE_B'
requestId=request-b
cjk=CjkA
latin=LatinB
digit=DigitB
previousFont=mix
previousLegacy=true
time=3
EOF_STATE_B
cat > "$MODULE/.luoshu-mix-stage/.luoshu-mix-generation.conf" <<'EOF_MANIFEST_B'
requestId=request-b
cjk=CjkA
latin=LatinB
digit=DigitB
cjkHash=cjk-a
latinHash=latin-b
digitHash=digit-b
compositeHash=composite-b
EOF_MANIFEST_B
MODDIR="$MODULE" sh "$ROUTER" finalize > "$TMP/second-generation.out" 2>&1
grep -q '"status":"ok"' "$TMP/second-generation.out"
grep -q '^newer-composite$' "$MODULE/.luoshu-payload-next/system/fonts/MiSansVF.ttf"
grep -q '^requestId=request-b$' "$MODULE/config/font-payload-next.conf"
grep -q '^latin=LatinB$' "$MODULE/config/font-payload-next.conf"
grep -q '^digit=DigitB$' "$MODULE/config/font-payload-next.conf"
grep -q '^compositeHash=composite-b$' "$MODULE/config/font-payload-next.conf"

# Combination-page refresh must be a config-only fast path. It must not prepare a
# compatibility runtime or touch payload directories merely to read saved choices.
cat > "$MODULE/config/axes_mix.conf" <<'EOF_CONFIG'
cjk=CjkFast
latin=LatinFast
digit=DigitFast
cjkWeight=410
latinWeight=420
digitWeight=430
cjkAxes=wght=410
latinAxes=wght=420
digitAxes=wght=430
EOF_CONFIG
MODDIR="$MODULE" sh "$ROUTER" config > "$TMP/config-fast.out"
grep -q '"cjk":"CjkFast"' "$TMP/config-fast.out"
grep -q '"latin":"LatinFast"' "$TMP/config-fast.out"
grep -q '"digit":"DigitFast"' "$TMP/config-fast.out"
grep -q '"latinWeight":420' "$TMP/config-fast.out"

# Polling is also config-only. A generated font is not reported successful until
# its next-boot payload is actually committed, and polling must never run setup_runtime.
cat > "$MODULE/config/axes_task.conf" <<'EOF_RUNNING'
task=axes-fast
state=running
message=正在后台生成
cjk=CjkFast
latin=LatinFast
digit=DigitFast
cjkAxes=wght=410
latinAxes=wght=420
digitAxes=wght=430
percent=62
EOF_RUNNING
MODDIR="$MODULE" sh "$ROUTER" status axes-fast > "$TMP/status-running.out"
grep -q '"state":"running"' "$TMP/status-running.out"
grep -q '"percent":62' "$TMP/status-running.out"
sed -i 's/^state=running$/state=success/' "$MODULE/config/axes_task.conf"
MODDIR="$MODULE" sh "$ROUTER" status axes-fast > "$TMP/status-commit.out"
grep -q '"state":"success"' "$TMP/status-commit.out"
grep -q '"percent":100' "$TMP/status-commit.out"

rm -rf "$MODULE/.luoshu-payload-next"
rm -f "$MODULE/config/font-payload-next.conf"
cat > "$MODULE/config/mix-finalize-state.conf" <<'EOF_FINALIZE_FAIL'
state=failed
task=axes-fast
message=提交校验失败
EOF_FINALIZE_FAIL
MODDIR="$MODULE" sh "$ROUTER" status axes-fast > "$TMP/status-failed.out"
grep -q '"state":"failed"' "$TMP/status-failed.out"
grep -q '提交校验失败' "$TMP/status-failed.out"

# Status polling may recover the atomic commit of an already mapped payload.
# It must never restart inventory generation merely because a child succeeded.
rm -f "$MODULE/config/mix-finalize-state.conf"
rm -rf "$MODULE/.luoshu-payload-next"
rm -f "$MODULE/config/font-payload-next.conf"
mkdir -p "$MODULE/.luoshu-mix-stage/system/fonts"
printf 'recovery-composite\n' > "$MODULE/.luoshu-mix-stage/system/fonts/MiSansVF.ttf"
cat > "$MODULE/config/mix-stage-next.conf" <<'EOF_STATE_RECOVERY'
requestId=request-recovery
cjk=CjkRecovery
latin=LatinRecovery
digit=DigitRecovery
previousFont=mix
previousLegacy=true
time=4
EOF_STATE_RECOVERY
cat > "$MODULE/.luoshu-mix-stage/.luoshu-mix-generation.conf" <<'EOF_MANIFEST_RECOVERY'
requestId=request-recovery
cjk=CjkRecovery
latin=LatinRecovery
digit=DigitRecovery
compositeHash=composite-recovery
EOF_MANIFEST_RECOVERY
printf 'state=ready\nrequestId=request-recovery\n' > "$MODULE/.luoshu-mix-stage/.luoshu-precommit-ready.conf"
cat > "$MODULE/config/axes_task.conf" <<'EOF_AXES_RECOVERY'
task=axes-recovery
state=success
message=字体已生成
cjk=CjkRecovery
latin=LatinRecovery
digit=DigitRecovery
percent=100
started=1
finished=2
EOF_AXES_RECOVERY
MODDIR="$MODULE" sh "$ROUTER" status axes-recovery > "$TMP/status-recovery-start.out"
grep -q '"state":"running"' "$TMP/status-recovery-start.out"
grep -q '"percent":99' "$TMP/status-recovery-start.out"

COUNT=0
while [ "$COUNT" -lt 10 ]; do
    [ -s "$MODULE/config/font-payload-next.conf" ] && [ -d "$MODULE/.luoshu-payload-next" ] && break
    sleep 1
    COUNT=$((COUNT + 1))
done
test -s "$MODULE/config/font-payload-next.conf"
test -d "$MODULE/.luoshu-payload-next"
MODDIR="$MODULE" sh "$ROUTER" status axes-recovery > "$TMP/status-recovery-done.out"
grep -q '"state":"success"' "$TMP/status-recovery-done.out"
grep -q '"percent":100' "$TMP/status-recovery-done.out"

grep -q 'finalize_compat_payload' "$ROOT/common/legacy_v14_4/v142_weighted_mix.sh"
grep -q "write_auto_generation_manifest" "$ROOT/common/legacy_v14_4/v143_auto_multiweight_mix.sh"
grep -q 'finalize_compat_payload' "$ROOT/common/legacy_v14_4/v143_auto_multiweight_mix.sh"
grep -q 'ensure_mix_finalize_worker' "$ROUTER"
grep -q 'prepare_mix_stage_for_commit' "$ROUTER"
grep -q 'PRECOMMIT_STATE=' "$ROUTER"
grep -q 'prepare-finalize' "$ROUTER"
grep -q " 90 " "$ROOT/common/legacy_v14_4/v142_weighted_mix.sh"
grep -q " 99 " "$ROOT/common/legacy_v14_4/v142_weighted_mix.sh"
grep -q 'prepare_compat_payload' "$ROOT/common/legacy_v14_4/v142_weighted_mix.sh"
grep -q 'prepare_compat_payload' "$ROOT/common/legacy_v14_4/v143_auto_multiweight_mix.sh"
sh -n "$ROOT/common/legacy_v14_4/v142_weighted_mix.sh"
sh -n "$ROOT/common/legacy_v14_4/v143_auto_multiweight_mix.sh"
sh -n "$ROUTER"

# A second mix generation must not inherit any prior text aliases from the live
# payload. Preserve unrelated XML, but clear every font partition and LuoShu XML.
# The real router sources payload_clone.sh before this function; mirror that
# dependency so scanner-discovered partition enumeration is available here too.
REALMOD="$MODULE"
export REALMOD
. "$ROOT/common/legacy_v14_4/payload_clone.sh"
FUNCTION=$(sed -n '/^clear_mix_text_payload()/,/^}/p' "$ROUTER")
eval "$FUNCTION"
MIX="$TMP/mix-clean"
for part in system system_ext product mi_ext vendor; do
    mkdir -p "$MIX/$part/fonts" "$MIX/$part/etc"
    printf 'old-%s\n' "$part" > "$MIX/$part/fonts/old.ttf"
    printf '<family>LuoShu-400.ttf</family>\n' > "$MIX/$part/etc/luoshu.xml"
    printf '<family>stock.ttf</family>\n' > "$MIX/$part/etc/stock.xml"
done
clear_mix_text_payload "$MIX"
for part in system_ext product mi_ext vendor; do
    test ! -d "$MIX/$part/fonts"
    test ! -e "$MIX/$part/etc/luoshu.xml"
    test -s "$MIX/$part/etc/stock.xml"
done
test -d "$MIX/system/fonts"
test -z "$(find "$MIX" -path '*/fonts/*' -type f -print -quit)"

grep -q 'clear_mix_text_payload "$MIX_STAGE"' "$ROUTER"
grep -q 'font_runtime_legacy_v14_4.conf' "$ROOT/boot-completed.sh"

# The safe switch may already have produced the exact next-boot payload for this
# mix request. prepare-finalize must recognize it and skip rebuilding/normalizing
# the compatibility stage a second time.
rm -rf "$MODULE/.luoshu-mix-stage"
mkdir -p "$MODULE/.luoshu-payload-next/system/fonts"
printf 'already-prepared\n' > "$MODULE/.luoshu-payload-next/system/fonts/Ready.ttf"
cat > "$MODULE/config/mix-stage-next.conf" <<'EOF_REUSE_STAGE'
requestId=request-reuse
cjk=CjkReuse
latin=LatinReuse
digit=DigitReuse
previousFont=mix
previousLegacy=true
time=5
EOF_REUSE_STAGE
cat > "$MODULE/config/font-payload-next.conf" <<'EOF_REUSE_NEXT'
state=prepared
font=mix
requestId=request-reuse
previousFont=mix
previousLegacy=true
time=5
EOF_REUSE_NEXT
MODDIR="$MODULE" sh "$ROUTER" prepare-finalize > "$TMP/prepare-reuse.out" 2>&1
grep -q '"status":"ok"' "$TMP/prepare-reuse.out"
grep -q 'next_mix_payload_ready_for_request' "$ROUTER"
grep -q 'LUOSHU_MIX_REQUEST_ID' "$ROOT/common/legacy_v14_4/font_switch_safe.sh"

echo 'Composite finalization is idempotent, generation-bound, and repeated mixes reuse the already-mapped next payload instead of rebuilding it.'
