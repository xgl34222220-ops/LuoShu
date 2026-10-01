"""Never accept persisted instrumentation output from a different invocation."""
import re

def require_instrumentation_success(log):
    text=log.decode(errors='replace') if isinstance(log,bytes) else log
    codes=re.findall(r'^INSTRUMENTATION_CODE:\s*(-?\d+)\s*$',text,re.MULTILINE)
    if codes!=['-1']:raise RuntimeError('instrumentation did not finish successfully: '+text[-1000:])

def validate_probe_result(log, report, request_id, expected_status):
    require_instrumentation_success(log)
    if not request_id or report.get('probeRequestId')!=request_id:
        raise RuntimeError('stale or missing instrumentation request identity')
    if report.get('status')!=expected_status:
        raise RuntimeError('probe did not satisfy '+expected_status+': '+str(report.get('error',report.get('status'))))
    return report
