#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation

import font_inventory
import font_source_profile
import minimal_xml_router
import universal_font_compiler as compiler
import universal_font_plan

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


def make_collection(path: Path, first: Path, second: Path) -> None:
    a = TTFont(first, lazy=False, recalcTimestamp=False)
    b = TTFont(second, lazy=False, recalcTimestamp=False)
    collection = TTCollection()
    collection.fonts = [a, b]
    try:
        collection.save(path)
    finally:
        a.close()
        b.close()


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


def role_map(role_name: str, action: str = "conditional") -> dict:
    return {
        "role": role_name,
        "confidence": 100,
        "action": action,
        "reasons": ["phase6-test"],
        "evidence": {},
        "comparison": "agree",
    }


def build_plans(
    source: Path,
    slot: dict,
    role_name: str,
    xml_path: Path | None,
) -> tuple[dict, dict]:
    source_profile = font_source_profile.build([source])
    topology = {
        "schema": "device-font-topology-v1",
        "topologyRevision": 2,
        "state": "ready",
        "buildKey": "phase6-test",
        "romKind": "generic",
        "summary": {
            "slotCount": 1,
            "dataFontFileCount": 0,
            "dataFontConfigReferenceCount": 0,
            "unresolvedXmlRefCount": 0,
        },
        "slots": {slot["path"]: slot},
        "families": {},
        "xmlAliases": [],
        "unresolvedXmlRefs": [],
        "runtime": {},
    }
    roles = {
        "schema": "device-font-roles-v1",
        "roleRevision": 1,
        "state": "ready",
        "buildKey": "phase6-test",
        "romKind": "generic",
        "slots": {slot["path"]: role_map(
            role_name,
            "specialized" if role_name in {"clock", "numeric"} else "conditional",
        )},
    }
    font_plan = universal_font_plan.build_plan(topology, roles, source_profile)
    universal_font_plan.validate_plan(font_plan)
    xml_map = {}
    if xml_path is not None:
        source_xml = slot["xmlRefs"][0]["sourceXml"]
        xml_map[source_xml] = xml_path
    route_plan = minimal_xml_router.build_route_plan(font_plan, xml_map, None, False)
    minimal_xml_router.validate_route_plan(route_plan, font_plan)
    return font_plan, route_plan


def artifact_by_kind(manifest: dict, kind: str) -> dict:
    for item in manifest["artifacts"]:
        if kind in item["deploymentKinds"]:
            return item
    raise AssertionError(f"missing artifact kind {kind}: {manifest['artifacts']}")


def assert_ready(manifest: dict) -> None:
    assert manifest["schema"] == "universal-font-artifacts-v1"
    assert manifest["mutatesSystem"] is False
    assert manifest["summary"]["blockedCount"] == 0, manifest
    assert manifest["summary"]["readyCount"] == manifest["summary"]["artifactCount"], manifest
    assert manifest["summary"]["deploymentReady"] is True, manifest


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="luoshu-phase6-") as raw:
        temp = Path(raw)

        # 1) Static TTF, source-as-base, both XML and physical artifacts.
        source = temp / "User-Regular.ttf"
        stock = temp / "Stock-Regular.ttf"
        make_font(source, family="User Font", y_min=-80, y_max=700)
        make_font(stock, family="Stock Font", y_min=-100, y_max=720)
        xml = temp / "fonts.xml"
        xml.write_text(
            '<familyset><family name="sans-serif">'
            '<font weight="400">Stock-Regular.ttf</font>'
            '</family></familyset>',
            encoding="utf-8",
        )
        logical = "/system/fonts/Stock-Regular.ttf"
        slot = slot_from_stock(
            logical, stock, family="sans-serif",
            source_xml="/system/etc/fonts.xml", declared="Stock-Regular.ttf",
        )
        font_plan, route_plan = build_plans(source, slot, "latin", xml)
        manifest = compiler.compile_all(
            font_plan,
            route_plan,
            {logical: stock},
            temp / "out-static",
            False,
        )
        assert_ready(manifest)
        xml_artifact = artifact_by_kind(manifest, "xml-route")
        assert xml_artifact["mode"] == "source-as-base", xml_artifact
        with TTFont(xml_artifact["output"]) as built:
            assert built["head"].unitsPerEm == 1000
            assert built["hhea"].ascent == 900
            assert built["hhea"].descent == -220

        # 2) Specialized clock: target digit advances must remain byte-exact.
        clock_source = temp / "User-Clock.ttf"
        clock_stock = temp / "AndroidClock.ttf"
        make_font(clock_source, family="User Clock", advance=620, y_min=-70, y_max=650)
        make_font(clock_stock, family="Android Clock", advance=760, y_min=-90, y_max=690)
        clock_xml = temp / "clock.xml"
        clock_xml.write_text(
            '<familyset><family name="clock-ui">'
            '<font weight="400">AndroidClock.ttf</font>'
            '</family></familyset>',
            encoding="utf-8",
        )
        clock_logical = "/system/fonts/AndroidClock.ttf"
        clock_slot = slot_from_stock(
            clock_logical, clock_stock, family="clock-ui",
            source_xml="/system/etc/clock.xml", declared="AndroidClock.ttf",
        )
        clock_plan, clock_route = build_plans(clock_source, clock_slot, "clock", clock_xml)
        clock_manifest = compiler.compile_all(
            clock_plan,
            clock_route,
            {clock_logical: clock_stock},
            temp / "out-clock",
            False,
        )
        assert_ready(clock_manifest)
        clock_artifact = artifact_by_kind(clock_manifest, "xml-route")
        assert clock_artifact["mode"] == "stock-shell"
        with TTFont(clock_stock) as before, TTFont(clock_artifact["output"]) as after:
            before_cmap = before.getBestCmap()
            after_cmap = after.getBestCmap()
            for cp in map(ord, "0123456789"):
                assert after["hmtx"].metrics[after_cmap[cp]][0] == before["hmtx"].metrics[before_cmap[cp]][0]

        # 3) CFF/OTF static general UI path must compile without pretending it is glyf.
        cff_source = temp / "UserCFF.otf"
        cff_stock = temp / "StockCFF.otf"
        make_font(cff_source, family="User CFF", cff=True, y_min=-80, y_max=710)
        make_font(cff_stock, family="Stock CFF", cff=True, y_min=-100, y_max=730)
        cff_xml = temp / "cff.xml"
        cff_xml.write_text(
            '<familyset><family name="sans-serif">'
            '<font weight="400">StockCFF.otf</font>'
            '</family></familyset>',
            encoding="utf-8",
        )
        cff_logical = "/product/fonts/StockCFF.otf"
        cff_slot = slot_from_stock(
            cff_logical, cff_stock, family="sans-serif",
            source_xml="/product/etc/fonts.xml", declared="StockCFF.otf",
        )
        cff_plan, cff_route = build_plans(cff_source, cff_slot, "latin", cff_xml)
        cff_manifest = compiler.compile_all(
            cff_plan, cff_route, {cff_logical: cff_stock}, temp / "out-cff", False
        )
        assert_ready(cff_manifest)
        cff_artifact = artifact_by_kind(cff_manifest, "xml-route")
        assert cff_artifact["mode"] == "source-as-base"
        with TTFont(cff_artifact["output"]) as built:
            assert "CFF " in built
            assert "glyf" not in built

        # 4) TTC face contract: face 0 survives while face 1 is the compiled clock face.
        face0 = temp / "Face0.ttf"
        face1 = temp / "Face1.ttf"
        collection = temp / "ClockCollection.ttc"
        make_font(face0, family="Untouched Face", advance=500)
        make_font(face1, family="Clock Face", advance=760, y_min=-100, y_max=700)
        make_collection(collection, face0, face1)
        ttc_xml = temp / "ttc.xml"
        ttc_xml.write_text(
            '<familyset><family name="clock-ui">'
            '<font weight="400" index="1">ClockCollection.ttc</font>'
            '</family></familyset>',
            encoding="utf-8",
        )
        ttc_logical = "/system/fonts/ClockCollection.ttc"
        ttc_slot = slot_from_stock(
            ttc_logical, collection, family="clock-ui",
            source_xml="/system/etc/ttc.xml", declared="ClockCollection.ttc",
            face_index=1,
        )
        ttc_plan, ttc_route = build_plans(clock_source, ttc_slot, "clock", ttc_xml)
        ttc_manifest = compiler.compile_all(
            ttc_plan, ttc_route, {ttc_logical: collection}, temp / "out-ttc", False
        )
        assert_ready(ttc_manifest)
        ttc_artifact = artifact_by_kind(ttc_manifest, "xml-route")
        assert ttc_artifact["mode"] == "stock-shell"
        compiled_collection = TTCollection(ttc_artifact["output"], lazy=False)
        stock_collection = TTCollection(collection, lazy=False)
        try:
            assert len(compiled_collection.fonts) == 2
            assert (
                compiled_collection.fonts[0].getTableData("glyf")
                == stock_collection.fonts[0].getTableData("glyf")
            )
            before = stock_collection.fonts[1]
            after = compiled_collection.fonts[1]
            before_cmap = before.getBestCmap()
            after_cmap = after.getBestCmap()
            for cp in map(ord, "0123456789"):
                assert after["hmtx"].metrics[after_cmap[cp]][0] == before["hmtx"].metrics[before_cmap[cp]][0]
        finally:
            compiled_collection.close()
            stock_collection.close()

        # 5) Physical-only variable UI keeps fvar/gvar when axis ranges and geometry match.
        variable_source = temp / "UserVF.ttf"
        variable_stock = temp / "StockVF.ttf"
        make_font(variable_source, family="User VF", variable=True, y_min=-100, y_max=720)
        make_font(variable_stock, family="Stock VF", variable=True, y_min=-100, y_max=720)
        vf_logical = "/system/fonts/StockVF.ttf"
        vf_slot = slot_from_stock(
            vf_logical, variable_stock, family="sans-serif",
            source_xml=None, declared="StockVF.ttf",
        )
        vf_plan, vf_route = build_plans(variable_source, vf_slot, "latin", None)
        vf_manifest = compiler.compile_all(
            vf_plan, vf_route, {vf_logical: variable_stock}, temp / "out-vf", False
        )
        assert_ready(vf_manifest)
        vf_artifact = artifact_by_kind(vf_manifest, "physical-slot")
        assert vf_artifact["mode"] == "source-variable-preserve", vf_artifact
        with TTFont(vf_artifact["output"]) as built:
            assert "fvar" in built
            assert "gvar" in built
            assert built["hhea"].ascent == 900
            assert built["hhea"].descent == -220

        # 6) A narrower variable source axis range must block instead of staticizing.
        narrow_source = temp / "NarrowVF.ttf"
        make_font(
            narrow_source, family="Narrow VF", variable=True,
            axis_min=300, axis_max=700, y_min=-100, y_max=720,
        )
        narrow_plan, narrow_route = build_plans(narrow_source, vf_slot, "latin", None)
        narrow_manifest = compiler.compile_all(
            narrow_plan, narrow_route, {vf_logical: variable_stock}, temp / "out-narrow", False
        )
        assert narrow_manifest["summary"]["blockedCount"] == 1
        assert narrow_manifest["summary"]["deploymentReady"] is False
        blocked = narrow_manifest["artifacts"][0]
        assert blocked["status"] == "blocked"
        assert "不能覆盖目标" in blocked["reason"], blocked

        # 7) Variable stock with real gvar deltas routed through an XML <axis>
        #    child (Android 12+ Roboto) uses stock-shell. Replacing outlines with
        #    a different point count must not corrupt gvar decoding.
        tri_source = temp / "UserTriangle.ttf"
        gvar_stock = temp / "StockGvar.ttf"
        make_font(tri_source, family="User Triangle", triangle=True, y_min=-100, y_max=720)
        make_font(gvar_stock, family="Stock Gvar", variable=True, gvar_deltas=True,
                  y_min=-100, y_max=720)
        gvar_xml = temp / "gvar.xml"
        gvar_xml.write_text(
            '<familyset><family name="sans-serif">'
            '<font weight="400" style="normal">StockGvar.ttf'
            '<axis tag="wght" stylevalue="400"/></font>'
            '</family></familyset>',
            encoding="utf-8",
        )
        gvar_logical = "/system/fonts/StockGvar.ttf"
        gvar_slot = slot_from_stock(
            gvar_logical, gvar_stock, family="sans-serif",
            source_xml="/system/etc/gvar.xml", declared="StockGvar.ttf",
        )
        gvar_plan, gvar_route = build_plans(tri_source, gvar_slot, "latin", gvar_xml)
        gvar_manifest = compiler.compile_all(
            gvar_plan, gvar_route, {gvar_logical: gvar_stock}, temp / "out-gvar", False
        )
        assert_ready(gvar_manifest)
        gvar_artifact = artifact_by_kind(gvar_manifest, "xml-route")
        assert gvar_artifact["mode"] == "stock-shell", gvar_artifact
        with TTFont(gvar_artifact["output"]) as built:
            built["gvar"].ensureDecompiled()
            replaced = built.getBestCmap()[ord("A")]
            assert built["glyf"][replaced].numberOfContours == 1
            assert len(built["glyf"][replaced].coordinates) == 3
            assert not built["gvar"].variations.get(replaced)

        # 9) Several XML weights of one variable stock file share a single
        #    variable artifact; nodes the source axes cannot reach (wght=50) or
        #    without <axis> children keep per-node compilation.
        group_source = temp / "UserGroupVF.ttf"
        group_stock = temp / "StockGroupVF.ttf"
        make_font(group_source, family="User Group VF", variable=True, y_min=-100, y_max=720)
        make_font(group_stock, family="Stock Group VF", variable=True, axis_min=50,
                  y_min=-100, y_max=720)
        group_xml = temp / "group.xml"
        group_xml.write_text(
            '<familyset><family name="sans-serif">'
            + "".join(
                f'<font weight="{w}" style="normal">StockGroupVF.ttf'
                f'<axis tag="wght" stylevalue="{w}"/></font>'
                for w in (50, 300, 400, 700)
            )
            + '<font weight="900" style="normal">StockGroupVF.ttf</font>'
            + '</family></familyset>',
            encoding="utf-8",
        )
        group_logical = "/system/fonts/StockGroupVF.ttf"
        group_slot = slot_from_stock(
            group_logical, group_stock, family="sans-serif",
            source_xml="/system/etc/group.xml", declared="StockGroupVF.ttf",
        )
        group_slot["xmlRefs"] = [
            dict(group_slot["xmlRefs"][0], weight=w) for w in (50, 300, 400, 700, 900)
        ]
        group_plan, group_route = build_plans(group_source, group_slot, "latin", group_xml)
        operations = group_route["documents"]["/system/etc/group.xml"]["operations"]
        by_weight = {op["node"]["weight"]: op["artifact"] for op in operations}
        assert len(by_weight) == 5, by_weight
        shared = {by_weight[w]["artifactId"] for w in (300, 400, 700)}
        assert len(shared) == 1, by_weight
        assert by_weight[400]["variableGroup"] is True
        assert by_weight[400]["requiredWeight"] == 400
        assert [m["weight"] for m in by_weight[400]["variableMembers"]] == [300, 400, 700]
        assert not by_weight[50].get("variableGroup"), by_weight[50]
        assert not by_weight[900].get("variableGroup"), by_weight[900]
        assert len({a["artifactId"] for a in by_weight.values()}) == 3

        group_manifest = compiler.compile_all(
            group_plan, group_route, {group_logical: group_stock}, temp / "out-group", False
        )
        modes = {item["artifactId"]: item for item in group_manifest["artifacts"]}
        grouped = modes[by_weight[400]["artifactId"]]
        assert grouped["status"] == "ready", grouped
        assert grouped["mode"] == "source-variable-preserve", grouped
        assert len(grouped["routeNodes"]) == 3, grouped
        with TTFont(grouped["output"]) as built:
            assert "fvar" in built and "gvar" in built
            assert built["hhea"].ascent == 900
        # The 50 node is outside the source wght range, so it compiles alone and
        # its own contract decides; it must not drag the shared artifact down.
        assert modes[by_weight[50]["artifactId"]].get("mode") != "source-variable-preserve"

        # Deployment renders all grouped nodes to one shared file; the 50 node,
        # if it compiled, keeps its own file.
        # The 50 node is the only blocked one: the source cannot reach it.
        assert group_manifest["summary"]["blockedCount"] == 1, group_manifest
        assert "wght=50" in modes[by_weight[50]["artifactId"]]["reason"]

        # Deployment renders all grouped nodes to one shared file while the
        # axis-less 900 node keeps its own file.
        import universal_font_deployment as deployment
        deploy_xml = temp / "group-deploy.xml"
        deploy_xml.write_text(group_xml.read_text(encoding="utf-8").replace(
            '<font weight="50" style="normal">StockGroupVF.ttf<axis tag="wght" stylevalue="50"/></font>', ""
        ), encoding="utf-8")
        deploy_slot = json.loads(json.dumps(group_slot))
        deploy_slot["xmlRefs"] = [ref for ref in deploy_slot["xmlRefs"] if ref["weight"] != 50]
        deploy_plan, deploy_route = build_plans(group_source, deploy_slot, "latin", deploy_xml)
        deploy_manifest = compiler.compile_all(
            deploy_plan, deploy_route, {group_logical: group_stock}, temp / "out-group-deploy", False
        )
        assert_ready(deploy_manifest)
        assert deploy_manifest["summary"]["artifactCount"] == 2, deploy_manifest["summary"]
        payload = temp / "group-payload"
        deployed = deployment.build_deployment(deploy_plan, deploy_route, deploy_manifest, payload)
        deployment.validate_deployment(deployed, deploy_plan, deploy_route, deploy_manifest, payload)
        rendered = ET.parse(payload / "system/etc/group.xml")
        refs = {
            int(font.get("weight")): (font.text or "").strip()
            for font in rendered.iter("font")
        }
        assert len({refs[w] for w in (300, 400, 700)}) == 1, refs
        assert refs[900] != refs[400], refs
        for font in rendered.iter("font"):
            if int(font.get("weight")) in (300, 400, 700):
                assert font.find("axis").get("stylevalue") == font.get("weight")
        assert len(list((payload / "system/fonts").glob("LuoShu-UF-*"))) == 2

        # 10) A second compile into the same directory reuses ready artifacts
        #     byte-for-byte, yields the same manifestId and prunes stale files.
        cache_dir = temp / "out-cache"
        first = compiler.compile_all(font_plan, route_plan, {logical: stock}, cache_dir, False)
        assert first["cache"] == {"reused": 0, "compiled": first["summary"]["artifactCount"]}
        (cache_dir / "LuoShu-UF-stale.ttf").write_bytes(b"stale")
        second = compiler.compile_all(font_plan, route_plan, {logical: stock}, cache_dir, False)
        assert second["cache"]["reused"] == first["summary"]["artifactCount"], second["cache"]
        assert second["cache"]["compiled"] == 0
        assert second["manifestId"] == first["manifestId"]
        compiler.validate_manifest(second, font_plan, route_plan)
        assert not (cache_dir / "LuoShu-UF-stale.ttf").exists()
        # A damaged artifact or a changed stock file is recompiled, not reused.
        victim = Path(second["artifacts"][0]["output"])
        victim.write_bytes(victim.read_bytes() + b"x")
        third = compiler.compile_all(font_plan, route_plan, {logical: stock}, cache_dir, False)
        assert third["cache"]["compiled"] == 1, third["cache"]
        compiler.validate_manifest(third, font_plan, route_plan)
        changed_stock = temp / "Stock-Regular-ota.ttf"
        changed_stock.write_bytes(stock.read_bytes() + b"\0\0\0\0")
        fourth = compiler.compile_all(
            font_plan, route_plan, {logical: changed_stock}, cache_dir, False
        )
        assert fourth["cache"]["reused"] == 0, fourth["cache"]

        # 8) Past the cutover deadline the compiler stops before starting a unit
        #    so the legacy fallback keeps the rest of the switch timeout.
        os.environ["LUOSHU_UNIVERSAL_DEADLINE"] = str(int(time.time()) - 1)
        try:
            compiler.compile_all(
                font_plan, route_plan, {logical: stock}, temp / "out-late", False
            )
        except compiler.CompilerError as error:
            assert "时间预算" in str(error) and "0/" in str(error), error
        else:
            raise AssertionError("compile_all ignored an expired deadline")
        finally:
            os.environ.pop("LUOSHU_UNIVERSAL_DEADLINE", None)
        assert not any((temp / "out-late").glob("*.ttf"))

        # Manifest validation checks actual artifact hashes.
        manifest_path = temp / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        compiler.validate_manifest(manifest, font_plan, route_plan)

        tampered_manifest = json.loads(json.dumps(manifest))
        tampered_manifest["artifacts"][0]["bytes"] += 1
        try:
            compiler.validate_manifest(tampered_manifest, font_plan, route_plan)
        except compiler.CompilerError as error:
            assert "manifestId" in str(error)
        else:
            raise AssertionError("tampered compiler manifest unexpectedly validated")

        bad_map = json.loads(json.dumps(manifest))
        first_id = next(iter(bad_map["artifactMap"]))
        bad_map["artifactMap"][first_id] = "wrong.ttf"
        try:
            compiler.validate_manifest(bad_map, font_plan, route_plan)
        except compiler.CompilerError as error:
            assert "artifactMap" in str(error)
        else:
            raise AssertionError("tampered artifactMap unexpectedly validated")

    print("universal_font_compiler_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
