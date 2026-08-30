#!/usr/bin/env python3
"""Align staged HyperOS fonts to the ROM's real UI/clock metric contracts.

The safe v4 switch path intentionally stages fonts off-line.  It used to hard-link
one raw regular/composite font into every MiSans/Mitype/MiClock slot, which bypassed
LuoShu's metric normalizer and the per-slot alignment engine.  This helper restores
those contracts without touching the payload mounted by the current boot.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from fontTools.ttLib import TTCollection, TTFont

COMMON_DIR = Path(__file__).resolve().parents[1]
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

import font_metrics_normalize as metrics_normalizer  # noqa: E402
import device_font_template as template_engine  # noqa: E402
import device_font_slot_plan as slot_planner  # noqa: E402
import device_font_slot_build as slot_builder  # noqa: E402

DIGIT_PROBES = tuple(map(ord, "0123456789"))
LATIN_PROBES = tuple(map(ord, "AHIOXahiox"))


class AlignError(RuntimeError):
    pass


def _is_collection(path: Path) -> bool:
    with path.open("rb") as stream:
        return stream.read(4) == b"ttcf"


def _stock_face(path: Path) -> int:
    if not _is_collection(path):
        return -1
    collection = TTCollection(str(path), lazy=True)
    try:
        count = len(collection.fonts)
    finally:
        collection.close()
    best: tuple[int, int] | None = None
    for index in range(count):
        font = TTFont(str(path), fontNumber=index, lazy=True, recalcTimestamp=False)
        try:
            cmap = font.getBestCmap() or {}
            score = sum(1 for cp in DIGIT_PROBES if cp in cmap) * 4 + sum(1 for cp in LATIN_PROBES if cp in cmap)
        finally:
            font.close()
        if best is None or score > best[0]:
            best = (score, index)
    return best[1] if best is not None else 0


def _stock_contract(path: Path) -> dict[str, Any]:
    face = _stock_face(path)
    kwargs: dict[str, Any] = {"lazy": True, "recalcTimestamp": False}
    if face >= 0:
        kwargs["fontNumber"] = face
    font = TTFont(str(path), **kwargs)
    try:
        if "head" not in font or "hhea" not in font:
            raise AlignError("原厂目标字体缺少 head/hhea")
        upem = int(font["head"].unitsPerEm)
        ascent = int(font["hhea"].ascent)
        descent = int(font["hhea"].descent)
        if upem <= 0 or ascent <= 0 or descent >= 0:
            raise AlignError("原厂目标字体度量无效")
        return {
            "source": "stock-slot",
            "slot": str(path),
            "buildKey": "",
            "upem": upem,
            "ascent": ascent,
            "descent": descent,
            "ascentRatio": ascent / upem,
            "descentRatio": abs(descent) / upem,
        }
    finally:
        font.close()


def _target_weight(path: Path) -> int:
    face = _stock_face(path)
    kwargs: dict[str, Any] = {"lazy": True, "recalcTimestamp": False}
    if face >= 0:
        kwargs["fontNumber"] = face
    font = TTFont(str(path), **kwargs)
    try:
        if "OS/2" in font:
            value = int(getattr(font["OS/2"], "usWeightClass", 400) or 400)
            return max(1, min(1000, value))
        return 400
    finally:
        font.close()


def _exact_slot_align(source: Path, stock: Path, output: Path, role: str) -> dict[str, Any]:
    source_profile = template_engine.inspect_font(source, -1, hash_fonts=False)
    stock_face = _stock_face(stock)
    stock_profile = template_engine.inspect_font(stock, stock_face, hash_fonts=False)
    roles = ["mono", "global-ui"] if role == "mono" else ["clock", "global-ui"]
    slot = {
        "family": f"physical-{stock.name}",
        "familyNormalized": f"physical-{stock.name}".lower(),
        "familyAttributes": {},
        "sourceXml": "",
        "declared": stock.name,
        "postScriptName": "",
        "weight": _target_weight(stock),
        "style": "normal",
        "index": 0,
        "axes": "",
        "roles": roles,
        "replaceable": True,
        "resolvedPath": str(stock),
        "directPhysical": True,
        "font": stock_profile,
    }
    plan = slot_planner.slot_plan(slot, source_profile)
    if plan.get("status") != "ready":
        raise AlignError(f"逐槽位计划不可用：{plan.get('status')}:{plan.get('reason', '')}")
    report = slot_builder.build_slot(source, -1, plan, output)
    return {"mode": "slot", "plan": plan, "build": report}


def align(source: Path, output: Path, role: str, inventory: Path | None, stock: Path | None) -> dict[str, Any]:
    if not source.is_file() or source.stat().st_size < 1024:
        raise AlignError(f"字体源不可用：{source}")
    output.parent.mkdir(parents=True, exist_ok=True)

    # Clock/mono slots are the visible HyperOS status-bar/lock-screen problem.  Use
    # the existing exact per-slot engine first so digit ink, advances and line box all
    # follow the real ROM font.  CFF/unsupported sources safely fall back to line metrics.
    if role in {"clock", "mono"} and stock is not None and stock.is_file():
        try:
            report = _exact_slot_align(source, stock, output, role)
            return {"status": "ok", "role": role, "source": str(source), "stock": str(stock), "output": str(output), **report}
        except Exception as exact_error:
            contract = _stock_contract(stock)
            normalized = metrics_normalizer.normalize_path(
                source,
                output,
                monospaced=(role == "mono"),
                inventory=inventory,
                target_contract=contract,
            )
            return {
                "status": "ok",
                "role": role,
                "mode": "stock-metrics-fallback",
                "source": str(source),
                "stock": str(stock),
                "output": str(output),
                "exactError": str(exact_error),
                "normalize": normalized,
            }

    normalized = metrics_normalizer.normalize_path(
        source,
        output,
        monospaced=(role == "mono"),
        inventory=inventory,
    )
    return {
        "status": "ok",
        "role": role,
        "mode": "ui-metrics",
        "source": str(source),
        "stock": str(stock) if stock is not None else "",
        "output": str(output),
        "normalize": normalized,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--role", choices=("ui", "clock", "mono"), default="ui")
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--stock", type=Path)
    args = parser.parse_args()
    try:
        report = align(args.source, args.output, args.role, args.inventory, args.stock)
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as error:
        args.output.unlink(missing_ok=True)
        print(json.dumps({"status": "error", "message": str(error) or error.__class__.__name__}, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
