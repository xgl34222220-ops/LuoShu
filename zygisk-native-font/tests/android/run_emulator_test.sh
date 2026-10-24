#!/bin/sh
# Push the harness and run it on the connected emulator.
#   run_emulator_test.sh HARNESS_DIR
# HARNESS_DIR: harness.dex, libluoshu_nf_harness.so (x86_64) and the font files the test uses.
set -eu
src="$1"
dst=/data/local/tmp/lsnf
adb shell "rm -rf $dst && mkdir -p $dst"
for f in "$src"/*; do adb push "$f" "$dst/" >/dev/null; done
adb shell "chmod 0755 $dst/libluoshu_nf_harness.so"
out=$(adb shell "cd $dst && app_process -Djava.class.path=$dst/harness.dex /system/bin LsnfHarness $dst" 2>&1 || true)
echo "$out"
echo "$out" | grep -q 'LSNF-HARNESS PASS'
