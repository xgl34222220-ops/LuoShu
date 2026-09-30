"""Build only original synthetic donors with the real LuoShu compositor."""
from pathlib import Path
from argparse import Namespace
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'common/legacy_v14_4'),str(ROOT/'scripts')]
import universal_font_compiler_test as fixture
from fontTools.ttLib import TTFont
from fontTools.pens.ttGlyphPen import TTGlyphPen
import composite_font
import font_coverage
OUT=Path(__file__).parent/'app/src/main/assets'
OUT.mkdir(parents=True,exist_ok=True)
points=tuple(sorted(set(range(32,127))|set(range(0x4e00,0x4e00+6100))|set(font_coverage.CJK_COMMON)))
fixture.ASCII_POINTS=points
shapes={
 'cjk':[(50,-100),(480,-100),(550,60),(550,700),(300,800),(50,700)],
 'latin':[(50,0),(550,0),(300,700)],
 'digit':[(50,0),(550,0),(550,520),(300,700),(50,520)]}
for role,shape in shapes.items():
 path=OUT/(role+'.ttf');fixture.make_font(path,family='LuoShuSynthetic'+role)
 with TTFont(path) as f:
  for cp in points:
   is_role=(cp>=0x4e00 if role=='cjk' else (48<=cp<=57 if role=='digit' else (65<=cp<=90 or 97<=cp<=122)))
   if not is_role:continue
   current_shape=shape
   if role=='latin' and 97<=cp<=122:
    bottom=-200 if chr(cp) in 'gjpqy' else 0
    current_shape=[(50,bottom),(550,bottom),(300,500)]
   pen=TTGlyphPen(None);pen.moveTo(current_shape[0])
   for p in current_shape[1:]:pen.lineTo(p)
   pen.closePath();name=f.getBestCmap()[cp];f['glyf'][name]=pen.glyph()
   if role=='cjk':f['hmtx'].metrics[name]=(1000,50)
  f.save(path)
result=composite_font.build(Namespace(cjk=str(OUT/'cjk.ttf'),latin=str(OUT/'latin.ttf'),digit=str(OUT/'digit.ttf'),
 output=str(OUT/'composite.ttf'),weight=400,cjk_face=0,latin_face=0,digit_face=0,progress=None))
with TTFont(OUT/'composite.ttf') as f:
 assert 'fvar' not in f and 'MVAR' not in f
 for cp,expected in [(ord('A'),3),(ord('1'),5),(ord('中'),6)]:
  glyph=f['glyf'][f.getBestCmap()[cp]];assert len(glyph.getCoordinates(f['glyf'])[0])==expected
 assert 0x03a9 not in f.getBestCmap() and 0x1f600 not in f.getBestCmap()
# Independent expected geometry for this fixed fixture: the compositor's
# documented Latin/digit UI top is 826, so 700-unit donors scale by 1.18.
# Horizontal origin is the scaled 40-unit LSB (47 after integer rounding).
# Do not copy glyphs or metrics from the composite under test.
expected={
 'latin':(65,[(47,0),(637,0),(342,826)],(732,47)),
 'digit':(49,[(47,0),(637,0),(637,614),(342,826),(47,614)],(732,47)),
 'cjk':(0x4e2d,shapes['cjk'],(1000,50))}
for role,(cp,outline,metrics) in expected.items():
 path=OUT/('expected-'+role+'.ttf')
 fixture.make_font(path,family='LuoShuExpected'+role)
 with TTFont(path) as reference:
  name=reference.getBestCmap()[cp];pen=TTGlyphPen(None);pen.moveTo(outline[0])
  for point in outline[1:]:pen.lineTo(point)
  pen.closePath();reference['glyf'][name]=pen.glyph();reference['hmtx'].metrics[name]=metrics
  # The compositor fixes the family line box and disables the xMin=LSB hint.
  reference['head'].flags=1
  reference['hhea'].ascent=928;reference['hhea'].descent=-244
  os2=reference['OS/2'];os2.version=4;os2.fsSelection=128
  os2.sTypoAscender=928;os2.sTypoDescender=-244
  os2.usWinAscent=928;os2.usWinDescent=244;os2.sxHeight=826;os2.sCapHeight=826
  reference.save(path)
 with TTFont(OUT/'composite.ttf') as actual:
  name=actual.getBestCmap()[cp]
  assert list(actual['glyf'][name].getCoordinates(actual['glyf'])[0])==outline
  assert actual['hmtx'].metrics[name]==metrics
report={'postScriptName':TTFont(OUT/'composite.ttf')['name'].getDebugName(6),'synthetic':True,'static':True,'compositor':result,'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('*.ttf')}}
with TTFont(OUT/'composite.ttf') as f:
 report['nativeGlyphIds']=[f.getGlyphID(f.getBestCmap()[cp]) for cp in [65,49,0x4e2d]]
 report['nativeAdvances']=[f['hmtx'].metrics[f.getBestCmap()[cp]][0] for cp in [65,49,0x4e2d]]
 report['unitsPerEm']=f['head'].unitsPerEm
(OUT/'fixture.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':'pass','static':True,'donorPointCounts':[3,5,6],'bytes':(OUT/'composite.ttf').stat().st_size}))
