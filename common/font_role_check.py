#!/usr/bin/env python3
"""Fast role coverage gate used before a LuoShu composite task is queued."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont

CJK = tuple(map(ord, "中文字体系统默认洛书汉字"))
LATIN = tuple(map(ord, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"))
DIGITS = tuple(map(ord, "0123456789"))
PUNCT = tuple(map(ord, " .,!?;:()[]+-/%"))


class RoleCheckError(RuntimeError):
    pass


def is_collection(path: Path) -> bool:
    with path.open("rb") as stream:
        return stream.read(4) == b"ttcf"


def faces(path: Path) -> range:
    if not is_collection(path):
        return range(1)
    collection = TTCollection(str(path), lazy=True)
    try:
        return range(len(collection.fonts))
    finally:
        collection.close()


def required(role: str) -> tuple[int, ...]:
    if role == "cjk":
        return CJK + LATIN + DIGITS + PUNCT
    if role == "latin":
        return LATIN + PUNCT
    return DIGITS + PUNCT


def inspect_face(path: Path, index: int, role: str) -> dict[str, object]:
    kwargs: dict[str, object] = {"lazy": True, "recalcTimestamp": False}
    if is_collection(path):
        kwargs["fontNumber"] = index
    font = TTFont(str(path), **kwargs)
    try:
        cmap = font.getBestCmap() or {}
        probes = required(role)
        missing = [codepoint for codepoint in probes if codepoint not in cmap]
        return {
            "face": index if is_collection(path) else -1,
            "required": len(probes),
            "present": len(probes) - len(missing),
            "missing": [f"U+{codepoint:04X}" for codepoint in missing[:16]],
            "valid": not missing,
        }
    finally:
        font.close()


def check(path: Path, role: str) -> dict[str, object]:
    if not path.is_file() or path.stat().st_size < 4096:
        raise RoleCheckError("字体文件不存在或文件过小")
    results = [inspect_face(path, index, role) for index in faces(path)]
    best = max(results, key=lambda item: int(item["present"]), default=None)
    if best is None:
        raise RoleCheckError("字体中没有可读取的字体面")
    return {
        "status": "ok" if best["valid"] else "error",
        "role": role,
        "path": str(path),
        **best,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("font")
    parser.add_argument("role", choices=("cjk", "latin", "digit"))
    args = parser.parse_args()
    try:
        result = check(Path(args.font), args.role)
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0 if result["valid"] else 2
    except Exception as error:
        print(
            json.dumps(
                {"status": "error", "role": args.role, "message": str(error) or error.__class__.__name__},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
