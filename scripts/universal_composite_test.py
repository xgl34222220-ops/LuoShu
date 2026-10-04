#!/usr/bin/env python3
"""Role-assigned composite (mix) on the Universal engine: profile, plan, compile."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))
sys.path.insert(0, str(ROOT / "scripts"))

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

import device_font_template as template_engine
import font_coverage
import font_role_shadow
import font_source_profile
import minimal_xml_router
import universal_font_plan
import universal_font_compiler_test as fixture

ASCII_POINTS = tuple(range(0x20, 0x7F))


def make_cjk_font(path: Path, *, family: str, variable: bool = False, y_max: int = 820) -> None:
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


def expect_error(fn, text: str) -> None:
    try:
        fn()
    except font_source_profile.ProfileError as error:
        assert text in str(error), error
    else:
        raise AssertionError(f"expected ProfileError containing {text!r}")


def test_profile(temp: Path) -> dict[str, Path]:
    cjk = temp / "UserCJK.ttf"
    latin = temp / "UserLatin.ttf"
    digit = temp / "UserDigit.ttf"
    make_cjk_font(cjk, family="User CJK", variable=True)
    fixture.make_font(latin, family="User Latin", variable=True)
    fixture.make_font(digit, family="User Digit", advance=560)

    roles = {"cjk": [cjk], "latin": [latin], "digit": [digit]}
    modes = {"cjk": "auto", "latin": "auto", "digit": "fixed"}
    axes = {"cjk": "wght=400", "latin": "wght=400", "digit": "wght=500"}
    profile = font_source_profile.build([], roles, modes, axes)
    font_source_profile.validate(profile)

    by_file = {Path(f["sourcePath"]).name: f for f in profile["files"]}
    assert by_file["UserCJK.ttf"]["faces"][0]["assignedRoles"] == ["cjk"]
    assert by_file["UserLatin.ttf"]["faces"][0]["assignedRoles"] == ["latin"]
    assert by_file["UserDigit.ttf"]["faces"][0]["assignedRoles"] == ["digit"]
    spec = profile["composite"]["roles"]
    assert spec["digit"] == {
        "mode": "fixed", "axes": {"wght": 500.0},
        "faceUids": [by_file["UserDigit.ttf"]["faces"][0]["uid"]],
    }, spec["digit"]

    # One file serving two roles is profiled once and carries both roles.
    shared = font_source_profile.build(
        [], {"cjk": [cjk], "latin": [latin], "digit": [latin]}, modes, axes
    )
    assert len(shared["files"]) == 2
    latin_face = next(f for f in shared["files"] if f["sourcePath"].endswith("UserLatin.ttf"))["faces"][0]
    assert latin_face["assignedRoles"] == ["digit", "latin"]

    # Same files, different assignment / mode / axes -> different identity.
    swapped = font_source_profile.build([], {"cjk": [cjk], "latin": [digit], "digit": [latin]}, modes, axes)
    remoded = font_source_profile.build([], roles, dict(modes, digit="auto"), axes)
    reaxed = font_source_profile.build([], roles, modes, dict(axes, digit="wght=600"))
    plain = font_source_profile.build([cjk, latin, digit])
    ids = {p["profileId"] for p in (profile, swapped, remoded, reaxed, plain)}
    assert len(ids) == 5, ids
    assert "composite" not in plain

    expect_error(lambda: font_source_profile.build([], {"cjk": [cjk], "latin": [latin]}, modes, axes), "数字")
    expect_error(lambda: font_source_profile.build([], roles, dict(modes, cjk="bogus"), axes), "组合模式无效")
    expect_error(lambda: font_source_profile.build([], roles, modes, dict(axes, cjk="weight=4")), "组合轴设置无效")
    return {"cjk": cjk, "latin": latin, "digit": digit}


def build_device(temp: Path) -> tuple[dict, dict, dict[str, Path], dict[str, Path]]:
    """Stock slots: Latin UI, CJK fallback, OEM broad UI (Han+Latin), clock."""
    stocks = {
        "/system/fonts/Roboto-Regular.ttf": temp / "Roboto-Regular.ttf",
        "/system/fonts/NotoSansCJK-Regular.ttf": temp / "NotoSansCJK-Regular.ttf",
        "/system/fonts/MiSansVF.ttf": temp / "MiSansVF.ttf",
        "/system/fonts/AndroidClock.ttf": temp / "AndroidClock.ttf",
    }
    fixture.make_font(stocks["/system/fonts/Roboto-Regular.ttf"], family="Stock Roboto", variable=True)
    make_cjk_font(stocks["/system/fonts/NotoSansCJK-Regular.ttf"], family="Stock CJK", variable=True)
    make_cjk_font(stocks["/system/fonts/MiSansVF.ttf"], family="Stock MiSans", variable=True)
    fixture.make_font(stocks["/system/fonts/AndroidClock.ttf"], family="Stock Clock", advance=760)
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
        slot = fixture.slot_from_stock(logical, stock, family=family or "zh", source_xml="/system/etc/fonts.xml",
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


def uid_of(profile: dict, name: str) -> str:
    return next(f for f in profile["files"] if f["sourcePath"].endswith(name))["faces"][0]["uid"]


def test_plan(temp: Path, fonts: dict[str, Path]) -> None:
    topology, roles, stocks, xml_map = build_device(temp)
    role_of = {path: item["role"] for path, item in roles["slots"].items()}
    assert role_of == {
        "/system/fonts/Roboto-Regular.ttf": "ui-sans",
        "/system/fonts/NotoSansCJK-Regular.ttf": "cjk",
        "/system/fonts/MiSansVF.ttf": "ui-sans",
        "/system/fonts/AndroidClock.ttf": "clock",
    }, role_of

    modes = {"cjk": "auto", "latin": "auto", "digit": "fixed"}
    axes = {"cjk": "wght=400", "latin": "wght=400", "digit": "wght=500"}
    profile = font_source_profile.build(
        [], {"cjk": [fonts["cjk"]], "latin": [fonts["latin"]], "digit": [fonts["digit"]]}, modes, axes
    )
    plan = universal_font_plan.build_plan(topology, roles, profile)
    universal_font_plan.validate_plan(plan)
    targets = plan["targets"]
    cjk_uid, latin_uid, digit_uid = (uid_of(profile, n) for n in ("UserCJK.ttf", "UserLatin.ttf", "UserDigit.ttf"))

    def sources(path: str) -> dict[str, str]:
        return {role: ref["uid"] for role, ref in targets[path]["compositeSources"].items()}

    # The CJK base also has full ASCII; Latin/digit slots must still use B/C.
    assert sources("/system/fonts/Roboto-Regular.ttf") == {"latin": latin_uid, "digit": digit_uid}
    assert targets["/system/fonts/Roboto-Regular.ttf"]["source"]["uid"] == latin_uid
    assert "composite-multi-source" in targets["/system/fonts/Roboto-Regular.ttf"]["requirements"]
    assert sources("/system/fonts/NotoSansCJK-Regular.ttf") == {"cjk": cjk_uid}
    assert "composite-multi-source" not in targets["/system/fonts/NotoSansCJK-Regular.ttf"]["requirements"]
    assert sources("/system/fonts/MiSansVF.ttf") == {"cjk": cjk_uid, "latin": latin_uid, "digit": digit_uid}
    assert targets["/system/fonts/MiSansVF.ttf"]["source"]["uid"] == cjk_uid
    assert sources("/system/fonts/AndroidClock.ttf") == {"digit": digit_uid}
    digit_ref = targets["/system/fonts/AndroidClock.ttf"]["compositeSources"]["digit"]
    assert digit_ref["compositeMode"] == "fixed" and digit_ref["compositeAxes"] == {"wght": 500.0}
    assert targets["/system/fonts/AndroidClock.ttf"]["selection"]["targetWeight"] == 500

    # Router: the CJK fallback slot shares one variable artifact (single auto
    # source); Roboto and MiSans need several sources and stay per node.
    route = minimal_xml_router.build_route_plan(plan, xml_map, None, False)
    ops = route["documents"]["/system/etc/fonts.xml"]["operations"]
    per_target: dict[str, set[str]] = {}
    for op in ops:
        per_target.setdefault(op["targetPath"], set()).add(op["artifact"]["artifactId"])
    assert len(per_target["/system/fonts/NotoSansCJK-Regular.ttf"]) == 1, per_target
    assert len(per_target["/system/fonts/Roboto-Regular.ttf"]) == 2, per_target
    assert len(per_target["/system/fonts/MiSansVF.ttf"]) == 2, per_target

    # Latin and digits from the same auto face: Roboto becomes single-source
    # again and may share a variable artifact across its weights.
    same = font_source_profile.build(
        [], {"cjk": [fonts["cjk"]], "latin": [fonts["latin"]], "digit": [fonts["latin"]]},
        {"cjk": "auto", "latin": "auto", "digit": "auto"}, {"cjk": "", "latin": "", "digit": ""},
    )
    same_plan = universal_font_plan.build_plan(topology, roles, same)
    roboto = same_plan["targets"]["/system/fonts/Roboto-Regular.ttf"]
    assert "composite-multi-source" not in roboto["requirements"], roboto["requirements"]
    same_route = minimal_xml_router.build_route_plan(same_plan, xml_map, None, False)
    roboto_ids = {op["artifact"]["artifactId"] for op in same_route["documents"]["/system/etc/fonts.xml"]["operations"]
                  if op["targetPath"] == "/system/fonts/Roboto-Regular.ttf"}
    assert len(roboto_ids) == 1, roboto_ids

    # A different digit font changes Roboto's artifacts even though its primary
    # (Latin) source is identical.
    swapped = font_source_profile.build(
        [], {"cjk": [fonts["cjk"]], "latin": [fonts["latin"]], "digit": [fonts["cjk"]]}, modes, axes
    )
    swapped_route = minimal_xml_router.build_route_plan(
        universal_font_plan.build_plan(topology, roles, swapped), xml_map, None, False
    )
    swapped_ids = {op["artifact"]["artifactId"] for op in swapped_route["documents"]["/system/etc/fonts.xml"]["operations"]
                   if op["targetPath"] == "/system/fonts/Roboto-Regular.ttf"}
    assert swapped_ids.isdisjoint(per_target["/system/fonts/Roboto-Regular.ttf"])


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="luoshu-composite-") as raw:
        temp = Path(raw)
        fonts = test_profile(temp)
        test_plan(temp, fonts)
    print("universal_composite_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
