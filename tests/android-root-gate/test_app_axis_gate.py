"""Selector regressions only; synthetic XML is not Android UI evidence."""
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from app_axis_gate import slot_chooser, clickable_text_targets, detail_headings
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
