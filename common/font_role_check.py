#!/usr/bin/env python3
"""Strict role coverage gate used before a LuoShu composite task is queued.

The selected CJK face becomes the complete base of the generated composite.  A
font collection is therefore accepted only when one concrete face contains a
usable CJK base together with Latin, digits and common punctuation.  This keeps
an English-only face, a symbol face or a .notdef-heavy face from reaching the
Android font renderer.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from fontTools.ttLib import TTCollection, TTFont

CJK = tuple(map(ord, "一丁七万三上下不与中为主人了二于五人今从他会但你作使入全国其分到前力十又只可同后和在地大天好学家小年心我日时有来民生的看种行要见言这"))
LATIN = tuple(map(ord, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"))
DIGITS = tuple(map(ord, "0123456789"))
PUNCTUATION = tuple(map(ord, ".,!?-:;()[]/+'\"，。！？：；（）【】《》、"))


def required(role: str) -> tuple[int, ...]:
    """Return the hard-required codepoints for a role.

    Punctuation remains a scored compatibility group instead of a hard list so
    decorative fonts are not rejected for one optional symbol.  CJK fonts must
    still carry complete Latin and digit coverage because they become the base
    face of the generated Android family.
    """
    if role == "cjk":
        return CJK + LATIN + DIGITS
    if role == "latin":
        return LATIN
    if role == "digit":
        return DIGITS
    raise ValueError(f"unsupported role: {role}")


class RoleCheckError(RuntimeError):
    pass


def is_collection(path: Path) -> bool:
    with path.open("rb") as stream:
        return stream.read(4) == b"ttcf"


def face_indexes(path: Path) -> range:
    if not is_collection(path):
        return range(1)
    collection = TTCollection(str(path), lazy=True)
    try:
        return range(len(collection.fonts))
    finally:
        collection.close()


def open_face(path: Path, index: int) -> TTFont:
    kwargs: dict[str, Any] = {"lazy": True, "recalcTimestamp": False}
    if is_collection(path):
        kwargs["fontNumber"] = index
    return TTFont(str(path), **kwargs)


def usable_glyphs(font: TTFont, probes: tuple[int, ...]) -> tuple[list[int], list[int], set[str]]:
    cmap = font.getBestCmap() or {}
    glyph_order = set(font.getGlyphOrder())
    present: list[int] = []
    missing: list[int] = []
    names: set[str] = set()
    for codepoint in probes:
        name = cmap.get(codepoint)
        if not name or name == ".notdef" or name not in glyph_order:
            missing.append(codepoint)
            continue
        present.append(codepoint)
        names.add(name)
    return present, missing, names


def ratio(present: list[int], probes: tuple[int, ...]) -> float:
    return len(present) / len(probes) if probes else 1.0


def inspect_face(path: Path, index: int, role: str) -> dict[str, object]:
    font = open_face(path, index)
    try:
        groups: dict[str, dict[str, object]] = {}
        probe_groups = {
            "cjk": CJK,
            "latin": LATIN,
            "digits": DIGITS,
            "punctuation": PUNCTUATION,
        }
        for name, probes in probe_groups.items():
            present, missing, glyph_names = usable_glyphs(font, probes)
            groups[name] = {
                "hits": len(present),
                "total": len(probes),
                "ratio": ratio(present, probes),
                "uniqueGlyphs": len(glyph_names),
                "missing": missing,
            }

        if role == "cjk":
            cjk = groups["cjk"]
            valid = (
                float(cjk["ratio"]) >= 0.95
                and int(cjk["uniqueGlyphs"]) >= max(12, int(int(cjk["hits"]) * 0.75))
                and float(groups["latin"]["ratio"]) == 1.0
                and float(groups["digits"]["ratio"]) == 1.0
                and float(groups["punctuation"]["ratio"]) >= 0.85
            )
            selected = ("cjk", "latin", "digits", "punctuation")
        elif role == "latin":
            valid = float(groups["latin"]["ratio"]) == 1.0
            selected = ("latin",)
        else:
            valid = float(groups["digits"]["ratio"]) == 1.0
            selected = ("digits",)

        missing_codes: list[int] = []
        for name in selected:
            missing_codes.extend(groups[name]["missing"])  # type: ignore[arg-type]
        present_count = sum(int(groups[name]["hits"]) for name in selected)
        required_count = sum(int(groups[name]["total"]) for name in selected)
        score = sum(float(groups[name]["ratio"]) for name in selected)
        return {
            "face": index if is_collection(path) else -1,
            "required": required_count,
            "present": present_count,
            "missing": [f"U+{codepoint:04X}" for codepoint in missing_codes[:24]],
            "coverage": {
                name: round(float(values["ratio"]) * 100)
                for name, values in groups.items()
            },
            "uniqueCjkGlyphs": int(groups["cjk"]["uniqueGlyphs"]),
            "score": score,
            "valid": valid,
        }
    finally:
        font.close()


def check(path: Path, role: str) -> dict[str, object]:
    if not path.is_file() or path.stat().st_size < 4096:
        raise RoleCheckError("字体文件不存在或文件过小")
    results = [inspect_face(path, index, role) for index in face_indexes(path)]
    best = max(
        results,
        key=lambda item: (
            1 if item["valid"] else 0,
            float(item["score"]),
            int(item["present"]),
        ),
        default=None,
    )
    if best is None:
        raise RoleCheckError("字体中没有可读取的字体面")
    return {
        "status": "ok" if best["valid"] else "error",
        "role": role,
        "path": str(path),
        "faces": len(results),
        **{key: value for key, value in best.items() if key != "score"},
        "message": (
            "字形角色检查通过"
            if best["valid"]
            else "没有任何单一字体面满足该角色所需的完整字形覆盖"
        ),
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
