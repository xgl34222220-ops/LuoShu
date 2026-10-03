#!/usr/bin/env python3
"""Legacy composite generation + background commit, distinct from App UI apply.

No replacement engine or synthetic success state is installed. The entry, frozen
engine, monitor, finalizer and next-boot mount path all come from the candidate.
"""
import json
from pathlib import Path
import re
import shlex
import time
import uuid


def fields(text):
    return dict(line.split('=', 1) for line in text.splitlines() if '=' in line)


def last_json(text):
    for line in reversed(text.splitlines()):
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                return value
        except ValueError:
            pass
    raise RuntimeError('Legacy composite returned no JSON: ' + text[-1000:])


def composite_blockers(report):
    if not isinstance(report, dict):
        return ['legacy composite evidence absent']
    errors = []
    try:
        if report.get('result') != 'PASS' or report.get('entry') != 'common/font_mix_controller.sh start':
            errors.append('actual legacy composite entry did not pass')
        probe = report.get('commit_lock_probe', {})
        if (probe.get('result') != 'PASS' or probe.get('environment') != 'ACTUAL_ANDROID_QEMU_ROOT_ENFORCING' or
                probe.get('unexported_fd_control', {}).get('exit') != 0 or
                probe.get('unexported_fd_control', {}).get('flock_errno') != 9 or
                probe.get('unexported_fd_control', {}).get('fstat_errno') != 9 or
                probe.get('caller_retains_lock', {}).get('result') != 'PASS' or
                probe.get('caller_retains_lock', {}).get('errno') != 11 or
                probe.get('contention', {}).get('exit') != 1 or
                'errno=11 (EAGAIN)' not in probe.get('contention', {}).get('stderr', '') or
                probe.get('waiter_blocked_while_owned') is not True or
                probe.get('owner_release', {}).get('exit') != 0 or
                probe.get('waiter_after_release', {}).get('exit') != 0 or
                probe.get('waiter_after_release', {}).get('stdout', '').strip() != 'ACQUIRED' or
                probe.get('persistent_inode_preserved') is not True):
            errors.append('Android fd transport/errno/serialization proof incomplete')
        task = report.get('task', {}).get('data', {})
        axes = report.get('axes_task', {})
        child = report.get('engine_task', {})
        final = report.get('background_finalize', {})
        manifest = report.get('generation_manifest', {})
        state = report.get('next_state', {})
        request = state.get('requestId')
        if (not task.get('task') or task.get('task') != axes.get('task') or
                not child.get('task') or axes.get('childTask') != child.get('task') or
                any(v.get('state') != 'success' for v in (task, axes, child, final))):
            errors.append('legacy parent/engine/monitor success identities incomplete')
        if (not request or request != final.get('requestId') or request != manifest.get('requestId') or
                state.get('state') != 'prepared' or state.get('font') != 'mix' or
                not re.fullmatch('[0-9a-f]{64}', state.get('compositeHash', '')) or
                state.get('compositeHash') != manifest.get('compositeHash') or
                state.get('compositeHash') not in report.get('next_payload_hashes', {}).values()):
            errors.append('generated composite/next state request and digest mismatch')
        sources = report.get('sources', {})
        if set(sources) != {'cjk', 'latin', 'digit'} or any(
                not sources[k] or any(value.get(k) != sources[k] for value in (task, axes, state, manifest))
                for k in sources):
            errors.append('composite source identities changed')
        for key in ('background_monitor_committed', 'live_unchanged_before_reboot',
                    'restore_hashes_equal_stock', 'stage_cleared', 'concurrent_finalize_unchanged',
                    'worker_sidecars_cleared', 'stage_cleared_after_replay'):
            if report.get(key) is not True:
                errors.append(key + ' not proven')
        if report.get('worker_sidecars') != []:
            errors.append('legacy worker sidecars remain or were not observed')
        concurrent = report.get('concurrent_finalize', [])
        if len(concurrent) != 3 or any(v.get('exit') != 0 or v.get('response', {}).get('status') != 'ok' for v in concurrent):
            errors.append('parallel actual finalizers did not all succeed')
        for key in ('reboot', 'restore_reboot'):
            value = report.get(key, {})
            if not value.get('before') or value.get('before') == value.get('after') or not value.get('after'):
                errors.append('legacy composite ' + key + ' unproven')
        activated = report.get('activated_state', {})
        if any(activated.get(k) != state.get(k) for k in ('requestId', 'compositeHash', 'cjk', 'latin', 'digit')) or activated.get('font') != 'mix':
            errors.append('reboot activated another composite generation')
        mounted = report.get('mounted', {})
        if (mounted.get('font') != 'mix' or not mounted.get('changed') or
                set(mounted.get('mount_proofs', {})) != set(mounted.get('changed', [])) or
                any(not proof.get('canonical') or not proof.get('mount_records')
                    for proof in mounted.get('mount_proofs', {}).values())):
            errors.append('legacy composite real mount mapping absent')
        if report.get('restore', {}).get('data', {}).get('state') != 'success':
            errors.append('legacy composite stock restore did not succeed')
    except (TypeError, AttributeError, KeyError, ValueError):
        return ['malformed legacy composite evidence']
    return errors


def run(report, module, root, command, boot, font_hashes, assert_mounted, switch, stock, ids, output):
    report.update(result='FAIL', entry='common/font_mix_controller.sh start',
                  scope='Candidate legacy CLI composite on disposable AOSP x86_64/nativebridge; not App composite UI or ColorOS validation')
    probe = Path(__file__).with_name('commit_lock_device.py')
    remote_probe = '/data/local/tmp/luoshu-commit-lock-device.py'
    remote_report = '/data/local/tmp/luoshu-commit-lock-device-' + uuid.uuid4().hex + '.json'
    report['commit_lock_probe_output'] = remote_report
    command(['push', str(probe), remote_probe])
    runtime = module + '/common/python'
    try:
        root(f'PYTHONHOME={runtime} PYTHONPATH={runtime}/lib/python3.14:{runtime}/lib/python3.14/site-packages '
             f'LD_LIBRARY_PATH={runtime}/lib:{runtime}/lib/python3.14/lib-dynload '
             f'{runtime}/bin/luoshu-python {remote_probe} --module {module} --output {remote_report}',
             timeout=120, required=True)
    except Exception as error:
        # A prior run's PASS can never substitute for a new process that failed
        # to start, crashed or exited nonzero. Preserve only this run's output
        # as diagnostics; even a contradictory PASS in it cannot pass the gate.
        report['commit_lock_probe'] = {'result': 'FAIL', 'execution_error': str(error)}
        try:
            report['commit_lock_probe']['output_after_failure'] = root('cat ' + remote_report, required=False)
        except Exception as read_error:
            report['commit_lock_probe']['evidence_read_error'] = str(read_error)
        raise RuntimeError('Actual Android commit-lock probe did not exit successfully') from error
    report['commit_lock_probe'] = json.loads(root('cat ' + remote_report))
    if report['commit_lock_probe'].get('result') != 'PASS':
        raise RuntimeError('Actual Android commit-lock transport failed; see errno evidence')
    before = font_hashes()
    root('test ! -e ' + module + '/.luoshu-payload-next && test ! -e ' + module + '/config/font-payload-next.conf')
    sources = dict(cjk=ids[0], latin=ids[1], digit=ids[1])
    report['sources'] = sources
    entry = 'sh ' + module + '/common/font_mix_controller.sh '
    report['start'] = last_json(root(entry + shlex.join(['start', *sources.values(), 'wght=400', 'wght=400', 'wght=400']), timeout=180))
    task = report['start'].get('data', {}).get('task')
    if report['start'].get('status') != 'ok' or not task:
        raise RuntimeError('Actual legacy composite entry did not admit a task')
    report['observations'] = []
    deadline = time.monotonic() + 720
    # Only read persisted states here: a manual finalizer/status fallback must
    # not turn a broken detached monitor into passing evidence.
    while time.monotonic() < deadline:
        values = {}
        text = root('for f in axes_task.conf mix_task.conf mix-finalize-state.conf; do printf "GATE_FILE:%s\\n" "$f"; cat ' + module + '/config/"$f" 2>/dev/null; done; true')
        for block in text.split('GATE_FILE:')[1:]:
            name, _, body = block.partition('\n')
            values[name] = fields(body)
        axes = values.get('axes_task.conf', {})
        child = values.get('mix_task.conf', {})
        final = values.get('mix-finalize-state.conf', {})
        report.update(axes_task=axes, engine_task=child, background_finalize=final)
        observation = {k: values.get(k, {}).get('state') for k in values}
        if not report['observations'] or report['observations'][-1] != observation:
            report['observations'].append(observation)
        if axes.get('task') != task:
            raise RuntimeError('Legacy composite parent task identity changed')
        if any(value.get('state') in ('failed', 'error', 'cancelled') for value in (axes, child, final)):
            report['failure_log'] = root('tail -n 180 ' + module + '/logs/fontswitch.log', required=False)
            raise RuntimeError('Legacy composite generation/background finalizer failed')
        if all(value.get('state') == 'success' for value in (axes, child, final)):
            # success is written before the monitor's final mode/log writes.
            # Wait for this exact child's marker within the original deadline;
            # do not let any manual replay finish or conceal monitor work.
            log = root('tail -n 240 ' + module + '/logs/fontswitch.log')
            marker = 'legacy-v14 composite task committed for next boot: ' + child.get('task', 'NO_TASK')
            if marker in log:
                report['background_monitor_committed'] = True
                (Path(output) / 'legacy-composite.log').write_text(log)
                break
        time.sleep(1)
    else:
        raise RuntimeError('Legacy composite background completion deadline exceeded')
    report['task'] = last_json(root(entry + 'status ' + shlex.quote(task)))
    report['next_state'] = fields(root('cat ' + module + '/config/font-payload-next.conf'))
    report['generation_manifest'] = fields(root('cat ' + module + '/.luoshu-payload-next/.luoshu-mix-generation.conf'))
    def next_hashes():
        text = root('find ' + module + '/.luoshu-payload-next -type f -exec sha256sum {} \\; | sort')
        return {line.split(None, 1)[1]: line.split()[0] for line in text.splitlines() if re.match(r'^[0-9a-f]{64}  ', line)}
    report['next_payload_hashes'] = next_hashes()
    report['live_unchanged_before_reboot'] = font_hashes() == before
    root('test ! -e ' + module + '/.luoshu-mix-stage && test ! -e ' + module + '/config/mix-stage-next.conf')
    report['stage_cleared'] = True
    # Check before reboot so a kernel restart cannot hide incomplete cleanup.
    sidecars = ' '.join(module + '/config/' + name + suffix
                        for name in ('axes_worker.pid', 'auto_multiweight_worker.pid', 'mix_worker.pid')
                        for suffix in ('', '.task', '.boot', '.start', '.scope', '.identity', '.cancel'))
    query = 'for p in ' + sidecars + '; do [ ! -e "$p" ] || echo "$p"; done; true'
    cleanup_deadline = time.monotonic() + 30
    while True:
        report['worker_sidecars'] = root(query).splitlines()
        if not report['worker_sidecars']:
            time.sleep(1)
            report['worker_sidecars'] = root(query).splitlines()
            if not report['worker_sidecars']:
                report['worker_sidecars_cleared'] = True
                break
        if time.monotonic() >= cleanup_deadline:
            raise RuntimeError('Legacy composite worker sidecars remained before reboot')
        time.sleep(1)

    # Real frozen finalizers race on the already prepared generation; the fd
    # probe separately holds a critical section open to prove serialization.
    temp = '/data/local/tmp/luoshu-finalize-gate-' + str(time.monotonic_ns())
    root('mkdir ' + temp)
    try:
        body = ('for n in 1 2 3; do (MODDIR=' + module + ' sh ' + module + '/common/legacy_v14_4/mix_router.sh finalize >' + temp + '/out-$n 2>&1; echo $? >' + temp + '/rc-$n) & done; wait')
        root(body, timeout=90)
        report['concurrent_finalize'] = [dict(exit=int(root('cat ' + temp + '/rc-' + str(n))),
            response=last_json(root('cat ' + temp + '/out-' + str(n)))) for n in (1, 2, 3)]
    finally:
        root('rm -f ' + temp + '/out-* ' + temp + '/rc-*; rmdir ' + temp, required=False)
    report['concurrent_finalize_unchanged'] = (next_hashes() == report['next_payload_hashes'] and
        fields(root('cat ' + module + '/config/font-payload-next.conf')) == report['next_state'])
    root('test ! -e ' + module + '/.luoshu-mix-stage && test ! -e ' + module + '/config/mix-stage-next.conf')
    report['stage_cleared_after_replay'] = True
    report['reboot'] = boot()
    report['activated_state'] = fields(root('cat ' + module + '/config/font-payload-activated.conf'))
    _, report['mounted'] = assert_mounted('mix', stock)
    report['restore'] = switch('default')
    report['restore_reboot'] = boot()
    report['restore_hashes_equal_stock'] = font_hashes() == stock
    report['result'] = 'PASS'
    report['blockers'] = composite_blockers(report)
    if report['blockers']:
        report['result'] = 'FAIL'
        raise RuntimeError('Legacy composite evidence incomplete: ' + '; '.join(report['blockers']))
