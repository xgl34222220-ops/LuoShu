#!/usr/bin/env python3
"""Actual scanner -> topology -> role -> plan -> router regressions (D1-D6)."""
from __future__ import annotations
import copy
import tempfile
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'common'), str(ROOT / 'scripts')]
import font_inventory as inventory
import font_inventory_scan as scanner
import font_topology_snapshot as topology
import font_role_shadow as roles
import font_source_profile as source_profile
import universal_font_plan as planner
import minimal_xml_router as router
import universal_font_compiler as compiler
import universal_font_deployment as deployment
import universal_font_cutover_gate as gate
from fontTools.ttLib import TTFont
from universal_font_compiler_test import make_font, make_collection


class DiscoveryPipelineTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fonts = self.root / 'system/fonts'
        self.etc = self.root / 'system/etc'
        self.fonts.mkdir(parents=True)
        self.etc.mkdir(parents=True)
        self.stock = self.fonts / 'Ui.ttf'
        make_font(self.stock, family='Stock UI', variable=True)
        with TTFont(self.stock) as font:
            for cmap in font['cmap'].tables:
                if cmap.isUnicode():
                    cmap.cmap[0xa0] = 'u0020'
            font.save(self.stock)
        self.source = self.root / 'User.ttf'
        make_font(self.source, family='User UI', variable=True)
        self.profile = source_profile.build([self.source])
        self.roots = [inventory.FontRoot('system', Path('/system/fonts'), self.fonts)]

    def scan(self, xml, *, config=None, data=None, dump='', mounts=''):
        self.xml = self.etc / 'fonts.xml'
        self.xml.write_text(xml)
        sources = [('system', Path('/system/etc/fonts.xml'), self.xml)]
        # Same policy installation as scanner._scan_current_roots.
        inventory._is_ui_family = scanner._is_ui_family
        families, slots = scanner._parse_partition_xml(sources, self.roots)
        inventory._add_verified_text_slots(slots, self.roots)
        inventory._populate_metrics(slots)
        graph = scanner._parse_full_xml_graph(sources, self.roots)
        inv = {'schema': inventory.SCHEMA, 'state': 'ready', 'buildKey': 'discovery-pipeline',
               'scannerRevision': scanner.SCANNER_REVISION, 'slots': slots, 'families': families,
               'sourceRoots': [{'partition': 'system', 'logical': '/system/fonts', 'actual': str(self.fonts)}],
               'xmlSources': ['/system/etc/fonts.xml'], 'xmlGraph': graph}
        candidates = {'paths': [{'path': '/system/fonts/' + p.name, 'partition': 'system'} for p in self.fonts.iterdir()]}
        tp = topology.build_topology(inv, candidates, dump, config, data, mounts)
        rm, _ = roles.build(tp)
        fp = planner.build_plan(tp, rm, self.profile)
        rp = router.build_route_plan(fp, {'/system/etc/fonts.xml': self.xml}, None, False)
        return inv, tp, rm, fp, rp

    def test_all_exact_weights_and_axis_nodes_survive_to_router(self):
        inv, tp, rm, fp, rp = self.scan('''<familyset><family name="sans-serif">
        <font weight="400">Ui.ttf</font><font weight="450">Ui.ttf</font><font weight="700">Ui.ttf</font>
        <font weight="400">Ui.ttf<axis tag="wght" stylevalue="500"/></font>
        <font weight="400">Ui.ttf<axis tag="wght" stylevalue="600"/></font>
        </family></familyset>''')
        self.assertEqual([r['weight'] for r in inv['xmlGraph']['refs']], [400,450,700,400,400])
        self.assertEqual(len({r['ordinal'] for r in inv['xmlGraph']['refs']}), 5)
        self.assertTrue(rp['summary']['routingComplete'])
        self.assertEqual(rp['summary']['operationCount'], 5)
        operations = rp['documents']['/system/etc/fonts.xml']['operations']
        self.assertEqual([x['node']['ordinal'] for x in operations], list(range(5)))
        manifest = compiler.compile_all(fp, rp, {'/system/fonts/Ui.ttf': self.stock}, self.root / 'compiled', False)
        self.assertTrue(manifest['summary']['deploymentReady'], manifest)
        self.assertEqual(manifest['summary']['readyCount'], 5)

    def test_inherited_wrapper_attributes_match_without_losing_semantics(self):
        inv, tp, rm, fp, rp = self.scan('''<familyset><family-list name="sans-serif" variant="compact">
        <family><font weight="450">Ui.ttf</font></family></family-list></familyset>''')
        self.assertEqual(inv['xmlGraph']['refs'][0]['familyAttributes'], {'name':'sans-serif','variant':'compact'})
        self.assertTrue(rp['summary']['routingComplete'], rp['unresolved'])
        self.assertEqual(rp['summary']['operationCount'], 1)

    def test_language_refs_not_deduplicated_and_unknown_scripts_are_protected(self):
        result = self.scan('''<familyset><family lang="zh-Hans"><font>Ui.ttf</font></family>
        <family lang="ja"><font>Ui.ttf</font></family></familyset>''')
        self.assertEqual(len(result[0]['xmlGraph']['refs']), 2)
        self.assertEqual(result[2]['slots']['/system/fonts/Ui.ttf']['role'], 'special-fallback')
        for lang in ('chr', 'ru', 'iu', 'xx', 'und'):
            result = self.scan(f'<familyset><family lang="{lang}"><font>Ui.ttf</font></family></familyset>')
            self.assertEqual(result[3]['targets']['/system/fonts/Ui.ttf']['action'], 'preserve', lang)
            self.assertEqual(result[4]['summary']['operationCount'], 0)
        result = self.scan('<familyset><family lang="en"><font>Ui.ttf</font></family></familyset>')
        self.assertEqual(result[2]['slots']['/system/fonts/Ui.ttf']['role'], 'latin')

    def test_condensed_ui_family_with_han_is_not_review_only(self):
        with TTFont(self.stock) as font:
            for cmap in font['cmap'].tables:
                if cmap.isUnicode():
                    cmap.cmap[0x4e00] = 'u0041'
            font.save(self.stock)
        result = self.scan('<familyset><family name="sans-serif-condensed"><font>Ui.ttf</font></family></familyset>')
        self.assertEqual(result[2]['slots']['/system/fonts/Ui.ttf']['role'], 'ui-sans')
        # The source has no Han; correct classification must not bypass coverage.
        self.assertEqual(result[3]['targets']['/system/fonts/Ui.ttf']['action'], 'blocked')

    def dynamic(self, body, *, face=0, collection=False):
        data = self.root / 'data/fonts/files'
        active = data / '~~active'
        active.mkdir(parents=True, exist_ok=True)
        name = 'Active.ttc' if collection else 'Active.ttf'
        font = active / name
        if collection:
            a, b = self.root / 'A.ttf', self.root / 'B.ttf'
            make_font(a, family='Unused')
            make_font(b, family='Dynamic')
            make_collection(font, a, b)
        else:
            make_font(font, family='Dynamic')
        config = self.root / 'data/fonts/config/config.xml'
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('<fontConfig><lastModifiedDate value="42"/><updatedFontDir value="~~active"/>' + body + '</fontConfig>')
        return config, data, font, '/data/fonts/files/~~active/' + name

    def test_real_dynamic_config_flows_to_target_compiler_and_deployment(self):
        config, data, actual, logical = self.dynamic('<family name="sans-serif"><font name="Dynamic-Regular" index="0" weight="400" slant="0" axis=""/></family>')
        result = self.scan('<familyset><family name="sans-serif"><font>Ui.ttf</font></family></familyset>', config=config, data=data, dump=logical)
        inv, tp, rm, fp, rp = result
        self.assertTrue(tp['runtime']['dynamicFontsEvidence']['complete'], tp['runtime'])
        identity = fp['targets'][logical]['targetContract']['dynamicIdentity']
        self.assertEqual(identity['fontPath'], logical)
        self.assertEqual(identity['configPath'], '/data/fonts/config/config.xml')
        self.assertEqual(identity['postScriptName'], 'Dynamic-Regular')
        self.assertEqual(len(identity['fontSha256']), 64)
        self.assertEqual(rp['deferredDynamicTargets'], [logical])
        artifacts = compiler.compile_all(fp, rp, {'/system/fonts/Ui.ttf':self.stock, logical:actual}, self.root/'compiled', False)
        self.assertTrue(artifacts['summary']['deploymentReady'], artifacts)
        dep = deployment.build_deployment(fp, rp, artifacts, self.root/'payload')
        self.assertEqual(dep['summary']['dynamicMountCount'], 1)
        decision = gate.evaluate(fp, rp, artifacts, dep, self.root/'payload')
        self.assertTrue(decision['eligible'], decision)

    def test_dynamic_collection_index_and_ambiguity_are_not_guessed(self):
        config, data, actual, logical = self.dynamic('<family name="sans-serif"><font name="Dynamic-Regular" index="1" weight="400"/></family>', collection=True)
        result = self.scan('<familyset><family name="sans-serif"><font>Ui.ttf</font></family></familyset>', config=config, data=data)
        self.assertEqual(result[1]['slots'][logical]['faceIndex'], 1)
        self.assertEqual(result[3]['targets'][logical]['targetContract']['dynamicIdentity']['faceIndex'], 1)
        config.write_text(config.read_text().replace('index="1"', 'index="0"'))
        result = self.scan('<familyset><family name="sans-serif"><font>Ui.ttf</font></family></familyset>', config=config, data=data)
        self.assertNotIn(logical, result[1]['slots'])
        self.assertIn('dynamic-font-discovery-incomplete', result[3]['constraints']['risks'])

    def test_dynamic_file_update_inherits_actual_stock_postscript_semantics(self):
        config, data, actual, logical = self.dynamic('')
        # Updated file uses the stock PostScript identity, though its filename differs.
        make_font(actual, family='Stock UI')
        result = self.scan('<familyset><family name="sans-serif"><font>Ui.ttf</font></family></familyset>', config=config, data=data)
        self.assertIn(logical, result[1]['slots'])
        self.assertEqual(result[2]['slots'][logical]['role'], 'ui-sans')
        self.assertTrue(result[1]['runtime']['dynamicFontsEvidence']['complete'])

    def test_unresolved_or_stale_dynamic_evidence_is_blocked_not_hidden(self):
        config, data, actual, logical = self.dynamic('<family name="sans-serif"><font name="Missing-Regular"/></family>')
        result = self.scan('<familyset><family name="sans-serif"><font>Ui.ttf</font></family></familyset>', config=config, data=data)
        fp, rp = result[3:]
        self.assertIn('dynamic-font-discovery-incomplete', fp['constraints']['risks'])
        artifacts = compiler.compile_all(fp, rp, {'/system/fonts/Ui.ttf':self.stock}, self.root/'compiled', False)
        dep = deployment.build_deployment(fp, rp, artifacts, self.root/'payload')
        decision = gate.evaluate(fp, rp, artifacts, dep, self.root/'payload')
        self.assertFalse(decision['eligible'])
        self.assertIn('dynamic-font-discovery-incomplete', decision['reasons'])
        config.write_text('<fontConfig/>')
        result = self.scan('<familyset><family name="sans-serif"><font>Ui.ttf</font></family></familyset>', config=config, data=data, dump=logical)
        self.assertNotIn(logical, result[1]['slots'])
        self.assertFalse(result[1]['runtime']['dynamicFontsEvidence']['complete'])


    def test_dynamic_traversal_symlink_and_live_overlay_never_become_stock(self):
        config, data, actual, logical = self.dynamic('<family name="sans-serif"><font name="Dynamic-Regular"/></family>')
        xml = '<familyset><family name="sans-serif"><font>Ui.ttf</font></family></familyset>'
        mounted = f'101 1 0:40 / {logical} ro - ext4 /dev/test rw\n'
        result = self.scan(xml, config=config, data=data, mounts=mounted)
        self.assertNotIn(logical, result[1]['slots'])
        self.assertIn('dynamic-active-overlay-stock-unavailable', [x['reason'] for x in result[1]['runtime']['dynamicFontsEvidence']['unresolved']])
        actual.unlink()
        actual.symlink_to(self.source)
        result = self.scan(xml, config=config, data=data)
        self.assertNotIn(logical, result[1]['slots'])
        self.assertFalse(result[1]['runtime']['dynamicFontsEvidence']['complete'])
        config.write_text('<fontConfig><family name="sans-serif"><font>../User.ttf</font></family></fontConfig>')
        result = self.scan(xml, config=config, data=data)
        self.assertEqual(result[1]['summary']['dynamicResolvedTargetCount'], 0)
        self.assertFalse(result[1]['runtime']['dynamicFontsEvidence']['complete'])

    def test_stale_revision_and_changed_dynamic_generation_are_rejected(self):
        config, data, actual, logical = self.dynamic('<family name="sans-serif"><font name="Dynamic-Regular"/></family>')
        inv, tp, rm, fp, rp = self.scan('<familyset><family name="sans-serif"><font>Ui.ttf</font></family></familyset>', config=config, data=data)
        for key, original in [('topologyRevision',tp),('roleRevision',rm)]:
            old = copy.deepcopy(original)
            old[key] = 2
            with self.assertRaises(planner.UniversalPlanError):
                planner.build_plan(old if key == 'topologyRevision' else tp, old if key == 'roleRevision' else rm, self.profile)
        invpath, tppath = self.root/'inventory.json', self.root/'topology.json'
        invpath.write_text(json.dumps(inv)); tppath.write_text(json.dumps(tp))
        command = [sys.executable, str(ROOT/'common/font_topology_snapshot.py'), '--validate-current',
                   '--inventory',str(invpath),'--output',str(tppath), '--data-fonts-config',str(config),'--data-fonts-dir',str(data)]
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
        config.write_text(config.read_text().replace('value="42"','value="43"'))
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)

    def test_dynamic_bad_index_weight_or_axes_are_not_coerced(self):
        xml = '<familyset><family name="sans-serif"><font>Ui.ttf</font></family></familyset>'
        for attrs in ('index="-1"', 'index="invalid"', 'weight="1001"', 'weight="invalid"', 'axis="bad"', 'axis="\'wght\' 1e999"'):
            config, data, actual, logical = self.dynamic(f'<family name="sans-serif"><font name="Dynamic-Regular" {attrs}/></family>')
            result = self.scan(xml, config=config, data=data)
            self.assertNotIn(logical, result[1]['slots'], attrs)
            self.assertFalse(result[1]['runtime']['dynamicFontsEvidence']['complete'], attrs)


    def cache_validation(self, inv, tp, config, data, mounts=None):
        invpath, tppath = self.root/'cache-inventory.json', self.root/'cache-topology.json'
        invpath.write_text(json.dumps(inv)); tppath.write_text(json.dumps(tp))
        command = [sys.executable, str(ROOT/'common/font_topology_snapshot.py'), '--validate-current',
                   '--inventory',str(invpath),'--output',str(tppath), '--data-fonts-config',str(config),'--data-fonts-dir',str(data)]
        if mounts is not None:
            mountpath = self.root/'mountinfo'
            mountpath.write_text(mounts)
            command.extend(['--mountinfo', str(mountpath)])
        return subprocess.run(command, capture_output=True, text=True)

    def test_cache_tracks_same_build_inventory_semantics_not_capture_time(self):
        config, data, actual, logical = self.dynamic('<family name="sans-serif"><font name="Dynamic-Regular"/></family>')
        inv, tp, _, _, _ = self.scan('<familyset><family name="sans-serif"><font>Ui.ttf</font></family></familyset>', config=config, data=data)
        self.assertEqual(self.cache_validation(inv,tp,config,data).returncode, 0)
        inv['generatedAt'] = 987654321
        self.assertEqual(self.cache_validation(inv,tp,config,data).returncode, 0)
        inv['xmlGraph']['refs'].append(dict(inv['xmlGraph']['refs'][0], weight=700, ordinal=1))
        stale = self.cache_validation(inv,tp,config,data)
        self.assertEqual(stale.returncode, 1)
        self.assertIn('清单内容已变化', stale.stdout)

    def test_cache_detects_changed_dynamic_bytes_and_blocks_overlay_recapture(self):
        config, data, actual, logical = self.dynamic('<family name="sans-serif"><font name="Dynamic-Regular"/></family>')
        xml = '<familyset><family name="sans-serif"><font>Ui.ttf</font></family></familyset>'
        inv, tp, _, _, _ = self.scan(xml, config=config, data=data)
        original_hash = tp['slots'][logical]['dynamicIdentity']['fontSha256']
        make_font(actual, family='Dynamic', y_max=730)
        stale = self.cache_validation(inv,tp,config,data)
        self.assertEqual(stale.returncode, 1)
        self.assertIn('内容已变化', stale.stdout)
        refreshed = self.scan(xml, config=config, data=data)[1]
        self.assertNotEqual(refreshed['slots'][logical]['dynamicIdentity']['fontSha256'], original_hash)
        blocked = self.cache_validation(inv,tp,config,data, f'101 1 0:40 / {logical} ro - ext4 /dev/test rw\n')
        self.assertEqual(blocked.returncode, 3)
        self.assertEqual(json.loads(blocked.stdout)['reason'], 'dynamic-original-view-required')

    def test_cache_blocked_overlay_keeps_sealed_topology_and_plan_files(self):
        module = self.root/'module'
        common, config = module/'common', module/'config'
        common.mkdir(parents=True); config.mkdir()
        shutil.copy(ROOT/'common/font_topology_snapshot.sh',common/'font_topology_snapshot.sh')
        (common/'font_topology_snapshot.py').write_text('import sys\nraise SystemExit(3)\n')
        (common/'font_role_shadow.sh').write_text('#!/bin/sh\ntouch "$MODDIR/role-ran"\n')
        sealed = config/'device_font_topology.json'
        sealed.write_text('sealed-original-topology')
        plans = config/'universal-font-plans'
        plans.mkdir(); (plans/'sealed.json').write_text('sealed-plan')
        result = subprocess.run(['sh',str(common/'font_topology_snapshot.sh'),'ensure'],
                                env={**os.environ,'MODDIR':str(module),'LUOSHU_PYTHON':sys.executable}, capture_output=True)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(sealed.read_text(),'sealed-original-topology')
        self.assertTrue((plans/'sealed.json').is_file())
        self.assertFalse((module/'role-ran').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
