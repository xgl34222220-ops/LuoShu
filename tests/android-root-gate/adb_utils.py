"""Bounded same-target recovery for transient emulator ADB root transport races."""
import subprocess
import time


def ensure_root(adb, steps=None, seconds=60):
    steps = steps if steps is not None else []
    deadline = time.monotonic() + seconds
    def invoke(args):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError('ADB root handshake deadline exceeded')
        try:
            p = subprocess.run(adb + args, capture_output=True, text=True, timeout=min(15, remaining))
        except subprocess.TimeoutExpired:
            steps.append({'argv': args, 'result': 'TRANSPORT_TIMEOUT'})
            return None
        steps.append({'argv': args, 'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
        combined = (p.stdout + p.stderr).lower()
        if any(marker in combined for marker in ('cannot run as root', 'production builds', 'permission denied', 'device unauthorized')):
            raise RuntimeError('ADB explicitly denied root/access; no fallback attempted')
        return p
    while time.monotonic() < deadline:
        identity = invoke(['shell', 'id -u'])
        if identity and identity.returncode == 0 and identity.stdout.strip() == '0':
            return
        # Always the same root operation on the same AVD. No reconnecting to a
        # different target, changing security settings, or hiding denied access.
        response = invoke(['root'])
        if response and response.returncode:
            message = (response.stdout + response.stderr).lower()
            if not any(marker in message for marker in ('closed', 'offline', 'not found', 'no devices', 'cannot connect', 'unable to connect')):
                raise RuntimeError('Non-transient ADB root failure')
        invoke(['wait-for-device'])
        if time.monotonic() < deadline:
            time.sleep(min(.5, deadline - time.monotonic()))
    raise RuntimeError('ADB root identity was not established within deadline')
