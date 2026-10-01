"""Non-deployable fixed-outline weight-selection experiment.

This is deliberately not a donor variation synthesizer. Its wght axis has a
constant outline/advance/line response and exists only to investigate Android
variable-family matching. It must never enter a generic source-VF or physical
replacement path. Production geometry and native acceptance remain separate.
"""
import hashlib
from pathlib import Path
from fontTools.ttLib import TTFont,newTable
from fontTools.ttLib.tables._f_v_a_r import Axis
from fontTools.varLib.instancer import instantiateVariableFont,OverlapMode


def geometry(font):
    glyphs={}
    for name in font.getGlyphOrder():
        coords,ends,flags=font['glyf'][name].getCoordinates(font['glyf'])
        glyphs[name]=(tuple(tuple(p) for p in coords),tuple(ends),tuple(flags),font['hmtx'].metrics[name])
    return (glyphs,dict(font.getBestCmap()),font['head'].unitsPerEm,
            tuple(getattr(font['hhea'],k) for k in ('ascent','descent','lineGap')),
            tuple(getattr(font['OS/2'],k) for k in ('sTypoAscender','sTypoDescender','sTypoLineGap','usWinAscent','usWinDescent')))


def build(source,output):
    source,output=Path(source),Path(output)
    if source.resolve()==output.resolve():raise ValueError('source must remain immutable')
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    with TTFont(source,recalcTimestamp=False) as font:
        if 'glyf' not in font or set(font.keys())&{'fvar','gvar','MVAR','HVAR','VVAR','cvar','VARC','CFF2','COLR','SVG '}:
            raise ValueError('prototype requires a plain static TrueType asset')
        if font['OS/2'].fsSelection&1 or font['head'].macStyle&2 or font['post'].italicAngle:
            raise ValueError('prototype requires upright outlines')
        source_weight=int(font['OS/2'].usWeightClass)
        if not 1<=source_weight<=1000:raise ValueError('invalid fixed source weight')
        expected=geometry(font)
        layout={tag:font.getTableData(tag) for tag in ('GSUB','GPOS','GDEF') if tag in font}
        axis=Axis();axis.axisTag='wght';axis.minValue=1;axis.defaultValue=source_weight;axis.maxValue=1000;axis.flags=0
        axis.axisNameID=font['name'].addName('Fixed outline matching weight')
        fvar=newTable('fvar');fvar.axes=[axis];fvar.instances=[];font['fvar']=fvar
        gvar=newTable('gvar');gvar.version=1;gvar.reserved=0;gvar.variations={name:[] for name in font.getGlyphOrder()};font['gvar']=gvar
        font.save(output)
    coordinates=(1,100,400,450,520,700,900,1000)
    with TTFont(output,recalcTimestamp=False) as font:
        for weight in coordinates:
            instance=instantiateVariableFont(font,{'wght':weight},inplace=False,
                                            overlap=OverlapMode.KEEP_AND_DONT_SET_FLAGS)
            try:
                if geometry(instance)!=expected:raise ValueError('matching axis changed fixed geometry')
                if any(instance.getTableData(tag)!=data for tag,data in layout.items()):raise ValueError('matching axis changed static shaping')
            finally:instance.close()
    if hashlib.sha256(source.read_bytes()).hexdigest()!=before:raise ValueError('source changed')
    return {'schema':'experimental-fixed-outline-matching-axis-v1','deviceDeployable':False,
            'sourceSha256':before,'outputSha256':hashlib.sha256(output.read_bytes()).hexdigest(),
            'sourceWeight':source_weight,'axisPurpose':'platform weight selection only',
            'shapeResponse':'constant; no donor weight variation claimed','verifiedCoordinates':list(coordinates),
            'requiresProductionGeometryProof':True,'nativeConsumerVerified':False}
