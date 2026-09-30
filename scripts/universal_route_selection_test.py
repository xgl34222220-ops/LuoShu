#!/usr/bin/env python3
"""Sanitized shared-face route regressions; no device logs or ROM fonts."""
from __future__ import annotations

import copy
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))

import minimal_xml_router as router
import universal_font_plan as planner
import universal_font_compiler as compiler
from minimal_xml_router_test import role, source_face, target_slot

PATH = "/system/fonts/SharedSans-VF.ttf"
XML = "/system/etc/fonts.xml"


def face(name: str, weight: int = 400, *, italic: bool = False, axes: list | None = None) -> dict:
    result = source_face()
    result.update(uid=f"sha256:{name}:face:0", fileUid=f"sha256:{name}")
    result["style"].update(weight=weight, italic=italic)
    result["names"].update(postScriptName=name, subfamily="Italic" if italic else "Regular")
    result["variation"] = {"variable": bool(axes), "axes": axes or []}
    return result


def node(weight: int = 400, style: str = "normal", **axes: float) -> dict:
    return {
        "weight": weight, "style": style, "index": 0,
        "axes": [{"tag": tag, "stylevalue": str(value)} for tag, value in axes.items()],
    }


def build_plan(faces: list[dict], nodes: list[dict]) -> dict:
    slot = target_slot(PATH, family="sans-serif", source_xml=XML,
                       declared=Path(PATH).name, axes=True)
    slot["xmlRefs"] = [dict(slot["xmlRefs"][0], **copy.deepcopy(value)) for value in nodes]
    topology = {
        "schema": planner.TOPOLOGY_SCHEMA, "state": "ready", "topologyRevision": 3,
        "buildKey": "synthetic-shared-style", "slots": {PATH: slot},
    }
    roles = {
        "schema": planner.ROLES_SCHEMA, "state": "ready", "roleRevision": 3,
        "buildKey": "synthetic-shared-style", "slots": {PATH: role("latin", "conditional")},
    }
    profile = {
        "schema": planner.SOURCE_SCHEMA, "state": "ready", "profileRevision": 1,
        "profileId": "sha256:synthetic-shared-style", "summary": {},
        "files": [{"sourcePath": f"/synthetic/{index}.ttf", "container": "TTF", "faces": [value]}
                  for index, value in enumerate(faces)],
    }
    return planner.build_plan(topology, roles, profile)


def route_plan(font_plan: dict, nodes: list[dict], directory: Path) -> dict:
    root = ET.Element("familyset")
    family = ET.SubElement(root, "family", {"name": "sans-serif"})
    for value in nodes:
        element = ET.SubElement(family, "font", {
            "weight": str(value["weight"]), "style": value["style"], "index": "0",
        })
        element.text = Path(PATH).name
        for axis in value["axes"]:
            ET.SubElement(element, "axis", axis)
    path = directory / "fonts.xml"
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return router.build_route_plan(font_plan, {XML: path}, None, False)


def fixed_face() -> dict:
    value = face("f" * 64)
    value["mixedSelection"] = {
        "policy": "fixed-composite-selection-v1", "requestId": "synthetic-fixed-request",
        "fontSha256": "f" * 64,
        "roles": {key: {"mode": "fixed", "selectedAxes": {"wght": 450}}
                  for key in ("cjk", "latin", "digit")},
    }
    return value


class RouteSelectionTest(unittest.TestCase):
    def test_shared_normal_italic_and_weights_choose_independent_sources(self):
        nodes = [node(400), node(400, "italic"), node(700), node(700, "italic")]
        sources = [face("regular"), face("italic", italic=True),
                   face("bold", 700), face("bold-italic", 700, italic=True)]
        plan = build_plan(sources, nodes)
        target = plan["targets"][PATH]
        self.assertFalse(target["targetContract"]["italic"])
        self.assertEqual(len(target["sourceCandidates"]), 4)
        with tempfile.TemporaryDirectory() as directory:
            route = route_plan(plan, nodes, Path(directory))
            operations = route["documents"][XML]["operations"]
            self.assertEqual([operation["routeTarget"]["source"]["postScriptName"] for operation in operations],
                             ["regular", "italic", "bold", "bold-italic"])
            self.assertEqual(len({operation["artifact"]["artifactId"] for operation in operations}), 4)
            for operation in operations:
                self.assertNotIn("italic-style-mismatch", operation["risks"])
                self.assertNotIn("static-weight-fallback", operation["risks"])
            router.validate_route_plan(route, plan)
            units = compiler._collect_units(plan, route)
            by_artifact = {item["artifact"]["artifactId"]: item["routeTarget"] for item in operations}
            self.assertEqual(len(units), 4)
            for unit in units:
                self.assertEqual(unit["target"], by_artifact[unit["artifact"]["artifactId"]])
            compiler._mixed_preflight(units, {}, False)

    def test_single_regular_source_does_not_clear_real_italic_or_weight_risks(self):
        nodes = [node(), node(style="italic"), node(700)]
        plan = build_plan([face("regular")], nodes)
        target = plan["targets"][PATH]
        self.assertNotIn("italic-style-mismatch", planner.route_target(target, nodes[0])["risks"])
        self.assertIn("italic-style-mismatch", planner.route_target(target, nodes[1])["risks"])
        self.assertIn("static-weight-fallback", planner.route_target(target, nodes[2])["risks"])
        with tempfile.TemporaryDirectory() as directory:
            route = route_plan(plan, nodes, Path(directory))
            self.assertEqual(route["summary"]["preservedRouteCount"], 0)
            self.assertEqual(route["summary"]["operationCount"], 3)
            units = compiler._collect_units(plan, route)
            normal = [unit for unit in units if unit["artifact"]["requiredStyle"] == "normal"
                      and unit["artifact"]["requiredWeight"] == 400]
            compiler._mixed_preflight(normal, {}, False)
            with self.assertRaises(compiler.CompilerError):
                compiler._mixed_preflight(units, {}, False)

    def test_xml_weight_and_fixed_wght_axis_override_physical_weight(self):
        nodes = [node(700), node(400, wght=700)]
        target = build_plan([face("regular"), face("bold", 700)], nodes)["targets"][PATH]
        self.assertEqual(target["targetContract"]["weight"], 400)
        for value in nodes:
            resolved = planner.route_target(target, value)
            self.assertEqual(resolved["source"]["weight"], 700)
            self.assertEqual(resolved["selection"]["targetWeight"], 700)
            self.assertNotIn("static-weight-fallback", resolved["risks"])

    def test_explicit_ital_and_slnt_contracts_select_effective_style(self):
        variable = face("style-variable", axes=[
            {"tag": "ital", "min": 0, "default": 0, "max": 1},
            {"tag": "slnt", "min": -12, "default": 0, "max": 0},
        ])
        nodes = [node(ital=1), node(style="italic", ital=0),
                 node(slnt=-12), node(style="italic")]
        target = build_plan([variable], nodes)["targets"][PATH]
        for value, expected in zip(nodes, (True, False, True, True)):
            resolved = planner.route_target(target, value)
            self.assertEqual(resolved["targetContract"]["italic"], expected)
            self.assertNotIn("italic-style-mismatch", resolved["risks"])
            self.assertNotIn("source-style-axis-out-of-range", resolved["risks"])
        self.assertEqual(planner.route_target(target, nodes[2])["selection"]["sourceAxes"]["slnt"], -12)
        self.assertEqual(planner.route_target(target, nodes[3])["selection"]["sourceAxes"]["ital"], 1)
        bad = planner.route_target(target, node(slnt=-20))
        self.assertIn("source-style-axis-out-of-range", bad["risks"])
        bad = planner.route_target(target, node(ital=2))
        self.assertIn("source-style-axis-out-of-range", bad["risks"])

    def test_source_style_axis_defaults_do_not_leak_between_routes(self):
        variable = face("default-italic", italic=True, axes=[
            {"tag": "ital", "min": 0, "default": 1, "max": 1},
            {"tag": "slnt", "min": -12, "default": -12, "max": 0},
        ])
        target = build_plan([variable], [node()])["targets"][PATH]
        resolved = planner.route_target(target, node())
        self.assertEqual(resolved["selection"]["sourceAxes"], {"ital": 0, "slnt": 0})
        self.assertNotIn("italic-style-mismatch", resolved["risks"])
        static = build_plan([face("static-italic", italic=True)], [node()])["targets"][PATH]
        self.assertIn("italic-style-mismatch", planner.route_target(static, node(ital=0))["risks"])
        self.assertIn("source-style-axis-missing", planner.route_target(static, node(slnt=-12))["risks"])

    def test_fixed_intent_preserves_unsupported_italic_with_explicit_coverage(self):
        nodes = [node(400), node(700), node(400, "italic")]
        plan = build_plan([fixed_face()], nodes)
        target = plan["targets"][PATH]
        self.assertIn("fixed-composite-selection", planner.route_target(target, nodes[1])["requirements"])
        self.assertNotIn("static-weight-fallback", planner.route_target(target, nodes[1])["risks"])
        self.assertIn("italic-style-mismatch", planner.route_target(target, nodes[2])["risks"])
        self.assertEqual(target["source"]["mixedSelection"], target["sourceCandidates"][0]["mixedSelection"])
        with tempfile.TemporaryDirectory() as directory:
            route = route_plan(plan, nodes, Path(directory))
            self.assertEqual(route["summary"]["operationCount"], 2)
            self.assertEqual(route["summary"]["preservedRouteCount"], 1)
            self.assertTrue(route["summary"]["routingComplete"])
            preserved = route["preservedRoutes"][0]
            self.assertEqual(preserved["reason"], "fixed-composite-italic-preserved")
            self.assertEqual(preserved["node"]["style"], "italic")
            self.assertIn("fixed-composite-italic-preserved", route["reviewReasons"])
            units = compiler._collect_units(plan, route)
            self.assertEqual(len(units), 2)
            compiler._mixed_preflight(units, {}, False)
            artifacts = {item["artifact"]["artifactId"]: item["artifact"]["suggestedFileName"]
                         for item in route["documents"][XML]["operations"]}
            output = Path(directory) / "rendered.xml"
            router.render_document(route, XML, artifacts, output)
            texts = [(element.text or "").strip() for element in ET.parse(output).iter("font")]
            self.assertNotEqual(texts[0], Path(PATH).name)
            self.assertNotEqual(texts[1], Path(PATH).name)
            self.assertEqual(texts[2], Path(PATH).name)

    def test_forged_fixed_intent_keeps_generic_static_gates(self):
        for mutate in (
            lambda policy: policy.update(fontSha256="0" * 64),
            lambda policy: policy.update(requestId=""),
            lambda policy: policy["roles"]["latin"].update(mode="variable"),
            lambda policy: policy["roles"]["digit"].update(selectedAxes={"wght": float("nan")}),
        ):
            source = fixed_face()
            mutate(source["mixedSelection"])
            target = build_plan([source], [node(700)])["targets"][PATH]
            resolved = planner.route_target(target, node(700))
            self.assertIn("static-weight-fallback", resolved["risks"])
            self.assertNotIn("fixed-composite-selection", resolved["requirements"])

    def test_fixed_normal_source_preserves_explicit_italic_slant_route(self):
        nodes = [node(), node(style="italic", slnt=-10)]
        plan = build_plan([fixed_face()], nodes)
        with tempfile.TemporaryDirectory() as directory:
            route = route_plan(plan, nodes, Path(directory))
            self.assertEqual(route["summary"]["operationCount"], 1)
            self.assertEqual(route["summary"]["preservedRouteCount"], 1)
            preserved = route["preservedRoutes"][0]
            self.assertEqual(preserved["artifact"]["requiredAxes"][0]["stylevalue"], "-10")
            self.assertIn("italic-style-mismatch", preserved["risks"])
            self.assertIn("source-style-axis-missing", preserved["risks"])
            units = compiler._collect_units(plan, route)
            self.assertEqual(len(units), 1)
            compiler._mixed_preflight(units, {}, False)
            artifacts = {item["artifact"]["artifactId"]: item["artifact"]["suggestedFileName"]
                         for item in route["documents"][XML]["operations"]}
            output = Path(directory) / "rendered.xml"
            router.render_document(route, XML, artifacts, output)
            italic = list(ET.parse(output).iter("font"))[1]
            self.assertEqual((italic.text or "").strip(), Path(PATH).name)
            self.assertEqual(italic.find("axis").attrib, {"tag": "slnt", "stylevalue": "-10"})

        # An italic fixed source cannot quietly preserve ordinary upright UI.
        source = fixed_face()
        source["style"]["italic"] = True
        resolved = planner.route_target(build_plan([source], [node()])["targets"][PATH], node())
        self.assertIn("italic-style-mismatch", resolved["risks"])
        self.assertFalse(router._preserve_fixed_italic(resolved))

    def test_resealed_route_cannot_swap_source_or_drop_style_risks(self):
        nodes = [node(), node(style="italic")]
        plan = build_plan([face("regular")], nodes)
        with tempfile.TemporaryDirectory() as directory:
            original = route_plan(plan, nodes, Path(directory))
            for key in ("source", "risks"):
                route = copy.deepcopy(original)
                operation = route["documents"][XML]["operations"][1]
                operation["routeTarget"][key] = {} if key == "source" else []
                route["routeId"] = router._recompute_route_id(route)
                with self.assertRaises(router.RouterError):
                    router.validate_route_plan(route, plan)


if __name__ == "__main__":
    unittest.main()
