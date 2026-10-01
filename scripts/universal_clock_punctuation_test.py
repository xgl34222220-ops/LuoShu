#!/usr/bin/env python3
"""Required clock digits change; unsafe optional punctuation stays original."""
import json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'common'),str(ROOT/'scripts')]
from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.pens.ttGlyphPen import TTGlyphPen
import universal_font_compiler as compiler
import universal_font_compiler_test as fixture

class ClockPunctuationTest(unittest.TestCase):
 def test_rejected_transform_cannot_silently_become_upem_scaling(self):
  with self.assertRaisesRegex(compiler.CompilerError,'cannot fall back'):
   compiler._transform_for_codepoint({'upemScale':2,'transforms':{'punctuationBaseline':{'status':'unsafe','risks':['advance-width']}}},ord(':'),True)

 def test_narrow_colon_is_preserved_and_digits_are_compiled(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'source.ttf';stock=root/'AndroidClock.ttf'
   fixture.make_font(source,family='Source');fixture.make_font(stock,family='Clock')
   with TTFont(stock) as font:
    sub=subset.Subsetter();sub.populate(text='0123456789:');sub.subset(font)
    name=font.getBestCmap()[ord(':')];pen=TTGlyphPen(None);pen.moveTo((30,100));pen.lineTo((80,100));pen.lineTo((80,600));pen.lineTo((30,600));pen.closePath();font['glyf'][name]=pen.glyph();font['hmtx'].metrics[name]=(120,30);font.save(stock)
   with TTFont(source) as font:
    name=font.getBestCmap()[ord('1')];pen=TTGlyphPen(None);pen.moveTo((40,-120));pen.lineTo((570,-120));pen.lineTo((250,720));pen.closePath();font['glyf'][name]=pen.glyph();font.save(source)
   before_source=source.read_bytes();before_stock=stock.read_bytes();logical='/system/fonts/AndroidClock.ttf'
   slot=fixture.slot_from_stock(logical,stock,family='',source_xml=None,declared='AndroidClock.ttf')
   plan,route=fixture.build_plans(source,slot,'clock',None)
   result=compiler.compile_all(plan,route,{logical:stock},root/'out',False)
   self.assertTrue(result['summary']['deploymentReady'],result)
   import universal_font_deployment as deployment, universal_font_cutover_gate as gate
   payload=root/'payload';deployed=deployment.build_deployment(plan,route,result,payload)
   decision=gate.evaluate(plan,route,result,deployed,payload)
   self.assertTrue(decision['eligible'],decision)
   self.assertEqual(decision['summary']['coverage'],'partial-protected-typography')
   self.assertEqual(decision['summary']['preservedClockPunctuation'],1)
   self.assertIn('partial-coverage:preserved-clock-punctuation:1',decision['warnings'])
   artifact=result['artifacts'][0];preserved=artifact['report']['replaced']['preservedOptionalPunctuation']
   self.assertEqual([x['codepoint'] for x in preserved],[ord(':')]);self.assertIn('advance-width',preserved[0]['risks'])
   with TTFont(stock) as original,TTFont(artifact['output']) as output:
    old=original.getBestCmap()[ord(':')];new=output.getBestCmap()[ord(':')]
    self.assertEqual(original['glyf'][old].compile(original['glyf']),output['glyf'][new].compile(output['glyf']))
    self.assertEqual(original['hmtx'].metrics[old],output['hmtx'].metrics[new])
    self.assertEqual(len(output['glyf'][output.getBestCmap()[ord('1')]].getCoordinates(output['glyf'])[0]),3)
    for cp in map(ord,'0123456789'):
     self.assertEqual(original['hmtx'].metrics[original.getBestCmap()[cp]][0],output['hmtx'].metrics[output.getBestCmap()[cp]][0])
   self.assertEqual(source.read_bytes(),before_source);self.assertEqual(stock.read_bytes(),before_stock)

 def test_required_digit_width_risk_still_blocks_whole_slot(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'source.ttf';stock=root/'clock.ttf'
   fixture.make_font(source,family='Wide digits',advance=2000);fixture.make_font(stock,family='Clock',advance=620)
   logical='/system/fonts/AndroidClock.ttf';slot=fixture.slot_from_stock(logical,stock,family='',source_xml=None,declared='AndroidClock.ttf')
   plan,route=fixture.build_plans(source,slot,'clock',None)
   result=compiler.compile_all(plan,route,{logical:stock},root/'out',False)
   self.assertFalse(result['summary']['deploymentReady']);self.assertEqual(result['summary']['readyCount'],0)
   self.assertIn('unsafe-probes:digits',result['artifacts'][0]['reason'])

 def test_clock_measurements_use_same_available_punctuation(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'source.ttf';stock=root/'stock.ttf'
   fixture.make_font(source,family='Source');fixture.make_font(stock,family='Clock')
   with TTFont(stock) as font:
    sub=subset.Subsetter();sub.populate(text='0123456789:');sub.subset(font);font.save(stock)
   with TTFont(stock) as target,TTFont(source) as donor:
    before=compiler._profile_from_font(donor)
    a,b=compiler._paired_geometry_profiles(target,donor,'clock',source_profile=before)
    self.assertEqual(a['sharedProbePoints']['punctuationBaseline'],[ord(':')])
    self.assertEqual(a['probes']['punctuationBaseline']['hits'],1)
    self.assertEqual(b['probes']['punctuationBaseline']['hits'],1)
    self.assertEqual(before['probes']['punctuationBaseline']['hits'],7)

if __name__=='__main__':unittest.main(verbosity=2)
