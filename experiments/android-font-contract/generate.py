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
OUT=Path(__file__).parent/'app/src/main/assets'
OUT.mkdir(parents=True,exist_ok=True)
points=tuple(sorted(set(range(32,127))|set(range(0x4e00,0x4e00+6100))))
fixture.ASCII_POINTS=points
shapes={
 'cjk':[(50,0),(480,0),(550,160),(550,540),(300,700),(50,540)],
 'latin':[(50,0),(550,0),(300,700)],
 'digit':[(50,0),(550,0),(550,520),(300,700),(50,520)]}
for role,shape in shapes.items():
 path=OUT/(role+'.ttf');fixture.make_font(path,family='LuoShuSynthetic'+role)
 with TTFont(path) as f:
  for cp in points:
   is_role=(cp>=0x4e00 if role=='cjk' else (48<=cp<=57 if role=='digit' else (65<=cp<=90 or 97<=cp<=122)))
   if not is_role:continue
   pen=TTGlyphPen(None);pen.moveTo(shape[0])
   for p in shape[1:]:pen.lineTo(p)
   pen.closePath();name=f.getBestCmap()[cp];f['glyf'][name]=pen.glyph()
  f.save(path)
result=composite_font.build(Namespace(cjk=str(OUT/'cjk.ttf'),latin=str(OUT/'latin.ttf'),digit=str(OUT/'digit.ttf'),
 output=str(OUT/'composite.ttf'),weight=400,cjk_face=0,latin_face=0,digit_face=0,progress=None))
with TTFont(OUT/'composite.ttf') as f:
 assert 'fvar' not in f and 'MVAR' not in f
 for cp,expected in [(ord('A'),3),(ord('1'),5),(ord('中'),6)]:
  glyph=f['glyf'][f.getBestCmap()[cp]];assert len(glyph.getCoordinates(f['glyf'])[0])==expected
 assert 0x03a9 not in f.getBestCmap() and 0x1f600 not in f.getBestCmap()
report={'postScriptName':TTFont(OUT/'composite.ttf')['name'].getDebugName(6),'synthetic':True,'static':True,'compositor':result,'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('*.ttf')}}
(OUT/'fixture.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':'pass','static':True,'donorPointCounts':[3,5,6],'bytes':(OUT/'composite.ttf').stat().st_size}))
