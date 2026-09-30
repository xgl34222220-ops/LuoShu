#!/usr/bin/env python3
"""Synthetic ColorOS fixed-selection pipeline, including explicitly preserved italic.

No phone files, vendor fonts, live mounts, or mocked compiler safety gates.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'common'), str(ROOT / 'scripts')]
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.varLib.instancer import instantiateVariableFont
import device_font_template_base as template
import font_source_profile
import minimal_xml_router
import universal_font_compiler as compiler
import universal_font_compiler_test as fixture
import universal_font_cutover_gate as gate
import universal_font_deployment as deployment
import universal_font_plan
import universal_mixed_font as mixed
from universal_mixed_pipeline_test import make_font, point_count, write_conf


def variable_stock(path: Path, *, cjk: bool, slant: bool = False) -> None:
    if cjk:
        make_font(path, variable=True)
    else:
        fixture.make_font(path, family='Synthetic Roboto VF', variable=True)
    with TTFont(path) as font:
        font.ensureDecompiled()
        if slant:
            FontBuilder(font=font).setupFvar([
                ('wght', 100, 400, 900, 'Weight'),
                ('slnt', -10, 0, 0, 'Slant'),
            ], [])
        # Real OEM deltas allow the test to prove the fixed selection removes
        # imported glyph variations while preserving the original VF container.
        for char in ('A', '1', '中'):
            name = font.getBestCmap().get(ord(char))
            if name is None:
                continue
            assert len(font['glyf'][name].coordinates) == 4
            font['gvar'].variations[name] = [TupleVariation(
                {'wght': (0, 1, 1)},
                [(0, 0), (30, 0), (30, 0), (0, 0), *[(0, 0)] * 4],
            )]
            if slant:
                font['gvar'].variations[name].append(TupleVariation(
                    {'slnt': (-1, -1, 0)},
                    [(0, 0), (0, 0), (84, 0), (84, 0), *[(0, 0)] * 4],
                ))
        font.save(path)


def glyph_points(font: TTFont, codepoint: int):
    return tuple(font['glyf'][font.getBestCmap()[codepoint]].getCoordinates(font['glyf'])[0])


def artifact_for(manifest: dict, logical: str) -> dict:
    matches = [entry for entry in manifest['artifacts'] if entry['targetPath'] == logical]
    assert len(matches) == 1, matches
    return matches[0]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix='luoshu-coloros-fixed-') as raw:
        temp = Path(raw)
        module = temp / 'module'
        generated = module / 'cache/generated/composite.ttf'
        generated.parent.mkdir(parents=True)
        make_font(generated, marked=True)
        with TTFont(generated) as font:
            canonical = set(template.PROBE_GROUPS['cjk'])
            rare = [cp for cp in sorted(font.getBestCmap()) if 0x5200 <= cp <= 0x6000 and cp not in canonical][:16]
            assert len(rare) == 16 and not set(rare) & canonical
            pen = TTGlyphPen(None)
            pen.moveTo((40, -120)); pen.lineTo((570, -120)); pen.lineTo((570, 600))
            pen.lineTo((305, 720)); pen.lineTo((40, 600)); pen.closePath()
            font['glyf'][font.getBestCmap()[rare[0]]] = pen.glyph()
            font.save(generated)
        request = 'coloros-fixed-pipeline'
        state = {'requestId': request, 'cjk': 'Han Fixed', 'latin': 'Latin Fixed', 'digit': 'Digit Fixed',
                 'cjkAxes': 'wght=400', 'latinAxes': 'wght=400', 'digitAxes': 'wght=400'}
        write_conf(module / 'config/mix-stage-next.conf', state)
        write_conf(module / '.luoshu-mix-stage/.luoshu-mix-generation.conf',
                   dict(state, compositeHash=mixed.digest(generated)))
        frozen = mixed.freeze(module, request, 'fixed', generated)
        source = frozen / 'fonts/LuoShuMix-Regular.ttf'
        selected_profile = font_source_profile.build([source], mixed_selection=frozen / 'source.json')
        generic_profile = font_source_profile.build([source])
        assert selected_profile['profileId'] != generic_profile['profileId']
        assert selected_profile['summary']['capabilities']['globalUiCandidate'] is True

        bold = temp / 'OplusSans-Bold.ttf'
        roboto = temp / 'RobotoVF.ttf'
        droid = temp / 'DroidSansFallbackVF.ttf'
        rare_file = temp / 'OplusRareHan.ttf'
        protected = temp / 'ProtectedEmoji.ttf'
        fixture.make_font(bold, family='Synthetic Oplus Sans', weight=700)
        variable_stock(roboto, cjk=False, slant=True)
        variable_stock(droid, cjk=True)
        original = fixture.ASCII_POINTS
        try:
            fixture.ASCII_POINTS = tuple(rare)
            fixture.make_font(rare_file, family='Synthetic Rare Han')
        finally:
            fixture.ASCII_POINTS = original
        fixture.make_font(protected, family='Protected Fixture')
        paths = {
            'bold': '/system/fonts/OplusSans-Bold.ttf',
            'roboto': '/system/fonts/RobotoVF.ttf',
            'droid': '/system/fonts/DroidSansFallbackVF.ttf',
            'rare': '/system/fonts/OplusRareHan.ttf',
            'protected': '/system/fonts/NotoColorEmoji.ttf',
        }
        stocks = {paths[key]: path for key, path in
                  [('bold', bold), ('roboto', roboto), ('droid', droid), ('rare', rare_file), ('protected', protected)]}
        xml = temp / 'fonts.xml'
        logical_xml = '/system/etc/fonts.xml'
        xml.write_text('''<familyset><family name="sans-serif">
<font weight="400" style="normal">RobotoVF.ttf<axis tag="wght" stylevalue="400"/><axis tag="slnt" stylevalue="0"/></font>
<font weight="100" style="italic">RobotoVF.ttf<axis tag="wght" stylevalue="100"/><axis tag="slnt" stylevalue="-10"/></font>
<font weight="700" style="normal">OplusSans-Bold.ttf</font>
</family></familyset>''')
        slots = {}
        for key, path in paths.items():
            with_xml = key in {'bold', 'roboto'}
            slots[path] = fixture.slot_from_stock(
                path, stocks[path], family='sans-serif',
                source_xml=logical_xml if with_xml else None,
                declared=Path(path).name, weight=700 if key == 'bold' else 400,
            )
        normal_ref = slots[paths['roboto']]['xmlRefs'][0]
        normal_ref['axes'] = 'wght=400,slnt=0'
        italic_ref = copy.deepcopy(normal_ref)
        italic_ref.update(weight=100, style='italic', axes='wght=100,slnt=-10')
        slots[paths['roboto']]['xmlRefs'].append(italic_ref)
        topology = {'schema': 'device-font-topology-v1', 'topologyRevision': 3, 'state': 'ready',
                    'buildKey': 'synthetic-coloros-fixed', 'romKind': 'coloros', 'summary': {},
                    'slots': slots, 'families': {}, 'xmlAliases': [], 'unresolvedXmlRefs': [], 'runtime': {}}
        role_names = {'bold': 'latin', 'roboto': 'latin', 'droid': 'ui-sans', 'rare': 'cjk', 'protected': 'emoji'}
        roles = {'schema': 'device-font-roles-v1', 'roleRevision': 3, 'state': 'ready',
                 'buildKey': topology['buildKey'], 'romKind': 'coloros',
                 'slots': {path: fixture.role_map(role_names[key]) for key, path in paths.items()}}
        originals = {path: mixed.digest(path) for path in [generated, source, frozen / 'source.json', xml, *stocks.values()]}

        # Generic static400 still cannot satisfy a700 stock target. No fixed
        # policy is inferred merely from the frozen filename or adjacent report.
        generic_plan = universal_font_plan.build_plan(topology, roles, generic_profile)
        assert 'static-weight-fallback' in generic_plan['targets'][paths['bold']]['risks']
        generic_route = minimal_xml_router.build_route_plan(generic_plan, {logical_xml: xml}, None, False)
        generic_artifacts = compiler.compile_all(generic_plan, generic_route, stocks, temp / 'generic-blocked', False)
        assert generic_artifacts['summary']['deploymentReady'] is False
        assert any('static-weight-fallback' in entry.get('reason', '') for entry in generic_artifacts['artifacts'])

        plan = universal_font_plan.build_plan(topology, roles, selected_profile)
        route = minimal_xml_router.build_route_plan(plan, {logical_xml: xml}, None, False)
        assert route['summary']['routingComplete'] is True, route['summary']
        assert len(route['preservedRoutes']) == 1, route['preservedRoutes']
        preserved = route['preservedRoutes'][0]
        assert preserved['targetPath'] == paths['roboto']
        assert preserved['reason'] == 'fixed-composite-italic-preserved'
        assert preserved['node']['style'] == 'italic' and preserved['node']['weight'] == 100
        assert plan['targets'][paths['protected']]['action'] == 'preserve'
        assert 'static-weight-fallback' not in plan['targets'][paths['bold']]['risks']
        previous = os.environ.get('LUOSHU_UNIVERSAL_MIX_STRICT')
        os.environ['LUOSHU_UNIVERSAL_MIX_STRICT'] = '1'
        try:
            artifacts = compiler.compile_all(plan, route, stocks, temp / 'compiled', False)
        finally:
            if previous is None:
                os.environ.pop('LUOSHU_UNIVERSAL_MIX_STRICT', None)
            else:
                os.environ['LUOSHU_UNIVERSAL_MIX_STRICT'] = previous
        fixture.assert_ready(artifacts)
        assert artifacts['summary']['artifactCount'] == 4, artifacts['summary']
        assert artifacts['preservedRoutes'] == route['preservedRoutes']
        assert paths['roboto'] not in artifacts['physicalTargetMap']
        assert paths['droid'] in artifacts['physicalTargetMap']
        assert all(entry['mode'] == 'stock-shell' for entry in artifacts['artifacts'])
        assert all(entry['report']['sourceWeight'] == 400 for entry in artifacts['artifacts'])
        assert artifact_for(artifacts, paths['bold'])['report']['targetWeight'] == 700
        for key in ('bold', 'roboto', 'droid'):
            with TTFont(artifact_for(artifacts, paths[key])['output']) as output:
                assert point_count(output, 'A') == 3
                assert point_count(output, '1') == 5
        rare_artifact = artifact_for(artifacts, paths['rare'])
        shared = rare_artifact['report']['geometry']['sharedProbePoints']['cjk']
        assert set(shared) == set(rare) and not set(shared) & canonical
        with TTFont(rare_artifact['output']) as output:
            assert set(output.getBestCmap()) == set(rare)
            assert len(glyph_points(output, rare[0])) == 5
        with TTFont(artifact_for(artifacts, paths['droid'])['output']) as output, TTFont(droid) as stock:
            assert output.getTableData('fvar') == stock.getTableData('fvar')
            assert 'gvar' in output
            light = instantiateVariableFont(output, {'wght': 100})
            heavy = instantiateVariableFont(output, {'wght': 900})
            stock_heavy = instantiateVariableFont(stock, {'wght': 900})
            try:
                for char in 'A1中':
                    assert glyph_points(light, ord(char)) == glyph_points(heavy, ord(char))
                assert glyph_points(stock, ord('A')) != glyph_points(stock_heavy, ord('A'))
            finally:
                light.close(); heavy.close(); stock_heavy.close()

        payload = temp / 'payload'
        deployed = deployment.build_deployment(plan, route, artifacts, payload)
        result = gate.evaluate(plan, route, artifacts, deployed, payload)
        assert result['eligible'] is True, result
        assert result['decision'] == 'universal'
        assert result['summary']['coverage'] == 'partial-style-preserved'
        assert result['summary']['preservedStyleRouteCount'] == 1
        assert 'partial-coverage:preserved-original-style-routes:1' in result['warnings']
        assert deployed['summary']['activationReady'] is True
        assert not any(entry['logicalPath'] in {paths['roboto'], paths['protected']} for entry in deployed['files'])
        rendered = ET.parse(payload / 'system/etc/fonts.xml').getroot().find('family')
        original_nodes = list(ET.parse(xml).getroot().find('family'))
        rendered_nodes = list(rendered)
        assert len(rendered_nodes) == len(original_nodes) == 3
        before, after = original_nodes[1], rendered_nodes[1]
        assert after.attrib == before.attrib and after.text.strip() == before.text.strip() == 'RobotoVF.ttf'
        assert [(child.tag, child.attrib) for child in after] == [(child.tag, child.attrib) for child in before]
        assert rendered_nodes[0].text.strip() != 'RobotoVF.ttf'
        assert rendered_nodes[2].text.strip() != 'OplusSans-Bold.ttf'
        assert originals == {path: mixed.digest(path) for path in originals}
    print('universal_coloros_fixed_pipeline_test: PASS (fixed metadata, static700, shared normal/italic VF, physical VF, rare Han, explicit partial coverage, generic rejection)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
