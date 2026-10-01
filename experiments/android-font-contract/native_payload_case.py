"""Read-only handoff of Android-produced payloads; never compile on the host."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'common'))
import universal_font_deployment as deployment


def read_prepared(root, fingerprint=None):
    root = Path(root)
    results = root / 'results'
    summary = json.loads((results / 'native-prepare-summary.json').read_text())
    if summary.get('state') != 'passed' or summary.get('androidPythonExecuted') is not True:
        raise ValueError('native preparation has not passed on Android')
    if fingerprint is not None and summary.get('fingerprint') != fingerprint:
        raise ValueError('native payload firmware differs from current VM')
    checks = summary.get('preparedDonorRoles', {})
    for role, char, points in [('cjk', '中', 6), ('latin', 'A', 3), ('digit', '1', 5)]:
        if checks.get(role, {}).get('character') != char or checks.get(role, {}).get('pointCount') != points:
            raise ValueError('native donor proof missing: ' + role)
    docs = {name: json.loads((results / file).read_text()) for name, file in [
        ('plan', 'font-plan.json'), ('route', 'route-plan.json'),
        ('artifacts', 'artifact-manifest.json'), ('manifest', 'deployment.json')]}
    manifest = docs['manifest']
    for key in ('deploymentId', 'payloadDigest'):
        if not manifest.get(key) or summary.get(key) != manifest[key]:
            raise ValueError('native summary identity differs: ' + key)
    payload = root / 'payload'
    deployment.validate_deployment(manifest, docs['plan'], docs['route'], docs['artifacts'], payload)
    for key, sealed in [('plan', 'fontPlan'), ('route', 'fixedStaticRoute'), ('artifacts', 'artifactManifest')]:
        docs[key] = json.loads((payload / manifest['verificationContracts'][sealed]['payloadPath']).read_text())
    if not docs['artifacts']['summary'].get('deploymentReady'):
        raise ValueError('native artifacts are not deployment ready')
    return payload, docs, summary


def expected_defaults(route, artifacts, manifest, baseline):
    """Select exact observed default routes, rejecting ambiguous contracts."""
    by_id = {a['artifactId']: a for a in artifacts['artifacts']}
    authoritative = '/system/etc/font_fallback.xml' if '/system/etc/font_fallback.xml' in route['documents'] else '/system/etc/fonts.xml'
    operations = route['documents'][authoritative]['operations']
    expected = {}
    for role, sample in [('Latin', 'A'), ('Digit', '1'), ('Cjk', '中')]:
        observed = baseline['actualDefaultFonts'][sample][0]
        candidates = [op for op in operations if op['targetPath'] == observed['file']
                      and op['node']['index'] == observed['ttcIndex'] and op['node']['weight'] == 400
                      and op.get('expandedWeight', 400) == 400 and op['node']['style'] == 'normal'
                      and (role == 'Cjk' or op['node']['family'] == 'sans-serif')]
        contracts = []
        for op in candidates:
            item = by_id[op['artifact']['artifactId']]
            files = [f for f in manifest['files'] if item['artifactId'] in f.get('artifactIds', [f.get('artifactId')])]
            if len(files) != 1:
                raise ValueError('default artifact does not identify one payload file')
            file = files[0]; contract = item['contract']; binding = item.get('staticXmlContract')
            contracts.append({'path': file['logicalPath'], 'face': 0 if binding else contract['requiredFaceIndex'],
                              'axes': [] if binding else contract['requiredAxes'], 'sha256': file['sha256']})
        unique = {json.dumps(c, sort_keys=True) for c in contracts}
        if len(unique) != 1:
            raise ValueError('missing or ambiguous native default route: ' + role)
        expected[role] = contracts[0]
    return expected
