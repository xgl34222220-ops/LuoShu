import sys,tempfile,unittest
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[2]/'scripts'),str(Path(__file__).resolve().parents[2]/'common')]
import universal_font_compiler_test as fixture
import fixed_weight_match as experiment
from fontTools.ttLib import TTFont
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString


class MatchingAxisTest(unittest.TestCase):
    def test_real_roundtrips_constant_geometry_with_honest_scope(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'fixed.ttf';out=Path(td)/'match.ttf'
            fixture.make_font(source,family='Fixed selection',weight=520)
            with TTFont(source) as font:
                addOpenTypeFeaturesFromString(font,'feature liga { sub u0066 u0069 by u0041; } liga; feature kern { pos u0041 u0056 -40; } kern; table GDEF { GlyphClassDef [u0041 u0066 u0069], [], [u0027], []; } GDEF;')
                self.assertTrue({'GSUB','GPOS','GDEF'}<=set(font.keys()))
                font.save(source)
            before=source.read_bytes();result=experiment.build(source,out)
            self.assertEqual(source.read_bytes(),before);self.assertFalse(result['deviceDeployable'])
            self.assertFalse(result['nativeConsumerVerified']);self.assertEqual(result['sourceWeight'],520)
            self.assertEqual(result['verifiedCoordinates'],[1,100,400,450,520,700,900,1000])

    def test_existing_variable_source_cannot_be_relabelled(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'variable.ttf';fixture.make_font(source,family='Variable',variable=True)
            with self.assertRaisesRegex(ValueError,'static'):experiment.build(source,Path(td)/'out.ttf')

    def test_source_path_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'fixed.ttf';fixture.make_font(source,family='Fixed')
            with self.assertRaisesRegex(ValueError,'immutable'):experiment.build(source,source)


if __name__=='__main__':unittest.main()
