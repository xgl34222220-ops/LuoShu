#!/bin/sh
# The emulator action executes each YAML script line separately. Keep compound
# shell control flow in this single process so native-only cannot fall through.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$ROOT"
if [ "${LUOSHU_NATIVE_PREPARE_TEST_APPROVED:-false}" = true ]; then
    exec python3 experiments/android-font-contract/run_native_prepare.py \
        --runtime experiments/android-font-contract/.runtime-x86 \
        --fixtures experiments/android-font-contract/app/src/main/assets \
        --output experiments/android-font-contract/output/android-native-prepare
fi
python3 experiments/android-font-contract/run_emulator.py \
    --apk experiments/android-font-contract/app/build/outputs/apk/debug/app-debug.apk \
    --output experiments/android-font-contract/output
python3 experiments/android-font-contract/run_native_runtime.py \
    --runtime experiments/android-font-contract/.runtime-x86 \
    --source experiments/android-font-contract/app/src/main/assets/composite.ttf \
    --output experiments/android-font-contract/output/android-runtime
if [ "${LUOSHU_DISPOSABLE_SYSTEM_TEST_APPROVED:-false}" = true ]; then
    python3 experiments/android-font-contract/run_system_emulator.py \
        --production-payload --matching-weight-family --module-app-default \
        --module-staged-hooks --output experiments/android-font-contract/output/system
fi
