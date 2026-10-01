import unittest
import xml.etree.ElementTree as ET
import style_expansion as model


class StyleExpansion(unittest.TestCase):
    axes = {'wght': {'min': 100, 'default': 400, 'max': 900},
            'ital': {'min': 0, 'default': 0, 'max': 1},
            'wdth': {'min': 75, 'default': 100, 'max': 100}}
    xml = b'<familyset><family name="sans-serif"><font index="2" postScriptName="Lookup" supportedAxes="wght,ital">Original.ttc<axis tag="wdth" stylevalue="75"/></font></family></familyset>'

    def test_discrete_weights_and_exact_original_italic(self):
        result = model.plan_family(self.xml, 0, self.axes, (450, 520))
        self.assertFalse(result['deviceDeployable'])
        self.assertEqual([x['weight'] for x in result['normal']], [100, 200, 300, 400, 450, 500, 520, 600, 700, 800, 900])
        for item in result['italic']:
            node = ET.fromstring(item['originalNode'])
            self.assertEqual(node.text, 'Original.ttc')
            self.assertEqual(node.get('index'), '2')
            self.assertEqual(node.get('postScriptName'), 'Lookup')
            self.assertNotIn('supportedAxes', node.attrib)
            self.assertEqual({a.get('tag'): float(a.get('stylevalue')) for a in node},
                             {'wght': item['weight'], 'ital': 1, 'wdth': 75})
        self.assertEqual(result['normal'][0]['requestedOriginalAxes'], {'wdth': 75, 'wght': 100, 'ital': 0})

    def test_weight_only_keeps_no_invented_italic(self):
        result = model.plan_family(self.xml.replace(b'wght,ital', b'wght'), 0, self.axes)
        self.assertEqual(result['italic'], [])
        self.assertEqual(len(result['normal']), 9)

    def test_inherited_language_and_fallback_group_preserved(self):
        xml = b'<familyset><family-list lang="zh-Hant"><family><font supportedAxes="wght" fallbackFor="serif">Original.ttc</font><font fallbackFor="sans-serif">Other.ttf</font></family></family-list></familyset>'
        result = model.plan_family(xml, 0, self.axes)
        self.assertEqual(result['familyContext']['lang'], 'zh-Hant')
        self.assertIn('fallbackFor="serif"', result['originalNode'])

    def test_ambiguous_peer_rejected(self):
        xml = self.xml.replace(b'</family>', b'<font>Other.ttf</font></family>')
        with self.assertRaisesRegex(ValueError, 'ambiguous'): model.plan_family(xml, 0, self.axes)

    def test_unknown_style_axis_or_variant_rejected(self):
        for xml in (self.xml.replace(b'wght,ital', b'wght,slnt'), self.xml.replace(b'name="sans-serif"', b'variant="elegant"')):
            with self.assertRaises(ValueError): model.plan_family(xml, 0, self.axes)

    def test_axis_metadata_and_runtime_weight_validation(self):
        with self.assertRaises(ValueError): model.plan_family(self.xml, 0, {}, ())
        with self.assertRaises(ValueError): model.plan_family(self.xml, 0, self.axes, (0,))
        with self.assertRaises(ValueError): model.plan_family(self.xml, 0, self.axes, (1001,))


if __name__ == '__main__': unittest.main()
