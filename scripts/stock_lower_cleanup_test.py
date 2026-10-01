"""Failure injection for production lower capture; no fake mount success claim."""
import os,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class LowerCleanupTest(unittest.TestCase):
 def run_case(self,body):
  with tempfile.TemporaryDirectory() as td:
   env=dict(os.environ,CASE_ROOT=td,BACKEND=os.environ.get('BACKEND_SCRIPT',str(ROOT/'common/mount_self_backend.sh')))
   script='''set -eu
r="$CASE_ROOT"
mkdir -p "$r/source" "$r/target" "$r/state/lower"
printf original > "$r/target/font.ttf"
_luoshu_self_state_root() { printf '%s/state\\n' "$r"; }
_luoshu_umount_cmd() { return 1; }
_luoshu_mount_cmd() {
 printf '%s\\n' "$*" >> "$r/calls"
 case "$1" in
  -o) if [ "$2" = private ]; then [ "${FAIL_PRIVATE:-0}" != 1 ]; else cp -a "$3/." "$4/"; fi ;;
  -t) [ "${FAIL_OVERLAY:-0}" != 1 ] ;;
  *) return 1 ;;
 esac
}
. "$BACKEND"
set -eu
_lsme_mount_list="$r/owned"
: > "$_lsme_mount_list"
'''+body
   result=subprocess.run(['sh','-c',script],env=env,capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
 def test_existing_failed_unmount_preserves_every_byte(self):
  for function in ('_luoshu_capture_lower_dir "$r/target" system-fonts','_luoshu_overlay_mount_dir "$r/source" "$r/target" system-fonts'):
   self.run_case('mkdir "$r/state/lower/system-fonts"\nprintf retained > "$r/state/lower/system-fonts/retained.ttf"\nif '+function+'; then exit 8; fi\ntest "$(cat "$r/state/lower/system-fonts/retained.ttf")" = retained\ntest ! -e "$r/calls"\n')
 def test_failed_overlay_and_failed_unmount_never_delete_bound_content(self):
  self.run_case('FAIL_OVERLAY=1\nif _luoshu_overlay_mount_dir "$r/source" "$r/target" system-fonts; then exit 8; fi\ntest "$(cat "$r/state/lower/system-fonts/font.ttf")" = original\ngrep -Fqx "$r/state/lower/system-fonts" "$r/owned"\n')
 def test_private_failure_rejects_capture_and_records_owned_mount(self):
  self.run_case('FAIL_PRIVATE=1\nif _luoshu_capture_lower_dir "$r/target" system-fonts; then exit 8; fi\ntest "$(cat "$r/state/lower/system-fonts/font.ttf")" = original\ngrep -Fqx "$r/state/lower/system-fonts" "$r/owned"\n')
 def test_private_capture_success_keeps_original_and_ownership(self):
  self.run_case('_luoshu_capture_lower_dir "$r/target" system-fonts\ntest "$(cat "$r/state/lower/system-fonts/font.ttf")" = original\ngrep -q -- "-o private none" "$r/calls"\ngrep -Fqx "$r/state/lower/system-fonts" "$r/owned"\n')
if __name__=='__main__':unittest.main()
