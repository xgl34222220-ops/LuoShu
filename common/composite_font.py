#!/usr/bin/env python3
"""LuoShu full composite font builder.

The CJK font is kept as the complete base. Latin and digit glyph outlines are
copied into glyph slots which already exist in the base font, so the output
retains one complete cmap and does not depend on Android fallback behavior.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import gc
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.qu2cuPen import Qu2CuPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont

LATIN_CODEPOINTS = (
    set(range(0x0020, 0x0030))
    | set(range(0x003A, 0x007F))
    | set(range(0x00A0, 0x0250))
    | set(range(0x0300, 0x0370))
    | set(range(0x1E00, 0x1F00))
    | set(range(0x2000, 0x2070))
    | set(range(0x20A0, 0x20D0))
    | set(range(0x2100, 0x2150))
)
DIGIT_CODEPOINTS = (
    set(range(0x0030, 0x003A))
    | set(range(0xFF10, 0xFF1A))
    | {0x00B2, 0x00B3, 0x00B9}
    | set(range(0x2070, 0x207A))
    | set(range(0x2080, 0x208A))
)
LATIN_CODEPOINTS -= DIGIT_CODEPOINTS

CJK_PROBES = tuple(map(ord, "中文字体系统默认洛书汉字国一的。"))
LATIN_PROBES = tuple(map(ord, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"))
DIGIT_PROBES = tuple(map(ord, "0123456789"))
REQUIRED_LATIN = set(LATIN_PROBES)
REQUIRED_DIGITS = set(DIGIT_PROBES)


def _progress(path: str | None, stage: str, message: str, percent: int) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + f".{os.getpid()}.tmp")
    payload = {"stage": stage, "message": message, "percent": int(percent), "time": int(time.time())}
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temp, target)


class CompositeError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for block in iter(lambda: fp.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _is_collection(path: Path) -> bool:
    with path.open("rb") as fp:
        return fp.read(4) == b"ttcf"


def _font_weight(font: TTFont) -> int:
    try:
        return int(font["OS/2"].usWeightClass)
    except Exception:
        return 400


def _score_face(font: TTFont, role: str, target_weight: int) -> tuple[int, int]:
    cmap = font.getBestCmap() or {}
    probes = CJK_PROBES if role == "cjk" else LATIN_PROBES if role == "latin" else DIGIT_PROBES
    hits = sum(1 for cp in probes if cp in cmap)
    return (hits, -abs(_font_weight(font) - target_weight))


def _pick_face(path: Path, role: str, target_weight: int, requested: int | None) -> int:
    if not _is_collection(path):
        return -1
    coll = TTCollection(str(path), lazy=True)
    try:
        count = len(coll.fonts)
    finally:
        coll.close()
    if requested is not None:
        if requested < 0 or requested >= count:
            raise CompositeError(f"{path.name} 的字体面索引 {requested} 超出范围（共 {count} 个）")
        return requested
    best: tuple[tuple[int, int], int] | None = None
    for index in range(count):
        font = TTFont(str(path), fontNumber=index, lazy=True, recalcTimestamp=False)
        try:
            score = _score_face(font, role, target_weight)
        finally:
            font.close()
        if best is None or score > best[0]:
            best = (score, index)
    if best is None or best[0][0] == 0:
        raise CompositeError(f"无法从 {path.name} 中找到适合的{role}字体面")
    return best[1]


def _load_font(
    path: Path, role: str, target_weight: int, requested_face: int | None
) -> tuple[TTFont, int, dict[str, float] | None]:
    face = _pick_face(path, role, target_weight, requested_face)
    kwargs = {"lazy": True, "recalcTimestamp": False, "recalcBBoxes": False}
    if face >= 0:
        kwargs["fontNumber"] = face
    font = TTFont(str(path), **kwargs)
    location: dict[str, float] | None = None
    if "fvar" in font:
        location = {}
        for axis in font["fvar"].axes:
            value = axis.defaultValue
            if axis.axisTag == "wght":
                value = max(axis.minValue, min(axis.maxValue, target_weight))
            location[axis.axisTag] = float(value)
    return font, face, location


def _outline_kind(font: TTFont) -> str:
    if "glyf" in font:
        return "glyf"
    if "CFF " in font:
        return "cff"
    if "CFF2" in font:
        return "cff2"
    raise CompositeError("字体不包含受支持的 glyf、CFF 或 CFF2 轮廓")


def _draw_decomposed(glyph_set, glyph_name: str, destination_pen, scale: float) -> None:
    recorder = DecomposingRecordingPen(glyph_set)
    glyph_set[glyph_name].draw(recorder)
    recorder.replay(TransformPen(destination_pen, (scale, 0, 0, scale, 0, 0)))


def _replace_glyf(base: TTFont, src: TTFont, src_glyph_set, base_name: str, src_name: str, scale: float) -> None:
    pen = TTGlyphPen(None)
    source_kind = _outline_kind(src)
    output_pen = Cu2QuPen(
        pen,
        max_err=max(0.5, base["head"].unitsPerEm / 2000),
        reverse_direction=source_kind in {"cff", "cff2"},
    )
    _draw_decomposed(src_glyph_set, src_name, output_pen, scale)
    glyph = pen.glyph()
    base["glyf"][base_name] = glyph
    glyph.recalcBounds(base["glyf"])
    if not hasattr(glyph, "xMin"):
        glyph.xMin = glyph.yMin = glyph.xMax = glyph.yMax = 0
    if "gvar" in base:
        base["gvar"].variations.pop(base_name, None)


def _replace_cff(base: TTFont, src: TTFont, src_glyph_set, base_name: str, src_name: str, scale: float, width: int) -> None:
    tag = "CFF " if "CFF " in base else "CFF2"
    cff = base[tag].cff
    top = cff.topDictIndex[0]
    _old, selector = top.CharStrings.getItemAndSelector(base_name)
    if hasattr(top, "FDArray"):
        private = top.FDArray[selector or 0].Private
    else:
        private = top.Private
    is_cff2 = tag == "CFF2"
    pen = T2CharStringPen(None if is_cff2 else width, None, CFF2=is_cff2)
    source_kind = _outline_kind(src)
    output_pen = Qu2CuPen(
        pen,
        max_err=max(0.5, base["head"].unitsPerEm / 2000),
        all_cubic=True,
        reverse_direction=source_kind == "glyf",
    )
    _draw_decomposed(src_glyph_set, src_name, output_pen, scale)
    char_string = pen.getCharString(private=private, globalSubrs=cff.GlobalSubrs)
    if selector is not None:
        char_string.fdSelectIndex = selector
    top.CharStrings[base_name] = char_string


def _replace_codepoints(base: TTFont, src: TTFont, codepoints: Iterable[int], location: dict[str, float] | None = None, required: set[int] | None = None) -> tuple[int, list[int]]:
    required = required or set()
    base_cmap = base.getBestCmap() or {}
    src_cmap = src.getBestCmap() or {}
    src_glyph_set = src.getGlyphSet(location=location) if location else src.getGlyphSet()
    base_kind = _outline_kind(base)
    base_upem = base["head"].unitsPerEm
    src_upem = src["head"].unitsPerEm
    scale = base_upem / src_upem
    replaced = 0
    missing: list[int] = []
    already: set[str] = set()
    for cp in sorted(codepoints):
        base_name = base_cmap.get(cp)
        src_name = src_cmap.get(cp)
        if not base_name or not src_name:
            if cp in required:
                raise CompositeError(f"源字体或中文基底缺少必要字符 U+{cp:04X}")
            missing.append(cp)
            continue
        key = f"{base_name}:{src_name}"
        if key in already:
            continue
        already.add(key)
        try:
            advance, lsb = src["hmtx"].metrics[src_name]
            variable_width = getattr(src_glyph_set[src_name], "width", None)
            if isinstance(variable_width, (int, float)):
                advance = variable_width
        except (KeyError, TypeError):
            missing.append(cp)
            continue
        advance = int(round(float(advance) * scale))
        lsb = int(round(float(lsb) * scale))
        try:
            if base_kind == "glyf":
                _replace_glyf(base, src, src_glyph_set, base_name, src_name, scale)
            else:
                _replace_cff(base, src, src_glyph_set, base_name, src_name, scale, advance)
        except Exception as exc:
            if cp in required:
                raise CompositeError(f"必要字符 U+{cp:04X} 的字形转换失败：{exc}") from exc
            missing.append(cp)
            continue
        base["hmtx"].metrics[base_name] = (advance, lsb)
        replaced += 1
    return replaced, missing


def _set_names(font: TTFont) -> None:
    replacements = {1: "LuoShu Composite", 4: "LuoShu Composite", 6: "LuoShuComposite"}
    if "name" not in font:
        return
    for record in font["name"].names:
        if record.nameID not in replacements:
            continue
        text = replacements[record.nameID]
        try:
            record.string = text.encode(record.getEncoding())
        except Exception:
            record.string = text.encode("utf-16-be")


def _validate_output(path: Path) -> dict[str, object]:
    font = TTFont(str(path), lazy=False, recalcTimestamp=False)
    try:
        cmap = font.getBestCmap() or {}
        required = {"cjk": ord("中"), "latin": ord("A"), "digit": ord("1")}
        missing = [role for role, cp in required.items() if cp not in cmap]
        if missing:
            raise CompositeError("复合字体缺少必要字符：" + ", ".join(missing))
        glyph_set = font.getGlyphSet()
        bounds = {}
        for role, cp in required.items():
            glyph_name = cmap[cp]
            pen = BoundsPen(glyph_set)
            glyph_set[glyph_name].draw(pen)
            if pen.bounds is None:
                raise CompositeError(f"复合字体的 {role} 字形为空")
            bounds[role] = list(pen.bounds)
        return {
            "tables": list(font.keys()),
            "glyphs": int(font["maxp"].numGlyphs),
            "coverage": len(cmap),
            "bounds": bounds,
            "upem": int(font["head"].unitsPerEm),
        }
    finally:
        font.close()


def build(args: argparse.Namespace) -> dict[str, object]:
    cjk_path, latin_path, digit_path, output = map(Path, (args.cjk, args.latin, args.digit, args.output))
    for path, label in ((cjk_path, "中文"), (latin_path, "英文"), (digit_path, "数字")):
        if not path.is_file() or path.stat().st_size < 12:
            raise CompositeError(f"{label}字体文件不可用：{path}")
    _progress(args.progress, "load-cjk", "正在读取中文基底", 5)
    base, cjk_face, _cjk_location = _load_font(cjk_path, "cjk", args.weight, args.cjk_face)
    latin = digit = None
    latin_face = digit_face = -1
    try:
        if not all(cp in (base.getBestCmap() or {}) for cp in (ord("中"), ord("A"), ord("1"))):
            raise CompositeError("中文基础字体必须同时包含中文、英文字母和数字，才能安全生成完整复合字体")
        _progress(args.progress, "latin", "正在导入英文字形", 20)
        latin, latin_face, latin_location = _load_font(latin_path, "latin", args.weight, args.latin_face)
        latin_replaced, latin_missing = _replace_codepoints(base, latin, LATIN_CODEPOINTS, latin_location, REQUIRED_LATIN)
        latin.close(); latin = None; gc.collect()
        _progress(args.progress, "digit", "正在导入数字字形", 52)
        digit, digit_face, digit_location = _load_font(digit_path, "digit", args.weight, args.digit_face)
        digit_replaced, digit_missing = _replace_codepoints(base, digit, DIGIT_CODEPOINTS, digit_location, REQUIRED_DIGITS)
        digit.close(); digit = None; gc.collect()
        if latin_replaced < 52:
            raise CompositeError(f"英文替换数量异常（仅 {latin_replaced} 个）")
        if digit_replaced < 10:
            raise CompositeError(f"数字替换数量异常（仅 {digit_replaced} 个）")
        for tag in ("DSIG", "LTSH", "hdmx", "VDMX"):
            if tag in base:
                del base[tag]
        _set_names(base)
        _progress(args.progress, "save", "正在写入完整复合字体", 68)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=output.name + ".", suffix=".tmp", dir=output.parent, delete=False) as temp:
            temp_path = Path(temp.name)
        try:
            base.save(str(temp_path), reorderTables=False)
            _progress(args.progress, "validate", "正在验证复合字体", 90)
            validation = _validate_output(temp_path)
            os.chmod(temp_path, 0o644)
            os.replace(temp_path, output)
            _progress(args.progress, "done", "完整复合字体已生成", 100)
        finally:
            temp_path.unlink(missing_ok=True)
        return {
            "status": "ok",
            "output": str(output),
            "sha256": _sha256(output),
            "size": output.stat().st_size,
            "faces": {"cjk": cjk_face, "latin": latin_face, "digit": digit_face},
            "replaced": {"latin": latin_replaced, "digit": digit_replaced},
            "missingCounts": {"latin": len(latin_missing), "digit": len(digit_missing)},
            "validation": validation,
        }
    finally:
        base.close()
        if latin is not None: latin.close()
        if digit is not None: digit.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cjk", required=True)
    parser.add_argument("--latin", required=True)
    parser.add_argument("--digit", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--weight", type=int, default=400)
    parser.add_argument("--cjk-face", type=int)
    parser.add_argument("--latin-face", type=int)
    parser.add_argument("--digit-face", type=int)
    parser.add_argument("--progress")
    return parser.parse_args()


def main() -> int:
    try:
        result = build(parse_args())
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except MemoryError:
        print(json.dumps({"status": "error", "message": "生成复合字体时内存不足，请更换体积较小的中文字体后重试"}, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 12
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc) or exc.__class__.__name__}, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
