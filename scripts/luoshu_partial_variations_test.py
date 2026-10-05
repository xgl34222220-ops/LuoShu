#!/usr/bin/env python3
"""Fixed-text imports must retain other-script and stock advance variation."""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))
sys.path.insert(0, str(ROOT / "scripts"))

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.otlLib.builder import buildStatTable
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.varLib.builder import buildVarData, buildVarIdxMap, buildVarRegionList, buildVarStore
from fontTools.varLib.instancer import instantiateVariableFont

import font_fixtures as fixture
import luoshu_merge
import luoshu_partial_variations as partial


WEIGHTS = (400, 475, 550, 625, 700)


def _fixture(temp: Path, *, implicit: bool = False, alias: bool = False,
             inherit_metric: bool = False) -> Path:
    path = temp / ("Implicit.ttf" if implicit else "Explicit.ttf")
    fixture.make_font(path, family="Variable Protected Stock", triangle=True, advance=510,
                      variable=True, axis_min=400, axis_max=700)
    with TTFont(path, recalcBBoxes=False, recalcTimestamp=False) as font:
        order = list(font.getGlyphOrder())
        for name in ("GreekSimple", "GreekComposite"):
            pen = TTGlyphPen(font.getGlyphSet())
            if name == "GreekComposite":
                pen.addComponent("u0042", (1, 0, 0, 1, 13, 17))
            else:
                pen.moveTo((25, 0)); pen.lineTo((450, 0)); pen.lineTo((200, 600)); pen.closePath()
            font["glyf"][name] = pen.glyph()
            font["hmtx"].metrics[name] = (510, 25 if name == "GreekSimple" else 53)
            order.append(name)
        if inherit_metric:
            pen = TTGlyphPen(font.getGlyphSet())
            pen.addComponent("u0042", (1, 0, 0, 1, 13, 17))
            font["glyf"]["MetricLatin"] = pen.glyph()
            font["glyf"]["MetricLatin"].components[0].flags |= 0x200
            # Its own cell deliberately differs from the inherited component
            # cell: a full outline rewrite would lose rasterizer inheritance.
            font["hmtx"].metrics["MetricLatin"] = (500, 53)
            order.append("MetricLatin")
        font.setGlyphOrder(order)
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap[0x03A9] = "GreekSimple"
                table.cmap[0x0416] = "GreekComposite"
                if alias:
                    table.cmap[0x2109] = "u0041"
                if inherit_metric:
                    table.cmap[0x00EF] = "MetricLatin"
        for index, name in enumerate(order):
            if name == ".notdef":
                font["gvar"].variations[name] = []
                continue
            glyph = font["glyf"][name]
            count = len(glyph.components) if glyph.isComposite() else len(glyph.coordinates)
            # Real valid HVAR and gvar advance representations agree. Tests
            # compare both glyph-set layout and full static instantiation.
            deltas = [(7, 9)] * count + [(0, 0), (index % 13 + 11, 0), (0, 0), (0, 0)]
            font["gvar"].variations[name] = [TupleVariation({"wght": (0, 1, 1)}, deltas)]
        regions = buildVarRegionList([{"wght": (0, 1, 1)}], ["wght"])
        data = buildVarData([0], [[0 if index == 0 else index % 13 + 11] for index in range(len(order))])
        store = buildVarStore(regions, [data])
        hvar = newTable("HVAR")
        hvar.table = otTables.HVAR()
        hvar.table.Version = 0x00010000
        hvar.table.VarStore = store
        hvar.table.AdvWidthMap = None if implicit else buildVarIdxMap(range(len(order)), order)
        hvar.table.LsbMap = None
        hvar.table.RsbMap = None
        font["HVAR"] = hvar
        mvar = newTable("MVAR")
        mvar.table = otTables.MVAR()
        mvar.table.Version, mvar.table.Reserved = 0x00010000, 0
        mvar.table.ValueRecordSize, mvar.table.ValueRecordCount = 8, 1
        record = otTables.MetricsValueRecord()
        record.ValueTag, record.VarIdx = "hasc", 0
        mvar.table.ValueRecord = [record]
        mvar.table.VarStore = copy.deepcopy(store)
        font["MVAR"] = mvar
        avar = newTable("avar")
        avar.majorVersion, avar.minorVersion = 1, 0
        avar.segments = {"wght": {-1.0: -1.0, 0.0: 0.0, 0.5: 0.6, 1.0: 1.0}}
        font["avar"] = avar
        buildStatTable(font, [{"tag": "wght", "name": "Weight", "values": [
            {"value": 400, "name": "Regular"}, {"value": 700, "name": "Bold"}]}])
        addOpenTypeFeaturesFromString(font, "feature kern { pos u0041 u0056 -20; } kern;")
        font.recalcBBoxes = True
        font.save(path)
    return path


def _static_source(temp: Path) -> TTFont:
    path = temp / "UserFixed.ttf"
    fixture.make_font(path, family="Fixed User Text", advance=620)
    font = TTFont(path, recalcBBoxes=False, recalcTimestamp=False)
    for table in font["cmap"].tables:
        if table.isUnicode():
            table.cmap[0x00EF] = "u0069"
    return font


def _view(font: TTFont, name: str, weight: float):
    glyphs = font.getGlyphSet(location={"wght": weight})
    pen = DecomposingRecordingPen(glyphs)
    glyph = glyphs[name]
    glyph.draw(pen)
    return pen.value, glyph.width


def _roundtrip(font: TTFont) -> tuple[TTFont, bytes]:
    stream = io.BytesIO()
    font.save(stream)
    data = stream.getvalue()
    stream.seek(0)
    return TTFont(stream, recalcBBoxes=False, recalcTimestamp=False), data


def _raw_layout(font: TTFont) -> dict[str, bytes]:
    return {tag: font.reader[tag] for tag in ("GSUB", "GPOS", "GDEF", "BASE") if tag in font}


def _preserve_raw_layout(font: TTFont, raw: dict[str, bytes]) -> None:
    from fontTools.ttLib.tables.DefaultTable import DefaultTable
    for tag, data in raw.items():
        table = DefaultTable(tag)
        table.data = data
        font[tag] = table


def _verify(original: TTFont, output: TTFont, details: dict, weights=WEIGHTS) -> dict:
    order = original.getGlyphOrder()
    assert output.getGlyphOrder()[:len(order)] == order
    assert original.getBestCmap() == output.getBestCmap()
    for tag in partial.SCALAR_VARIATION_TABLES:
        if tag in original:
            assert original.reader[tag] == output.reader[tag], tag
    for tag, data in _raw_layout(original).items():
        assert output.reader[tag] == data, tag
    # Keep the stock variation store and each existing mapping, including
    # side bearings. Only clone map entries may be appended.
    old_hvar, new_hvar = original["HVAR"].table, output["HVAR"].table
    old_width_map = old_hvar.AdvWidthMap
    for field in ("AdvWidthMap", "LsbMap", "RsbMap"):
        old, new = getattr(old_hvar, field, None), getattr(new_hvar, field, None)
        if old is not None:
            assert all(new.mapping[name] == old.mapping[name] for name in order), field
        elif field == "AdvWidthMap":
            assert new is not None and all(new.mapping[name] == index for index, name in enumerate(order))
        else:
            assert new is None
    assert old_hvar.VarStore.VarData[0].Item == new_hvar.VarStore.VarData[0].Item
    changed = set(details["replacedGlyphNames"])
    retained = [name for name in order if name not in changed]
    snapshots = []
    for weight in weights:
        for name in order:
            before, after = _view(original, name, weight), _view(output, name, weight)
            assert before[1] == after[1], ("stock advance changed", weight, name, before[1], after[1])
            if name not in changed:
                assert before == after, ("retained outline changed", weight, name)
                snapshots.append((weight, name, before))
    for name in retained:
        old, new = original["glyf"][name], output["glyf"][name]
        assert getattr(getattr(old, "program", None), "bytecode", None) == \
            getattr(getattr(new, "program", None), "bytecode", None), name
        old_variations = original["gvar"].variations.get(name, [])
        new_variations = output["gvar"].variations.get(name, [])
        assert [(entry.axes, entry.coordinates) for entry in old_variations] == \
            [(entry.axes, entry.coordinates) for entry in new_variations], name
    for clone, name in details["clonedGlyphSources"].items():
        before, after = original["gvar"].variations.get(name, []), output["gvar"].variations[clone]
        assert [(entry.axes, entry.coordinates) for entry in before] == \
            [(entry.axes, entry.coordinates) for entry in after], (clone, name)
    expected_phantoms = partial._phantom_variations(original)
    actual_phantoms = partial._phantom_variations(output)
    for name in changed:
        expected = [(axes, points) for axes, points in expected_phantoms[name]
                    if any(delta != (0, 0) for delta in points)]
        assert actual_phantoms[name] == expected, name
        for variation in output["gvar"].variations[name]:
            assert all(delta is None or tuple(delta) == (0, 0) for delta in variation.coordinates[:-4]), name
    # A full instancer derives hmtx from gvar phantom points, then drops HVAR.
    # This is a separate metric consumer from getGlyphSet's HVAR layout path.
    for weight in weights:
        old_instance = instantiateVariableFont(original, {"wght": weight}, inplace=False)
        new_instance = instantiateVariableFont(output, {"wght": weight}, inplace=False)
        try:
            assert all(old_instance["hmtx"].metrics[name][0] == new_instance["hmtx"].metrics[name][0]
                       for name in order), ("instantiated advance changed", weight)
        finally:
            old_instance.close()
            new_instance.close()
    assert _view(original, original.getBestCmap()[ord("B")], 400)[0] != \
        _view(output, output.getBestCmap()[ord("B")], 400)[0]
    return {"retainedGlyphCount": len(retained), "sampleWeights": list(weights),
            "allOriginalAdvanceCount": len(order),
            "retainedShapeTraceSha256": hashlib.sha256(json.dumps(
                snapshots, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest(),
            "implicitOriginalAdvanceMap": old_width_map is None,
            "fullInstancerAdvanceVerified": True}


def supported_cases(temp: Path) -> None:
    for implicit, alias, inherit_metric in ((False, False, False), (True, False, False),
                                             (False, True, False), (False, False, True)):
        path = _fixture(temp, implicit=implicit, alias=alias, inherit_metric=inherit_metric)
        with TTFont(path, recalcBBoxes=False, recalcTimestamp=False) as original, \
                TTFont(path, recalcBBoxes=False, recalcTimestamp=False) as base, _static_source(temp) as source:
            assert partial.validate_variable_base(base) == ""
            details = partial.import_variable_partial(base, {"latin": source, "digit": source})
            assert details["asciiLettersReplaced"] == (51 if alias else 52)
            assert details["asciiDigitsReplaced"] == 10
            assert details["clonedGlyphSources"], "composite dependency fixture did not exercise cloning"
            assert details["originalHvarMappingsPreserved"]
            assert details["clonedVariationGlyphs"] == len(details["clonedGlyphSources"])
            if alias:
                assert "u0041" in details["protectedSharedGlyphs"]
            if inherit_metric:
                assert "MetricLatin" in details["protectedMetricGlyphs"]
                assert "MetricLatin" not in details["replacedGlyphNames"]
            _preserve_raw_layout(base, _raw_layout(original))
            output, _data = _roundtrip(base)
            try:
                _verify(original, output, details)
            finally:
                output.close()


def unsupported_cases(temp: Path) -> None:
    path = _fixture(temp)
    with TTFont(path) as font:
        del font["HVAR"]
        assert partial.validate_variable_base(font) == "partial-stock-variable-unsupported"
    with TTFont(path) as font:
        extra = copy.deepcopy(font["fvar"].axes[0])
        extra.axisTag = "wdth"
        font["fvar"].axes.append(extra)
        assert partial.validate_variable_base(font) == "partial-stock-variable-unsupported"
    with TTFont(path) as font:
        font["VVAR"] = newTable("VVAR")
        assert partial.validate_variable_base(font) == "partial-stock-variable-metrics-unsupported"
    with TTFont(path) as font:
        font["gvar"].variations["u0041"][0].coordinates[-2] = (0, 3)
        assert partial.validate_variable_base(font) == "partial-stock-variable-metrics-unsupported"
    with TTFont(path) as font:
        # Sparse phantom points are resolved on the stock point topology by
        # the same IUP algorithm used when reading the variable glyph.
        font["gvar"].variations["u0041"][0].coordinates[-2:] = [None, None]
        assert partial.validate_variable_base(font) == ""
    with TTFont(path) as font:
        font["HVAR"].table.AdvWidthMap.mapping["u0041"] = 0x10000
        assert partial.validate_variable_base(font) == "partial-stock-variable-metrics-unsupported"
    with TTFont(path) as font:
        font["HVAR"].table.LsbMap = buildVarIdxMap(range(len(font.getGlyphOrder())), font.getGlyphOrder())
        assert partial.validate_variable_base(font) == "partial-stock-variable-metrics-unsupported"
    with TTFont(path) as font:
        font["HVAR"].table.RsbMap = buildVarIdxMap(range(len(font.getGlyphOrder())), font.getGlyphOrder())
        assert partial.validate_variable_base(font) == "partial-stock-variable-metrics-unsupported"
    with TTFont(path) as font:
        font["gvar"].variations["u0041"][0].coordinates[-4] = (3, 0)
        assert partial.validate_variable_base(font) == "partial-stock-variable-metrics-unsupported"
    with TTFont(path) as font:
        font["gvar"].variations["u0041"][0].coordinates[-3] = (36, 0)
        assert partial.validate_variable_base(font) == "partial-stock-variable-metrics-unsupported"
    with TTFont(path) as base:
        bad_source = temp / "VariableSource.ttf"
        fixture.make_font(bad_source, family="Unpinned User", variable=True)
        before = base["glyf"]["u0041"].compile(base["glyf"])
        with TTFont(bad_source) as source:
            try:
                partial.import_variable_partial(base, {"latin": source, "digit": source})
            except luoshu_merge.MergeError as error:
                assert str(error) == "partial-source-variable-not-fixed"
            else:
                raise AssertionError("uninstantiated variable source was accepted")
        assert base["glyf"]["u0041"].compile(base["glyf"]) == before


def device_case(bundle: Path) -> dict:
    stock = bundle / "stock/system/fonts/DancingScript-Regular.ttf"
    source_path = next(path for path in (bundle / "sources").glob("*.ttf") if "保时捷" in path.name)
    with TTFont(stock, recalcBBoxes=False, recalcTimestamp=False) as original, \
            TTFont(stock, recalcBBoxes=False, recalcTimestamp=False) as base, \
            TTFont(source_path, recalcBBoxes=False, recalcTimestamp=False) as source:
        source = instantiateVariableFont(source, {axis.axisTag: 700 if axis.axisTag == "wght"
                                               else axis.defaultValue for axis in source["fvar"].axes}, inplace=True)
        assert partial.validate_variable_base(base) == ""
        details = partial.import_variable_partial(base, {"latin": source, "digit": source})
        assert details["asciiLettersReplaced"] == 52 and details["asciiDigitsReplaced"] == 10
        _preserve_raw_layout(base, _raw_layout(original))
        output, data = _roundtrip(base)
        try:
            evidence = _verify(original, output, details)
        finally:
            output.close()
    return {"scope": "host-replay-of-supplied-complete-stock; mobile-rendering-unverified",
            "stockSha256": hashlib.sha256(stock.read_bytes()).hexdigest(),
            "sourceSha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
            "fixedSourceWeight": 700, "outputSha256": hashlib.sha256(data).hexdigest(),
            "asciiLettersReplaced": details["asciiLettersReplaced"],
            "asciiDigitsReplaced": details["asciiDigitsReplaced"],
            "changedGlyphCount": len(details["replacedGlyphNames"]),
            "componentCloneCount": len(details["clonedGlyphSources"]), **evidence}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device-bundle", type=Path)
    options = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="luoshu-partial-variation-") as scratch:
        temp = Path(scratch)
        supported_cases(temp)
        unsupported_cases(temp)
    print("PASS: fixed variable partial imports retain other-script and original advance variation")
    if options.device_bundle:
        print(json.dumps(device_case(options.device_bundle), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
