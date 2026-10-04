#!/usr/bin/env python3
"""Engine v3: direct replacement with stock line metrics."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

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


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="luoshu-engine-") as raw:
        temp = Path(raw)
        for test in (test_variable_single, test_static_family, test_composite_variable, test_composite_static,
                     test_latin_only,
                     test_collection_and_protected, test_no_ui_target):
            sub = temp / test.__name__
            sub.mkdir()
            test(sub)
    print("luoshu_engine_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
