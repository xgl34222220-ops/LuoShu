"""Explicit XML-only, constant-outline weight-selection contract.

The axis is for Android variable-family selection, never evidence of preserved
donor variation or permission to replace an OEM physical VF. Constant response
is proved structurally, including absence of axis-dependent shaping and metrics.
"""
from fontTools.ttLib import newTable
from fontTools.ttLib.tables._f_v_a_r import Axis

STATIC = 'fixed-static-xml-v1'
MATCHING = 'fixed-outline-weight-match-xml-v1'
REPRESENTATIONS = frozenset({STATIC, MATCHING})
PAYLOAD_KINDS = frozenset({'xml-static-font', 'xml-matching-font'})
FORBIDDEN = frozenset({'avar','MVAR','HVAR','VVAR','cvar','VARC','CFF2','COLR','SVG '})


def policy(weight):
    if type(weight) is not int or not 1 <= weight <= 1000:
        raise ValueError('invalid fixed source metadata weight')
    return {'policy':'fixed-outline-selection-axis-v1','tag':'wght','min':1,'default':weight,
            'max':1000,'shapeResponse':'constant','sourceVariationPreserved':False}


def _layout(font):
    if (int(font['OS/2'].fsSelection)&((1<<0)|(1<<9)) or int(font['head'].macStyle)&2
            or float(font['post'].italicAngle)!=0):
        raise ValueError('fixed matching contract requires upright metadata')
    for tag in ('GSUB','GPOS'):
        if tag in font and getattr(font[tag].table,'FeatureVariations',None) is not None:
            raise ValueError('fixed matching axis cannot activate variable shaping: '+tag)
    for tag in ('GDEF','BASE'):
        if tag in font and getattr(font[tag].table,'VarStore',None) is not None:
            raise ValueError('fixed matching axis cannot activate layout variation store: '+tag)


def attach(font, expected):
    if expected != policy(int(font['OS/2'].usWeightClass)):
        raise ValueError('fixed matching policy differs from source metadata')
    if 'glyf' not in font or ({'fvar','gvar'} | FORBIDDEN) & set(font.keys()):
        raise ValueError('matching axis requires an already verified static glyf asset')
    _layout(font)
    axis=Axis();axis.axisTag='wght';axis.minValue=1;axis.defaultValue=expected['default'];axis.maxValue=1000;axis.flags=0
    axis.axisNameID=font['name'].addName('Fixed outline matching weight')
    fvar=newTable('fvar');fvar.axes=[axis];fvar.instances=[];font['fvar']=fvar
    gvar=newTable('gvar');gvar.version=1;gvar.reserved=0;gvar.variations={name:[] for name in font.getGlyphOrder()};font['gvar']=gvar
    return validate(font,expected)


def validate(font,expected):
    if expected != policy(int(font['OS/2'].usWeightClass)) or FORBIDDEN & set(font.keys()):
        raise ValueError('fixed matching metric/outline policy changed')
    if 'glyf' not in font or 'fvar' not in font or 'gvar' not in font:
        raise ValueError('fixed matching tables missing')
    axes=font['fvar'].axes
    if len(axes)!=1 or font['fvar'].instances:
        raise ValueError('fixed matching axis repertoire changed')
    axis=axes[0]
    if (axis.axisTag!='wght' or float(axis.minValue)!=1 or float(axis.defaultValue)!=expected['default']
            or float(axis.maxValue)!=1000 or axis.flags!=0):
        raise ValueError('fixed matching axis bounds changed')
    variations=font['gvar'].variations
    if set(variations)!=set(font.getGlyphOrder()) or any(variations[name] for name in variations):
        raise ValueError('fixed matching outline response is not constant')
    _layout(font)
    return {'state':'verified','method':'empty-glyph-variation-and-no-variable-metrics-or-layout',
            'domain':{'wght':[1,1000]},'shapeResponse':'constant','sourceVariationPreserved':False}
