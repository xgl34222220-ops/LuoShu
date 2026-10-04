"""Selector regressions only; synthetic XML is not Android UI evidence."""
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from app_axis_gate import slot_chooser, clickable_text_targets, detail_headings, library_preflight_ok
from app_library_gate import PACKAGE


def tree(extra='', enabled='true'):
    return ET.fromstring(f'''<hierarchy><node package="{PACKAGE}">
      <node package="{PACKAGE}"><node package="{PACKAGE}" text="中文基底" bounds="[0,70][200,95]"/>
        <node package="{PACKAGE}" text="完整中文、符号与系统回退基底" bounds="[0,95][200,99]"/>
        <node package="{PACKAGE}" clickable="true" enabled="{enabled}" bounds="[0,100][200,150]">
          <node package="{PACKAGE}" text="Same Font"/>
        </node>{extra}
      </node>
      <node package="{PACKAGE}"><node package="{PACKAGE}" text="英文字形" bounds="[0,260][200,290]"/>
        <node package="{PACKAGE}" clickable="true" enabled="true" bounds="[0,300][200,350]">
          <node package="{PACKAGE}" text="Same Font"/>
        </node>
      </node>
    </node></hierarchy>''')


class AppAxisSelectorTest(unittest.TestCase):
    def test_live_preflight_rejects_missing_stale_failed_or_replaced_session(self):
        import copy
        from test_verdict import valid_delivery
        value=valid_delivery()['app_axes']['library_preflight']
        self.assertTrue(library_preflight_ok(value,'123'))
        self.assertFalse(library_preflight_ok({},'123'))
        for change in ('unverified','failed-request','different-pid','stale-request','missing-detail'):
            changed=copy.deepcopy(value);sample=changed['samples'][0]
            if change=='unverified':sample['verified']=False
            elif change=='failed-request':sample['request_timings'][0]['code']=124
            elif change=='different-pid':sample['pid']='456'
            elif change=='stale-request':sample['request_timings'][0]['completed_at_ms']=0
            else:sample['request_timings'][0]['phases'].pop('inventory_detail')
            self.assertFalse(library_preflight_ok(changed,'123'),change)

    def test_same_click_moves_outside_actual_fresh_chooser_during_loading(self):
        import re
        original=ET.parse(Path(__file__).with_name('fixtures')/'axis-loading-37184908266.xml').getroot()
        loaded=ET.parse(Path(__file__).with_name('fixtures')/'axis-loaded-37184908266.xml').getroot()
        initial,_=slot_chooser(original,'中文基底',['LuoShuAxisGate','LuoShuSyntheticGate0000','LuoShuSyntheticGate0001'])
        final,_=slot_chooser(loaded,'中文基底',['LuoShuAxisGate','LuoShuSyntheticGate0000','LuoShuSyntheticGate0001'])
        from android_ui_smoke import center
        x,y=center(initial);left,top,right,bottom=map(int,re.findall(r'\d+',final.get('bounds')))
        self.assertFalse(left <= x <= right and top <= y <= bottom)
        self.assertEqual((x,y),(540,1164))
        self.assertEqual(final.get('bounds'),'[95,1179][985,1359]')

    def test_actual_recorded_summary_and_detail_titles_bind_only_to_detail(self):
        # Replay protects selection logic; it is not a new Android execution.
        raw = Path(__file__).with_name('fixtures') / 'axis-navigation-37160499707.xml'
        tree = ET.parse(raw).getroot()
        target, region = slot_chooser(tree, '中文基底', ['LuoShuSyntheticGate0000', 'LuoShuSyntheticGate0001'])
        self.assertEqual(target.get('bounds'), '[95,1179][985,1359]')
        self.assertGreater(region[0], 900)
        english = detail_headings(tree, '英文字形')
        self.assertEqual([n.get('bounds') for n in english], ['[243,1881][431,1920]'])

    def test_summary_only_is_neither_a_card_chooser_nor_a_scanning_endpoint(self):
        raw = ET.fromstring(f'<hierarchy><node package="{PACKAGE}" clickable="true"><node package="{PACKAGE}" text="英文字形" bounds="[0,100][200,200]"/></node></hierarchy>')
        self.assertEqual(detail_headings(raw, '英文字形'), [])

    def test_detailed_card_requires_its_exact_explanation(self):
        raw = tree()
        for node in raw.iter('node'):
            if node.get('text') == '完整中文、符号与系统回退基底':
                node.set('text', 'Different card')
        with self.assertRaises(ValueError):
            slot_chooser(raw, '中文基底', ['Same Font'])

    def test_same_font_in_another_slot_is_not_the_cjk_chooser(self):
        target, region = slot_chooser(tree(), '中文基底', ['Same Font'])
        self.assertEqual(target.get('bounds'), '[0,100][200,150]')
        self.assertGreater(region[0], 0)
        self.assertLess(region[1], 300)

    def test_foreign_package_lookalikes_are_not_candidates(self):
        raw = ET.fromstring('<hierarchy><node package="foreign.app" text="Same Font" clickable="true" enabled="true" bounds="[0,0][200,100]"/></hierarchy>')
        self.assertEqual(clickable_text_targets(raw, {'Same Font'}), [])
        with self.assertRaises(ValueError):
            slot_chooser(raw, '中文基底', ['Same Font'])

    def test_disabled_chooser_does_not_redirect_to_another_slot(self):
        with self.assertRaises(ValueError):
            slot_chooser(tree(enabled='false'), '中文基底', ['Same Font'])

    def test_ambiguous_cjk_chooser_is_rejected(self):
        extra = f'<node package="{PACKAGE}" clickable="true" enabled="true" bounds="[0,160][200,200]"><node package="{PACKAGE}" text="Same Font"/></node>'
        with self.assertRaises(ValueError):
            slot_chooser(tree(extra), '中文基底', ['Same Font'])


if __name__ == '__main__':
    unittest.main()
