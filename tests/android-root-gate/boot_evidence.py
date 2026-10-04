"""A verified kernel reboot, with bounded evidence from the failing boot itself."""
from pathlib import Path
import time

PROBE = ('cat /proc/sys/kernel/random/boot_id; '
         'getprop sys.boot_completed; getenforce')
DIAGNOSTICS = {
    'properties.txt': ['shell', 'getprop'],
    'system-logcat.txt': ['shell', 'logcat -b all -d -t 4000'],
    'crash-logcat.txt': ['shell', 'logcat -b crash -d -t 1200'],
    'processes.txt': ['shell', 'ps -A'],
}


def wait_for_reboot(command, ensure_root, before, output, report, seconds=240,
                    clock=time.monotonic, sleep=time.sleep):
    if not before:
        raise RuntimeError('Pre-reboot kernel identity is missing')
    attempts = report.setdefault('boot_attempts', [])
    attempt = {'sequence': len(attempts) + 1, 'before': before, 'result': 'FAIL'}
    attempts.append(attempt)
    deadline = clock() + seconds
    try:
        command(['reboot'], timeout=min(30, seconds))
        # wait-for-device alone can return the OLD transport before it drops.
        # Both a changed kernel identity and completed boot are required.
        while clock() < deadline:
            remaining = deadline - clock()
            try:
                raw = command(['shell', PROBE], timeout=min(10, remaining), required=False)
                attempt['last_observation'] = raw
            except Exception as error:
                attempt['last_transport_error'] = str(error)
                raw = ''
            lines = raw.splitlines()
            if (len(lines) == 3 and lines[0] and lines[0] != before and
                    lines[1] == '1'):
                if lines[2] != 'Enforcing':
                    raise RuntimeError('Boot SELinux invariant failed')
                ensure_root()
                confirmed = command(['shell', PROBE], timeout=10).splitlines()
                if confirmed != lines:
                    raise RuntimeError('Boot identity changed during root verification')
                attempt.update(result='PASS', after=lines[0])
                return {'before': before, 'after': lines[0]}
            remaining = deadline - clock()
            if remaining > 0:
                sleep(min(2, remaining))
        raise RuntimeError('Module reboot did not complete')
    except Exception as error:
        attempt['error'] = str(error)
        directory = Path(output) / 'boot-failures' / f"reboot-{attempt['sequence']:03d}"
        attempt['evidence_files'] = []
        attempt['diagnostic_errors'] = {}
        for name, args in DIAGNOSTICS.items():
            try:
                directory.mkdir(parents=True, exist_ok=True)
                text = command(args, timeout=8, required=False)
                # Diagnostic commands and output have independent finite bounds.
                (directory / name).write_text(text[-2 * 1024 * 1024:], encoding='utf-8')
                attempt['evidence_files'].append(str((directory / name).relative_to(output)))
            except Exception as diagnostic_error:
                attempt['diagnostic_errors'][name] = str(diagnostic_error)
        raise
