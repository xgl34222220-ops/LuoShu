#!/system/bin/sh
# Compatibility entrypoint. The implementation lives in app_multiweight_real.sh.
SCRIPT_DIR="${0%/*}"
exec sh "$SCRIPT_DIR/app_multiweight_real.sh" "$@"
