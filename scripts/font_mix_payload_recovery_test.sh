#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
python3 - "$ROOT/common/font_mix.sh" "$TMP/functions.sh" <<'PY'
import re, sys
from pathlib import Path
source = Path(sys.argv[1]).read_text()
names = ('recover_interrupted_payload','payload_stage_begin','payload_stage_activate',
         'payload_stage_abort','payload_stage_rollback','payload_stage_finalize')
Path(sys.argv[2]).write_text('\n'.join(re.search(r'^' + name + r'\(\) \{.*?^\}',source,re.M|re.S).group() for name in names))
PY
. "$TMP/functions.sh"
MODDIR="$TMP/module"
LUOSHU_TMP_DIR="$MODDIR/.luoshu-state/tmp"
LUOSHU_TASK_SCOPE_TMPDIR="$LUOSHU_TMP_DIR/task-owned"
LUOSHU_TASK_SCOPE_TASK=recovery-test
PAYLOAD_COMMIT_MARKER="$LUOSHU_TMP_DIR/font-payload-commit.ok"
SYSTEM_FONTS_DIR="$MODDIR/system/fonts"
mkdir -p "$SYSTEM_FONTS_DIR" "$LUOSHU_TASK_SCOPE_TMPDIR"
printf 'original-font-bytes\n' >"$SYSTEM_FONTS_DIR/font.ttf"
payload_stage_begin
case "$PAYLOAD_STAGE" in "$LUOSHU_TASK_SCOPE_TMPDIR"/*) ;; *) exit 1 ;; esac
case "$PAYLOAD_BACKUP" in "$LUOSHU_TMP_DIR"/payload-backup.*) ;; *) exit 1 ;; esac
printf 'replacement-font-bytes\n' >"$PAYLOAD_STAGE/font.ttf"
payload_stage_activate
test "$(cat "$SYSTEM_FONTS_DIR/font.ttf")" = replacement-font-bytes
SAVED_BACKUP="$PAYLOAD_BACKUP"
# A real command failure must leave the original bytes outside auto-cleaned scope tmp.
mv() { case "$1" in "$SAVED_BACKUP") return 1 ;; esac; command mv "$@"; }
if payload_stage_rollback; then exit 1; fi
test "$(cat "$SAVED_BACKUP/font.ttf")" = original-font-bytes
test "$PAYLOAD_BACKUP" = "$SAVED_BACKUP"
test "$PAYLOAD_ACTIVATED" = 1
if recover_interrupted_payload; then exit 1; fi
test "$(cat "$SAVED_BACKUP/font.ttf")" = original-font-bytes
unset -f mv
recover_interrupted_payload
test "$(cat "$SYSTEM_FONTS_DIR/font.ttf")" = original-font-bytes
test ! -e "$SAVED_BACKUP"
# Activation failure and failed immediate restore preserve the same rollback copy.
payload_stage_begin
printf 'replacement-2\n' >"$PAYLOAD_STAGE/font.ttf"
SAVED_BACKUP="$PAYLOAD_BACKUP"
SAVED_STAGE="$PAYLOAD_STAGE"
mv() {
    case "$1" in "$SAVED_STAGE"|"$SAVED_BACKUP") return 1 ;; esac
    command mv "$@"
}
if payload_stage_activate; then exit 1; fi
test "$(cat "$SAVED_BACKUP/font.ttf")" = original-font-bytes
unset -f mv
recover_interrupted_payload
test "$(cat "$SYSTEM_FONTS_DIR/font.ttf")" = original-font-bytes
test ! -e "$SAVED_BACKUP"
# Exercise the public recovery CLI, including its final JSON and return code.
mkdir -p "$MODDIR/common" "$TMP/bin"
for part in task_scope.sh task_scope.py background_task.sh runtime_paths.sh runtime_paths_lock.py; do
    ln -s "$ROOT/common/$part" "$MODDIR/common/$part"
done
printf 'id=LuoShu\n' > "$MODDIR/module.prop"
CLI_BACKUP="$LUOSHU_TMP_DIR/payload-backup.cli-failure"
mkdir -p "$CLI_BACKUP"
printf 'original-cli-font\n' > "$CLI_BACKUP/font.ttf"
cat > "$TMP/bin/mv" <<'EOF'
#!/bin/sh
[ "$1" != "$EXPECTED_BACKUP" ] || exit 9
exec /bin/mv "$@"
EOF
chmod 0755 "$TMP/bin/mv"
if MODDIR="$MODDIR" EXPECTED_BACKUP="$CLI_BACKUP" PATH="$TMP/bin:$PATH" \
    LUOSHU_TASK_SCOPE_PYTHON=python3 LUOSHU_RUNTIME_PATHS_PYTHON=python3 \
    sh "$ROOT/common/font_mix.sh" recover > "$TMP/recover.out" 2> "$TMP/recover.err"; then
    exit 1
fi
grep -q '"status":"error"' "$TMP/recover.out"
test "$(cat "$CLI_BACKUP/font.ttf")" = original-cli-font
grep -q '"cleaned": true' "$TMP/recover.err"
printf 'font_mix_payload_recovery_test: PASS\n'
