#!/usr/bin/env python3
"""The hook registry (src/hooks.def) may only name allow-listed creation-time hooks.

Drawing / paint / layout / canvas paths must never be hooked. N1 ships an empty registry; later
stages add entries here and to ALLOWED in the same change.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALLOWED = {
    ("jni", "android/graphics/fonts/Font$Builder.nBuild"),
    ("jni", "android/graphics/FontFamily.nAddFont"),
    ("jni", "android/graphics/FontFamily.nAddFontWeightStyle"),
    ("jni", "java/lang/Runtime.nativeLoad"),
    *{("plt", f"libflutter.so:{s}") for s in (
        "openat", "open", "__open_2", "fopen", "AAssetManager_open", "AAsset_getBuffer", "AAsset_getLength",
        "AAsset_getLength64", "AAsset_getRemainingLength", "AAsset_getRemainingLength64", "AAsset_read",
        "AAsset_seek", "AAsset_seek64", "AAsset_openFileDescriptor", "AAsset_openFileDescriptor64",
        "AAsset_close")},
}
FORBIDDEN = re.compile(r"draw|paint|layout|canvas|render|shaper|harfbuzz|hb_|minikin.*layout", re.I)


def main() -> int:
    errors = []
    entries = []
    for n, raw in enumerate((ROOT / "src" / "hooks.def").read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            errors.append(f"line {n}: expected '<kind> <target>'")
            continue
        entry = (parts[0], parts[1])
        entries.append(entry)
        if FORBIDDEN.search(parts[1]):
            errors.append(f"line {n}: drawing/layout path is never hooked: {parts[1]}")
        if entry not in ALLOWED:
            errors.append(f"line {n}: not in allow list: {line}")
    # Sources must not hook anything the registry does not declare.
    src = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "src").glob("*.cpp"))
    if not entries and re.search(r"hookJniNativeMethods|pltHookRegister|pltHookCommit", src):
        errors.append("sources install hooks but hooks.def is empty")
    for e in errors:
        print(f"::error::{e}", file=sys.stderr)
    print(f"hook registry: {len(entries)} entries, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
