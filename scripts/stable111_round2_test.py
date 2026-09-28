#!/usr/bin/env python3
"""Synthetic host integration tests; not a substitute for Android device QA."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'common'), str(ROOT/'scripts')]
from fontTools.ttLib import TTFont, TTCollection
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.pens.boundsPen import BoundsPen
import font_inventory as inventory
import font_role_policy as policy
import font_slot_weight as weights
import hyperos_metrics_batch as batch
from font_config_overlay import rewrite_tree
from font_slot_coverage import valid_coverage
from hyperos_cjk_routing_test import make_font, DEFAULT_POINTS


def variable_font(path):
    make_font(path, tuple(dict.fromkeys((*DEFAULT_POINTS, *range(32, 127)))), variable=True)
    with TTFont(path) as font:
        for name in font.getGlyphOrder():
            glyph = font['glyf'][name]
            if glyph.numberOfContours <= 0:
                continue
            coords = [(0,0),(240,0),(240,0),(0,0),*( [(0,0)]*4 )]
            thin = [(0,0),(-120,0),(-120,0),(0,0),*( [(0,0)]*4 )]
            font['gvar'].variations[name] = [TupleVariation({'wght':(0,1,1)},coords),
                                             TupleVariation({'wght':(-1,-1,0)},thin)]
        font.save(path)


def bounds(font, cp=65, **kwargs):
    glyphs=font.getGlyphSet(**kwargs); pen=BoundsPen(glyphs)
    glyphs[font.getBestCmap()[cp]].draw(pen)
    return pen.bounds


class Round2(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.module=self.root/'module'
        self.stage=self.module/'.luoshu-payload-next'; self.fonts=self.stage/'system/fonts'
        self.fonts.mkdir(parents=True); (self.module/'config').mkdir()
        self.slots={}; self.env={'LUOSHU_BUILD_KEY':'round2'}
        for part in batch.PARTS:
            root=self.root/'stock'/part; root.mkdir(parents=True)
            self.env[f'LUOSHU_{part.upper()}_FONTS_ROOT']=str(root)
        context=patch.dict(os.environ,self.env);context.start();self.addCleanup(context.stop)
        # Full UI donor: cases below include stock slots with all 52 letters/10 digits.
        make_font(self.fonts/'400.ttf', tuple(dict.fromkeys((*DEFAULT_POINTS, *range(32,127)))))
        self.stock('MiSansVF.ttf')

    def stock(self,name,part='system',family='sans-serif',weight=400,variable=False,points=DEFAULT_POINTS):
        path=self.root/'stock'/part/name
        if variable: variable_font(path)
        else: make_font(path,points)
        fmt,metrics=inventory._read_metrics(path)
        logical=f'/{part}/fonts/{name}'
        self.slots[logical]={'path':logical,'format':fmt,'metrics':metrics,'weight':weight,
                             'families':[family] if family else [],'source':'xml','faceIndex':0}
        return path

    def save_inventory(self):
        (self.module/'config/device_font_inventory.json').write_text(json.dumps({
            'schema':inventory.SCHEMA,'state':'ready','inventoryRevision':1,
            'buildKey':'round2','slots':self.slots}))

    def build(self,names=None):
        self.save_inventory()
        result=batch.build(self.module,self.stage,names or ['MiSansVF.ttf'])
        self.report=json.loads((self.stage/'.luoshu-metrics-report.json').read_text())
        self.by_slot={s['slot']:s for s in self.report['slots']}
        return result

    def test_default_mono_physical_aliases_removed_without_touching_stock(self):
        names=['DroidSansMono.ttf','NotoSansMono-Regular.ttf','RobotoMono-Regular.ttf']
        original={}
        for name in names:
            path=self.stock(name,family='monospace');original[name]=path.read_bytes()
            make_font(self.fonts/name)
        self.build(['MiSansVF.ttf',*names])
        for name in names:
            self.assertFalse((self.fonts/name).exists())
            self.assertEqual((self.root/'stock/system'/name).read_bytes(),original[name])
            self.assertIn('/system/fonts/'+name,(self.stage/'.luoshu-stock-preserved.paths').read_text())

    def test_mono_xml_role_protects_unusual_filename(self):
        self.stock('VendorTerminal.ttf',family='monospace')
        make_font(self.fonts/'VendorTerminal.ttf')
        self.build(['MiSansVF.ttf','VendorTerminal.ttf'])
        self.assertFalse((self.fonts/'VendorTerminal.ttf').exists())

    def test_mitype_mono_is_a_numeral_role_not_code_monospace(self):
        name='MitypeMonoVF.ttf';self.stock(name,family='mitype-mono')
        self.build(['MiSansVF.ttf',name])
        self.assertTrue((self.fonts/name).exists())
        self.assertEqual(self.by_slot['/system/fonts/'+name]['cjkRoutingReason'],'specialized-slot')

    def test_explicit_monospace_role_wins_over_clock_filename(self):
        self.stock('MitypeMonoVF.ttf',family='monospace');make_font(self.fonts/'MitypeMonoVF.ttf')
        self.build(['MiSansVF.ttf','MitypeMonoVF.ttf'])
        self.assertFalse((self.fonts/'MitypeMonoVF.ttf').exists())

    def test_unknown_single_face_ui_slot_added_from_inventory(self):
        original=self.stock('VendorInterface-Bold.ttf',weight=700).read_bytes()
        self.build()
        key='/system/fonts/VendorInterface-Bold.ttf'
        self.assertIn(key,self.by_slot);self.assertEqual(self.by_slot[key]['targetDiscovery'],'inventory')
        self.assertEqual((self.root/'stock/system/VendorInterface-Bold.ttf').read_bytes(),original)

    def test_unknown_lock_digits_added_when_stock_coverage_proves_digits(self):
        self.stock('VendorLockscreen.ttf',family='system-ui-clock',points=tuple(range(48,58)))
        self.build()
        self.assertIn('/system/fonts/VendorLockscreen.ttf',self.by_slot)

    def test_partition_inventory_does_not_invent_another_partition_target(self):
        self.stock('VendorInterface.ttf',part='product')
        self.build()
        self.assertTrue((self.stage/'product/fonts/VendorInterface.ttf').exists())
        self.assertFalse((self.fonts/'VendorInterface.ttf').exists())

    def test_unproven_paths_and_corrupt_contracts_stay_stock(self):
        path=self.stock('UnknownClock.ttf');original=path.read_bytes()
        self.slots['/system/fonts/UnknownClock.ttf']['metrics']['hhea']['ascent']=-1
        self.build()
        self.assertFalse((self.fonts/'UnknownClock.ttf').exists())
        self.assertEqual(path.read_bytes(),original)

    def test_nontext_icons_do_not_become_ui_targets(self):
        for name in ['VendorIcons.ttf','VendorEmoji.ttf','VendorSymbols.ttf','VendorSerif.ttf']:
            self.stock(name)
        self.build()
        self.assertEqual(len(self.by_slot),1)

    def test_unrelated_private_display_family_is_not_global_ui(self):
        self.stock('PrivateDisplay.ttf',family='private-display')
        self.build()
        self.assertFalse((self.fonts/'PrivateDisplay.ttf').exists())

    def test_verified_unknown_text_scan_is_accepted_without_a_vendor_prefix(self):
        self.stock('CustomText.ttf',family='',points=tuple(range(32,129)))
        self.slots['/system/fonts/CustomText.ttf']['source']='verified-scan'
        self.build();self.assertTrue((self.fonts/'CustomText.ttf').exists())

    def test_path_traversal_in_inventory_is_rejected(self):
        data={'slots':{'/system/fonts/../../outside.ttf':next(iter(self.slots.values()))}}
        self.assertFalse(batch.inventory_target(data,'/system/fonts/../../outside.ttf'))
        self.assertFalse(batch.inventory_target(data,'/system/fonts/nested/file.ttf'))

    def test_stock_collection_under_ttf_name_is_not_flattened(self):
        name='Roboto-Collection.ttf';path=self.stock(name)
        self.slots['/system/fonts/'+name]['format']='TTC'
        make_font(self.fonts/name);self.build(['MiSansVF.ttf',name])
        self.assertFalse((self.fonts/name).exists());self.assertTrue(path.exists())

    def test_stock_nonzero_face_index_is_not_flattened(self):
        name='GoogleSans-Regular.ttf';self.stock(name)
        self.slots['/system/fonts/'+name]['faceIndex']=2
        make_font(self.fonts/name);self.build(['MiSansVF.ttf',name])
        self.assertFalse((self.fonts/name).exists())

    def test_real_variable_donor_generates_different_static_weight_outlines(self):
        variable_font(self.fonts/'400.ttf')
        before=(self.fonts/'400.ttf').read_bytes()
        names=['Roboto-Light.ttf','Roboto-Bold.ttf','Roboto-ExtraBold.ttf']
        for name in names:self.stock(name)
        self.build(['MiSansVF.ttf',*names]); actual=[]
        for name,weight in zip(names,(300,700,800)):
            with TTFont(self.fonts/name) as out:
                self.assertNotIn('fvar',out)
                self.assertEqual(out['OS/2'].usWeightClass,weight)
                actual.append(bounds(out)[2])
                with TTFont(self.fonts/'400.ttf') as src:
                    self.assertEqual(bounds(out),bounds(src,location={'wght':weight}))
            self.assertEqual(self.by_slot['/system/fonts/'+name]['weightAction'],'variable-instanced')
        self.assertTrue(actual[0] < actual[1] < actual[2],actual)
        self.assertEqual(before,(self.fonts/'400.ttf').read_bytes())

    def test_variable_container_retains_nondefault_dynamic_weights(self):
        variable_font(self.fonts/'400.ttf');self.build()
        with TTFont(self.fonts/'400.ttf') as src,TTFont(self.fonts/'MiSansVF.ttf') as out:
            self.assertIn('fvar',out)
            self.assertEqual(bounds(src,location={'wght':800}),bounds(out,location={'wght':800}))
            self.assertNotEqual(bounds(out,location={'wght':100}),bounds(out,location={'wght':800}))

    def test_xml_weight_drives_unknown_static_slot(self):
        variable_font(self.fonts/'400.ttf');self.stock('VendorFace.ttf',weight=650)
        self.build()
        with TTFont(self.fonts/'VendorFace.ttf') as font:self.assertEqual(font['OS/2'].usWeightClass,650)

    def test_explicit_named_weight_precedes_default_inventory_weight(self):
        self.stock('Roboto-ExtraBold.ttf',weight=400)
        self.assertEqual(weights.requested_weight({'slots':self.slots},'/system/fonts/Roboto-ExtraBold.ttf'),800)

    def test_legacy_family_anchor_used_for_new_bold_clock_target(self):
        store=self.fonts/'.luoshu-font-store';store.mkdir()
        make_font(store/'bold.font')
        with TTFont(store/'bold.font') as font:
            font['OS/2'].usWeightClass=700;font.save(store/'bold.font')
        self.stock('MiClock-Bold.ttf')
        self.build(['MiSansVF.ttf','MiClock-Bold.ttf'])
        with TTFont(self.fonts/'MiClock-Bold.ttf') as font:self.assertEqual(font['OS/2'].usWeightClass,700)

    def test_single_static_font_is_not_faked_as_a_bold_font(self):
        source=self.fonts/'400.ttf'
        result,report=weights.prepare(source,self.root/'out.font',700,False)
        self.assertEqual(result,source);self.assertFalse((self.root/'out.font').exists())
        self.assertTrue(report['weightFallback']);self.assertEqual(report['actualWeight'],400)

    def test_variable_axis_clamp_is_explicit_in_report(self):
        source=self.fonts/'400.ttf';variable_font(source)
        _,report=weights.prepare(source,self.root/'out.font',1000,False)
        self.assertEqual(report['actualWeight'],900);self.assertTrue(report['weightFallback'])

    def test_same_source_weight_prepared_only_once_across_partitions(self):
        variable_font(self.fonts/'400.ttf')
        self.stock('Roboto-Bold.ttf');self.stock('Roboto-Bold.ttf',part='product')
        with patch.object(weights,'prepare',wraps=weights.prepare) as prep:
            self.build(['MiSansVF.ttf','Roboto-Bold.ttf'])
            self.assertEqual(sum(call.args[2]==700 for call in prep.call_args_list),1)
        self.assertFalse(list((self.fonts/'.luoshu-font-store').glob('hyperos-metrics-*')))

    def test_failed_weight_preparation_removes_workdir_and_preserves_source(self):
        source=self.fonts/'400.ttf';before=source.read_bytes();self.save_inventory()
        with patch.object(weights,'prepare',side_effect=ValueError('bad axis')):
            with self.assertRaisesRegex(ValueError,'bad axis'):batch.build(self.module,self.stage,['MiSansVF.ttf'])
        self.assertEqual(source.read_bytes(),before)
        self.assertFalse(list((self.fonts/'.luoshu-font-store').glob('hyperos-metrics-*')))

    def test_cleanup_is_idempotent_on_every_partition(self):
        for part in ('system','product','vendor'):
            self.stock('DroidSansMono.ttf',part=part,family='monospace')
            target=self.stage/part/'fonts/DroidSansMono.ttf';target.parent.mkdir(parents=True,exist_ok=True)
            make_font(target)
        self.save_inventory();first=policy.cleanup(self.module,self.stage)
        second=policy.cleanup(self.module,self.stage)
        self.assertEqual(len(first['removedStagedAliases']),3)
        self.assertEqual(second['removedStagedAliases'],[])
        self.assertEqual(first['preservedStockPaths'],second['preservedStockPaths'])

    def test_boot_repair_does_not_recreate_protected_named_ui_alias(self):
        name='Roboto-Regular.ttf';self.stock(name,family='monospace');make_font(self.fonts/name)
        self.build(['MiSansVF.ttf',name]);self.assertFalse((self.fonts/name).exists())
        env={**os.environ,'IS_HYPEROS':'true','LUOSHU_REAL_MODDIR':str(self.module),
             'LUOSHU_HYPEROS_CLOCK_PAYLOAD_ROOT':str(self.stage)}
        helper=ROOT/'common/legacy_v14_4/hyperos_clock_compat.sh'
        subprocess.run(['sh','-c','. "$1"; luoshu_hyperos_clock_payload_ensure','sh',str(helper)],env=env,check=True)
        self.assertFalse((self.fonts/name).exists())

    def test_mono_xml_retains_index_axes_and_alias_graph(self):
        xml='<familyset><family name="monospace" supportedAxes="wght"><font index="2" weight="700">Custom.ttc<axis tag="wght" stylevalue="700"/></font></family><alias name="ui-monospace" to="monospace"/></familyset>'
        tree=ET.ElementTree(ET.fromstring(xml));before=ET.tostring(tree.getroot())
        result=rewrite_tree(tree,'LuoShu')
        self.assertFalse(result['changed']);self.assertEqual(before,ET.tostring(tree.getroot()))

    def test_known_fixed_pitch_metadata_protects_unknown_name(self):
        # A genuinely unclassified fixed-pitch face must remain stock.
        self.stock('VendorFixedFace.ttf', family='')
        self.slots['/system/fonts/VendorFixedFace.ttf']['metrics']['isFixedPitch']=True
        make_font(self.fonts/'VendorFixedFace.ttf');self.build()
        self.assertFalse((self.fonts/'VendorFixedFace.ttf').exists())

    def test_new_stock_metadata_captures_axis_weight_and_digits(self):
        source=self.fonts/'400.ttf';variable_font(source);_,metrics=inventory._read_metrics(source)
        self.assertEqual(metrics['weightClass'],400)
        self.assertEqual(metrics['variationAxes'][0]['tag'],'wght')
        self.assertEqual(metrics['coverage']['digitCount'],10)
        self.assertTrue(valid_coverage(metrics['coverage']))
        metrics['coverage']['digitCount']=20
        self.assertFalse(valid_coverage(metrics['coverage']))

    def test_cleanup_refuses_live_descendant_and_external_font_symlink(self):
        live=self.module/'.luoshu-payload';(live/'nested').mkdir(parents=True)
        for target in (self.module,live,live/'nested'):
            with self.assertRaises(ValueError):policy.cleanup(self.module,target)
        external=self.root/'external';external.mkdir()
        (self.stage/'product').mkdir();(self.stage/'product/fonts').symlink_to(external)
        with self.assertRaises(ValueError):policy.cleanup(self.module,self.stage)

    def test_font_task_finishes_with_zero_owned_processes(self):
        # Run an actual staging build under the existing one-shot task owner.
        variable_font(self.fonts/'400.ttf');self.stock('Roboto-Bold.ttf');self.save_inventory()
        command=[sys.executable,str(ROOT/'common/task_scope.py'),'--timeout','20','--',
                 sys.executable,str(ROOT/'common/hyperos_metrics_batch.py'),str(self.module),str(self.stage)]
        result=subprocess.run(command,input='MiSansVF.ttf\nRoboto-Bold.ttf\n',capture_output=True,text=True,timeout=25)
        self.assertEqual(result.returncode,0,result.stderr)
        report=json.loads(next(line.removeprefix('[TASK-CLEANUP] ') for line in result.stderr.splitlines()
                               if line.startswith('[TASK-CLEANUP] ')))
        self.assertEqual(report['leftoverPids'],[]);self.assertEqual(report['result'],0)

    def test_legacy_xml_slot_discovery_does_not_offer_code_fonts(self):
        from font_config_targets import discover
        xml=self.root/'fonts.xml'
        xml.write_text('<familyset><family name="sans-serif"><font weight="400">Roboto-Regular.ttf</font></family>'
                       '<family name="monospace"><font index="2">PrivateTerminal.ttc</font></family>'
                       '<family name="sans-serif-monospace"><font>RobotoMono-Regular.ttf</font></family></familyset>')
        self.assertEqual([r['filename'] for r in discover(xml)], ['Roboto-Regular.ttf'])

    def test_legacy_weight_finalizer_no_longer_generates_monospace(self):
        donor=self.fonts/'400.ttf'; make_font(donor, tuple(range(32,127)))
        script = '. "$1/common/font_config_weights.sh"; . "$1/common/font_finalize_hotfix.sh"; '
        script += '_luoshu_config_weight_source() { printf "%s\\n" "$DONOR"; }; '
        script += 'is_variable_font() { return 1; }; font_config_prepare_payload_weights'
        env={**os.environ,'DONOR':str(donor),'MODULE_DIR':str(self.module),'MODDIR':str(self.module)}
        # The preserved XML backend uses module/system/fonts, separate from the
        # active safe-switch next-boot tree. Both must honor stock monospace.
        result=subprocess.run(['sh','-c',script,'test',str(ROOT)],env=env,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        generated=self.module/'system/fonts'
        self.assertEqual(len(list(generated.glob('LuoShu-*.ttf'))),9)
        self.assertEqual(list(generated.glob('LuoShuMono-*.ttf')),[])

    def test_new_stage_drops_previous_payload_role_sidecars(self):
        source=(ROOT/'common/legacy_v14_4/font_switch_safe.sh').read_text()
        function=source.split('stage_clear_text_payload() {',1)[1].split('\n}\n',1)[0]
        for name in ['.luoshu-stock-preserved.paths','.luoshu-font-role-report.json','.luoshu-metrics-report.json']:
            (self.stage/name).write_text('previous font metadata')
        command='safe_partition_list() { echo system; }; stage_clear_text_payload() {'+function+'\n}; stage_clear_text_payload'
        result=subprocess.run(['sh','-c',command],env={**os.environ,'STAGE_PAYLOAD':str(self.stage)},capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse((self.stage/'.luoshu-stock-preserved.paths').exists())
        self.assertFalse((self.stage/'.luoshu-metrics-report.json').exists())
        self.assertTrue(self.fonts.is_dir())

if __name__=='__main__':unittest.main()
