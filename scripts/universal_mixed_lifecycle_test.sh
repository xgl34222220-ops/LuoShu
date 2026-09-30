#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
mkdir -p "$MOD/config" "$MOD/.luoshu-payload-next/system/fonts" "$MOD/.luoshu-mix-stage/system/fonts"
mkdir -p "$MOD/common/python/bin"
cat > "$MOD/common/python/bin/luoshu-python" <<EOF_PYTHON
#!/bin/sh
unset PYTHONHOME PYTHONPATH LD_LIBRARY_PATH
exec "$(command -v python3)" "\$@"
EOF_PYTHON
chmod +x "$MOD/common/python/bin/luoshu-python"
printf 'id=LuoShu\n' > "$MOD/module.prop"
printf 'universal-compiled\n' > "$MOD/.luoshu-payload-next/system/fonts/UI.ttf"
printf 'legacy-alias\n' > "$MOD/.luoshu-mix-stage/system/fonts/UI.ttf"
printf 'requestId=mix-a\ncjk=C\nlatin=L\ndigit=D\n' > "$MOD/config/mix-stage-next.conf"
printf 'font=mix\nrequestId=mix-a\ndeploymentId=sha256:real-deployment\npayloadDigest=sha256:real-payload\n' > "$MOD/config/universal-font-next.conf"
printf 'task=task-a\nstate=success\ncjk=C\nlatin=L\ndigit=D\n' > "$MOD/config/axes_task.conf"
ROUTER="$ROOT/common/legacy_v14_4/mix_router.sh"
# Repeated concurrent finalizers must never run old ROM slot completion or rewrite
# the payload already accepted by Universal.
for n in 1 2 3; do MODDIR="$MOD" sh "$ROUTER" finalize > "$TMP/$n.out" & done
wait
for n in 1 2 3; do grep -q '"pipeline":"universal"' "$TMP/$n.out"; done
grep -q '^universal-compiled$' "$MOD/.luoshu-payload-next/system/fonts/UI.ttf"
test ! -f "$MOD/config/font-payload-next.conf"
test ! -f "$MOD/config/font_runtime_legacy_v14_4.conf"
grep -q '^deploymentId=sha256:real-deployment$' "$MOD/config/universal-font-next.conf"
MODDIR="$MOD" sh "$ROUTER" status task-a > "$TMP/status"
grep -q '"state":"success"' "$TMP/status"
# A queued mix from another request cannot masquerade as this task's success.
printf 'requestId=mix-b\ncjk=C\nlatin=L2\ndigit=D2\n' > "$MOD/config/mix-stage-next.conf"
MODDIR="$MOD" sh "$ROUTER" status task-a > "$TMP/status"
grep -q '"state":"running"' "$TMP/status"
if MODDIR="$MOD" sh "$ROUTER" finalize > "$TMP/stale"; then
    echo 'stale Universal request was finalized' >&2; exit 1
fi
grep -q '^universal-compiled$' "$MOD/.luoshu-payload-next/system/fonts/UI.ttf"
printf 'universal_mixed_lifecycle_test: PASS\n'
# Completed task remains completed after the Universal next-boot swap consumes
# the pending marker; runtime state must carry the same request identity.
printf 'requestId=mix-a\n' > "$MOD/config/mix-stage-next.conf"
mv "$MOD/.luoshu-payload-next" "$MOD/.luoshu-payload"
mv "$MOD/config/universal-font-next.conf" "$MOD/config/universal-font-runtime.conf"
printf 'state=active\n' >> "$MOD/config/universal-font-runtime.conf"
MODDIR="$MOD" sh "$ROUTER" status task-a > "$TMP/status"
grep -q '"state":"success"' "$TMP/status"
printf 'universal_mixed_lifecycle_post_boot: PASS\n'
