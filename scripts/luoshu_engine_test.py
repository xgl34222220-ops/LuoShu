#!/usr/bin/env python3
"""Engine v3: direct replacement with stock line metrics."""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))
sys.path.insert(0, str(ROOT / "scripts"))

from fontTools.ttLib import TTCollection, TTFont

import luoshu_engine as engine
import font_fixtures as composite
import font_fixtures as fixture
import luoshu_payload as payload_format

ROBOTO = "/system/fonts/Roboto-Regular.ttf"
CJK = "/system/fonts/NotoSansCJK-Regular.ttf"
MISANS = "/system/fonts/MiSansVF.ttf"
CLOCK = "/system/fonts/AndroidClock.ttf"
FONTS_XML = "/system/etc/fonts.xml"


def device(temp: Path):
    topology, _roles, stocks, xml_map = composite.build_device(temp / "device")
    return topology, stocks, xml_map


def run(temp: Path, name: str, topology: dict, spec: dict, xml_map: dict, stock_paths=None):
    payload = temp / name / "payload"
    payload.parent.mkdir(parents=True, exist_ok=True)
    manifest, report = engine.build(topology, spec, payload, temp / "cache", xml_map=xml_map,
                                    stock_paths=stock_paths or {})
    payload_format.validate_payload_integrity(manifest, payload)
    return manifest, report, payload


def xml_nodes(payload: Path, original: Path | None = None) -> list[tuple[str, str, dict[str, str]]]:
    rendered = payload / "system" / "etc" / "fonts.xml"
    if not rendered.is_file():
        assert original is not None, "fonts.xml was expected to change"
        rendered = original
    nodes = []
    indexes = xml_nodes.indexes = []
    for family in ET.parse(rendered).getroot().iter("family"):
        for font in family.iter("font"):
            axes = {axis.get("tag"): axis.get("stylevalue") for axis in font.iter("axis")}
            nodes.append(((font.text or "").strip(), font.get("weight"), axes))
            indexes.append(font.get("index"))
    return nodes


def glyph_points(font: TTFont, char: str) -> int:
    name = font.getBestCmap()[ord(char)]
    return len(font["glyf"][name].getCoordinates(font["glyf"])[0])


def set_weight(path: Path, weight: int) -> None:
    font = TTFont(str(path))
    font["OS/2"].usWeightClass = weight
    font.save(str(path))


def test_variable_single(temp: Path) -> None:
    topology, stocks, xml_map = device(temp)
    user = temp / "UserVF.ttf"
    composite.make_cjk_font(user, family="User VF", variable=True, pentagon=True)
    manifest, report, payload = run(temp, "vf", topology, {"mode": "single", "files": [str(user)]}, xml_map)

    replaced = {item["path"] for item in report["replaced"]}
    assert replaced == {ROBOTO, CJK, MISANS, CLOCK}, report
    assert report["keptStock"] == []
    assert all(item["variable"] for item in report["replaced"])
    # Same file names, stock line metrics, the user's outlines.
    for logical in replaced:
        output = TTFont(str(payload / logical.lstrip("/")))
        stock = TTFont(str(stocks[logical]))
        assert output["hhea"].ascent == stock["hhea"].ascent, logical
        assert output["hhea"].descent == stock["hhea"].descent, logical
        assert output["OS/2"].usWinAscent == stock["OS/2"].usWinAscent, logical
        assert "fvar" in output and glyph_points(output, "一") == 5
    # Variable output: every node keeps its file and carries a wght axis (the
    # static stock clock node gains one).
    nodes = xml_nodes(payload)
    assert nodes and all(axes == {"wght": weight} for _name, weight, axes in nodes), nodes
    assert {name for name, *_ in nodes} == {Path(path).name for path in replaced}
    kinds = {item["kind"] for item in manifest["files"]}
    assert kinds == {"physical-font", "xml"}, kinds

    # A stock XML without axes (static stock files) gets them added.
    plain = temp / "fonts-plain.xml"
    plain.write_text(xml_map[FONTS_XML].read_text(encoding="utf-8").replace(
        '<axis tag="wght" stylevalue="700"/>', '').replace('<axis tag="wght" stylevalue="400"/>', ''),
        encoding="utf-8")
    _m, _r, payload = run(temp, "vf-plain", topology, {"mode": "single", "files": [str(user)]}, {FONTS_XML: plain})
    nodes = xml_nodes(payload)
    assert all(axes == {"wght": weight} for _name, weight, axes in nodes), nodes

    # A snapshot captured while the pre-v3 pipeline's XML was mounted names its
    # generated files (gone now): they map back to the stock file and get replaced.
    stale = temp / "fonts-stale.xml"
    stale.write_text(xml_map[FONTS_XML].read_text(encoding="utf-8").replace(
        ">Roboto-Regular.ttf<", ">LuoShu-Roboto-Regular-100.ttf<"), encoding="utf-8")
    assert "LuoShu-Roboto-Regular-100.ttf" in stale.read_text(encoding="utf-8")
    _m, _r, payload = run(temp, "vf-stale", topology, {"mode": "single", "files": [str(user)]}, {FONTS_XML: stale})
    names = {name for name, *_ in xml_nodes(payload)}
    assert "Roboto-Regular.ttf" in names and not any(name.startswith("LuoShu-") for name in names), names

    # HyperOS lists MiSansVF_Overlay.ttf (a link to the theme font) first in
    # sans-serif; those nodes are pointed at the replaced MiSansVF.ttf, with
    # weights the topology never recorded. OEM copies of the config get the same.
    overlay_family = ('<family name="sans-serif"><font weight="400">MiSansVF_Overlay.ttf'
                      '<axis tag="wght" stylevalue="330"/></font>'
                      '<font weight="350">MiSansVF_Overlay.ttf</font></family>')
    root = temp / "xml-root"
    for partition, name in (("system", "fonts.xml"), ("system_ext", "hyper_fonts.xml")):
        (root / partition).mkdir(parents=True, exist_ok=True)
        (root / partition / name).write_text(xml_map[FONTS_XML].read_text(encoding="utf-8").replace(
            "<familyset>", "<familyset>" + overlay_family, 1), encoding="utf-8")
    (root / "system_ext" / "gone_fonts.xml").write_text(overlay_family.join(("<familyset>", "</familyset>")),
                                                        encoding="utf-8")
    live = temp / "live"
    (live / "system_ext" / "etc").mkdir(parents=True)
    (live / "system_ext" / "etc" / "hyper_fonts.xml").write_text("<familyset/>", encoding="utf-8")
    payload = temp / "overlay-payload"
    manifest, _report = engine.build(topology, {"mode": "single", "files": [str(user)]}, payload,
                                     temp / "cache", xml_root=root, live_root=live)
    payload_format.validate_payload_integrity(manifest, payload)
    written = {item["logicalPath"] for item in manifest["files"] if item["kind"] == "xml"}
    assert written == {FONTS_XML, "/system_ext/etc/hyper_fonts.xml"}, written
    for rendered in (payload / "system/etc/fonts.xml", payload / "system_ext/etc/hyper_fonts.xml"):
        family = ET.parse(rendered).getroot().find("family")
        fonts = [((font.text or "").strip(), font.get("weight"),
                  {axis.get("tag"): axis.get("stylevalue") for axis in font.iter("axis")})
                 for font in family.iter("font")]
        assert fonts == [("MiSansVF.ttf", "400", {"wght": "400"}), ("MiSansVF.ttf", "350", {"wght": "350"})], fonts


def test_static_family(temp: Path) -> None:
    topology, stocks, xml_map = device(temp)
    regular, bold = temp / "UserRegular.ttf", temp / "UserBold.ttf"
    composite.make_cjk_font(regular, family="User Static", y_max=700)
    composite.make_cjk_font(bold, family="User Static", y_max=800, pentagon=True)
    set_weight(bold, 700)
    manifest, report, payload = run(temp, "static", topology,
                                    {"mode": "single", "files": [str(regular), str(bold)]}, xml_map)
    assert not any(item["variable"] for item in report["replaced"])
    nodes = xml_nodes(payload)
    # No new file names (a per-file bind cannot add them): the bold weight
    # becomes face 1 of the same file and its XML node selects it by index.
    roboto = [(node, index) for node, index in zip(nodes, xml_nodes.indexes) if "Roboto" in node[0]]
    assert (("Roboto-Regular.ttf", "400", {}), None) in roboto, roboto
    assert (("Roboto-Regular.ttf", "700", {}), "1") in roboto, roboto
    collection = TTCollection(str(payload / ROBOTO.lstrip("/")))
    assert len(collection.fonts) == 2
    regular_face, bold_face = collection.fonts
    assert regular_face["OS/2"].usWeightClass == 400 and glyph_points(regular_face, "一") == 4
    assert bold_face["OS/2"].usWeightClass == 700 and glyph_points(bold_face, "一") == 5
    assert bold_face["hhea"].ascent == TTFont(str(stocks[ROBOTO]))["hhea"].ascent
    assert {item["kind"] for item in manifest["files"]} <= {"physical-font", "xml"}


def _bounds(font: TTFont, char: str, weight: float | None = None):
    from fontTools.pens.boundsPen import BoundsPen
    glyph_set = font.getGlyphSet(location={"wght": weight} if weight else None)
    pen = BoundsPen(glyph_set)
    glyph_set[font.getBestCmap()[ord(char)]].draw(pen)
    return pen.bounds


def widen_at_max_weight(path: Path) -> None:
    """Rectangle glyphs grow 40 units wider (right edge and advance) at wght max."""
    from fontTools.ttLib.tables.TupleVariation import TupleVariation
    font = TTFont(str(path))
    for name in font.getGlyphOrder():
        if name != ".notdef" and font["glyf"][name].numberOfContours == 1:
            font["gvar"].variations[name] = [TupleVariation(
                {"wght": (0.0, 1.0, 1.0)},
                [(0, 0), (40, 0), (40, 0), (0, 0), (0, 0), (40, 0), (0, 0), (0, 0)],
            )]
    if "HVAR" in font:
        del font["HVAR"]
    font.save(str(path))


def _mix_spec(temp: Path, cjk_mode: str) -> dict:
    cjk, latin, digit = temp / "MixCJK.ttf", temp / "MixLatin.ttf", temp / "MixDigit.ttf"
    composite.make_cjk_font(cjk, family="Mix CJK", variable=True, pentagon=True)
    fixture.make_font(latin, family="Mix Latin", variable=True)
    widen_at_max_weight(latin)
    fixture.make_font(digit, family="Mix Digit", advance=560, triangle=True)
    return {"mode": "composite", "roles": {
        "cjk": {"files": [str(cjk)], "mode": cjk_mode, "axes": {"wght": 400} if cjk_mode == "fixed" else {}},
        "latin": {"files": [str(latin)], "mode": "auto"},
        "digit": {"files": [str(digit)], "mode": "fixed", "axes": {"wght": 500}},
    }}


def test_composite_variable(temp: Path) -> None:
    topology, stocks, xml_map = device(temp)
    spec = _mix_spec(temp, "auto")
    manifest, report, payload = run(temp, "mix", topology, spec, xml_map)
    assert {item["path"] for item in report["replaced"]} == {ROBOTO, CJK, MISANS, CLOCK}
    assert all(item["variable"] for item in report["replaced"])
    assert report["stats"]["instancesBuilt"] == 1, report["stats"]
    for logical in (ROBOTO, MISANS):
        with TTFont(str(payload / logical.lstrip("/"))) as font:
            assert "fvar" in font and "HVAR" not in font
            assert glyph_points(font, "\u4e00") == 5, "Han from the CJK font"
            assert glyph_points(font, "A") == 4, "Latin from the Latin font"
            assert glyph_points(font, "0") == 3, "digits from the digit font"
            assert font["hhea"].ascent == TTFont(str(stocks[logical]))["hhea"].ascent
            # Latin keeps the source's weight variation; fixed digits do not vary.
            assert _bounds(font, "A", 900)[2] > _bounds(font, "A")[2] + 20, "Latin must vary with wght"
            heavy = font.getGlyphSet(location={"wght": 900})[font.getBestCmap()[ord("A")]]
            heavy.draw(__import__("fontTools.pens.recordingPen", fromlist=["RecordingPen"]).RecordingPen())
            assert heavy.width > font["hmtx"].metrics[font.getBestCmap()[ord("A")]][0] + 20, "advance varies too"
            assert _bounds(font, "0", 900) == _bounds(font, "0"), "fixed digits stay static"
    nodes = xml_nodes(payload, xml_map[FONTS_XML])
    assert all(axes == {"wght": weight} for _name, weight, axes in nodes), nodes
    assert not any(name.startswith("LuoShu-") for name, *_ in nodes)
    _manifest, again, _payload = run(temp, "mix-again", topology, spec, xml_map)
    assert again["stats"]["instancesBuilt"] == 0 and again["stats"]["outputsBuilt"] == 0, again["stats"]
    assert again["deploymentId"] == report["deploymentId"]


def test_composite_static(temp: Path) -> None:
    topology, stocks, xml_map = device(temp)
    spec = _mix_spec(temp, "fixed")
    _manifest, report, payload = run(temp, "mix-static", topology, spec, xml_map)
    assert not any(item["variable"] for item in report["replaced"])
    for logical in (ROBOTO, MISANS):
        with TTFont(str(payload / logical.lstrip("/")), fontNumber=0) as font:
            assert "fvar" not in font
            assert glyph_points(font, "\u4e00") == 5 and glyph_points(font, "A") == 4
            assert glyph_points(font, "0") == 3
            assert font["hhea"].ascent == TTFont(str(stocks[logical]))["hhea"].ascent
    nodes = xml_nodes(payload)
    assert all(not axes for _name, _weight, axes in nodes), nodes
    misans = [index for node, index in zip(nodes, xml_nodes.indexes) if node[0] == "MiSansVF.ttf"]
    assert misans == [None, "1"], misans

    # Every role fixed (as on the HyperOS device that hit this): all weights are
    # the same font, so no extra faces, no index changes, plain single fonts.
    for item in spec["roles"].values():
        item.update(mode="fixed", axes={"wght": 400})
    _manifest, report, payload = run(temp, "mix-fixed", topology, spec, xml_map)
    assert all(item["faces"] == 1 for item in report["replaced"]), report["replaced"]
    with TTFont(str(payload / ROBOTO.lstrip("/"))) as font:
        assert glyph_points(font, "A") == 4
    nodes = xml_nodes(payload)
    assert all(index is None for index in xml_nodes.indexes), nodes


def add_fullwidth_latin(path: Path) -> None:
    """Give the original fixture independent fullwidth Latin glyph slots."""
    with TTFont(path) as font:
        cmap = font.getBestCmap()
        order = list(font.getGlyphOrder())
        variations = font["gvar"].variations if "gvar" in font else None
        for point in (*range(0xFF21, 0xFF3B), *range(0xFF41, 0xFF5B)):
            original = cmap[point - 0xFEE0]
            name = f"fullwidth_u{point:04X}"
            order.append(name)
            font["glyf"][name] = copy.deepcopy(font["glyf"][original])
            font["hmtx"].metrics[name] = font["hmtx"].metrics[original]
            if variations is not None:
                variations[name] = copy.deepcopy(variations.get(original, []))
            for table in font["cmap"].tables:
                if table.isUnicode():
                    table.cmap[point] = name
        font.setGlyphOrder(order)
        font.save(path)


def test_composite_fullwidth_latin(temp: Path) -> None:
    # Both uploaded HyperOS source cmaps include fullwidth Latin slots. Original
    # fixtures give them visible outlines: those letters follow the English
    # slot and must not silently retain the Chinese source's outlines.
    topology, _stocks, xml_map = device(temp)
    spec = _mix_spec(temp, "auto")
    for role in ("cjk", "latin"):
        add_fullwidth_latin(Path(spec["roles"][role]["files"][0]))
    for mode in ("auto", "fixed"):
        spec["roles"]["cjk"]["mode"] = mode
        _manifest, _report, payload = run(temp, f"fullwidth-{mode}", topology, spec, xml_map)
        with TTFont(payload / MISANS.lstrip("/"), fontNumber=0) as font:
            for point in (*range(0xFF21, 0xFF3B), *range(0xFF41, 0xFF5B)):
                assert glyph_points(font, chr(point)) == 4, f"fullwidth Latin U+{point:04X} kept CJK glyph"
            assert glyph_points(font, "一") == 5, "Chinese stays in the Chinese slot"
            assert glyph_points(font, "0") == 3, "digits stay in the digit slot"
            if mode == "auto":
                assert _bounds(font, "Ａ", 900)[2] > _bounds(font, "Ａ")[2] + 20


def test_latin_only(temp: Path) -> None:
    topology, _stocks, xml_map = device(temp)
    latin = temp / "LatinOnly.ttf"
    fixture.make_font(latin, family="Latin Only", variable=True)
    _manifest, report, payload = run(temp, "latin", topology, {"mode": "single", "files": [str(latin)]}, xml_map)
    kept = {item["path"]: item["reason"] for item in report["keptStock"]}
    assert kept == {CJK: "source-has-no-han", MISANS: "source-has-no-han"}, kept
    assert {item["path"] for item in report["replaced"]} == {ROBOTO, CLOCK}
    assert not (payload / CJK.lstrip("/")).exists()


def test_collection_and_protected(temp: Path) -> None:
    topology, stocks, xml_map = device(temp)
    topology = copy.deepcopy(topology)
    # A two-face stock collection referenced by index, and an emoji font.
    ttc = temp / "NotoSansCJK.ttc"
    collection = TTCollection()
    collection.fonts = [TTFont(str(stocks[CJK])), TTFont(str(stocks[CJK]))]
    collection.save(str(ttc))
    slot = copy.deepcopy(topology["slots"].pop(CJK))
    logical = "/system/fonts/NotoSansCJK-Regular.ttc"
    slot.update(path=logical, slotName=Path(logical).name, format="TTC")
    slot["xmlRefs"] = [dict(ref, declared=Path(logical).name, resolvedPath=logical, index=index)
                       for index, ref in enumerate(slot["xmlRefs"])]
    topology["slots"][logical] = slot
    emoji = copy.deepcopy(topology["slots"][ROBOTO])
    emoji.update(path="/system/fonts/NotoColorEmoji.ttf", slotName="NotoColorEmoji.ttf", families=["emoji"])
    emoji["xmlRefs"] = []
    topology["slots"]["/system/fonts/NotoColorEmoji.ttf"] = emoji
    xml = xml_map[FONTS_XML].read_text(encoding="utf-8").replace(
        'weight="400" style="normal">NotoSansCJK-Regular.ttf', 'weight="400" style="normal" index="0">NotoSansCJK-Regular.ttc'
    ).replace('weight="700" style="normal">NotoSansCJK-Regular.ttf', 'weight="700" style="normal" index="1">NotoSansCJK-Regular.ttc')
    fixed_xml = temp / "fonts-ttc.xml"
    fixed_xml.write_text(xml, encoding="utf-8")
    user = temp / "UserVF2.ttf"
    composite.make_cjk_font(user, family="User VF", variable=True, pentagon=True)
    _manifest, report, payload = run(temp, "ttc", topology, {"mode": "single", "files": [str(user)]},
                                     {FONTS_XML: fixed_xml}, {logical: ttc})
    replaced = {item["path"]: item for item in report["replaced"]}
    assert replaced[logical]["faces"] == 2
    assert "/system/fonts/NotoColorEmoji.ttf" not in replaced
    output = TTCollection(str(payload / logical.lstrip("/")))
    assert len(output.fonts) == 2 and all(glyph_points(font, "一") == 5 for font in output.fonts)


def test_no_ui_target(temp: Path) -> None:
    topology, _stocks, xml_map = device(temp)
    for slot in topology["slots"].values():
        slot["families"] = ["serif"]
        for ref in slot["xmlRefs"]:
            ref["family"] = ref["familyNormalized"] = "serif"
    user = temp / "UserVF3.ttf"
    composite.make_cjk_font(user, family="User VF", variable=True)
    try:
        run(temp, "none", topology, {"mode": "single", "files": [str(user)]}, xml_map)
    except engine.EngineError as error:
        assert "没有可替换的系统界面字体" in str(error)
    else:
        raise AssertionError("a device without replaceable UI fonts must fail unchanged")


def test_metrics_from_stock_file(temp: Path) -> None:
    # The topology scanner measures only legacy-replaceable slots; ColorOS
    # SysFont-* and OSans-Solid-Digits arrive without metrics. They are read
    # from the stock file instead of keeping the slot stock.
    topology, stocks, xml_map = device(temp)
    slot = topology["slots"][CLOCK]
    expected = TTFont(str(stocks[CLOCK]))["hhea"].ascent
    topology["slots"][CLOCK] = {key: value for key, value in slot.items() if key not in {"metrics", "weight"}}
    user = temp / "UserVF.ttf"
    composite.make_cjk_font(user, family="User VF", variable=True, pentagon=True)
    _manifest, report, payload = run(temp, "nometrics", topology, {"mode": "single", "files": [str(user)]},
                                     xml_map, stock_paths={CLOCK: stocks[CLOCK]})
    assert CLOCK in {item["path"] for item in report["replaced"]}, report
    assert TTFont(str(payload / CLOCK.lstrip("/")))["hhea"].ascent == expected
    # ColorOS SysFont-Regular.ttf: no XML family, no metrics, Latin coverage
    # only. Measured from the stock file it is a Latin text font and replaced.
    bare = "/system/fonts/SysFont-Regular.ttf"
    topology["slots"][bare] = {"path": bare, "slotName": "SysFont-Regular.ttf", "partition": "system",
                               "families": [], "source": "physical-scan"}
    _manifest, report, _payload = run(temp, "bare", topology, {"mode": "single", "files": [str(user)]},
                                      xml_map, stock_paths={CLOCK: stocks[CLOCK], bare: stocks[ROBOTO]})
    assert {"path": bare, "role": "latin"} in [{"path": item["path"], "role": item["role"]}
                                               for item in report["replaced"]], report["replaced"]
    del topology["slots"][bare]
    # No stock bytes anywhere: still kept, with the reason.
    _manifest, report, _payload = run(temp, "nometrics-none", topology,
                                      {"mode": "single", "files": [str(user)]}, xml_map)
    assert {"path": CLOCK, "reason": "stock-metrics-missing"} in report["keptStock"], report["keptStock"]


def test_stock_alias_uses_lower_only(temp: Path) -> None:
    # HyperOS exposes system MiSans as an absolute product-font alias. Reading
    # the copied symlink directly follows the active replacement, whereas the
    # captured product bytes retain the stock coverage and line metrics.
    lower = temp / "lower"
    (lower / "system-fonts").mkdir(parents=True)
    (lower / "product-fonts").mkdir()
    alias = lower / "system-fonts/MiSansVF.ttf"
    alias.symlink_to("/product/fonts/MiSansVF.ttf")
    original = lower / "product-fonts/MiSansVF.ttf"
    fixture.make_font(original, family="Captured Original", ascent=910)
    live = temp / "active-custom.ttf"
    fixture.make_cjk_font(live, family="Active Custom", pentagon=True)
    with patch.dict(os.environ, LUOSHU_SELF_MOUNT_STATE_ROOT=str(temp)):
        found = engine._stock_file(MISANS, {})
        assert found == original, found
        assert engine._read_metrics(found)["hhea"]["ascent"] == 910
        alias.unlink()
        alias.symlink_to(live)
        assert engine._stock_file(MISANS, {}) is None, "lower must not read an external active custom font"
        assert engine._stock_file(MISANS, {MISANS: live}) == live, "explicit caller map remains authoritative"
        alias.unlink()
        alias.symlink_to("/product/fonts/missing.ttf")
        assert engine._stock_file(MISANS, {}) is None
        alias.unlink()
        alias.symlink_to("/product/fonts/cycle.ttf")
        (lower / "product-fonts/cycle.ttf").symlink_to(MISANS)
        assert engine._stock_file(MISANS, {}) is None


def _partial_stock(temp: Path, *, alias: bool = False, variable: bool = False) -> Path:
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    stock = temp / "PartialStock.ttf"
    fixture.make_font(stock, family="Stock Mono", triangle=True, advance=510, variable=variable)
    with TTFont(str(stock), recalcBBoxes=False) as font:
        variations = font["gvar"].variations if "gvar" in font else None
        order = list(font.getGlyphOrder())
        for name in ("fi", "B.alt", "retained"):
            pen = TTGlyphPen(font.getGlyphSet())
            if name == "retained":
                pen.addComponent("u0042", (1, 0, 0, 1, 13, 17))
            else:
                pen.moveTo((20, 0)); pen.lineTo((450, 0)); pen.lineTo((300, 500)); pen.closePath()
            font["glyf"][name] = pen.glyph()
            font["hmtx"].metrics[name] = (510, 20 if name != "retained" else 53)
            order.append(name)
            if variations is not None:
                variations[name] = []
        font.setGlyphOrder(order)
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap[0x0416] = "retained"
                if alias:
                    table.cmap[0x2109] = "u0041"
        addOpenTypeFeaturesFromString(font, "feature liga { sub u0066 u0069 by fi; } liga;"
                                    "feature ss01 { sub u0042 by B.alt; } ss01;"
                                    "feature kern { pos u0041 u0056 -20; } kern;")
        font.recalcBBoxes = True
        font.save(str(stock))
    return stock


def _partial_slot(topology: dict, stock: Path, logical: str, family: str) -> dict:
    slot = fixture.slot_from_stock(logical, stock, family=family, source_xml=FONTS_XML,
                                   declared=Path(logical).name)
    topology["slots"][logical] = slot
    return slot


def _coords(font: TTFont, name: str):
    coordinates, ends, flags = font["glyf"][name].getCoordinates(font["glyf"])
    return list(coordinates), list(ends), list(flags)


def test_partial_system_text(temp: Path) -> None:
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
    topology, stocks, xml_map = device(temp)
    stock = _partial_stock(temp)
    logical = "/system/fonts/DroidSansMono.ttf"
    slot = _partial_slot(topology, stock, logical, "monospace")
    # Exercise the real device's unmeasured protected slots too.
    slot.pop("metrics")
    slot["xmlRefs"][0]["postScriptName"] = "StockMono-Regular"
    spec = _mix_spec(temp, "fixed")
    spec["roles"]["latin"] = {"files": [spec["roles"]["latin"]["files"][0]],
                                  "mode": "fixed", "axes": {"wght": 700}}
    latin = Path(spec["roles"]["latin"]["files"][0])
    with TTFont(str(latin), recalcBBoxes=False) as font:
        variations = font["gvar"].variations
        order = list(font.getGlyphOrder())
        font["glyf"]["fi"] = copy.deepcopy(font["glyf"]["u0041"])
        font["hmtx"].metrics["fi"] = (620, 40)
        variations["fi"] = []
        font.setGlyphOrder([*order, "fi"])
        addOpenTypeFeaturesFromString(font, "feature liga { sub u0066 u0069 by fi; } liga;")
        font.save(str(latin))
    original_xml = xml_map[FONTS_XML].read_text()
    node = ('<family name="monospace"><font weight="400" style="normal" index="0" '
            'postScriptName="StockMono-Regular">DroidSansMono.ttf</font></family>')
    xml_map[FONTS_XML].write_text(original_xml.replace("</familyset>", node + "</familyset>"))
    _manifest, report, payload = run(temp, "partial", topology, spec, xml_map, {logical: stock})
    item = next(item for item in report["replaced"] if item["path"] == logical)
    assert item["mode"] == "partial-stock" and item["asciiLettersReplaced"] == 52, item
    assert item["asciiDigitsReplaced"] == 10 and item["ligatureGlyphsReplaced"] == 1, item
    assert item["clonedGlyphCount"] > 0 and item["originalGlyphOrderPreservedPrefix"], item
    with TTFont(str(stock), recalcBBoxes=False) as before, \
            TTFont(str(payload / logical.lstrip("/")), recalcBBoxes=False) as after:
        assert after.getGlyphOrder()[:len(before.getGlyphOrder())] == before.getGlyphOrder()
        assert after.getBestCmap() == before.getBestCmap()
        assert after["GSUB"].compile(after) == before["GSUB"].compile(before)
        assert after["GPOS"].compile(after) == before["GPOS"].compile(before)
        assert _coords(after, "retained") == _coords(before, "retained"), "non-Latin component outline"
        assert _coords(after, "B.alt") == _coords(before, "B.alt"), "unmatched layout output remains stock"
        assert glyph_points(after, "B") == 4 and glyph_points(after, "0") == 3
        assert _coords(after, "fi") != _coords(before, "fi"), "matched ligature uses English source"
        assert after["hhea"].ascent == before["hhea"].ascent
        assert all(after["hmtx"].metrics[name][0] == metrics[0]
                   for name, metrics in before["hmtx"].metrics.items()), "all original advances stay stock"
        assert _bounds(after, "B")[0] >= 0 and _bounds(after, "B")[2] <= 510
        assert after["maxp"].maxPoints >= len(after["glyf"]["u0042"].coordinates)
    rendered = ET.parse(payload / FONTS_XML.lstrip("/")).getroot()
    assert ET.tostring(rendered.find("family[@name='monospace']")) == ET.tostring(ET.fromstring(node))
    # Full-byte stock identity invalidates cached partial output even when
    # size/mtime and layout inputs are unchanged.
    _manifest, again, _payload = run(temp, "partial-again", topology, spec, xml_map, {logical: stock})
    assert again["stats"]["outputsBuilt"] == 0, again["stats"]
    with TTFont(str(stock), recalcBBoxes=False) as font:
        font["glyf"]["B.alt"].coordinates[0] = (31, 9)
        font.save(str(stock))
    _manifest, changed, _payload = run(temp, "partial-changed", topology, spec, xml_map, {logical: stock})
    assert changed["stats"]["outputsBuilt"] == 1, changed["stats"]


def test_partial_protection_and_missing_stock(temp: Path) -> None:
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
    from fontTools.ttLib.tables import otTables
    topology, _stocks, xml_map = device(temp)
    stock = _partial_stock(temp, alias=True)
    logical = "/system/fonts/NotoSerif-Regular.ttf"
    slot = _partial_slot(topology, stock, logical, "serif")
    spec = _mix_spec(temp, "fixed")
    _manifest, report, payload = run(temp, "partial-alias", topology, spec, xml_map, {logical: stock})
    item = next(item for item in report["replaced"] if item["path"] == logical)
    assert item["asciiLettersReplaced"] == 51 and "u0041" in item["protectedSharedGlyphs"], item
    with TTFont(str(stock)) as before, TTFont(str(payload / logical.lstrip("/"))) as after:
        assert _coords(before, "u0041") == _coords(after, "u0041"), "symbol alias must stay stock"
    # Language semantics and ROM filenames do not restrict text candidates.
    # This only admits trusted stock inspection, never a whole-face rewrite.
    bad_slot = copy.deepcopy(slot)
    bad_slot["xmlRefs"][0]["familyAttributes"]["lang"] = "und-Arab"
    assert engine.is_partial_text_slot(logical, bad_slot)
    assert engine.is_partial_text_slot("/system/fonts/VendorMono.ttf", slot)
    assert engine.is_partial_text_slot(logical, slot)
    assert not engine.is_partial_text_slot("/data/fonts/NotoSerif-Regular.ttf", slot)
    icon_slot = copy.deepcopy(slot)
    icon_slot["families"] = ["monospace", "Material Icons"]
    assert not engine.is_partial_text_slot(logical, icon_slot)
    with patch.dict(os.environ, {"LUOSHU_SELF_MOUNT_STATE_ROOT": str(temp / "missing-lower")}):
        _manifest, missing, _payload = run(temp, "partial-missing", topology, spec, xml_map)
    assert {"path": logical, "reason": "partial-stock-base-missing"} in missing["keptStock"]
    variable = _partial_stock(temp, variable=True)
    _manifest, unsupported, _payload = run(temp, "partial-variable", topology, spec, xml_map, {logical: variable})
    assert {"path": logical, "reason": "partial-stock-variable-unsupported"} in unsupported["keptStock"]
    collection = TTCollection()
    collection.fonts = [TTFont(str(stock)), TTFont(str(stock))]
    ttc = temp / "stock.ttc"; collection.save(str(ttc))
    _manifest, unsupported, _payload = run(temp, "partial-collection", topology, spec, xml_map, {logical: ttc})
    assert {"path": logical, "reason": "partial-stock-collection-unsupported"} in unsupported["keptStock"]
    # A Latin ligature also produced by Cyrillic input is not a proved text
    # glyph. A Cyrillic SingleSubst producing A protects A even without a cmap
    # alias. Keep both outlines and the GSUB program intact.
    stock = _partial_stock(temp)
    with TTFont(str(stock), recalcBBoxes=False) as font:
        addOpenTypeFeaturesFromString(font, "feature liga { sub u0066 u0069 by fi; "
                                    "sub retained retained by fi; } liga;"
                                    "feature ss01 { sub retained by u0041; } ss01;")
        font.save(str(stock))
    latin = Path(spec["roles"]["latin"]["files"][0])
    with TTFont(str(latin), recalcBBoxes=False) as font:
        variations = font["gvar"].variations
        order = list(font.getGlyphOrder())
        font["glyf"]["fi"] = copy.deepcopy(font["glyf"]["u0041"])
        font["hmtx"].metrics["fi"] = (620, 40)
        variations["fi"] = []
        font.setGlyphOrder([*order, "fi"])
        addOpenTypeFeaturesFromString(font, "feature liga { sub u0066 u0069 by fi; } liga;")
        font.save(str(latin))
    _manifest, shared, payload = run(temp, "partial-shared-gsub", topology, spec, xml_map, {logical: stock})
    item = next(item for item in shared["replaced"] if item["path"] == logical)
    assert {"fi", "u0041"} <= set(item["protectedLayoutGlyphs"]), item
    assert item["asciiLettersReplaced"] == 51 and item["ligatureGlyphsReplaced"] == 0, item
    with TTFont(str(stock), recalcBBoxes=False) as before, \
            TTFont(str(payload / logical.lstrip("/")), recalcBBoxes=False) as after:
        assert _coords(before, "fi") == _coords(after, "fi")
        assert _coords(before, "u0041") == _coords(after, "u0041")
        assert before["GSUB"].compile(before) == after["GSUB"].compile(after)
    # Old point-index anchors are unsuitable for the newly drawn glyph. The
    # partial slot fails closed in planning while ordinary UI targets build.
    stock = _partial_stock(temp)
    with TTFont(str(stock), recalcBBoxes=False) as font:
        table = otTables.CursivePos(); table.Format = 1
        table.Coverage = otTables.Coverage(); table.Coverage.glyphs = ["u0041"]
        anchor = otTables.Anchor(); anchor.Format = 2
        anchor.XCoordinate = anchor.YCoordinate = 0; anchor.AnchorPoint = 1
        record = otTables.EntryExitRecord(); record.EntryAnchor = anchor; record.ExitAnchor = None
        table.EntryExitRecord = [record]; table.EntryExitCount = 1
        lookup = otTables.Lookup(); lookup.LookupType = 3; lookup.LookupFlag = 0
        lookup.SubTable = [table]; lookup.SubTableCount = 1
        font["GPOS"].table.LookupList.Lookup.append(lookup)
        font["GPOS"].table.LookupList.LookupCount += 1
        font.save(str(stock))
    _manifest, guarded, _payload = run(temp, "partial-point-layout", topology, spec, xml_map, {logical: stock})
    assert {"path": logical, "reason": "partial-stock-point-layout-unsupported"} in guarded["keptStock"]
    # A permitted single source missing a digit keeps this optional partial
    # slot, rather than breaking an otherwise valid ordinary UI application.
    user = temp / "PartialSingle.ttf"; fixture.make_cjk_font(user, family="Partial Single")
    with TTFont(str(user)) as font:
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap.pop(ord("0"), None)
        font.save(str(user))
    stock = _partial_stock(temp)
    _manifest, incomplete, _payload = run(temp, "partial-incomplete-source", topology,
                                          {"mode": "single", "files": [str(user)]}, xml_map, {logical: stock})
    assert {"path": logical, "reason": "partial-source-text-incomplete"} in incomplete["keptStock"]


def test_partial_real_component_fonts(temp: Path) -> None:
    # Optional host evidence, not the device's original stock. CI may lack the
    # DejaVu packages; the synthetic component/alias assertions always run.
    for filename, logical, family in (("DejaVuSerif.ttf", "/system/fonts/NotoSerif-Regular.ttf", "serif"),
                                     ("DejaVuSansMono.ttf", "/system/fonts/DroidSansMono.ttf", "monospace")):
        source = Path("/usr/share/fonts/truetype/dejavu") / filename
        if not source.is_file():
            continue
        case = temp / source.stem; case.mkdir()
        topology, _stocks, xml_map = device(case)
        stock = case / filename; shutil.copyfile(source, stock)
        _partial_slot(topology, stock, logical, family)
        spec = _mix_spec(case, "fixed")
        with TTFont(str(stock)) as original:
            has_math = "MATH" in original
        if has_math:
            _manifest, guarded, guarded_payload = run(case, "partial-math-guard", topology, spec,
                                                       xml_map, {logical: stock})
            assert {"path": logical, "reason": "partial-stock-math-layout-unsupported"} in guarded["keptStock"]
            assert not (guarded_payload / logical.lstrip("/")).exists()
            # The complete host original is now explicitly unsupported. Its
            # copied non-math fixture still exercises all prior component,
            # GID, script, layout and advance assertions without hiding that
            # change in eligibility or claiming real-device evidence.
            with TTFont(str(stock)) as non_math_fixture:
                del non_math_fixture["MATH"]
                non_math_fixture.save(str(stock))
        _manifest, report, payload = run(case, "partial-real", topology, spec, xml_map, {logical: stock})
        item = next(item for item in report["replaced"] if item["path"] == logical)
        assert item["asciiLettersReplaced"] == 52 and item["asciiDigitsReplaced"] == 10, item
        with TTFont(str(stock), recalcBBoxes=False) as before, \
                TTFont(str(payload / logical.lstrip("/")), recalcBBoxes=False) as after:
            order = before.getGlyphOrder()
            assert after.getGlyphOrder()[:len(order)] == order
            for tag in ("GSUB", "GPOS", "GDEF"):
                if tag in before:
                    assert before.reader[tag] == after.reader[tag], (filename, tag, "original bytes")
                    assert before[tag].compile(before) == after[tag].compile(after), (filename, tag)
            with TTFont(spec["roles"]["latin"]["files"][0]) as donor:
                latin_cmap = donor.getBestCmap()
                ligatures = engine.luoshu_merge.partial_ligatures(donor)
            with TTFont(spec["roles"]["digit"]["files"][0]) as donor:
                digit_cmap = donor.getBestCmap()
            changed = {before.getBestCmap()[point] for point in engine.luoshu_merge.PARTIAL_TEXT_CODEPOINTS
                       if point in before.getBestCmap() and point in
                       (digit_cmap if point in engine.luoshu_merge.DIGIT_CODEPOINTS else latin_cmap)}
            changed.update(name for sequence, name in engine.luoshu_merge.partial_ligatures(before).items()
                           if sequence in ligatures)
            changed.difference_update(item["protectedSharedGlyphs"])
            for name in order:
                assert before["hmtx"].metrics[name][0] == after["hmtx"].metrics[name][0], (filename, name)
                if name not in changed:
                    assert _coords(before, name) == _coords(after, name), (filename, name)
        label = "host-derived non-math fixture" if has_math else "host font"
        print(f"partial {label}: {filename} Latin={item['asciiLettersReplaced']} digits={item['asciiDigitsReplaced']} "
              f"clones={item['clonedGlyphCount']} retained outlines/layout/advances PASS")


def test_generic_partial_text_routes(temp: Path) -> None:
    cases = (
        ("/product/fonts/OemText.ttf", "serif", {"lang": "und-Arab"}, True),
        ("/vendor/fonts/brand/VendorMonoText.ttf", "vendor-monospace", {}, False),
        ("/system_ext/fonts/RomCasual.ttf", "casual", {"fallbackFor": "sans-serif", "lang": "ja,ko"}, True),
        ("/cust/fonts/BrandCursive.ttf", "cursive", {}, False),
    )
    for number, (logical, family, attributes, with_xml) in enumerate(cases):
        case = temp / str(number); case.mkdir()
        topology, _stocks, xml_map = device(case)
        stock = _partial_stock(case)
        slot = _partial_slot(topology, stock, logical, family)
        slot.pop("metrics")
        node = None
        if with_xml:
            slot["xmlRefs"][0]["familyAttributes"] = dict(attributes)
            node = ET.Element("family", {"name": family, **attributes})
            ET.SubElement(node, "font", {"weight": "400", "style": "normal"}).text = Path(logical).name
            original = ET.parse(xml_map[FONTS_XML])
            original.getroot().append(node)
            original.write(xml_map[FONTS_XML], encoding="unicode")
        else:
            slot["xmlRefs"] = []
        assert engine.is_partial_text_slot(logical, slot), (logical, family)
        _manifest, report, payload = run(case, "generic-partial", topology, _mix_spec(case, "fixed"),
                                         xml_map, {logical: stock})
        item = next(item for item in report["replaced"] if item["path"] == logical)
        assert item["mode"] == "partial-stock" and item["asciiLettersReplaced"] == 52
        assert item["asciiDigitsReplaced"] == 10 and not item["variable"]
        with TTFont(str(stock), recalcBBoxes=False) as before, \
                TTFont(str(payload / logical.lstrip("/")), recalcBBoxes=False) as after:
            assert after.getBestCmap() == before.getBestCmap()
            assert after.getGlyphOrder()[:len(before.getGlyphOrder())] == before.getGlyphOrder()
            assert _coords(after, "retained") == _coords(before, "retained"), "other-script composite"
            assert _coords(after, "B.alt") == _coords(before, "B.alt"), "unmatched stylistic output"
            assert after.reader["GSUB"] == before.reader["GSUB"]
            assert after.reader["GPOS"] == before.reader["GPOS"]
            assert all(after["hmtx"].metrics[name][0] == advance
                       for name, (advance, _lsb) in before["hmtx"].metrics.items())
        if node is not None:
            rendered = ET.parse(payload / FONTS_XML.lstrip("/")).getroot()
            assert ET.tostring(rendered.find(f"family[@name='{family}']")) == ET.tostring(node)

    # A Latin-only source may patch a protected multilingual stock font: its
    # retained Han/other scripts do not need to be supplied by the donor.
    case = temp / "latin-only"; case.mkdir()
    topology, _stocks, xml_map = device(case)
    stock = _partial_stock(case)
    with TTFont(str(stock), recalcBBoxes=False) as font:
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap[0x4E00] = "retained"
        font.save(str(stock))
    logical = "/product/fonts/LocalizedSerif.ttf"
    _partial_slot(topology, stock, logical, "serif")["xmlRefs"] = []
    source = case / "LatinOnly.ttf"; fixture.make_font(source, family="Latin Only")
    _manifest, report, payload = run(case, "partial-latin-only", topology,
                                     {"mode": "single", "files": [str(source)]}, xml_map, {logical: stock})
    assert any(item["path"] == logical and item["mode"] == "partial-stock" for item in report["replaced"])
    with TTFont(str(stock)) as before, TTFont(str(payload / logical.lstrip("/"))) as after:
        assert _coords(after, after.getBestCmap()[0x4E00]) == _coords(before, before.getBestCmap()[0x4E00])


def test_generic_partial_trust_and_unsupported(temp: Path) -> None:
    from fontTools.ttLib.tables.DefaultTable import DefaultTable
    topology, _stocks, xml_map = device(temp)
    logical = "/product/fonts/OemSerif.ttf"
    stock = _partial_stock(temp)
    slot = _partial_slot(topology, stock, logical, "serif")
    slot["xmlRefs"] = []
    spec = _mix_spec(temp, "fixed")

    def reason(name: str, source: Path, expected: str, modified_slot: dict | None = None,
               target_path: str = logical):
        modified = copy.deepcopy(topology)
        modified["slots"].pop(logical)
        modified["slots"][target_path] = copy.deepcopy(modified_slot or slot)
        _manifest, report, payload = run(temp, name, modified, spec, xml_map, {target_path: source})
        assert {"path": target_path, "reason": expected} in report["keptStock"], report["keptStock"]
        assert not any(item["path"] == target_path for item in report["replaced"])
        if engine._partial_path_supported(target_path):
            assert not (payload / target_path.lstrip("/")).exists()

    for number, path in enumerate(("/data/fonts/OemSerif.ttf", "/system/fonts/../OemSerif.ttf",
                                    "/system//fonts/OemSerif.ttf", "/cache/fonts/OemSerif.ttf",
                                    "/product/fonts/./OemSerif.ttf", "/product/fonts/sub//OemSerif.ttf")):
        assert not engine.is_partial_text_slot(path, slot)
        reason(f"bad-path-{number}", stock, "partial-stock-path-unsupported", target_path=path)

    mismatch = copy.deepcopy(slot)
    mismatch["xmlRefs"] = [{"resolvedPath": "/product/fonts/Another.ttf"}]
    reason("mismatch", stock, "partial-stock-reference-mismatch", mismatch)
    indexed = copy.deepcopy(slot); indexed["faceIndex"] = 1
    reason("single-index", stock, "partial-stock-face-index-unsupported", indexed)

    cff = temp / "CffBase.otf"; fixture.make_font(cff, family="Text Serif", cff=True)
    reason("cff-base", cff, "partial-stock-outline-unsupported")
    unreadable = temp / "Unreadable.ttf"; unreadable.write_bytes(b"not-a-font")
    reason("unreadable", unreadable, "partial-stock-unreadable")
    empty = temp / "EmptyLetter.ttf"; shutil.copyfile(stock, empty)
    from fontTools.ttLib.tables._g_l_y_f import Glyph
    with TTFont(str(empty)) as font:
        for point in engine.LATIN_LETTERS | engine.DIGITS:
            font["glyf"][font.getBestCmap()[point]] = Glyph()
        font.save(str(empty))
    reason("empty-letter", empty, "partial-stock-text-incomplete")

    for tag, expected in (("COLR", "partial-stock-color-or-bitmap-unsupported"),
                          ("MATH", "partial-stock-math-layout-unsupported"),
                          ("LSDG", "partial-stock-hollow-base")):
        tagged = temp / f"{tag}.ttf"; shutil.copyfile(stock, tagged)
        with TTFont(str(tagged)) as font:
            table = DefaultTable(tag); table.data = b"luoshu-guard-fixture"
            font[tag] = table; font.save(str(tagged))
        reason(f"tag-{tag}", tagged, expected)

    disguised = temp / "Disguised.ttf"; fixture.make_font(disguised, family="Material Icons")
    reason("font-name-symbol", disguised, "partial-stock-protected-identity")
    icon_slot = copy.deepcopy(slot); icon_slot["families"] = ["monospace", "Material Icons"]
    reason("slot-symbol", stock, "partial-stock-protected-identity", icon_slot)

    archive = temp / "old-lite"; archived = archive / "stock/product/fonts/OemSerif.ttf"
    archived.parent.mkdir(parents=True); shutil.copyfile(stock, archived)
    (archive / "index.json").write_text(json.dumps({"stock": {
        logical: {"file": "stock/product/fonts/OemSerif.ttf", "hollow": True}}}))
    reason("old-hollow-index", archived, "partial-stock-hollow-base")
    (archive / "index.json").write_text(json.dumps({"stock": {
        logical: {"file": "stock/product/fonts/OemSerif.ttf", "hollow": False}}}))
    assert engine._partial_stock_reason(archived, logical) == "", "complete archived originals remain valid"

    # The lower snapshot, never an active absolute alias target, proves stock.
    lower_root = temp / "lower-state"
    product = lower_root / "lower/product-fonts"; vendor = lower_root / "lower/vendor-fonts"
    product.mkdir(parents=True); vendor.mkdir()
    (product / "OemSerif.ttf").symlink_to("/vendor/fonts/Original.ttf")
    shutil.copyfile(stock, vendor / "Original.ttf")
    with patch.dict(os.environ, {"LUOSHU_SELF_MOUNT_STATE_ROOT": str(lower_root)}):
        assert engine._partial_stock_file(logical, {}) == vendor / "Original.ttf"
        (product / "OemSerif.ttf").unlink()
        (product / "OemSerif.ttf").symlink_to("/data/fonts/active.ttf")
        assert engine._partial_stock_file(logical, {}) is None
        _manifest, report, _payload = run(temp, "unsafe-live-alias", topology, spec, xml_map)
        assert {"path": logical, "reason": "partial-stock-base-missing"} in report["keptStock"]


def test_generic_partial_subset_text(temp: Path) -> None:
    # Script-specific fonts can supply ASCII digits without Latin. Requiring
    # 62 characters in the stock base would leave those digits untouched.
    for number, kept_letters in enumerate((set(), {ord("A")})):
        case = temp / str(number); case.mkdir()
        topology, _stocks, xml_map = device(case)
        stock = _partial_stock(case)
        with TTFont(str(stock), recalcBBoxes=False) as font:
            for table in font["cmap"].tables:
                if table.isUnicode():
                    for point in engine.LATIN_LETTERS - kept_letters:
                        table.cmap.pop(point, None)
            font.save(str(stock))
        logical = "/product/fonts/VendorArabicText.ttf"
        slot = _partial_slot(topology, stock, logical, "vendor-text")
        slot["xmlRefs"][0]["familyAttributes"]["lang"] = "und-Arab"
        assert engine.is_partial_text_slot(logical, slot)
        _manifest, report, payload = run(case, "partial-subset", topology, _mix_spec(case, "fixed"),
                                         xml_map, {logical: stock})
        item = next(item for item in report["replaced"] if item["path"] == logical)
        assert item["mode"] == "partial-stock" and item["asciiDigitsReplaced"] == 10
        assert item["asciiLettersReplaced"] == len(kept_letters)
        audit = next(item for item in report["coverageAudit"]["paths"] if item["path"] == logical)
        assert audit["presentAsciiComplete"] is True and audit["asciiComplete"] is False
        assert audit["retainedPresentAscii"] == {"letters": 0, "digits": 0}
        with TTFont(str(stock), recalcBBoxes=False) as before, \
                TTFont(str(payload / logical.lstrip("/")), recalcBBoxes=False) as after:
            assert after.getBestCmap() == before.getBestCmap(), "no source-only Latin coverage introduced"
            assert _coords(after, "retained") == _coords(before, "retained")
            assert _coords(after, "fi") == _coords(before, "fi"), "unproved substitution remains stock"
            assert after.reader["GSUB"] == before.reader["GSUB"] and after.reader["GPOS"] == before.reader["GPOS"]
            for point in engine.DIGITS:
                name = before.getBestCmap()[point]
                assert _coords(after, name) != _coords(before, name), f"digit U+{point:04X}"
                assert after["hmtx"].metrics[name][0] == before["hmtx"].metrics[name][0]


def test_generic_partial_uvs_ownership(temp: Path) -> None:
    from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
    topology, _stocks, xml_map = device(temp)
    stock = _partial_stock(temp)
    with TTFont(str(stock), recalcBBoxes=False) as font:
        variation = CmapSubtable.newSubtable(14)
        variation.platformID, variation.platEncID, variation.language = 0, 5, 0
        variation.cmap = {}
        variation.uvsDict = {0xFE0F: [(0x0041, None), (0x0628, "u0042")]}
        font["cmap"].tables.append(variation)
        font.save(str(stock))
    logical = "/vendor/fonts/LocalizedSerif.ttf"
    _partial_slot(topology, stock, logical, "serif")["xmlRefs"] = []
    _manifest, report, payload = run(temp, "partial-uvs", topology, _mix_spec(temp, "fixed"),
                                     xml_map, {logical: stock})
    item = next(item for item in report["replaced"] if item["path"] == logical)
    assert item["asciiLettersBefore"] == 52 and item["asciiLettersReplaced"] == 51
    assert item["asciiDigitsReplaced"] == 10 and "u0042" in item["protectedSharedGlyphs"]
    audit = next(item for item in report["coverageAudit"]["paths"] if item["path"] == logical)
    assert audit["presentAsciiComplete"] is False
    assert audit["retainedPresentAscii"] == {"letters": 1, "digits": 0}
    with TTFont(str(stock), recalcBBoxes=False) as before, \
            TTFont(str(payload / logical.lstrip("/")), recalcBBoxes=False) as after:
        assert _coords(before, "u0042") == _coords(after, "u0042"), "Arabic UVS shared glyph remains original"
        old_uvs = [table.uvsDict for table in before["cmap"].tables if table.format == 14]
        new_uvs = [table.uvsDict for table in after["cmap"].tables if table.format == 14]
        assert old_uvs == new_uvs


def test_generic_partial_inherited_metrics(temp: Path) -> None:
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    topology, _stocks, xml_map = device(temp)
    stock = _partial_stock(temp)
    with TTFont(str(stock), recalcBBoxes=False) as font:
        pen = TTGlyphPen(font.getGlyphSet())
        pen.addComponent("u0043", (1, 0, 0, 1, 0, 0))
        glyph = pen.glyph()
        glyph.components[0].flags |= 0x0200  # USE_MY_METRICS
        font["glyf"]["u0041"] = glyph
        glyph.recalcBounds(font["glyf"])
        # The own hmtx value deliberately differs from the inherited cell.
        # Retaining own hmtx while redrawing a simple A would be incorrect.
        font["hmtx"].metrics["u0041"] = (900, 40)
        font.save(str(stock))
    logical = "/product/fonts/InheritedSerif.ttf"
    _partial_slot(topology, stock, logical, "serif")["xmlRefs"] = []
    _manifest, report, payload = run(temp, "inherited-metrics", topology, _mix_spec(temp, "fixed"),
                                     xml_map, {logical: stock})
    item = next(item for item in report["replaced"] if item["path"] == logical)
    assert item["asciiLettersReplaced"] == 51 and item["asciiDigitsReplaced"] == 10
    assert item["protectedMetricGlyphs"] == ["u0041"] and "u0041" not in item["replacedGlyphNames"]
    with TTFont(str(stock), recalcBBoxes=False) as before, \
            TTFont(str(payload / logical.lstrip("/")), recalcBBoxes=False) as after:
        assert after["glyf"]["u0041"].isComposite(), "inherited-metric target must retain its composite semantics"
        component = after["glyf"]["u0041"].components[0]
        assert component.flags & 0x0200
        assert item["clonedGlyphSources"][component.glyphName] == "u0043"
        assert after["hmtx"].metrics[component.glyphName] == before["hmtx"].metrics["u0043"]
        assert after["hmtx"].metrics["u0041"] == before["hmtx"].metrics["u0041"] == (900, 40)
        assert _coords(after, "u0041") == _coords(before, "u0041")
        assert _coords(after, "u0043") != _coords(before, "u0043"), "other safe text glyph is still replaced"


def test_policy_revision_reuses_full_output_cache(temp: Path) -> None:
    topology, _stocks, xml_map = device(temp)
    stock = _partial_stock(temp)
    logical = "/system/fonts/DroidSansMono.ttf"
    _partial_slot(topology, stock, logical, "monospace")
    spec = _mix_spec(temp, "fixed")
    with patch.object(engine, "ENGINE_REVISION", 4):
        _manifest, old_report, old_payload = run(temp, "rev4", topology, spec, xml_map, {logical: stock})
    old_full_files = {item["path"]: payload_format._sha256(old_payload / item["path"].lstrip("/"))
                      for item in old_report["replaced"] if item.get("mode") != "partial-stock"}
    old_partial_cache = set((temp / "cache").glob("partial-*.ttf"))
    _manifest, report, payload = run(temp, "rev5", topology, spec, xml_map, {logical: stock})
    assert report["engineRevision"] == 5 and engine.FULL_OUTPUT_REVISION == 4
    assert report["stats"]["instancesBuilt"] == 0 and report["stats"]["outputsBuilt"] == 1, report["stats"]
    assert report["stats"]["outputsCached"] == len(old_full_files), report["stats"]
    assert not old_partial_cache & set((temp / "cache").glob("partial-*.ttf")), "partial outputs use revision 5"
    assert all(payload_format._sha256(payload / path.lstrip("/")) == digest
               for path, digest in old_full_files.items()), "full output bytes stay unchanged"
    for item in report["replaced"]:
        if item.get("mode") != "partial-stock":
            assert item["sourceCoverage"]["asciiLetters"] == 52 and item["sourceCoverage"]["asciiDigits"] == 10
            assert item["sourceCoverage"]["faces"] == item["faces"]


def test_generic_partial_fixed_variable_route(temp: Path) -> None:
    import luoshu_partial_variations_test as variable_fixture
    topology, _stocks, xml_map = device(temp)
    stock = variable_fixture._fixture(temp, implicit=True)
    logical = "/product/fonts/VendorCursiveVF.ttf"
    slot = _partial_slot(topology, stock, logical, "cursive")
    slot["xmlRefs"][0]["familyAttributes"]["lang"] = "ja,ko"
    spec = _mix_spec(temp, "fixed")
    _manifest, unsupported, _payload = run(temp, "auto-vf-donor", topology, spec, xml_map, {logical: stock})
    assert {"path": logical, "reason": "partial-stock-variable-auto-source-unsupported"} in unsupported["keptStock"]
    fixed = copy.deepcopy(spec)
    fixed["roles"]["latin"]["mode"] = "fixed"
    fixed["roles"]["latin"]["axes"] = {"wght": 700}
    _manifest, report, payload = run(temp, "fixed-vf-donor", topology, fixed, xml_map, {logical: stock})
    item = next(item for item in report["replaced"] if item["path"] == logical)
    assert item["mode"] == "partial-stock" and item["variable"] and item["stockVariable"]
    assert item["asciiLettersBefore"] == item["asciiLettersReplaced"] == 52
    assert item["asciiDigitsBefore"] == item["asciiDigitsReplaced"] == 10
    with TTFont(str(stock), recalcBBoxes=False, recalcTimestamp=False) as before, \
            TTFont(str(payload / logical.lstrip("/")), recalcBBoxes=False, recalcTimestamp=False) as after:
        variable_fixture._verify(before, after, item)
    _manifest, cached, _payload = run(temp, "fixed-vf-cached", topology, fixed, xml_map, {logical: stock})
    assert cached["stats"]["outputsBuilt"] == 0
    assert next(item for item in cached["replaced"] if item["path"] == logical)["variable"]


def test_full_output_coverage_uses_all_generated_faces(temp: Path) -> None:
    topology, _stocks, xml_map = device(temp)
    regular, bold = temp / "Regular.ttf", temp / "Bold.ttf"
    fixture.make_cjk_font(regular, family="User Regular")
    fixture.make_cjk_font(bold, family="User Bold")
    with TTFont(str(bold)) as font:
        font["OS/2"].usWeightClass = 700
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap.pop(ord("A"), None)
                table.cmap.pop(ord("0"), None)
        font.save(str(bold))
    _manifest, report, payload = run(temp, "coverage-faces", topology,
                                     {"mode": "single", "files": [str(regular), str(bold)]}, xml_map)
    item = next(item for item in report["replaced"] if item["path"] == ROBOTO)
    coverage = item["sourceCoverage"]
    assert coverage["asciiLetters"] == 51 and coverage["asciiDigits"] == 9, coverage
    assert coverage["faces"] == item["faces"] == 2, "minimum includes requested bold face"
    with TTCollection(str(payload / ROBOTO.lstrip("/"))) as collection:
        maps = [font.getBestCmap() for font in collection.fonts]
        assert any(ord("A") in cmap and ord("0") in cmap for cmap in maps)
        assert any(ord("A") not in cmap and ord("0") not in cmap for cmap in maps)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="luoshu-engine-") as raw:
        temp = Path(raw)
        for test in (test_variable_single, test_static_family, test_composite_variable, test_composite_static,
                     test_composite_fullwidth_latin, test_latin_only,
                     test_collection_and_protected, test_no_ui_target, test_metrics_from_stock_file,
                     test_stock_alias_uses_lower_only, test_partial_system_text,
                     test_partial_protection_and_missing_stock, test_partial_real_component_fonts,
                     test_generic_partial_text_routes, test_generic_partial_trust_and_unsupported,
                     test_generic_partial_subset_text, test_generic_partial_uvs_ownership,
                     test_generic_partial_inherited_metrics,
                     test_policy_revision_reuses_full_output_cache,
                     test_generic_partial_fixed_variable_route,
                     test_full_output_coverage_uses_all_generated_faces):
            sub = temp / test.__name__
            sub.mkdir()
            test(sub)
    print("luoshu_engine_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
