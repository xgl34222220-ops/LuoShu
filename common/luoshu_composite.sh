#!/system/bin/sh
set -eu
MODDIR="${MODDIR:-$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)}"
RUNTIME="$MODDIR/common/python"
PYBIN="$RUNTIME/bin/luoshu-python"
[ -x "$PYBIN" ] || { echo '{"status":"error","message":"复合字体运行时缺失"}' >&2; exit 20; }
export PYTHONHOME="$RUNTIME"
export PYTHONPATH="$RUNTIME/lib/python3.14:$RUNTIME/lib/python3.14/site-packages"
export LD_LIBRARY_PATH="$RUNTIME/lib:$RUNTIME/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export TMPDIR="${TMPDIR:-$MODDIR/cache/tmp}"
mkdir -p "$TMPDIR" 2>/dev/null || true
case "$(uname -m 2>/dev/null || true)" in
    aarch64|arm64) ;;
    x86_64)
        # Narrow official-AVD compatibility: execute the unchanged ARM64 runtime
        # via Android's native bridge. Never spoof uname or use a host runtime.
        if [ "$(getprop ro.kernel.qemu 2>/dev/null)" != "1" ] ||
           [ "$(getprop ro.enable.native.bridge.exec 2>/dev/null)" != "1" ] ||
           [ "$(getprop ro.dalvik.vm.native.bridge 2>/dev/null)" != "libndk_translation.so" ] ||
           ! command -v timeout >/dev/null 2>&1 ||
           ! timeout 15 "$PYBIN" -c 'import fontTools, sys; from fontTools.ttLib import TTFont; f = open(sys.executable, "rb"); h = f.read(20); f.close(); assert h[:4] == b"\x7fELF" and int.from_bytes(h[18:20], "little") == 183' >/dev/null 2>&1; then
            echo '{"status":"error","message":"模拟器未通过原 ARM64 运行时兼容验证"}' >&2
            exit 21
        fi
        ;;
    *) echo '{"status":"error","message":"完整复合字体引擎仅支持 ARM64"}' >&2; exit 21 ;;
esac
if [ "${1:-}" = "--self-test" ]; then
    exec "$PYBIN" -c 'import fontTools; print("ok")'
fi
exec "$PYBIN" "$MODDIR/common/composite_font.py" "$@"
