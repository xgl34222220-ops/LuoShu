#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "common"
sys.path.insert(0, str(COMMON))

import minimal_xml_router as router
import universal_font_plan


def target_slot(
    path: str,
    *,
    family: str,
    source_xml: str | None,
    declared: str,
    weight: int = 400,
    role_has_han: bool = False,
    postscript: str = "",
    index: int = 0,
    axes: bool = False,
) -> dict:
    refs = []
    if source_xml is not None:
        refs.append({
            "sourceXml": source_xml,
            "sourcePartition": Path(source_xml).parts[1] if source_xml.startswith("/") else "",
            "family": family,
            "familyNormalized": family.lower().replace("_", "-"),
            "familyAttributes": {},
            "declared": declared,
            "postScriptName": postscript,
            "weight": weight,
            "style": "normal",
            "index": index,
            "axes": "",
            "resolvedPath": path,
        })
    return {
        "slotName": Path(path).name,
        "path": path,
        "partition": Path(path).parts[1],
        "source": "synthetic",
        "families": [family] if family else [],
        "legacyReplaceable": True,
        "runtimeEvidence": {"fontManager": True, "mount": False},
        "metrics": {
            "upem": 1000,
            "weightClass": weight,
            "isFixedPitch": False,
            "variationAxes": (
                [{"tag": "wght", "minimum": 100.0, "default": 400.0, "maximum": 900.0}]
                if axes else []
            ),
            "coverage": {
                "hasHan": role_has_han,
                "hanCount": 7000 if role_has_han else 0,
                "hasLatin": True,
                "latinCount": 52,
                "hasDigits": True,
                "digitCount": 10,
                "unicodeCount": 8000 if role_has_han else 220,
                "cjkPunctuation": [],
            },
            "ascent": 900,
            "descent": -220,
            "head": {
                "xMin": -50,
                "yMin": -220,
                "xMax": 1050,
                "yMax": 980,
                "flags": 0,
                "lowestRecPPEM": 8,
            },
            "hhea": {"ascent": 900, "descent": -220, "lineGap": 0},
            "os2": {
                "fsSelection": 0,
                "typoAscender": 850,
                "typoDescender": -200,
                "typoLineGap": 0,
                "winAscent": 980,
                "winDescent": 220,
            },
        },
        "xmlRefs": refs,
    }


def role(name: str, action: str, confidence: int = 100) -> dict:
    return {
        "role": name,
        "confidence": confidence,
        "action": action,
        "reasons": ["phase5-test"],
        "evidence": {},
        "comparison": "agree",
    }


def source_face() -> dict:
    return {
        "uid": "sha256:source-file:face:0",
        "fileUid": "sha256:source-file",
        "fileName": "Demo-VF.ttf",
        "faceIndex": 0,
        "names": {
            "family": "Demo",
            "familyNormalized": "demo",
            "subfamily": "Regular",
            "fullName": "Demo",
            "postScriptName": "Demo-Regular",
        },
        "format": "TTF/glyf",
        "style": {
            "weight": 400,
            "widthClass": 5,
            "italic": False,
            "fixedPitch": False,
        },
        "metrics": {
            "unitsPerEm": 1000,
            "head": {"xMin": -40, "yMin": -210, "xMax": 1030, "yMax": 970},
            "hhea": {"ascent": 890, "descent": -210, "lineGap": 0, "advanceWidthMax": 1200},
            "os2": {
                "weightClass": 400,
                "widthClass": 5,
                "fsSelection": 0,
                "typoAscender": 840,
                "typoDescender": -190,
                "typoLineGap": 0,
                "winAscent": 970,
                "winDescent": 210,
                "capHeight": 700,
                "xHeight": 500,
            },
        },
        "variation": {
            "variable": True,
            "axes": [
                {"tag": "wght", "name": "Weight", "min": 100.0, "default": 400.0, "max": 900.0}
            ],
            "namedInstances": [],
        },
        "tables": {
            "all": ["cmap", "head", "hhea", "maxp", "name", "OS/2", "fvar", "GSUB", "GPOS"],
            "outline": "glyf",
            "color": [],
            "variable": ["fvar"],
            "shaping": ["GSUB", "GPOS"],
        },
        "coverage": {
            "codepoints": 10000,
            "coreHan": 7000,
            "minimumCoreHan": 6000,
            "scriptCounts": {"han": 7000, "latin": 120},
            "emojiCodepointsApprox": 0,
            "probes": {
                "cjk": {"hits": 160, "total": 160, "ratio": 1.0},
                "latin": {"hits": 52, "total": 52, "ratio": 1.0},
                "digits": {"hits": 10, "total": 10, "ratio": 1.0},
                "punctuation": {"hits": 16, "total": 16, "ratio": 1.0},
            },
        },
        "capabilities": {
            "text": True,
            "latinUi": True,
            "cjkUi": True,
            "numeric": True,
            "punctuationUi": True,
            "monospaceCandidate": False,
            "variable": True,
            "variableWeight": True,
            "variableWidth": False,
            "variableOpticalSize": False,
            "colorFont": False,
            "globalUiCandidate": True,
        },
        "warnings": [],
    }


def build_font_plan(*, missing_bold_ref: bool = False, duplicate_xml_ref: bool = False) -> dict:
    slots = {
        "/system/fonts/Roboto-Regular.ttf": target_slot(
            "/system/fonts/Roboto-Regular.ttf",
            family="sans-serif",
            source_xml="/system/etc/fonts.xml",
            declared="Roboto-Regular.ttf",
            weight=400,
            postscript="Roboto-Regular",
            index=0,
            axes=True,
        ),
        "/system/fonts/Roboto-Bold.ttf": target_slot(
            "/system/fonts/Roboto-Bold.ttf",
            family="sans-serif",
            source_xml="/system/etc/fonts.xml",
            declared=("Missing-Bold.ttf" if missing_bold_ref else "Roboto-Bold.ttf"),
            weight=700,
        ),
        "/product/fonts/GoogleSans-Medium.ttf": target_slot(
            "/product/fonts/GoogleSans-Medium.ttf",
            family="google-sans",
            source_xml="/product/etc/fonts_customization.xml",
            declared="GoogleSans-Medium.ttf",
            weight=500,
        ),
        "/system/fonts/NotoSerif-Regular.ttf": target_slot(
            "/system/fonts/NotoSerif-Regular.ttf",
            family="serif",
            source_xml="/system/etc/fonts.xml",
            declared="NotoSerif-Regular.ttf",
            weight=400,
        ),
        "/vendor/fonts/DirectLatin.ttf": target_slot(
            "/vendor/fonts/DirectLatin.ttf",
            family="vendor-ui",
            source_xml=None,
            declared="DirectLatin.ttf",
            weight=400,
        ),
        "/data/fonts/files/RuntimeLatin.ttf": target_slot(
            "/data/fonts/files/RuntimeLatin.ttf",
            family="runtime-sans",
            source_xml="/data/fonts/config/config.xml",
            declared="RuntimeLatin.ttf",
            weight=400,
        ),
    }
    if duplicate_xml_ref:
        duplicate = copy.deepcopy(slots["/system/fonts/Roboto-Regular.ttf"]["xmlRefs"][0])
        duplicate["captureEvidence"] = "duplicate-semantic-ref"
        slots["/system/fonts/Roboto-Regular.ttf"]["xmlRefs"].append(duplicate)

    topology = {
        "schema": "device-font-topology-v1",
        "topologyRevision": 3,
        "state": "ready",
        "buildKey": "phase5-test-build",
        "romKind": "generic",
        "summary": {
            "slotCount": len(slots),
            "dataFontFileCount": 1,
            "dataFontConfigReferenceCount": 1,
            "unresolvedXmlRefCount": 0,
        },
        "slots": slots,
        "families": {},
        "xmlAliases": [],
        "unresolvedXmlRefs": [],
        "runtime": {
            "dataFontFiles": [{"path": "/data/fonts/files/RuntimeLatin.ttf"}],
            "dataFontsConfig": {"references": ["RuntimeLatin.ttf"]},
        },
    }
    roles = {
        "schema": "device-font-roles-v1",
        "roleRevision": 3,
        "state": "ready",
        "buildKey": "phase5-test-build",
        "romKind": "generic",
        "slots": {
            "/system/fonts/Roboto-Regular.ttf": role("latin", "conditional"),
            "/system/fonts/Roboto-Bold.ttf": role("latin", "conditional"),
            "/product/fonts/GoogleSans-Medium.ttf": role("latin", "conditional"),
            "/system/fonts/NotoSerif-Regular.ttf": role("serif", "preserve"),
            "/vendor/fonts/DirectLatin.ttf": role("latin", "conditional"),
            "/data/fonts/files/RuntimeLatin.ttf": role("latin", "conditional"),
        },
    }
    profile = {
        "schema": "source-font-profile-v1",
        "profileRevision": 1,
        "state": "ready",
        "generatedAt": 1,
        "profileId": "sha256:phase5-source",
        "summary": {
            "fileCount": 1,
            "faceCount": 1,
            "familyCount": 1,
            "containers": ["TTF"],
            "weights": [400],
            "axisTags": ["wght"],
            "requiresSfntConversion": False,
            "capabilities": {
                "latinUi": True,
                "cjkUi": True,
                "numeric": True,
                "monospaceCandidate": False,
                "variable": True,
                "variableWeight": True,
                "colorFont": False,
                "globalUiCandidate": True,
            },
        },
        "families": {},
        "files": [
            {
                "fileUid": "sha256:source-file",
                "sha256": "source-file",
                "sourcePath": "/sdcard/LuoShu/fonts/Demo-VF.ttf",
                "fileName": "Demo-VF.ttf",
                "bytes": 100000,
                "container": "TTF",
                "collection": False,
                "requiresSfntConversion": False,
                "faceCount": 1,
                "faces": [source_face()],
            }
        ],
    }
    return universal_font_plan.build_plan(topology, roles, profile)


def font_texts(path: Path) -> list[tuple[str, dict[str, str], str, list[dict[str, str]]]]:
    tree = ET.parse(path)
    result = []
    for family in tree.getroot().iter("family"):
        family_name = family.attrib.get("name", "")
        for font in family.findall("font"):
            axes = [dict(axis.attrib) for axis in font.findall("axis")]
            result.append((family_name, dict(font.attrib), (font.text or "").strip(), axes))
    return result


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="luoshu-phase5-") as raw:
        temp = Path(raw)
        system_xml = temp / "stock-system-fonts.xml"
        product_xml = temp / "stock-product-custom.xml"

        system_xml.write_text(
            """<?xml version="1.0" encoding="utf-8"?>
<familyset version="21">
  <family name="sans-serif">
    <font weight="400" style="normal" index="0" postScriptName="Roboto-Regular">Roboto-Regular.ttf
      <axis tag="wght" stylevalue="400" />
    </font>
    <font weight="700" style="normal">Roboto-Bold.ttf</font>
  </family>
  <family name="serif"><font weight="400">NotoSerif-Regular.ttf</font></family>
  <family lang="zh-Hans" variant="elegant"><font weight="400">NotoSansCJK-Regular.otf</font></family>
  <alias name="sans" to="sans-serif" weight="400" />
</familyset>
""",
            encoding="utf-8",
        )
        product_xml.write_text(
            """<?xml version="1.0" encoding="utf-8"?>
<familyset>
  <family-list name="google-sans" customizationType="new-named-family">
    <family>
      <font weight="500" style="normal">GoogleSans-Medium.ttf</font>
    </family>
  </family-list>
  <family name="material-icons"><font weight="400">MaterialIcons.ttf</font></family>
</familyset>
""",
            encoding="utf-8",
        )

        font_plan = build_font_plan()
        universal_font_plan.validate_plan(font_plan)

        xml_map = {
            "/system/etc/fonts.xml": system_xml,
            "/product/etc/fonts_customization.xml": product_xml,
        }
        route = router.build_route_plan(font_plan, xml_map, None, False)
        router.validate_route_plan(route, font_plan)

        assert route["schema"] == "minimal-xml-route-plan-v1"
        assert route["mutatesSystem"] is False
        assert route["summary"]["executableNow"] is False
        assert route["summary"]["routingComplete"] is True
        assert route["summary"]["documentCount"] == 2
        assert route["summary"]["operationCount"] == 3
        assert route["summary"]["physicalOnlyTargetCount"] == 1
        assert route["summary"]["deferredDynamicTargetCount"] == 1
        assert route["physicalOnlyTargets"] == ["/vendor/fonts/DirectLatin.ttf"]
        assert route["deferredDynamicTargets"] == ["/data/fonts/files/RuntimeLatin.ttf"]
        assert "data-font-layer-deferred" in route["reviewReasons"]

        system_doc = route["documents"]["/system/etc/fonts.xml"]
        assert system_doc["operationCount"] == 2
        regular = system_doc["operations"][0]
        assert regular["mutation"]["field"] == "font.text"
        assert regular["mutation"]["preserveFontAttributes"] is True
        assert regular["mutation"]["preserveAxisChildren"] is True
        assert regular["node"]["fontAttributes"]["postScriptName"] == "Roboto-Regular"
        assert regular["node"]["fontAttributes"]["index"] == "0"
        assert regular["node"]["axes"] == [{
            "tag": "wght",
            "stylevalue": "400",
            "attributes": {"stylevalue": "400", "tag": "wght"},
        }]
        assert regular["artifact"]["requiredPostScriptName"] == "Roboto-Regular"
        assert regular["artifact"]["requiredFaceIndex"] == 0
        assert regular["artifact"]["requiredAxes"] == regular["node"]["axes"]

        assert router._artifact_extension(
            {"source": {"format": "OTF/CFF"}},
            {"declared": "VendorCollection.otc", "index": 2},
        ) == ".otc"
        assert router._artifact_extension(
            {"source": {"format": "TTF/glyf"}},
            {"declared": "VendorCollection.ttc", "index": 2},
        ) == ".ttc"

        # Every operation must use a deterministic compiler artifact.
        artifact_map = {}
        route_ids = []
        for document in route["documents"].values():
            for operation in document["operations"]:
                artifact = operation["artifact"]
                artifact_map[artifact["artifactId"]] = artifact["suggestedFileName"]
                route_ids.append(artifact["artifactId"])
        assert len(route_ids) == len(set(route_ids))

        output_root = temp / "rendered"
        report = router.render_all(route, artifact_map, output_root)
        assert report["renderedDocuments"] == 2
        assert report["changedFonts"] == 3

        rendered_system = output_root / "system/etc/fonts.xml"
        rendered_product = output_root / "product/etc/fonts_customization.xml"
        assert rendered_system.is_file()
        assert rendered_product.is_file()

        before_system = font_texts(system_xml)
        after_system = font_texts(rendered_system)
        assert len(before_system) == len(after_system)

        # Only the two sans references changed. Serif and zh-Hans fallback stay byte-semantic.
        assert after_system[0][2] != "Roboto-Regular.ttf"
        assert after_system[1][2] != "Roboto-Bold.ttf"
        assert after_system[2][2] == "NotoSerif-Regular.ttf"
        assert after_system[3][2] == "NotoSansCJK-Regular.otf"
        assert after_system[0][1] == before_system[0][1]
        assert after_system[0][3] == before_system[0][3]

        sys_tree = ET.parse(rendered_system)
        root = sys_tree.getroot()
        aliases = [dict(alias.attrib) for alias in root.findall("alias")]
        assert aliases == [{"name": "sans", "to": "sans-serif", "weight": "400"}]
        fallback = [family for family in root.findall("family") if family.attrib.get("lang") == "zh-Hans"][0]
        assert fallback.attrib == {"lang": "zh-Hans", "variant": "elegant"}

        prod_tree = ET.parse(rendered_product)
        family_list = prod_tree.getroot().find("family-list")
        assert family_list is not None
        assert family_list.attrib == {
            "name": "google-sans",
            "customizationType": "new-named-family",
        }
        product_font = family_list.find("family/font")
        assert product_font is not None
        assert (product_font.text or "").strip() != "GoogleSans-Medium.ttf"
        material = prod_tree.getroot().find("family[@name='material-icons']/font")
        assert material is not None and (material.text or "").strip() == "MaterialIcons.ttf"

        # Determinism: the same plan + same stock XML must yield the same routeId.
        route2 = router.build_route_plan(font_plan, xml_map, None, False)
        assert route2["routeId"] == route["routeId"]

        alternate_system = temp / "alternate-system.xml"
        alternate_product = temp / "alternate-product.xml"
        alternate_system.write_bytes(system_xml.read_bytes())
        alternate_product.write_bytes(product_xml.read_bytes())
        route3 = router.build_route_plan(
            font_plan,
            {
                "/system/etc/fonts.xml": alternate_system,
                "/product/etc/fonts_customization.xml": alternate_product,
            },
            None,
            False,
        )
        assert route3["routeId"] == route["routeId"], "local snapshot path must not affect routeId"

        duplicate_plan = build_font_plan(duplicate_xml_ref=True)
        universal_font_plan.validate_plan(duplicate_plan)
        duplicate_route = router.build_route_plan(duplicate_plan, xml_map, None, False)
        assert duplicate_route["summary"]["operationCount"] == 3
        assert duplicate_route["summary"]["conflictCount"] == 0
        assert duplicate_route["documents"]["/system/etc/fonts.xml"]["operationCount"] == 2

        # Route JSON tampering must fail integrity validation.
        tampered = copy.deepcopy(route)
        tampered["documents"]["/system/etc/fonts.xml"]["operations"][0]["mutation"]["preserveAxisChildren"] = False
        try:
            router.validate_route_plan(tampered, font_plan)
        except router.RouterError:
            pass
        else:
            raise AssertionError("tampered route plan unexpectedly validated")

        # A stale stock XML snapshot must be rejected during render.
        stale = copy.deepcopy(route)
        system_xml.write_text(system_xml.read_text(encoding="utf-8").replace(
            "Roboto-Bold.ttf", "Roboto-Bold-Changed.ttf"
        ), encoding="utf-8")
        try:
            router.render_all(stale, artifact_map, temp / "stale-output")
        except router.RouterError as error:
            assert "已经变化" in str(error)
        else:
            raise AssertionError("stale XML snapshot unexpectedly rendered")

        # Exact-node routing is fail-closed even for a fully valid Phase 4 plan:
        # if the frozen declared filename cannot be uniquely located in stock XML,
        # the diagnostic plan is incomplete and partial XML rendering is forbidden.
        mismatch_plan = build_font_plan(missing_bold_ref=True)
        universal_font_plan.validate_plan(mismatch_plan)
        mismatch_route = router.build_route_plan(mismatch_plan, xml_map, None, False)
        assert mismatch_route["summary"]["routingComplete"] is False
        assert mismatch_route["summary"]["unresolvedCount"] == 1
        assert mismatch_route["unresolved"][0]["reason"] == "xml-node-missing"
        mismatch_artifacts = {}
        for document in mismatch_route["documents"].values():
            for operation in document["operations"]:
                artifact = operation["artifact"]
                mismatch_artifacts[artifact["artifactId"]] = artifact["suggestedFileName"]
        try:
            router.render_all(mismatch_route, mismatch_artifacts, temp / "partial-output")
        except router.RouterError as error:
            assert "尚不完整" in str(error)
        else:
            raise AssertionError("incomplete XML route unexpectedly rendered")

    print("minimal_xml_router_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
