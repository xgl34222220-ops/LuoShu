#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ROUTER="$ROOT/common/legacy_v14_4/mix_router.sh"
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-mix-finalize)
PHASE=setup
finish_test() {
    _test_rc=$?
    if [ "$_test_rc" -ne 0 ]; then
        printf 'legacy_mix_finalize_race_test failed: phase=%s exit=%s\n' "$PHASE" "$_test_rc" >&2
        for _test_output in "$TMP"/*.out "$TMP"/*.exit; do
            [ -f "$_test_output" ] || continue
            printf '\n--- %s ---\n' "${_test_output##*/}" >&2
            cat "$_test_output" >&2
        done
        for _test_state in "$TMP/module/config"/*.conf; do
            [ -f "$_test_state" ] || continue
            printf '\n--- %s ---\n' "${_test_state##*/}" >&2
            cat "$_test_state" >&2
        done
    fi
    rm -rf "$TMP"
    exit "$_test_rc"
}
trap finish_test EXIT
trap 'exit 130' HUP INT TERM

# Hold the exact owner-publication window open deterministically. The old
# mkdir/pid lock lets another caller delete this empty directory during 0.2s;
# the kernel-fd replacement remains exclusive through the same pause before
# commit. Both wrappers execute the real operations, never fake success.
mkdir -p "$TMP/bin"
export LUOSHU_TEST_MKDIR="$(command -v mkdir)"
export LUOSHU_TEST_PYTHON="$(command -v python3)"
cat > "$TMP/bin/mkdir" <<'EOF_MKDIR_PAUSE'
#!/bin/sh
"$LUOSHU_TEST_MKDIR" "$@"
rc=$?
if [ "$rc" = 0 ]; then
    case "$*" in *'.mix-stage-finalize.lock'*) /bin/sleep 0.2 ;; esac
fi
exit "$rc"
EOF_MKDIR_PAUSE
cat > "$TMP/bin/python3" <<'EOF_FLOCK_PAUSE'
#!/bin/sh
case " $* " in
    *' lock-fd '*)
        "$LUOSHU_TEST_PYTHON" "$@"
        rc=$?
        [ "$rc" != 0 ] || /bin/sleep 0.2
        exit "$rc"
        ;;
esac
exec "$LUOSHU_TEST_PYTHON" "$@"
EOF_FLOCK_PAUSE
chmod 0755 "$TMP/bin/mkdir" "$TMP/bin/python3"
PATH="$TMP/bin:$PATH"; export PATH

MODULE="$TMP/module"
mkdir -p "$MODULE/.luoshu-mix-stage/system/fonts" "$MODULE/config" "$MODULE/logs"
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
PHASE=concurrent-finalize
FINALIZE_PIDS=''
for index in 1 2 3 4 5 6; do
    MODDIR="$MODULE" sh "$ROUTER" finalize > "$TMP/finalize-$index.out" 2>&1 &
    FINALIZE_PIDS="$FINALIZE_PIDS $!:$index"
done
FINALIZE_FAILED=0
for record in $FINALIZE_PIDS; do
    pid=${record%:*}; index=${record#*:}
    if wait "$pid"; then rc=0; else rc=$?; FINALIZE_FAILED=1; fi
    printf 'pid=%s exit=%s\n' "$pid" "$rc" > "$TMP/finalize-$index.exit"
done
[ "$FINALIZE_FAILED" = 0 ]
for output in "$TMP"/finalize-*.out; do
    grep -q '"status":"ok"' "$output"
done
test -s "$MODULE/.luoshu-payload-next/system/fonts/MiSansVF.ttf"
grep -q '^font=mix$' "$MODULE/config/font-payload-next.conf"
grep -q '^requestId=request-a$' "$MODULE/config/font-payload-next.conf"
grep -q '^compositeHash=composite-a$' "$MODULE/config/font-payload-next.conf"
test ! -e "$MODULE/.mix-stage-finalize.lock"

PHASE=interrupted-state-recovery
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

PHASE=second-generation
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

PHASE=config-fast-path
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

PHASE=status-fast-path
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
message=提交校验失败
EOF_FINALIZE_FAIL
MODDIR="$MODULE" sh "$ROUTER" status axes-fast > "$TMP/status-failed.out"
grep -q '"state":"failed"' "$TMP/status-failed.out"
grep -q '提交校验失败' "$TMP/status-failed.out"

PHASE=old-alias-cleanup
# A second mix generation must not inherit any prior text aliases from the live
# payload. Preserve unrelated XML, but clear every font partition and LuoShu XML.
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

PHASE=kernel-lock-ownership
python3 "$ROOT/scripts/finalize_lock_test.py"

echo 'Composite finalization is idempotent, generation-bound, and repeated mixes drop every old text slot.'
