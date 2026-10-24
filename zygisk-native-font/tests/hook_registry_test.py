#!/usr/bin/env python3
"""The hook registry (src/hooks.def) may only name allow-listed creation-time hooks.

Drawing / paint / layout / canvas paths must never be hooked. Every JNI method the sources hand to
a hook registrar (kFontBuilderClass / kNBuildName style constants) must be declared in the registry.
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
    headers = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "src").glob("*.h"))
    consts = dict(re.findall(r'constexpr const char \*(k\w+) = "([^"]+)";', headers))
    declared = {t for k, t in entries if k == "jni"}
    cls, name = consts.get("kFontBuilderClass"), consts.get("kNBuildName")
    if cls and name and f"{cls}.{name}" not in declared:
        errors.append(f"sources hook {cls}.{name} but hooks.def does not declare it")
    for sym in re.findall(r"JNINativeMethod\s+\w+\[\]\s*=\s*\{\{\s*\"?(\w+)", src):
        if not any(t.endswith("." + sym) for t in declared) and sym not in consts:
            errors.append(f"JNI method {sym} registered by the sources is not declared in hooks.def")
    # Drawing paths stay untouched in the sources too, not only in the registry.
    for m in re.finditer(r"hookJniNativeMethods\([^;]*", src):
        if FORBIDDEN.search(m.group(0)):
            errors.append(f"drawing/layout path hooked in sources: {m.group(0)[:80]}")
    for e in errors:
        print(f"::error::{e}", file=sys.stderr)
    print(f"hook registry: {len(entries)} entries, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
