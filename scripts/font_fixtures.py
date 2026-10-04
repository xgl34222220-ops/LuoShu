#!/usr/bin/env python3
"""Synthetic fonts and a small device topology for engine tests."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables.TupleVariation import TupleVariation

import device_font_template as template_engine
import font_coverage
import font_inventory
import font_role_shadow

ASCII_POINTS = tuple(range(0x20, 0x7F))


def make_font(
    path: Path,
    *,
    family: str,
    weight: int = 400,
    upem: int = 1000,
    ascent: int = 900,
    descent: int = -220,
    advance: int = 620,
    y_min: int = -120,
    y_max: int = 720,
    cff: bool = False,
    variable: bool = False,
    axis_min: int = 100,
    axis_max: int = 900,
    triangle: bool = False,
    gvar_deltas: bool = False,
) -> None:
    cmap = {cp: f"u{cp:04X}" for cp in ASCII_POINTS}
    order = [".notdef", *cmap.values()]
    builder = FontBuilder(upem, isTTF=not cff)
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap(cmap)

    glyphs = {}
    for name in order:
        if cff:
            pen = T2CharStringPen(advance, None)
        else:
            pen = TTGlyphPen(None)
        if name != ".notdef":
            pen.moveTo((40, y_min))
            pen.lineTo((advance - 50, y_min))
            if not triangle:
                pen.lineTo((advance - 50, y_max))
            pen.lineTo((40, y_max))
            pen.closePath()
        glyphs[name] = pen.getCharString() if cff else pen.glyph()

    if cff:
        ps = family.replace(" ", "") + "-Regular"
        builder.setupCFF(ps, {"FullName": family}, glyphs, {})
    else:
        builder.setupGlyf(glyphs)

    builder.setupHorizontalMetrics({name: (advance, 40) for name in order})
    builder.setupHorizontalHeader(ascent=ascent, descent=descent)
    builder.setupOS2(
        usWeightClass=weight,
        sTypoAscender=ascent,
        sTypoDescender=descent,
        sTypoLineGap=0,
        usWinAscent=max(0, ascent),
        usWinDescent=abs(descent),
    )
    builder.setupNameTable({
        "familyName": family,
        "styleName": "Regular" if weight < 700 else "Bold",
        "fullName": family,
        "psName": family.replace(" ", "") + ("-Bold" if weight >= 700 else "-Regular"),
    })
    builder.setupPost()
    builder.setupMaxp()

    if variable:
        if cff:
            raise ValueError("test fixture variable CFF is not supported")
        builder.setupFvar([("wght", axis_min, 400, axis_max, "Weight")], [])
        variations = {name: [] for name in order}
        if gvar_deltas:
            # Real per-point deltas: decoding them depends on each glyph's
            # original point count (4 outline points + 4 phantom points).
            for name in order:
                if name != ".notdef":
                    variations[name] = [
                        TupleVariation({"wght": (0, 1.0, 1.0)}, [(12, 0)] * 8)
                    ]
        builder.setupGvar(variations)

    builder.save(path)


def slot_from_stock(
    logical: str,
    stock: Path,
    *,
    family: str,
    source_xml: str | None,
    declared: str,
    face_index: int = 0,
    weight: int = 400,
    postscript: str = "",
) -> dict:
    fmt, metrics = font_inventory._read_metrics(stock, face_index)
    refs = []
    if source_xml:
        refs.append({
            "sourceXml": source_xml,
            "sourcePartition": Path(source_xml).parts[1],
            "family": family,
            "familyNormalized": family.lower(),
            "familyAttributes": {},
            "declared": declared,
            "postScriptName": postscript,
            "weight": weight,
            "style": "normal",
            "index": face_index,
            "axes": "",
            "resolvedPath": logical,
        })
    return {
        "slotName": Path(logical).name,
        "path": logical,
        "partition": Path(logical).parts[1],
        "source": "phase6-test",
        "families": [family],
        "weight": weight,
        "style": "normal",
        "faceIndex": face_index,
        "format": fmt,
        "metrics": metrics,
        "xmlRefs": refs,
        "legacyReplaceable": True,
        "runtimeEvidence": {"fontManager": True, "mount": False},
    }


def make_cjk_font(path: Path, *, family: str, variable: bool = False, y_max: int = 820,
                  pentagon: bool = False) -> None:
    """A CJK base with >= MIN_CORE_HAN Han glyphs, the CJK probes and ASCII."""
    han = list(range(0x4E00, 0x4E00 + font_coverage.MIN_CORE_HAN + 64))
    points = sorted(set(han) | set(template_engine.PROBE_GROUPS["cjk"])
                    | set(template_engine.PROBE_GROUPS["punctuationFullwidth"]) | set(ASCII_POINTS)
                    | set(font_coverage.CJK_COMMON) | set(font_coverage.PUNCTUATION))
    cmap = {cp: f"u{cp:04X}" for cp in points}
    order = [".notdef", *cmap.values()]
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap(cmap)
    glyphs = {}
    for name in order:
        pen = TTGlyphPen(None)
        if name != ".notdef":
            pen.moveTo((60, -110))
            pen.lineTo((940, -110))
            pen.lineTo((940, y_max))
            if pentagon:
                pen.lineTo((500, y_max))
            pen.lineTo((60, y_max))
            pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (1000, 60) for name in order})
    builder.setupHorizontalHeader(ascent=880, descent=-120)
    builder.setupOS2(usWeightClass=400, sTypoAscender=880, sTypoDescender=-120,
                     sTypoLineGap=0, usWinAscent=880, usWinDescent=120)
    builder.setupNameTable({"familyName": family, "styleName": "Regular",
                            "fullName": family, "psName": family.replace(" ", "") + "-Regular"})
    builder.setupPost()
    builder.setupMaxp()
    if variable:
        builder.setupFvar([("wght", 100, 400, 900, "Weight")], [])
        builder.setupGvar({name: [] for name in order})
    builder.save(path)


def build_device(temp: Path) -> tuple[dict, dict, dict[str, Path], dict[str, Path]]:
    """Stock slots: Latin UI, CJK fallback, OEM broad UI (Han+Latin), clock."""
    temp.mkdir(parents=True, exist_ok=True)
    stocks = {
        "/system/fonts/Roboto-Regular.ttf": temp / "Roboto-Regular.ttf",
        "/system/fonts/NotoSansCJK-Regular.ttf": temp / "NotoSansCJK-Regular.ttf",
        "/system/fonts/MiSansVF.ttf": temp / "MiSansVF.ttf",
        "/system/fonts/AndroidClock.ttf": temp / "AndroidClock.ttf",
    }
    make_font(stocks["/system/fonts/Roboto-Regular.ttf"], family="Stock Roboto", variable=True)
    make_cjk_font(stocks["/system/fonts/NotoSansCJK-Regular.ttf"], family="Stock CJK", variable=True)
    make_cjk_font(stocks["/system/fonts/MiSansVF.ttf"], family="Stock MiSans", variable=True)
    make_font(stocks["/system/fonts/AndroidClock.ttf"], family="Stock Clock", advance=640)
    weights = (400, 700)
    families = {
        "/system/fonts/Roboto-Regular.ttf": ("sans-serif", {}),
        "/system/fonts/NotoSansCJK-Regular.ttf": ("", {"lang": "zh-Hans"}),
        "/system/fonts/MiSansVF.ttf": ("mipro", {}),
        "/system/fonts/AndroidClock.ttf": ("clock-ui", {}),
    }
    xml_nodes = []
    slots = {}
    for logical, stock in stocks.items():
        family, attrs = families[logical]
        declared = Path(logical).name
        clock = "Clock" in declared
        slot = slot_from_stock(logical, stock, family=family or "zh", source_xml="/system/etc/fonts.xml",
                                       declared=declared)
        slot["families"] = [family] if family else []
        refs = []
        for weight in ((400,) if clock else weights):
            refs.append(dict(slot["xmlRefs"][0], family=family, familyNormalized=family,
                             familyAttributes=attrs, weight=weight))
        slot["xmlRefs"] = refs
        slots[logical] = slot
        attr_text = "".join(f' {k}="{v}"' for k, v in attrs.items())
        name_text = f' name="{family}"' if family else ""
        xml_nodes.append(f"<family{name_text}{attr_text}>" + "".join(
            f'<font weight="{w}" style="normal">{declared}'
            + ("" if clock else f'<axis tag="wght" stylevalue="{w}"/>') + "</font>"
            for w in ((400,) if clock else weights)
        ) + "</family>")
    xml = temp / "fonts.xml"
    xml.write_text("<familyset>" + "".join(xml_nodes) + "</familyset>", encoding="utf-8")
    topology = {
        "schema": "device-font-topology-v1", "topologyRevision": 2, "state": "ready",
        "buildKey": "composite-test", "romKind": "hyperos",
        "summary": {"slotCount": len(slots), "dataFontFileCount": 0,
                    "dataFontConfigReferenceCount": 0, "unresolvedXmlRefCount": 0},
        "slots": slots, "families": {}, "xmlAliases": [], "unresolvedXmlRefs": [], "runtime": {},
    }
    roles, _shadow = font_role_shadow.build(topology)
    return topology, roles, stocks, {"/system/etc/fonts.xml": xml}
