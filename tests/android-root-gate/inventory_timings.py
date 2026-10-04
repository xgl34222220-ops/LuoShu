"""Read numeric App diagnostics; they never replace directory or actual UI proof."""
import math
import re

ACTIONS = '(cached|preview|scan|refresh|fingerprint)'
DECIMAL = r'([0-9]+(?:[.][0-9]+)?)'
REQUEST = re.compile(r'event=font_request stage=' + ACTIONS + r' elapsed_ms=(\d+) duration_ms=(\d+) code=(-?\d+)$')
BODY = re.compile(r'event=font_request_phase stage=' + ACTIONS + r' phase=inventory duration_ms=' + DECIMAL + r' count=(\d+) code=(\d+)$')
SCOPE = re.compile(r'event=font_request_phase stage=' + ACTIONS + r' phase=scope duration_ms=' + DECIMAL + r' code=(\d+) cleaned=(true|false) reason=(success|worker-error|cancel|timeout|client-disconnect|error)$')
DETAIL_PHASES = ('storage', 'snapshot', 'cache', 'build', 'verify', 'write', 'output')
DETAIL = re.compile(r'event=font_request_phase stage=' + ACTIONS + r' phase=inventory_detail ' +
                    ' '.join(phase + '_ms=' + DECIMAL for phase in DETAIL_PHASES) +
                    r' cache_hit=([01]) snapshot_count=(\d+) build_count=(\d+) write_count=(\d+) code=(\d+)$')


def request_timings(logs, start_ms):
    """The App logs phases immediately before its outer completed-request marker."""
    pending = {}
    records = []
    for line in logs.splitlines():
        message = line.rsplit('LuoShuStartup:', 1)[-1].strip()
        body = BODY.fullmatch(message)
        scope = SCOPE.fullmatch(message)
        detail = DETAIL.fullmatch(message)
        completed = REQUEST.fullmatch(message)
        if body:
            action, duration, count, code = body.groups()
            pending.setdefault(action, {})['inventory'] = dict(duration_ms=float(duration), count=int(count), code=int(code))
        elif scope:
            action, duration, code, cleaned, reason = scope.groups()
            pending.setdefault(action, {})['scope'] = dict(duration_ms=float(duration), code=int(code), cleaned=cleaned == 'true', reason=reason)
        elif detail:
            action, *values = detail.groups()
            fields = {phase + '_ms': float(value) for phase, value in zip(DETAIL_PHASES, values[:7])}
            fields.update(zip(('cache_hit', 'snapshot_count', 'build_count', 'write_count', 'code'), map(int, values[7:])))
            pending.setdefault(action, {})['inventory_detail'] = fields
        elif completed:
            action, completed_ms, duration, code = completed.groups()
            phases = pending.pop(action, {})
            if int(completed_ms) >= start_ms:
                records.append(dict(stage=action, completed_at_ms=int(completed_ms), duration_ms=int(duration), code=int(code), phases=phases))
    return records


def verified_detail(detail, action, body_duration):
    keys = tuple(phase + '_ms' for phase in DETAIL_PHASES)
    counters = ('cache_hit', 'snapshot_count', 'build_count', 'write_count', 'code')
    if not isinstance(detail, dict) or set(detail) != set(keys + counters):
        return False
    spans = [detail[key] for key in keys]
    if any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or not 0 <= value <= 180000 for value in spans):
        return False
    if sum(spans) > body_duration + 1 or any(type(detail[key]) is not int for key in counters) or detail['code'] != 0:
        return False
    hit, snapshots, builds, writes = (detail[key] for key in counters[:-1])
    if action == 'fingerprint':
        return (hit, snapshots, builds, writes) == (0, 1, 0, 0) and all(detail[key + '_ms'] == 0 for key in ('storage', 'cache', 'build', 'verify', 'write'))
    if action == 'refresh':
        return (hit, snapshots, builds, writes) == (0, 2, 1, 2)
    if action == 'scan':
        return ((hit, snapshots, builds, writes) == (0, 2, 1, 2) or
                ((hit, snapshots, builds, writes) == (1, 2, 0, 0) and detail['build_ms'] == detail['write_ms'] == 0))
    return False


def verified_timing(records, start_ms, expected_count=None):
    """Require a current live check and complete spans for every successful live request."""
    if not isinstance(records, list):
        return False
    proven = False
    for record in records:
        if not isinstance(record, dict) or record.get('stage') not in ('fingerprint', 'scan', 'refresh'):
            continue
        if type(record.get('code')) is not int:
            return False
        if record['code'] != 0:
            continue  # Failed attempts remain recorded; a later live success is still required.
        completed, total = record.get('completed_at_ms'), record.get('duration_ms')
        phases = record.get('phases', {})
        if not isinstance(phases, dict):
            return False
        body, scope = phases.get('inventory', {}), phases.get('scope', {})
        if not isinstance(body, dict) or not isinstance(scope, dict):
            return False
        values = [total, body.get('duration_ms'), scope.get('duration_ms')]
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or not 0 <= value <= 180000 for value in values):
            return False
        count = body.get('count')
        if (isinstance(completed, int) and not isinstance(completed, bool) and completed >= start_ms and
                isinstance(count, int) and not isinstance(count, bool) and count >= 0 and (expected_count is None or count == expected_count) and
                type(body.get('code')) is int and body.get('code') == 0 and type(scope.get('code')) is int and scope.get('code') == 0 and
                scope.get('cleaned') is True and scope.get('reason') == 'success' and
                values[1] <= values[2] + 1 and values[2] <= values[0] + 1 and
                verified_detail(phases.get('inventory_detail'), record['stage'], values[1])):
            proven = True
        else:
            return False
    return proven
