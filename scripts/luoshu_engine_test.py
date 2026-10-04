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
import universal_composite_test as composite
import universal_font_compiler_test as fixture
import universal_font_deployment as payload_format

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
    for family in ET.parse(rendered).getroot().iter("family"):
        for font in family.iter("font"):
            axes = {axis.get("tag"): axis.get("stylevalue") for axis in font.iter("axis")}
            nodes.append(((font.text or "").strip(), font.get("weight"), axes))
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
    roboto = [node for node in nodes if "Roboto" in node[0]]
    assert ("Roboto-Regular.ttf", "400", {}) in roboto, roboto
    assert ("LuoShu-Roboto-Regular-700.ttf", "700", {}) in roboto, roboto
    variant = payload / "system/fonts/LuoShu-Roboto-Regular-700.ttf"
    with TTFont(str(variant)) as font:
        assert font["OS/2"].usWeightClass == 700 and glyph_points(font, "一") == 5
        assert font["hhea"].ascent == TTFont(str(stocks[ROBOTO]))["hhea"].ascent
    with TTFont(str(payload / ROBOTO.lstrip("/"))) as font:
        assert font["OS/2"].usWeightClass == 400 and glyph_points(font, "一") == 4
    assert any(item["kind"] == "xml-font" for item in manifest["files"])


def test_composite(temp: Path) -> None:
    topology, stocks, xml_map = device(temp)
    cjk, latin, digit = temp / "MixCJK.ttf", temp / "MixLatin.ttf", temp / "MixDigit.ttf"
    composite.make_cjk_font(cjk, family="Mix CJK", variable=True, pentagon=True)
    fixture.make_font(latin, family="Mix Latin", variable=True, triangle=True)
    fixture.make_font(digit, family="Mix Digit", advance=560)
    spec = {"mode": "composite", "roles": {
        "cjk": {"files": [str(cjk)], "mode": "auto"},
        "latin": {"files": [str(latin)], "mode": "auto"},
        "digit": {"files": [str(digit)], "mode": "fixed", "axes": {"wght": 500}},
    }}
    manifest, report, payload = run(temp, "mix", topology, spec, xml_map)
    assert {item["path"] for item in report["replaced"]} == {ROBOTO, CJK, MISANS, CLOCK}
    for logical in (ROBOTO, MISANS):
        with TTFont(str(payload / logical.lstrip("/"))) as font:
            assert "fvar" not in font
            assert glyph_points(font, "一") == 5, "Han from the CJK font"
            assert glyph_points(font, "A") == 3, "Latin from the Latin font"
            assert glyph_points(font, "0") == 4, "digits from the digit font (the CJK base draws pentagons)"
            assert font["hhea"].ascent == TTFont(str(stocks[logical]))["hhea"].ascent
    nodes = xml_nodes(payload)
    assert all(not axes for _name, _weight, axes in nodes), nodes
    assert ("LuoShu-MiSansVF-700.ttf", "700", {}) in nodes
    # A second build with the same inputs reuses every cached instance.
    _manifest, again, _payload = run(temp, "mix-again", topology, spec, xml_map)
    assert again["stats"]["instancesBuilt"] == 0 and again["stats"]["outputsBuilt"] == 0, again["stats"]
    assert again["deploymentId"] == report["deploymentId"]


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
        for test in (test_variable_single, test_static_family, test_composite, test_latin_only,
                     test_collection_and_protected, test_no_ui_target):
            sub = temp / test.__name__
            sub.mkdir()
            test(sub)
    print("luoshu_engine_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
