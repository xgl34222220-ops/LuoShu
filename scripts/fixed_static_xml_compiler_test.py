#!/usr/bin/env python3
"""Synthetic fixed-static XML assets; no OEM/root-manager readiness claims."""
from copy import deepcopy
from pathlib import Path
import hashlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "common"), str(ROOT / "scripts")]
from fontTools.ttLib import TTFont
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
import fixed_static_xml_compiler as fixed
import universal_font_compiler as compiler
import universal_font_compiler_test as fixture


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def add_points(path, points, *, tall=None):
    with TTFont(path, recalcTimestamp=False) as font:
        cmap = font.getBestCmap()
        order = list(font.getGlyphOrder())
        base = cmap[ord("A")]
        for cp in points:
            name = "extra%X" % cp
            font["glyf"][name] = deepcopy(font["glyf"][base])
            if cp == tall:
                font["glyf"][name].coordinates.scale((1, 2))
            font["hmtx"].metrics[name] = font["hmtx"].metrics[base]
            for table in font["cmap"].tables:
                if table.isUnicode() and hasattr(table, "cmap"):
                    table.cmap[cp] = name
            if "gvar" in font:
                font["gvar"].variations[name] = []
            order.append(name)
        font.setGlyphOrder(order)
        font.save(path)


class FixedStaticCompilerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="fixed-static-xml-")
        self.root = Path(self.tmp.name)
        self.source, self.stock = self.root / "source.ttf", self.root / "stock.ttf"
        fixture.make_font(self.source, family="Synthetic Fixed", weight=400)
        fixture.make_font(self.stock, family="Synthetic OEM", weight=400)
        self.logical = "/system/fonts/SyntheticOEM.ttf"

    def tearDown(self):
        self.tmp.cleanup()

    def unit(self, *, role="latin", weight=400, stock=None, logical=None, face=0):
        stock, logical = stock or self.stock, logical or self.logical
        slot = fixture.slot_from_stock(logical, stock, family="sans-serif", source_xml=None,
                                       declared=Path(logical).name, face_index=face)
        # These focused compiler fixtures intentionally use four shared Han
        # probes, below the full source selector's production CJK repertoire.
        plan, _ = fixture.build_plans(self.source, slot, "latin" if role == "cjk" else role, None)
        target = plan["targets"][logical]
        target["role"] = role
        target["source"]["mixedSelection"] = {
            "policy": "fixed-composite-selection-v1", "requestId": "synthetic-fixed",
            "fontSha256": digest(self.source),
            "roles": {r: {"mode": "fixed", "selectedAxes": {"wght": 400}}
                      for r in ("cjk", "latin", "digit")},
        }
        artifact = compiler._physical_artifact(target, plan)
        artifact.update(representation=fixed.REPRESENTATION, originalStockFaceIndex=face,
                        originalStockAxes=[], requiredFaceIndex=0, requiredAxes=[],
                        requiredPostScriptName="", requiredStyle="normal", requiredWeight=weight,
                        container="sfnt")
        return {"artifact": artifact, "target": target, "deploymentKinds": ["xml-route"],
                "routeNodes": [{"sourceXml": "/system/etc/fonts.xml", "ordinal": 0,
                                "nodeFingerprint": "sha256:synthetic"}]}

    def compile(self, unit=None, cache=None, mapping=None):
        return compiler._compile_unit(unit or self.unit(), mapping or {self.logical: self.stock},
                                      self.root / "out", False, cache)

    def test_honest_static_source_at_different_xml_weight(self):
        before = digest(self.source), digest(self.stock)
        unit = self.unit(weight=700)
        result = self.compile(unit)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["mode"], fixed.REPRESENTATION)
        self.assertEqual(result["staticXmlContract"]["fontWeight"], 400)
        with TTFont(result["output"]) as font:
            self.assertFalse(fixed.VARIABLE_TABLES & set(font.keys()))
            self.assertEqual(font["OS/2"].usWeightClass, 400)
            self.assertEqual({n.toUnicode() for n in font["name"].names if n.nameID == 6},
                             {result["staticXmlContract"]["postScriptName"]})
        fixed.validate_artifact(result, unit)
        self.assertEqual((digest(self.source), digest(self.stock)), before)

    def test_coverage_intersection_excludes_greek_emoji_and_unrelated_han(self):
        extra = [ord("Ω"), 0x2600, ord("中"), ord("国"), ord("永"), ord("文")]
        add_points(self.source, extra)
        add_points(self.stock, [ord("Ω"), 0x2600])
        result = self.compile(self.unit(role="ui-sans"))
        self.assertEqual(result["status"], "ready", result)
        with TTFont(result["output"]) as font:
            self.assertTrue(set(extra).isdisjoint(font.getBestCmap()))
        self.assertEqual(result["report"]["renderContract"]["coverage"]["exposedRoles"], ["digit", "latin"])

    def test_cjk_uses_own_shared_han_geometry(self):
        shared = list(map(ord, "中永国文"))
        add_points(self.source, shared + [ord("书")])
        add_points(self.stock, shared + [ord("字")])
        result = self.compile(self.unit(role="cjk"))
        self.assertEqual(result["status"], "ready", result)
        with TTFont(result["output"]) as font:
            self.assertEqual(set(font.getBestCmap()), set(shared))
        self.assertEqual(result["report"]["renderContract"]["coverage"]["preservedMissingSourceCount"], 1)

    def test_unselected_latin_geometry_cannot_veto_cjk_asset(self):
        shared=list(map(ord,"中永国文"))
        add_points(self.source,shared);add_points(self.stock,shared)
        with TTFont(self.stock) as font:
            for cp in range(ord('a'),ord('z')+1):
                glyph=font['glyf'][font.getBestCmap()[cp]];glyph.coordinates.scale((1,2))
            font.save(self.stock)
        unit=self.unit(role='cjk')
        with TTFont(self.stock) as stock, TTFont(self.source) as source:
            stock_profile,source_profile=compiler._paired_geometry_profiles(stock,source,'cjk')
            with self.assertRaisesRegex(compiler.CompilerError,'latinX'):
                compiler._geometry_plan(unit['target'],stock_profile,source_profile,400)
        result=self.compile(unit)
        self.assertEqual(result['status'],'ready',result)
        self.assertEqual(result['report']['renderContract']['coverage']['exposedRoles'],['cjk'])
        with TTFont(result['output']) as font:self.assertEqual(set(font.getBestCmap()),set(shared))

    def test_equal_contracts_group_before_render_and_keep_route_ids(self):
        a, b = self.unit(weight=400), self.unit(weight=700)
        b["artifact"]["artifactId"] = "ufc:" + "b" * 32
        b["routeNodes"][0]["ordinal"] = 1
        prepared = [fixed.prepare_unit(u, {self.logical: self.stock}, False) for u in (a, b)]
        self.assertEqual(prepared[0]["binding"], prepared[1]["binding"])
        cache = {}
        results = []
        with patch.object(fixed.slot_build, "apply_outline_transforms", wraps=fixed.slot_build.apply_outline_transforms) as render:
            for unit, prep in zip((a, b), prepared):
                unit["_fixedStaticPrepared"] = prep
                results.append(self.compile(unit, cache))
            self.assertEqual(render.call_count, 1)
        self.assertTrue(all(r["status"] == "ready" for r in results), results)
        self.assertNotEqual(results[0]["artifactId"], results[1]["artifactId"])
        self.assertEqual(results[0]["output"], results[1]["output"])
        self.assertTrue(results[1]["report"]["renderReuse"]["hit"])

    def test_distinct_line_geometry_never_groups(self):
        other = self.root / "other.ttf"
        fixture.make_font(other, family="Synthetic OEM", ascent=950)
        other_logical = "/system/fonts/Other.ttf"
        a = fixed.prepare_unit(self.unit(), {self.logical: self.stock}, False)
        b = fixed.prepare_unit(self.unit(stock=other, logical=other_logical), {other_logical: other}, False)
        self.assertNotEqual(a["binding"], b["binding"])

    def test_source_and_stock_changes_are_rejected(self):
        unit = self.unit()
        prepared = fixed.prepare_unit(unit, {self.logical: self.stock}, False)
        self.source.write_bytes(self.source.read_bytes() + b"changed")
        self.assertEqual(self.compile(unit)["status"], "blocked")
        with self.assertRaisesRegex(compiler.CompilerError, "input changed"):
            fixed.compile_prepared(prepared, self.root / "out", {})
        self.source.write_bytes(self.source.read_bytes()[:-7])
        self.stock.write_bytes(self.stock.read_bytes() + b"changed")
        self.assertEqual(self.compile(unit)["status"], "blocked")

    def test_physical_italic_and_generic_sources_cannot_opt_in(self):
        variants = []
        physical = self.unit(); physical["deploymentKinds"] = ["physical-slot"]; variants.append(physical)
        generic = self.unit(); generic["target"]["source"].pop("mixedSelection"); variants.append(generic)
        italic = self.unit(); italic["artifact"]["requiredStyle"] = "italic"; variants.append(italic)
        for unit in variants:
            with self.subTest(kind=unit["deploymentKinds"], style=unit["artifact"]["requiredStyle"]):
                self.assertEqual(self.compile(unit)["status"], "blocked")

    def test_oem_reference_clamps_like_skia_and_unknown_axis_is_rejected(self):
        fixture.make_font(self.stock, family="Synthetic OEM", variable=True)
        unit = self.unit(weight=700)
        unit["artifact"]["originalStockAxes"] = [{"tag": "wght", "stylevalue": "650"}]
        result = self.compile(unit)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["report"]["renderContract"]["stock"]["location"], {"wght": 650})
        with TTFont(result["output"]) as font:
            self.assertNotIn("fvar", font)
        unit["artifact"]["originalStockAxes"][0]["stylevalue"] = "950"
        bounded = self.compile(unit)
        self.assertEqual(bounded["status"], "ready", bounded)
        self.assertEqual(bounded["report"]["stockAxisEvidence"]["requested"], {"wght": 950})
        self.assertEqual(bounded["report"]["stockAxisEvidence"]["effective"], {"wght": 900})
        self.assertEqual(bounded["report"]["stockAxisEvidence"]["clampedAxes"], ["wght"])
        bounded_bytes = Path(bounded["output"]).read_bytes()
        unit["artifact"]["originalStockAxes"][0]["stylevalue"] = "900"
        endpoint = self.compile(unit)
        self.assertEqual(bounded_bytes, Path(endpoint["output"]).read_bytes())
        unit["artifact"]["originalStockAxes"][0]["stylevalue"] = "NaN"
        self.assertIn("nonfinite", self.compile(unit)["reason"])
        unit["artifact"]["originalStockAxes"] = [{"tag": "wdth", "stylevalue": "100"}]
        self.assertIn("absent", self.compile(unit)["reason"])

    def test_batch_contract_failure_precedes_all_geometry_measurements(self):
        plan, route = self.routed_plan()
        units = compiler._collect_units(plan, route)
        units[-1]["artifact"]["originalStockAxes"] = [{"tag": "wdth", "stylevalue": "100"}]
        with patch.object(compiler, "_collect_units", return_value=units), patch.object(fixed, "prepare_unit", wraps=fixed.prepare_unit) as measure:
            with self.assertRaisesRegex(compiler.CompilerError, "fixed-static-preflight.*absent"):
                compiler.compile_all(plan, route, {self.logical: self.stock}, self.root / "preflight", False)
            self.assertEqual(measure.call_count, 0)

    def test_atomic_blocked_plan_never_measures_other_static_routes(self):
        import universal_font_plan as planner
        import minimal_xml_router as legacy
        import fixed_static_xml_router as router
        import os
        xml=self.root/'atomic.xml';xml.write_text('<familyset><family name="sans-serif"><font>SyntheticOEM.ttf</font></family></familyset>')
        good=fixture.slot_from_stock(self.logical,self.stock,family='sans-serif',source_xml='/system/etc/fonts.xml',declared='SyntheticOEM.ttf')
        bad_path='/system/fonts/Cjk.ttf';bad=fixture.slot_from_stock(bad_path,self.stock,family='',source_xml=None,declared='Cjk.ttf')
        profile=fixture.font_source_profile.build([self.source])
        for file in profile['files']:
            for face in file['faces']:face['mixedSelection']=deepcopy(self.unit()['target']['source']['mixedSelection'])
        topology={'schema':planner.TOPOLOGY_SCHEMA,'state':'ready','topologyRevision':3,'buildKey':'phase6-test','slots':{self.logical:good,bad_path:bad},'summary':{},'families':{},'xmlAliases':[],'unresolvedXmlRefs':[]}
        roles={'schema':planner.ROLES_SCHEMA,'state':'ready','roleRevision':3,'buildKey':'phase6-test','slots':{self.logical:fixture.role_map('latin'),bad_path:fixture.role_map('cjk')}}
        plan=planner.build_plan(topology,roles,profile);self.assertEqual(plan['targets'][bad_path]['status'],'blocked')
        base=legacy.build_route_plan(plan,{'/system/etc/fonts.xml':xml},None,False);route=router.build_route_plan(plan,base)
        with patch.dict(os.environ,{'LUOSHU_UNIVERSAL_MIX_STRICT':'1'}),patch.object(fixed,'prepare_unit',wraps=fixed.prepare_unit) as measure:
            with self.assertRaisesRegex(compiler.CompilerError,'blocked plan target'):
                compiler.compile_all(plan,route,{self.logical:self.stock,bad_path:self.stock},self.root/'atomic-out',False)
            self.assertEqual(measure.call_count,0)

    def test_unmeasured_han_and_unprobed_clipping_fail_closed(self):
        add_points(self.source, [ord("中")])
        add_points(self.stock, [ord("中")])
        self.assertEqual(self.compile(self.unit(role="cjk"))["status"], "blocked")
        fixture.make_font(self.source, family="Synthetic Fixed")
        fixture.make_font(self.stock, family="Synthetic OEM")
        add_points(self.source, [ord("À")], tall=ord("À"))
        add_points(self.stock, [ord("À")])
        result = self.compile()
        self.assertEqual(result["status"], "blocked", result)
        self.assertIn("line budget", result["reason"])

    def test_shaping_closure_survives_without_expanding_cmap(self):
        with TTFont(self.source) as font:
            order = list(font.getGlyphOrder())
            font["glyf"]["f_i"] = deepcopy(font["glyf"][font.getBestCmap()[ord("f")]])
            font["hmtx"].metrics["f_i"] = (600, 40)
            font.setGlyphOrder(order + ["f_i"])
            addOpenTypeFeaturesFromString(font, "feature liga { sub u0066 u0069 by f_i; } liga;")
            font.save(self.source)
        result = self.compile()
        self.assertEqual(result["status"], "ready", result)
        with TTFont(result["output"]) as font:
            self.assertIn("GSUB", font)
            cmap = font.getBestCmap()
            ligature = font["GSUB"].table.LookupList.Lookup[0].SubTable[0].ligatures[cmap[ord("f")]][0].LigGlyph
            self.assertIn(ligature, font.getGlyphOrder())
            self.assertNotIn(ligature, cmap.values())
            self.assertEqual(set(font.getBestCmap()), set(fixture.ASCII_POINTS))

    def test_tampered_preparation_binding_and_reused_output_rejected(self):
        prepared = fixed.prepare_unit(self.unit(), {self.logical: self.stock}, False)
        bad = deepcopy(prepared); bad["binding"]["postScriptName"] = "Forged"
        with self.assertRaisesRegex(compiler.CompilerError, "contract changed"):
            fixed.compile_prepared(bad, self.root / "out", {})
        cache = {}
        result = fixed.compile_prepared(prepared, self.root / "out", cache)
        Path(result["output"]).write_bytes(b"tamper")
        with self.assertRaisesRegex(compiler.CompilerError, "integrity"):
            fixed.compile_prepared(prepared, self.root / "out", cache)

    def routed_plan(self):
        import fixed_static_xml_router
        xml = self.root / "fonts.xml"
        xml.write_text('<familyset><family name="sans-serif"><font weight="400">SyntheticOEM.ttf</font>'
                       '<font weight="700">SyntheticOEM.ttf</font></family></familyset>')
        slot = fixture.slot_from_stock(self.logical, self.stock, family="sans-serif",
                                       source_xml="/system/etc/fonts.xml", declared="SyntheticOEM.ttf")
        slot["xmlRefs"].append(dict(slot["xmlRefs"][0], weight=700))
        profile = fixture.font_source_profile.build([self.source])
        policy = self.unit()["target"]["source"]["mixedSelection"]
        for file in profile["files"]:
            for face in file["faces"]:
                face["mixedSelection"] = deepcopy(policy)
        with patch.object(fixture.font_source_profile, "build", return_value=profile):
            plan, route = fixture.build_plans(self.source, slot, "latin", xml)
        return plan, fixed_static_xml_router.build_route_plan(plan, route)

    def test_real_router_batch_prepares_every_route_before_render(self):
        plan, route = self.routed_plan()
        events = []
        original_prepare, original_save = fixed.prepare_unit, compiler._save_font
        def prepare(*args, **kwargs):
            events.append("prepare")
            return original_prepare(*args, **kwargs)
        def save(*args, **kwargs):
            events.append("render")
            return original_save(*args, **kwargs)
        with patch.object(fixed, "prepare_unit", side_effect=prepare), patch.object(compiler, "_save_font", side_effect=save):
            manifest = compiler.compile_all(plan, route, {self.logical: self.stock}, self.root / "batch", False)
        self.assertEqual(events, ["prepare", "prepare", "render"])
        self.assertEqual(manifest["summary"]["blockedCount"], 0)
        self.assertEqual(len(manifest["staticXmlBindings"]), 2)
        self.assertEqual(len(set(manifest["artifactMap"].values())), 1)
        compiler.validate_manifest(manifest, plan, route)
        bad = deepcopy(manifest)
        next(iter(bad["staticXmlBindings"].values()))["fontWeight"] = 700
        with self.assertRaisesRegex(compiler.CompilerError, "staticXmlBindings"):
            compiler.validate_manifest(bad, plan, route)
        bad = deepcopy(manifest)
        bad["artifacts"].pop()
        with self.assertRaisesRegex(compiler.CompilerError, "artifact set is incomplete"):
            compiler.validate_manifest(bad, plan, route)
        bad = deepcopy(manifest)
        bad["artifacts"][0]["contract"].pop("representation")
        with self.assertRaisesRegex(compiler.CompilerError, "complete route unit"):
            compiler.validate_manifest(bad, plan, route)

    def test_batch_preparation_failure_never_renders_partial_static_assets(self):
        plan, route = self.routed_plan()
        original = fixed.prepare_unit
        calls = []
        def prepare(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise compiler.CompilerError("synthetic second route geometry failure")
            return original(*args, **kwargs)
        with patch.object(fixed, "prepare_unit", side_effect=prepare), patch.object(compiler, "_save_font") as save:
            with self.assertRaisesRegex(compiler.CompilerError, "second route"):
                compiler.compile_all(plan, route, {self.logical: self.stock}, self.root / "batch", False)
            save.assert_not_called()

    def test_nonzero_collection_original_produces_face_zero_sfnt(self):
        other = self.root / "first.ttf"
        fixture.make_font(other, family="Unselected Face", ascent=1000)
        collection = self.root / "stock.ttc"
        fixture.make_collection(collection, other, self.stock)
        logical = "/system/fonts/SyntheticCollection.ttc"
        unit = self.unit(stock=collection, logical=logical, face=1)
        result = self.compile(unit, mapping={logical: collection})
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["stock"]["faceIndex"], 1)
        self.assertEqual(result["staticXmlContract"]["faceIndex"], 0)
        self.assertNotEqual(Path(result["output"]).read_bytes()[:4], b"ttcf")

    def test_collection_xml_update_key_is_not_selected_face_name(self):
        first = self.root / "jp.ttf"
        fixture.make_font(first, family="Container JP", ascent=1000)
        collection = self.root / "locale.ttc"
        fixture.make_collection(collection, first, self.stock)
        logical = "/system/fonts/Locale.ttc"
        unit = self.unit(stock=collection, logical=logical, face=1)
        with TTFont(first) as font:
            key = next(n.toUnicode() for n in font["name"].names if n.nameID == 6)
        unit["artifact"]["originalStockPostScriptName"] = key
        unit["target"]["xmlRefs"] = [{"index": 1, "postScriptName": key, "fingerprint": "sha256:sealed-xml"}]
        result = self.compile(unit, mapping={logical: collection})
        self.assertEqual(result["status"], "ready", result)
        proof = result["report"]["stockXmlIdentity"]
        self.assertEqual(proof["declaredPostScriptName"], key)
        self.assertNotIn(key, proof["actualFacePostScriptNames"])
        self.assertEqual(proof["faceIndex"], 1)
        unit["target"]["xmlRefs"][0]["postScriptName"] = "DifferentKey"
        self.assertIn("sealed XML", self.compile(unit, mapping={logical: collection})["reason"])

    def test_source_variations_and_unsealed_xml_update_key_are_rejected(self):
        unit = self.unit()
        unit["artifact"]["originalStockPostScriptName"] = "WrongOEMFace"
        self.assertIn("PostScript", self.compile(unit)["reason"])
        fixture.make_font(self.source, family="Synthetic Fixed", variable=True)
        self.assertEqual(self.compile()["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
