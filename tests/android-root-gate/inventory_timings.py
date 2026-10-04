"""Read numeric App diagnostics; they never replace directory or actual UI proof."""
import math
import re

ACTIONS = '(cached|preview|scan|refresh|fingerprint)'
DECIMAL = r'([0-9]+(?:[.][0-9]+)?)'
REQUEST = re.compile(r'event=font_request stage=' + ACTIONS + r' elapsed_ms=(\d+) duration_ms=(\d+) code=(-?\d+)$')
BODY = re.compile(r'event=font_request_phase stage=' + ACTIONS + r' phase=inventory duration_ms=' + DECIMAL + r' count=(\d+) code=(\d+)$')
SCOPE = re.compile(r'event=font_request_phase stage=' + ACTIONS + r' phase=scope duration_ms=' + DECIMAL + r' code=(\d+) cleaned=(true|false) reason=(success|worker-error|cancel|timeout|client-disconnect|error)$')


def request_timings(logs, start_ms):
    """The App logs phases immediately before its outer completed-request marker."""
    pending = {}
    records = []
    for line in logs.splitlines():
        message = line.rsplit('LuoShuStartup:', 1)[-1].strip()
        body = BODY.fullmatch(message)
        scope = SCOPE.fullmatch(message)
        completed = REQUEST.fullmatch(message)
        if body:
            action, duration, count, code = body.groups()
            pending.setdefault(action, {})['inventory'] = dict(duration_ms=float(duration), count=int(count), code=int(code))
        elif scope:
            action, duration, code, cleaned, reason = scope.groups()
            pending.setdefault(action, {})['scope'] = dict(duration_ms=float(duration), code=int(code), cleaned=cleaned == 'true', reason=reason)
        elif completed:
            action, completed_ms, duration, code = completed.groups()
            phases = pending.pop(action, {})
            if int(completed_ms) >= start_ms:
                records.append(dict(stage=action, completed_at_ms=int(completed_ms), duration_ms=int(duration), code=int(code), phases=phases))
    return records


def verified_timing(records, start_ms, expected_count=None):
    """Require a current completed successful live check and consistent numeric spans."""
    if not isinstance(records, list):
        return False
    for record in records:
        if (not isinstance(record, dict) or record.get('stage') not in ('fingerprint', 'scan', 'refresh') or
                type(record.get('code')) is not int or record.get('code') != 0):
            continue
        completed, total = record.get('completed_at_ms'), record.get('duration_ms')
        phases = record.get('phases', {})
        if not isinstance(phases, dict):
            continue
        body, scope = phases.get('inventory', {}), phases.get('scope', {})
        if not isinstance(body, dict) or not isinstance(scope, dict):
            continue
        values = [total, body.get('duration_ms'), scope.get('duration_ms')]
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or not 0 <= value <= 180000 for value in values):
            continue
        count = body.get('count')
        if (isinstance(completed, int) and not isinstance(completed, bool) and completed >= start_ms and
                isinstance(count, int) and not isinstance(count, bool) and count >= 0 and (expected_count is None or count == expected_count) and
                type(body.get('code')) is int and body.get('code') == 0 and type(scope.get('code')) is int and scope.get('code') == 0 and
                scope.get('cleaned') is True and scope.get('reason') == 'success' and
                values[1] <= values[2] + 1 and values[2] <= values[0] + 1):
            return True
    return False
