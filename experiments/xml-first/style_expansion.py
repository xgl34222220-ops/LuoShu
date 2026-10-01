"""Non-deployable specification for an implicit variable XML font.

This returns requested render contracts, not font bytes or trusted bindings.
Each normal child still needs the production compiler's OEM geometry proof.
Italic children require an independently sealed original container. The native
consumer matrix must pass before this representation can enter production.
"""
import copy
import hashlib
import math
import xml.etree.ElementTree as ET


WEIGHTS = tuple(range(100, 1000, 100))


def plan_family(xml, ordinal, axes, extra_weights=()):
    root = ET.fromstring(xml)
    if root.tag != 'familyset':
        raise ValueError('unsupported document adapter')
    fonts = list(root.iter('font'))
    if type(ordinal) is not int or not 0 <= ordinal < len(fonts):
        raise ValueError('invalid original ordinal')
    parents = {child: parent for parent in root.iter() for child in parent}
    node = fonts[ordinal]
    family = parents[node]
    parent = parents.get(family)
    if family.tag != 'family' or parent is None:
        raise ValueError('unsupported family structure')
    if parent is not root and (parent.tag != 'family-list' or parents.get(parent) is not root):
        raise ValueError('unsupported inherited family structure')
    context = dict(parent.attrib if parent is not root else {})
    context.update(family.attrib)
    if context.get('variant'):
        raise ValueError('special family variant requires separate adapter')
    supported = set(node.get('supportedAxes', '').replace(' ', '').split(','))
    if supported not in ({'wght'}, {'wght', 'ital'}):
        raise ValueError('unsupported implicit axis contract')
    if node.get('style', 'normal') != 'normal':
        raise ValueError('explicit italic node is outside this prototype')
    for tag in supported:
        axis = axes.get(tag)
        if not isinstance(axis, dict) or not all(math.isfinite(float(axis.get(k, float('nan')))) for k in ('min', 'default', 'max')):
            raise ValueError('missing finite original axis metadata')
        if not axis['min'] <= axis['default'] <= axis['max']:
            raise ValueError('invalid original axis range')
    if 'ital' in supported and not (axes['ital']['min'] <= 0 < 1 <= axes['ital']['max']):
        raise ValueError('original face cannot supply both exact styles')
    fixed_axes, seen_axes = {}, set()
    for child in node:
        if child.tag != 'axis':
            raise ValueError('unknown font child cannot be expanded')
        tag = child.get('tag')
        value = float(child.get('stylevalue', 'nan'))
        if tag in seen_axes or tag not in axes or not math.isfinite(value):
            raise ValueError('invalid fixed original axis')
        seen_axes.add(tag)
        if tag not in supported:
            fixed_axes[tag] = value
    # A same-style peer in this matching group could change style selection.
    group = node.get('fallbackFor')
    if any(peer is not node and peer.tag == 'font' and peer.get('fallbackFor') == group
           for peer in family):
        raise ValueError('ambiguous matching group requires separate adapter')
    requested_weights = list(extra_weights)
    if any(type(w) is not int or not 1 <= w <= 1000 for w in requested_weights):
        raise ValueError('invalid declared weight')
    weights = sorted(set(WEIGHTS) | set(requested_weights))
    normal, italic = [], []
    for weight in weights:
        reference = dict(fixed_axes, wght=weight)
        if 'ital' in supported:
            reference['ital'] = 0
        normal.append({'weight': weight, 'style': 'normal',
                       'requestedOriginalAxes': reference,
                       'requiresMeasuredStaticAsset': True})
        if 'ital' in supported:
            kept = copy.deepcopy(node)
            kept.attrib.pop('supportedAxes', None)
            kept.set('weight', str(weight)); kept.set('style', 'italic')
            for child in list(kept): kept.remove(child)
            for tag, value in sorted(dict(fixed_axes, wght=weight, ital=1).items()):
                ET.SubElement(kept, 'axis', tag=tag, stylevalue=str(value))
            italic.append({'weight': weight, 'style': 'italic',
                           'originalNode': ET.tostring(kept, encoding='unicode'),
                           'requiresSealedOriginalAsset': True})
    return {'schema': 'experimental-explicit-style-plan-v1', 'deviceDeployable': False,
            'sourceXmlSha256': hashlib.sha256(xml).hexdigest(), 'ordinal': ordinal,
            'originalNode': ET.tostring(node, encoding='unicode'), 'familyContext': context,
            'normal': normal, 'italic': italic,
            'limits': ['discrete declared weights; arbitrary runtime weights use platform matching',
                       'italic keeps OEM glyphs rather than inventing a donor italic',
                       'normal assets and immutable original fallback remain unmaterialized',
                       'no native consumer or module activation proof for this expansion']}
