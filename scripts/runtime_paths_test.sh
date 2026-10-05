#!/bin/sh
# Exercise migrations with real trees, including interrupted/conflicting layouts.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
CASE_ROOT=$(mktemp -d)
trap 'rm -rf "$CASE_ROOT"' EXIT HUP INT TERM
HELPER="$ROOT/common/runtime_paths.sh"
export LUOSHU_RUNTIME_PATHS_PYTHON="$(python3 -c 'import sys; print(sys.executable)')"

fail() { printf 'runtime paths regression: %s\n' "$*" >&2; exit 1; }
prepare_fixture() {
    mkdir -p "$1/common"
    cp "$HELPER" "$ROOT/common/runtime_paths_lock.py" "$1/common/"
}
initialize() {
    [ -f "$1/common/runtime_paths.sh" ] && [ -f "$1/common/runtime_paths_lock.py" ] || prepare_fixture "$1"
    sh -c '. "$1"; luoshu_runtime_paths_init "$2"' sh "$1/common/runtime_paths.sh" "$1"
}

MODULE="$CASE_ROOT/module with spaces"
PUBLIC="$CASE_ROOT/public"
mkdir -p "$MODULE/config/nested" "$MODULE/logs" "$MODULE/cache" "$MODULE/backup" "$MODULE/reports" "$PUBLIC/fonts" "$MODULE/system/fonts"
printf '用户选择\n' > "$MODULE/config/active_font.conf"
printf 'default\n' > "$MODULE/config/nested/default.conf"
printf 'hidden preference\n' > "$MODULE/config/.keep"
printf 'mounted clone bytes\n' > "$MODULE/config/clone.font"
printf 'log bytes\n' > "$MODULE/logs/run.log"
printf 'cache bytes\n' > "$MODULE/cache/font.bin"
printf 'original font bytes\n' > "$MODULE/backup/stock.font"
printf 'diagnostic report\n' > "$MODULE/reports/latest.json"
printf 'user font bytes\n' > "$PUBLIC/fonts/用户.ttf"
printf 'unrelated\n' > "$MODULE/unrelated.txt"
printf 'payload bytes\n' > "$MODULE/system/fonts/stock.ttf"
CLONE_INODE=$(stat -c '%d:%i' "$MODULE/config/clone.font")
initialize "$MODULE" || fail 'legacy directory migration'
for NAME in config logs cache backup reports; do
    [ "$(readlink "$MODULE/$NAME")" = ".luoshu-state/$NAME" ] || fail "compatibility link $NAME"
done
[ "$(cat "$MODULE/config/active_font.conf")" = '用户选择' ] || fail 'selection lost'
[ "$(cat "$MODULE/config/.keep")" = 'hidden preference' ] || fail 'dotfile lost'
[ "$(stat -c '%d:%i' "$MODULE/config/clone.font")" = "$CLONE_INODE" ] || fail 'mounted clone inode changed'
[ "$(cat "$MODULE/backup/stock.font")" = 'original font bytes' ] || fail 'stock backup lost'
[ "$(cat "$MODULE/reports/latest.json")" = 'diagnostic report' ] || fail 'diagnostic report lost'
[ "$(cat "$PUBLIC/fonts/用户.ttf")" = 'user font bytes' ] || fail 'public font changed'
[ "$(cat "$MODULE/unrelated.txt")" = unrelated ] || fail 'unknown module file touched'
[ "$(cat "$MODULE/system/fonts/stock.ttf")" = 'payload bytes' ] || fail 'mount payload touched'
initialize "$MODULE" || fail 'idempotent initialization'
[ ! -e "$MODULE/.luoshu-state/.paths-migrate.lock" ] || fail 'migration lock retained'
printf '#!/bin/sh\nexit 99\n' > "$CASE_ROOT/reject-python"
chmod 0755 "$CASE_ROOT/reject-python"
LUOSHU_RUNTIME_PATHS_PYTHON="$CASE_ROOT/reject-python" initialize "$MODULE" || fail 'warm initialization starts Python'
sh -c '. "$1"; luoshu_runtime_paths_init "$2" || exit; [ "$TMPDIR" = "$2/.luoshu-state/tmp" ] && [ "$CONFIG_DIR" = "$2/.luoshu-state/config" ] && [ "$LUOSHU_TASKS_DIR" = "$2/.luoshu-state/tasks" ]' sh "$HELPER" "$MODULE" || fail 'exported contract'

CONFLICT="$CASE_ROOT/conflict"
mkdir -p "$CONFLICT/config/nested" "$CONFLICT/.luoshu-state/config/nested"
printf 'central current\n' > "$CONFLICT/.luoshu-state/config/active_font.conf"
printf 'old choice\n' > "$CONFLICT/config/active_font.conf"
printf 'central default\n' > "$CONFLICT/.luoshu-state/config/nested/default.conf"
printf 'old default\n' > "$CONFLICT/config/nested/default.conf"
printf 'old only preference\n' > "$CONFLICT/config/nested/old-only.conf"
initialize "$CONFLICT" || fail 'interrupted conflicting migration'
[ "$(cat "$CONFLICT/config/active_font.conf")" = 'central current' ] || fail 'current central state clobbered'
[ "$(cat "$CONFLICT/config/nested/old-only.conf")" = 'old only preference' ] || fail 'old-only preference lost'
[ "$(find "$CONFLICT/.luoshu-state/migration-conflicts" -name active_font.conf -exec cat {} \;)" = 'old choice' ] || fail 'old choice snapshot lost'
[ "$(find "$CONFLICT/.luoshu-state/migration-conflicts" -name default.conf -exec cat {} \;)" = 'old default' ] || fail 'old defaults snapshot lost'

RESUME="$CASE_ROOT/resume"
mkdir -p "$RESUME/.luoshu-state/config"
printf 'preserved\n' > "$RESUME/.luoshu-state/config/active_font.conf"
initialize "$RESUME" || fail 'resume between directory move and link'
[ "$(cat "$RESUME/config/active_font.conf")" = preserved ] || fail 'resume selection'

OUTSIDE="$CASE_ROOT/outside"
mkdir -p "$OUTSIDE"
printf 'do not touch\n' > "$OUTSIDE/keep"
for BAD in source-link state-link target-link; do
    BAD_MODULE="$CASE_ROOT/$BAD"
    mkdir -p "$BAD_MODULE/config" "$BAD_MODULE/logs"
    printf 'local bytes\n' > "$BAD_MODULE/logs/local.log"
    case "$BAD" in
        source-link) rmdir "$BAD_MODULE/config"; ln -s "$OUTSIDE" "$BAD_MODULE/config" ;;
        state-link) ln -s "$OUTSIDE" "$BAD_MODULE/.luoshu-state" ;;
        target-link) mkdir -p "$BAD_MODULE/.luoshu-state"; ln -s "$OUTSIDE" "$BAD_MODULE/.luoshu-state/config" ;;
    esac
    if initialize "$BAD_MODULE"; then fail "accepted external $BAD"; fi
    [ -f "$BAD_MODULE/logs/local.log" ] && [ ! -L "$BAD_MODULE/logs" ] || fail "modified safe directory before rejecting $BAD"
done
[ "$(cat "$OUTSIDE/keep")" = 'do not touch' ] || fail 'external files changed'
[ "$(find "$OUTSIDE" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')" = 1 ] || fail 'created files outside module'
if LUOSHU_STATE_DIR="$OUTSIDE" initialize "$MODULE"; then fail 'accepted outside state override'; fi

for GIT_SHAPE in directory file symlink; do
    CHECKOUT="$CASE_ROOT/checkout-$GIT_SHAPE"
    mkdir -p "$CHECKOUT/config"
    printf 'source input\n' > "$CHECKOUT/config/active_font.conf"
    case "$GIT_SHAPE" in
        directory) mkdir "$CHECKOUT/.git" ;;
        file) printf 'gitdir: elsewhere\n' > "$CHECKOUT/.git" ;;
        symlink) ln -s "$CASE_ROOT/missing-git" "$CHECKOUT/.git" ;;
    esac
    if initialize "$CHECKOUT"; then fail "migrated $GIT_SHAPE checkout"; fi
    [ ! -e "$CHECKOUT/.luoshu-state" ] && [ ! -L "$CHECKOUT/config" ] || fail "mutated $GIT_SHAPE checkout"
    mkdir -p "$CHECKOUT/common"
    cp "$HELPER" "$CHECKOUT/common/runtime_paths.sh"
    cp "$ROOT/common/util_functions_core.sh" "$CHECKOUT/common/util_functions_core.sh"
    MODULE_DIR="$CHECKOUT" sh -c '. "$1"; [ "$CONFIG_DIR" = "$MODULE_DIR/config" ]' sh "$CHECKOUT/common/util_functions_core.sh" || fail "util sourcing $GIT_SHAPE checkout"
    [ ! -e "$CHECKOUT/.luoshu-state" ] && [ ! -L "$CHECKOUT/config" ] || fail "util mutated $GIT_SHAPE checkout"
done

FIRST="$CASE_ROOT/first"; SECOND="$CASE_ROOT/second"
mkdir -p "$FIRST" "$SECOND"
initialize "$FIRST"; initialize "$SECOND"
sh -c '. "$1"; luoshu_runtime_paths_init "$2" && luoshu_runtime_paths_init "$3" && [ "$LUOSHU_STATE_DIR" = "$3/.luoshu-state" ]' sh "$HELPER" "$FIRST" "$SECOND" || fail 'generation switch in installer shell'
CONCURRENT="$CASE_ROOT/concurrent"
mkdir -p "$CONCURRENT/config"
printf 'same selection\n' > "$CONCURRENT/config/active_font.conf"
prepare_fixture "$CONCURRENT"
initialize "$CONCURRENT" & ONE=$!
initialize "$CONCURRENT" & TWO=$!
wait "$ONE" || fail 'first concurrent initializer'
wait "$TWO" || fail 'second concurrent initializer'
[ "$(cat "$CONCURRENT/config/active_font.conf")" = 'same selection' ] || fail 'concurrent selection'
[ ! -e "$CONCURRENT/.luoshu-state/.paths-migrate.lock" ] || fail 'concurrent lock retained'

# A real interrupted move must release the kernel lock while this test's parent
# remains alive, and the next initializer must resume without replacing its inode.
"$LUOSHU_RUNTIME_PATHS_PYTHON" - "$ROOT" "$CASE_ROOT" <<'PY'
import fcntl
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

root, cases = map(Path, sys.argv[1:])
module = cases / "killed-migration"
(module / "config").mkdir(parents=True)
(module / "common").mkdir()
(module / "config/active_font.conf").write_text("choice-before-kill\n")
helper = module / "common/runtime_paths.sh"
shutil.copy2(root / "common/runtime_paths.sh", helper)
shutil.copy2(root / "common/runtime_paths_lock.py", module / "common/runtime_paths_lock.py")
with helper.open("a") as target:
    target.write('''
# Test-only gate after the real legacy config directory has moved.
mv() {
    command mv "$@" || return
    case "$1" in
        */config)
            printf '%s\\n' "$$" > "$2/../test-migration-owner"
            kill -STOP "$$"
            ;;
    esac
}
''')
process = subprocess.Popen([sys.executable, str(module / "common/runtime_paths_lock.py"), str(module)])
try:
    gate = module / ".luoshu-state/test-migration-owner"
    deadline = time.monotonic() + 5
    while not gate.exists():
        assert process.poll() is None, "migration ended before interrupted move"
        assert time.monotonic() < deadline, "migration gate timeout"
        time.sleep(0.01)
    assert int(gate.read_text()) == process.pid, "kernel lock holder changed process at exec"
    lock = module / ".luoshu-state/.paths-migrate.flock"
    inode = lock.stat().st_ino
    with lock.open("r+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            raise AssertionError("exec migration did not retain its kernel lock")
    # The config really moved, but its old compatibility link was not committed.
    assert not (module / "config").exists()
    assert (module / ".luoshu-state/config/active_font.conf").read_text() == "choice-before-kill\n"
    process.kill()
    assert process.wait(timeout=5) == -signal.SIGKILL
finally:
    if process.poll() is None:
        process.kill()
        process.wait(timeout=5)
shutil.copy2(root / "common/runtime_paths.sh", helper)
environment = dict(os.environ, LUOSHU_RUNTIME_PATHS_PYTHON=sys.executable)
subprocess.run(["sh", "-c", '. "$1"; luoshu_runtime_paths_init "$2"',
                "sh", str(helper), str(module)], env=environment, check=True, timeout=5)
assert (module / "config").is_symlink()
assert (module / "config/active_font.conf").read_text() == "choice-before-kill\n"
assert lock.stat().st_ino == inode, "lock pathname replaced with a different kernel-lock inode"
with lock.open("r+") as handle:
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
PY

sh -n "$HELPER"
sh -ec '. "$1"; case "$-" in *e*) ;; *) exit 1;; esac' sh "$HELPER" || fail 'sourcing changes errexit'
printf 'Central runtime path migration checks passed.\n'
