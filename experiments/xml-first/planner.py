"""Reversible fixed-selection XML prototype. Never writes a module or device.

Plans exact snapshot edits and groups render contracts BEFORE compilation. Only
explicit upright fixed-role selections are accepted. A caller must supply a
validated source/geometry contract; this module does not infer OEM geometry.
"""
import copy, hashlib, json, xml.etree.ElementTree as ET


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def plan(xml_bytes, expected_sha, selections):
    if hashlib.sha256(xml_bytes).hexdigest() != expected_sha:
        raise ValueError('stock XML snapshot changed')
    root = ET.fromstring(xml_bytes)
    original = copy.deepcopy(root)
    nodes = list(root.iter('font'))
    parents = {child: parent for parent in root.iter() for child in parent}
    groups, routes, seen = {}, [], set()
    for selected in selections:
        ordinal = selected['ordinal']
        if not isinstance(ordinal, int) or ordinal < 0 or ordinal >= len(nodes) or ordinal in seen:
            raise ValueError('invalid or duplicate XML ordinal')
        seen.add(ordinal)
        node = nodes[ordinal]
        family = parents.get(node)
        family_name = family.get('name', '') if family is not None else ''
        if family is None or family.tag != 'family' or family_name not in {'sans-serif', 'sans-serif-condensed'} or family.get('lang'):
            raise ValueError('prototype only adapts explicit primary sans families')
        before = ET.tostring(node, encoding='unicode')
        if digest(before) != selected['nodeDigest']:
            raise ValueError('XML node contract changed')
        if selected['role'] not in {'cjk', 'latin', 'digit', 'ui-sans'}:
            raise ValueError('protected or unknown role cannot be selected')
        if node.get('style', 'normal') != 'normal':
            raise ValueError('true italic route requires a separate styling contract')
        contract = selected['renderContract']
        if contract.get('selection') != 'fixed-static' or not contract.get('sourceSha256'):
            raise ValueError('explicit immutable fixed source required')
        if not contract.get('geometryVerified') or not contract.get('roleGeometry'):
            raise ValueError('verified per-role geometry required')
        # Full semantic contract, not filename, determines sharing. XML weight
        # is deliberately outside this key: the user chose fixed source shapes.
        key = digest(contract)
        asset = 'LuoShuFixed-' + key + '.ttf'
        ps_name = 'LuoShuFixed-' + key[:32]
        groups.setdefault(key, {'id': key, 'asset': asset, 'postScriptName': ps_name,
                                'renderContract': copy.deepcopy(contract), 'routes': []})['routes'].append(ordinal)
        node.text = asset
        node.set('index', '0')
        for attr in ('name', 'postscriptName', 'postScriptName', 'supportedAxes'):
            node.attrib.pop(attr, None)
        node.set('postScriptName', ps_name)
        for child in list(node):
            if child.tag == 'axis':
                node.remove(child)
        routes.append({'ordinal': ordinal, 'renderGroup': key, 'oldNode': before,
                       'declaredWeight': node.get('weight', '400'),
                       'selectionSemantics': 'fixed shapes across declared XML weights'})
    # Every unselected node and all non-font nodes retain their exact semantics.
    old_nodes = list(original.iter('font'))
    for i, node in enumerate(nodes):
        if i not in seen and ET.tostring(node) != ET.tostring(old_nodes[i]):
            raise AssertionError('unselected font changed')
    return {'schema': 'experimental-fixed-xml-plan-v1', 'deviceDeployable': False,
            'stockXmlSha256': expected_sha, 'groups': list(groups.values()), 'routes': routes,
            'xml': ET.tostring(root, encoding='unicode'),
            'limits': ['upright fixed selections only', 'caller verifies geometry',
                       'no global mount or OEM deployment evidence']}


def compile_groups(planned, renderer):
    """Call the renderer exactly once per immutable contract; validate each result."""
    result = {}
    for group in planned['groups']:
        output = renderer(copy.deepcopy(group))
        if not isinstance(output, bytes) or not output:
            raise ValueError('renderer did not return font bytes')
        result[group['id']] = {'bytes': output, 'sha256': hashlib.sha256(output).hexdigest()}
    return result
