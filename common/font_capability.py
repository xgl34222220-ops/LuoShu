#!/usr/bin/env python3
"""Font capability decisions shared by import and slot mapping.

One place answers the questions every mapper used to guess from filenames:

* which weight a face really has (OS/2 usWeightClass reconciled with its style
  name, with ExtraBold/UltraLight/SemiBold parsed before Bold/Light);
* which face of a user family serves each 100..900 slot: a static face of that
  weight, a variable font instantiated on its fvar ``wght`` axis, or the nearest
  available weight (never "everything falls back to Regular");
* which faces of a TTC/OTC collection are usable, routed by face index;
* italic faces never serve upright slots and vice versa;
* colour (emoji) fonts and the slots that hold them are recognised so a text
  font is never written over NotoColorEmoji;
* whether a font covers the script a language-specific fallback slot exists
  for, so a font that lacks Traditional Chinese or rare Han keeps the stock
  fallback chain instead of replacing it.

The module only reads fonts, except for ``materialize`` which writes one
requested face/instance to an explicit output path.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from fontTools.ttLib import TTCollection, TTFont

SLOT_WEIGHTS = (100, 200, 300, 400, 500, 600, 700, 800, 900)
COLOR_TABLES = ("COLR", "CBDT", "CBLC", "sbix", "SVG ")
OUTLINE_TABLES = ("glyf", "CFF ", "CFF2")

# ---------------------------------------------------------------- weight names
# Exact tokens only: "Highlight" or "Nothing" must not read as Light/Thin.
_COMPOUND = {
    ("extra", "black"): 900, ("ultra", "black"): 900,
    ("extra", "bold"): 800, ("ultra", "bold"): 800,
    ("semi", "bold"): 600, ("demi", "bold"): 600,
    ("extra", "light"): 200, ("ultra", "light"): 200,
    ("extra", "thin"): 100, ("ultra", "thin"): 100,
}
_SINGLE = {
    "extrablack": 900, "ultrablack": 900,
    "extrabold": 800, "ultrabold": 800,
    "semibold": 600, "demibold": 600,
    "extralight": 200, "ultralight": 200,
    "extrathin": 100, "ultrathin": 100, "xthin": 100,
    "hairline": 100, "thin": 100,
    "black": 900, "heavy": 900,
    "bold": 700,
    "medium": 500,
    "light": 300,
    "regular": 400, "normal": 400, "book": 400, "roman": 400, "plain": 400,
}
# Longest first so 特粗 wins over 粗 and 极细 over 细.
_CJK_WEIGHTS = (
    ("极细", 100), ("纤细", 200), ("特细", 200), ("中粗", 600), ("半粗", 600),
    ("特粗", 800), ("超粗", 900), ("细体", 300), ("常规", 400), ("标准", 400),
    ("中等", 500), ("粗体", 700), ("重体", 900), ("黑体", None),
)
_TOKEN_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")
_W_RE = re.compile(r"^w([1-9])$")


def weight_from_name(name: str) -> int | None:
    """Weight a style or file name states, or ``None`` when it states none."""
    text = Path(str(name or "")).name
    for suffix in (".ttf", ".otf", ".ttc", ".otc", ".font"):
        if text.lower().endswith(suffix):
            text = text[: -len(suffix)]
            break
    if text.isdigit() and 100 <= int(text) <= 900:
        return int(text)
    for term, value in _CJK_WEIGHTS:
        if term in text and value is not None:
            return value
    tokens = [token.lower() for token in _TOKEN_RE.findall(text)]
    found: int | None = None
    index = 0
    while index < len(tokens):
        token = tokens[index]
        pair = (token, tokens[index + 1]) if index + 1 < len(tokens) else None
        if pair in _COMPOUND:
            return _COMPOUND[pair]
        if token in _SINGLE and _SINGLE[token] != 400:
            return _SINGLE[token]
        if token in _SINGLE:
            found = 400
        match = _W_RE.match(token)
        if match:
            return int(match.group(1)) * 100
        if token == "w" and index + 1 < len(tokens) and re.fullmatch(r"[1-9]", tokens[index + 1]):
            return int(tokens[index + 1]) * 100
        if token.isdigit() and len(token) == 3 and 100 <= int(token) <= 900 and int(token) % 50 == 0:
            return int(token)
        index += 1
    return found


# ---------------------------------------------------------------- slot names
def is_variable_slot_name(name: str) -> bool:
    """A ROM slot that declares a variable font (MiSansVF, GoogleSans-VF, ...)."""
    stem = Path(name).stem
    tokens = _TOKEN_RE.findall(stem)
    return (any(token in ("VF", "Variable", "Flex") for token in tokens)
            or stem.endswith("VF") or "-VF" in stem or "_VF" in stem
            or "VF_" in stem or "VF-" in stem)


def is_emoji_slot_name(name: str) -> bool:
    return "emoji" in Path(name).name.lower()


def is_italic_slot_name(name: str) -> bool:
    lower = Path(name).name.lower()
    return "italic" in lower or "oblique" in lower


def is_serif_slot_name(name: str) -> bool:
    lower = Path(name).name.lower()
    return "serif" in lower and "sans-serif" not in lower and "sansserif" not in lower


# Language-specific fallback slots: replacing them only makes sense when the
# donor covers that script. Main UI slots (MiSansVF, MiSansVF_Overlay) are not
# gated; MiSansL3 is already kept stock by the HyperOS policy.
_HANT_SLOT_RE = re.compile(r"(TCVF|TC[-_.]|TC$|HK|Hant|CJKtc|CJKhk|CJKTC|CJKHK)")
_HAN_SLOT_RE = re.compile(r"(^NotoSansCJK|^NotoSansSC|^NotoSansHans|CJKsc|CJKSC|^DroidSansFallback)")

# A Traditional Chinese UI sample (frequent characters whose Hant form differs
# from Hans) and a frequent Simplified/shared Han sample.
HANT_PROBES = tuple(map(ord, "這個們說時國會來後對當過還實讓體點樣與麼開關問題門東車長書見"))
HAN_PROBES = tuple(map(ord, "的一是不了人我在有他这中大来上个国到说们为子和你地出道也时年得就那要下以生会自着去之过家学对可"))
SCRIPT_COVERAGE_MIN = 0.9


def fallback_script_for_slot(name: str) -> str | None:
    stem = Path(name).stem
    if stem.startswith(("MiSansVF", "MiSansLatin")):
        return None
    if _HANT_SLOT_RE.search(stem):
        return "hant"
    if _HAN_SLOT_RE.search(stem):
        return "han"
    return None


def script_coverage(cmap: dict, script: str) -> float:
    probes = HANT_PROBES if script == "hant" else HAN_PROBES
    return sum(1 for codepoint in probes if codepoint in cmap) / len(probes)


# ---------------------------------------------------------------- faces
@dataclass
class Face:
    path: str
    index: int  # -1 for a single SFNT, otherwise the collection face index
    family: str = ""
    subfamily: str = ""
    weight: int = 400
    weight_source: str = "default"
    italic: bool = False
    variable: bool = False
    wght: tuple[float, float, float] | None = None  # min, default, max
    color: bool = False
    supported: bool = True
    reason: str = ""
    extra_axes: list[str] = field(default_factory=list)


def is_collection(path: Path) -> bool:
    try:
        with path.open("rb") as stream:
            return stream.read(4) == b"ttcf"
    except OSError:
        return False


def collection_size(path: Path) -> int:
    collection = TTCollection(str(path), lazy=True)
    try:
        return len(collection.fonts)
    finally:
        collection.close()


def _name(font: TTFont, getter: str, name_id: int, fallback: str) -> str:
    try:
        table = font["name"]
        value = getattr(table, getter)() or table.getDebugName(name_id)
        return " ".join(str(value or fallback).split())
    except Exception:
        return fallback


def _os2_weight(font: TTFont) -> int | None:
    try:
        value = int(font["OS/2"].usWeightClass)
    except Exception:
        return None
    if 1 <= value <= 9:  # pre-OpenType 1..9 scale
        value *= 100
    return value if 1 <= value <= 1000 else None


def _italic(font: TTFont, subfamily: str) -> bool:
    try:
        if int(font["OS/2"].fsSelection) & 0x01:
            return True
    except Exception:
        pass
    try:
        if int(font["head"].macStyle) & 0x02:
            return True
    except Exception:
        pass
    lower = subfamily.lower()
    return "italic" in lower or "oblique" in lower


def reconcile_weight(os2: int | None, named: int | None) -> tuple[int, str]:
    """usWeightClass is authoritative unless it is missing or the generic 400
    while the style name states a different weight (a common authoring slip)."""
    if os2 is None:
        return (named or 400), ("name" if named else "default")
    if os2 == 400 and named is not None and named != 400:
        return named, "name"
    return os2, "os2"


def inspect_face(path: Path, index: int) -> Face:
    kwargs = {"lazy": True, "recalcTimestamp": False}
    if index >= 0:
        kwargs["fontNumber"] = index
    face = Face(path=str(path), index=index)
    try:
        font = TTFont(str(path), **kwargs)
    except Exception as error:  # damaged face
        face.supported = False
        face.reason = f"无法读取字体面：{error.__class__.__name__}"
        return face
    try:
        face.family = _name(font, "getBestFamilyName", 1, path.stem)
        face.subfamily = _name(font, "getBestSubFamilyName", 2, "Regular")
        named = weight_from_name(face.subfamily)
        if named is None and index < 0:
            named = weight_from_name(path.name)
        face.weight, face.weight_source = reconcile_weight(_os2_weight(font), named)
        face.italic = _italic(font, face.subfamily)
        face.color = any(tag in font for tag in COLOR_TABLES)
        if not any(tag in font for tag in OUTLINE_TABLES):
            face.supported = False
            face.reason = "字体面没有 glyf/CFF/CFF2 轮廓（仅位图或损坏），不能作为文字字体"
        if "cmap" not in font:
            face.supported = False
            face.reason = "字体面缺少 cmap 字符映射表"
        if "fvar" in font:
            face.variable = True
            for axis in font["fvar"].axes:
                tag = str(axis.axisTag)
                if tag == "wght":
                    face.wght = (float(axis.minValue), float(axis.defaultValue), float(axis.maxValue))
                else:
                    face.extra_axes.append(tag)
            if face.wght:
                face.weight = int(round(face.wght[1]))
                face.weight_source = "fvar-default"
    finally:
        font.close()
    return face


def faces_for(path: Path) -> list[Face]:
    if is_collection(path):
        count = collection_size(path)
        if not 1 <= count <= 256:
            raise ValueError(f"{path.name}：字体集合的字体面数量异常")
        return [inspect_face(path, index) for index in range(count)]
    return [inspect_face(path, -1)]


def _resolve_collisions(faces: list[Face]) -> None:
    """Static faces that claim one usWeightClass while their names disagree
    (whole family authored as 400) are separated by their style names."""
    by_key: dict[tuple[bool, int], list[Face]] = {}
    for face in faces:
        if face.supported and not face.variable:
            by_key.setdefault((face.italic, face.weight), []).append(face)
    for group in by_key.values():
        if len(group) < 2:
            continue
        for face in group:
            named = weight_from_name(face.subfamily)
            if named is None and face.index < 0:
                named = weight_from_name(Path(face.path).name)
            if named is not None and named != face.weight:
                face.weight, face.weight_source = named, "name"


def collect_faces(paths: Iterable[Path]) -> list[Face]:
    faces: list[Face] = []
    for path in paths:
        faces.extend(faces_for(Path(path)))
    _resolve_collisions(faces)
    return faces


# ---------------------------------------------------------------- planning
@dataclass
class SlotChoice:
    weight: int
    path: str
    index: int
    mode: str  # exact | instance | nearest | nearest-instance
    wght: float | None
    source_weight: int


def _usable(faces: Iterable[Face], italic: bool) -> list[Face]:
    return [face for face in faces if face.supported and not face.color and face.italic == italic]


def _distance(face: Face, target: int) -> float:
    if face.wght:
        low, _default, high = face.wght
        if low <= target <= high:
            return 0.0
        return min(abs(low - target), abs(high - target))
    return float(abs(face.weight - target))


def _effective(face: Face, target: int) -> int:
    if face.wght:
        low, _default, high = face.wght
        return int(round(max(low, min(high, target))))
    return face.weight


def _tie_break(face: Face, target: int) -> tuple:
    effective = _effective(face, target)
    heavier = effective > target
    # CSS-like direction: from 400 up prefer heavier, below 400 prefer lighter.
    prefer = heavier if target >= 400 else not heavier
    return (_distance(face, target), 0 if prefer else 1, 0 if face.index < 0 else 1, face.path, face.index)


def plan_slots(faces: list[Face], *, italic: bool = False,
               weights: Iterable[int] = SLOT_WEIGHTS) -> dict[int, SlotChoice]:
    """Pick the face for every weight slot. Empty when no face of that style exists."""
    pool = _usable(faces, italic)
    plan: dict[int, SlotChoice] = {}
    if not pool:
        return plan
    statics = [face for face in pool if not face.wght]
    variables = [face for face in pool if face.wght]
    for target in weights:
        exact = [face for face in statics if face.weight == target]
        if exact:
            face = min(exact, key=lambda item: (item.index >= 0, item.path, item.index))
            plan[target] = SlotChoice(target, face.path, face.index, "exact", None, face.weight)
            continue
        covering = [face for face in variables if face.wght[0] <= target <= face.wght[2]]
        if covering:
            face = min(covering, key=lambda item: (item.index >= 0, item.path, item.index))
            plan[target] = SlotChoice(target, face.path, face.index, "instance", float(target), target)
            continue
        face = min(pool, key=lambda item: _tie_break(item, target))
        if face.wght:
            value = _effective(face, target)
            plan[target] = SlotChoice(target, face.path, face.index, "nearest-instance", float(value), value)
        else:
            plan[target] = SlotChoice(target, face.path, face.index, "nearest", None, face.weight)
    return plan


def variable_source(faces: list[Face]) -> Face | None:
    """Upright variable face with a wght axis, to serve declared VF slots."""
    candidates = [face for face in _usable(faces, False) if face.wght]
    if not candidates:
        return None
    return min(candidates, key=lambda item: (item.index >= 0, -(item.wght[2] - item.wght[0]), item.path))


# ---------------------------------------------------------------- materialize
def has_fvar(path: Path) -> bool:
    try:
        index = 0 if is_collection(path) else -1
        kwargs = {"lazy": True}
        if index >= 0:
            kwargs["fontNumber"] = index
        with TTFont(str(path), **kwargs) as font:
            return "fvar" in font
    except Exception:
        return False


def is_color_font(path: Path) -> bool:
    try:
        return any(face.color for face in faces_for(path))
    except Exception:
        return False


def materialize(source: Path, index: int, wght: float | None, output: Path) -> dict:
    """Write one face (and optionally one wght instance) as a standalone SFNT.

    Line metrics are preserved: later per-ROM stages apply the stock slot
    contract, exactly as they do for a plain copied anchor.
    """
    if index < 0 and wght is None:
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output)
        os.chmod(output, 0o644)
        return {"status": "ok", "mode": "copy", "output": str(output)}
    kwargs = {"lazy": False, "recalcTimestamp": False, "recalcBBoxes": True}
    if index >= 0:
        kwargs["fontNumber"] = index
    font = TTFont(str(source), **kwargs)
    location: dict[str, float] = {}
    try:
        if wght is not None and "fvar" in font:
            from fontTools.varLib.instancer import instantiateVariableFont
            for axis in font["fvar"].axes:
                tag = str(axis.axisTag)
                value = float(wght) if tag == "wght" else float(axis.defaultValue)
                location[tag] = max(float(axis.minValue), min(float(axis.maxValue), value))
            font = instantiateVariableFont(font, location, inplace=False, optimize=True)
            if "OS/2" in font and "wght" in location:
                font["OS/2"].usWeightClass = max(1, min(1000, int(round(location["wght"]))))
        output.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(prefix=output.name + ".", suffix=".tmp",
                                             dir=output.parent, delete=False)
        temporary = Path(handle.name)
        handle.close()
        try:
            font.save(str(temporary), reorderTables=False)
            if temporary.stat().st_size < 1024:
                raise ValueError("生成的字体面异常为空")
            os.chmod(temporary, 0o644)
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
    finally:
        font.close()
    return {"status": "ok", "mode": "instance" if location else "face", "index": index,
            "location": location, "output": str(output)}


def build_anchors(fonts: list[Path], store: Path, *, prefix: str = "wght-",
                  italic: bool = False, weights: Iterable[int] = SLOT_WEIGHTS,
                  variable_anchor: str = "") -> list[tuple[int, Path, str]]:
    """Materialize one anchor per weight slot in one process.

    Identical (face, instance) choices share one file through hard links, so a
    single static Regular mapped to nine slots still costs one copy.
    """
    faces = collect_faces(fonts)
    plan = plan_slots(faces, italic=italic, weights=weights)
    store.mkdir(parents=True, exist_ok=True)
    made: dict[tuple[str, int, float | None], Path] = {}
    result: list[tuple[int, Path, str]] = []
    for weight in sorted(plan):
        choice = plan[weight]
        target = store / f"{prefix}{weight}.font"
        key = (choice.path, choice.index, choice.wght)
        if key in made:
            target.unlink(missing_ok=True)
            try:
                os.link(made[key], target)
            except OSError:
                shutil.copyfile(made[key], target)
        else:
            materialize(Path(choice.path), choice.index, choice.wght, target)
            made[key] = target
        result.append((weight, target, choice.mode))
    if variable_anchor and not italic:
        face = variable_source(faces)
        if face is not None:
            materialize(Path(face.path), face.index, None, store / variable_anchor)
    return result


# ---------------------------------------------------------------- CLI
def _plan_lines(plan: dict[int, SlotChoice]) -> list[str]:
    lines = []
    for weight in sorted(plan):
        choice = plan[weight]
        wght = "" if choice.wght is None else str(int(round(choice.wght)))
        lines.append(f"{weight}|{choice.path}|{choice.index}|{choice.mode}|{wght}|{choice.source_weight}")
    return lines


def _face_json(face: Face) -> dict:
    data = asdict(face)
    data["wght"] = list(face.wght) if face.wght else None
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_plan = sub.add_parser("plan", help="weight slot plan: weight|path|index|mode|wght|sourceWeight")
    p_plan.add_argument("--italic", action="store_true")
    p_plan.add_argument("--json", action="store_true")
    p_plan.add_argument("fonts", nargs="+")
    p_faces = sub.add_parser("faces", help="JSON description of every face")
    p_faces.add_argument("font")
    p_mat = sub.add_parser("materialize")
    p_mat.add_argument("--input", required=True)
    p_mat.add_argument("--index", type=int, default=-1)
    p_mat.add_argument("--wght", default="")
    p_mat.add_argument("--output", required=True)
    p_weight = sub.add_parser("weight", help="weight stated by a style/file name (empty if none)")
    p_weight.add_argument("name")
    p_fvar = sub.add_parser("has-fvar")
    p_fvar.add_argument("font")
    p_color = sub.add_parser("is-color")
    p_color.add_argument("font")
    p_anchor = sub.add_parser("anchors", help="materialize weight anchors: weight|file|mode")
    p_anchor.add_argument("--store", required=True)
    p_anchor.add_argument("--prefix", default="wght-")
    p_anchor.add_argument("--italic", action="store_true")
    p_anchor.add_argument("--weights", default="")
    p_anchor.add_argument("--variable-anchor", default="")
    p_anchor.add_argument("fonts", nargs="+")
    p_cov = sub.add_parser("covers", help="exit 0 when the font covers the script (han|hant)")
    p_cov.add_argument("--script", choices=("han", "hant"), required=True)
    p_cov.add_argument("font")
    p_vf = sub.add_parser("variable-source", help="path|index of the upright wght variable face")
    p_vf.add_argument("fonts", nargs="+")
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            faces = collect_faces(Path(item) for item in args.fonts if Path(item).is_file())
            plan = plan_slots(faces, italic=args.italic)
            if args.json:
                print(json.dumps({"status": "ok", "slots": {str(k): asdict(v) for k, v in plan.items()},
                                  "faces": [_face_json(face) for face in faces]},
                                 ensure_ascii=False, separators=(",", ":")))
            else:
                print("\n".join(_plan_lines(plan)))
            return 0 if plan else 3
        if args.command == "faces":
            faces = faces_for(Path(args.font))
            print(json.dumps({"status": "ok", "collection": is_collection(Path(args.font)),
                              "faces": [_face_json(face) for face in faces]},
                             ensure_ascii=False, separators=(",", ":")))
            return 0
        if args.command == "materialize":
            wght = float(args.wght) if str(args.wght).strip() else None
            print(json.dumps(materialize(Path(args.input), args.index, wght, Path(args.output)),
                             ensure_ascii=False, separators=(",", ":")))
            return 0
        if args.command == "weight":
            value = weight_from_name(args.name)
            print("" if value is None else value)
            return 0
        if args.command == "has-fvar":
            return 0 if has_fvar(Path(args.font)) else 1
        if args.command == "is-color":
            return 0 if is_color_font(Path(args.font)) else 1
        if args.command == "anchors":
            weights = tuple(int(item) for item in args.weights.split(",") if item.strip()) or SLOT_WEIGHTS
            if any(not 1 <= weight <= 1000 for weight in weights):
                raise ValueError("字重槽位无效")
            if any(ch in args.prefix for ch in "/\\") or any(ch in args.variable_anchor for ch in "/\\"):
                raise ValueError("锚点名称无效")
            rows = build_anchors([Path(item) for item in args.fonts if Path(item).is_file()],
                                 Path(args.store), prefix=args.prefix, italic=args.italic,
                                 weights=weights, variable_anchor=args.variable_anchor)
            for weight, target, mode in rows:
                print(f"{weight}|{target}|{mode}")
            return 0 if rows else 3
        if args.command == "covers":
            path = Path(args.font)
            index = 0 if is_collection(path) else -1
            kwargs = {"lazy": True}
            if index >= 0:
                kwargs["fontNumber"] = index
            with TTFont(str(path), **kwargs) as font:
                ratio = script_coverage(font.getBestCmap() or {}, args.script)
            print(f"{ratio:.3f}")
            return 0 if ratio >= SCRIPT_COVERAGE_MIN else 1
        if args.command == "variable-source":
            face = variable_source(collect_faces(Path(item) for item in args.fonts if Path(item).is_file()))
            if face is None:
                return 3
            print(f"{face.path}|{face.index}")
            return 0
    except Exception as error:
        print(json.dumps({"status": "error", "message": str(error) or error.__class__.__name__},
                         ensure_ascii=False), file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
