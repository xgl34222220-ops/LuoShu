"""Fail-closed structured verdicts. A printed PASS or green job is not evidence."""
import re

PACKAGE = 'io.github.xgl34222220.luoshu.stabletest'
OLD_CASES = {'success': 0, 'failure': 7, 'timeout': 124, 'cancel': 143}
REQUEST_CASES = {**OLD_CASES, 'cancel_int': 130, 'cancel_hup': 129, 'stdin_eof': 130, 'writer_death': 130}


def reboot_ok(value):
    return isinstance(value, dict) and all(re.fullmatch(r'[0-9a-f-]{36}', str(value.get(k, ''))) for k in ('before', 'after')) and value['before'] != value['after']


def identity_ok(value):
    return isinstance(value, dict) and type(value.get('pid')) is int and value['pid'] > 1 and type(value.get('start')) is int and value['start'] >= 0 and bool(re.fullmatch(r'[0-9a-f-]{36}', str(value.get('boot', ''))))


def scope_blockers(value, expected, request=False):
    errors = []
    if not isinstance(value, dict) or value.get('result') != 'PASS' or value.get('selinux') != 'Enforcing':
        return ['actual Android scope result/SELinux missing or failed']
    if request and value.get('environment') != 'ACTUAL_ANDROID_QEMU_ROOT_ENFORCING':
        errors.append('request scope is not actual Android')
    cases = value.get('cases', [])
    if len(cases) != len(expected) or {c.get('mode') for c in cases} != set(expected):
        errors.append('scope case set incomplete or duplicated')
    for case in cases:
        label = case.get('mode')
        if case.get('result') != 'PASS' or case.get('supervisor_exit') != expected.get(label):
            errors.append(f'{label}: wrong actual outcome')
        if not identity_ok(case.get('late_fork')) or not identity_ok(case.get('sentinel')):
            errors.append(f'{label}: missing late-fork/sentinel identity')
        identities = case.get('identities', []) if request else [case.get(k) for k in ('supervisor','worker','owned_leaf','double_fork_intermediate','late_fork')]
        owned = identities
        if request and label == 'writer_death':
            writer = case.get('client_writer', {})
            if not identity_ok(writer) or case.get('client_writer_exit') != -9:
                errors.append('writer_death: actual client death not proven')
            owned = [r for r in identities if (r.get('pid'), r.get('start'), r.get('boot')) != (writer.get('pid'), writer.get('start'), writer.get('boot'))]
        if len(owned) < 5 or not all(identity_ok(record) for record in identities) or not all(re.fullmatch('[0-9a-f]{32}', str(record.get('token', ''))) for record in owned):
            errors.append(f'{label}: full owned PID/start/boot/token identities missing')
        for when in ('immediate_cleanup', 'delayed_cleanup'):
            clean = case.get(when, {})
            if clean.get('token_members') != [] or clean.get('recorded_alive_including_zombies') != []:
                errors.append(f'{label}: {when} not proven empty')
            if request and clean.get('scope_directory_entries') != []:
                errors.append(f'{label}: request directory not empty')
        if not request and case.get('terminal_state', {}).get('state') != ('success' if label == 'success' else 'failed'):
            errors.append(f'{label}: worker terminal state missing')
        if request and (case.get('finished', {}).get('cleaned') is not True or case.get('scope_entries_after') != [] or
                        case.get('worker_stdin', {}).get('is_devnull') is not True or
                        case.get('worker_stdin', {}).get('private_fd_not_inherited') is not True):
            errors.append(f'{label}: request ownership/FD cleanup incomplete')
    return errors


def preflight_blockers(report):
    errors = []
    if not isinstance(report, dict) or report.get('selinux') != 'Enforcing':
        return ['preflight absent or not Enforcing']
    checks = report.get('checks', {})
    entry = checks.get('candidate_official_composite_entry', {})
    if entry.get('result') != 'PASS' or entry.get('exit') != 0:
        errors.append('candidate actual runtime entry failed or absent')
    errors.extend(scope_blockers(checks.get('candidate_scope'), OLD_CASES))
    ui = checks.get('app_launch_only', {})
    if ui.get('result') not in ('PASS', 'BLOCKED'):
        errors.append('target App startup failed or absent')
    if ui.get('result') == 'BLOCKED' and not ui.get('reason'):
        errors.append('unexplained preflight UI BLOCKED')
    # Other pre-root BLOCKED fields are deliberately superseded only by the
    # complete Magisk App/root/mount proof below, never by a changed exit code.
    return errors


def input_validation_blockers(events, task, boot):
    if not isinstance(events, list) or len(events) != 3 or [e.get('event') for e in events] != ['snapshot', 'full_validation', 'core_entry']:
        return ['ordered snapshot/full validation/core entry evidence missing']
    snapshot, validation, core = events
    token = snapshot.get('token', '')
    if not re.fullmatch('[0-9a-f]{32}', token) or any(e.get('task') != task or e.get('boot') != boot or e.get('token') != token for e in events):
        return ['input events are not bound to one owned App task/boot']
    if validation.get('valid') is not True or validation.get('code') != 0 or core.get('source_rechecked') is not True:
        return ['full validation or source identity recheck failed']
    for key, pattern in (('snapshot_digest', '[0-9a-f]{64}'), ('source_fingerprint', 'font-selection-v1:[0-9a-f]{64}')):
        if not re.fullmatch(pattern, snapshot.get(key, '')) or snapshot.get(key) != core.get(key):
            return ['validated source changed before original core entry']
    return []


def delivery_blockers(report):
    errors = []
    if not isinstance(report, dict):
        return ['missing delivery report']
    if report.get('run_scope') != 'FULL_GATE':
        errors.append('diagnostic/unknown run cannot pass delivery')
    if report.get('error'):
        errors.append('execution recorded an error')
    if not re.fullmatch('[0-9a-f]{64}', report.get('candidate_apk_sha256', '')):
        errors.append('candidate APK hash not bound')
    uid = report.get('root_policy', {}).get('uid')
    if type(uid) is not int or not 10000 <= uid < 20000:
        errors.append('authorized App UID evidence missing')
    fixtures = report.get('fixture_inventory', [])
    if len(fixtures) != 2 or {f.get('files') for f in fixtures} != {100, 1000} or any(len(f.get('unique_content_hashes', [])) != 2 for f in fixtures):
        errors.append('actual synthetic file inventory/hashes incomplete')
    cycles = report.get('cycles', [])
    if len(cycles) != 2 or {c.get('label') for c in cycles} != {'baseline', 'candidate'}:
        errors.append('both module cycles required')
    for cycle in cycles:
        label = cycle.get('label')
        if cycle.get('result') != 'PASS' or not re.fullmatch('[0-9a-f]{64}', cycle.get('zip_sha256', '')):
            errors.append(f'{label}: module cycle failed/unbound')
        for field in ('install_reboot', 'font_reboot', 'switch_b_reboot', 'restore_reboot'):
            if not reboot_ok(cycle.get(field)):
                errors.append(f'{label}: {field} missing or no real reboot')
        for field in ('mounted_a', 'mounted_b'):
            mounted = cycle.get(field, {})
            changed = mounted.get('changed', [])
            if not changed or not mounted.get('font') or set(mounted.get('mount_proofs', {})) != set(changed) or any(not proof.get('canonical') or not proof.get('mount_records') for proof in mounted.get('mount_proofs', {}).values()):
                errors.append(f'{label}: exact mount mapping missing')
        if cycle.get('mounted_a', {}).get('font') == cycle.get('mounted_b', {}).get('font'):
            errors.append(f'{label}: distinct A/B font identities not shown')
        if cycle.get('restore_hashes_equal_stock') is not True:
            errors.append(f'{label}: exact stock restoration evidence missing')
        for field in ('invalid_switch', 'commit_failure'):
            if cycle.get(field, {}).get('data', {}).get('state') != 'failed':
                errors.append(f'{label}: {field} did not fail as intended')
        commit = cycle.get('commit_failure', {})
        if not commit.get('injection_hit') or not reboot_ok(commit.get('reboot')):
            errors.append(f'{label}: injected commit/reboot proof missing')
        if label == 'candidate' and (cycle.get('prepare_failure_crashes') != '' or commit.get('crash_buffer') != ''):
            errors.append('candidate error path has missing/native-crash evidence')
    from composite_gate import composite_blockers
    errors.extend(composite_blockers(report.get('legacy_composite')))
    errors.extend(scope_blockers(report.get('magisk_task_scope'), OLD_CASES))
    errors.extend(scope_blockers(report.get('magisk_request_scope'), REQUEST_CASES, True))
    if report.get('app_root') != 'PROVEN_BY_ACTUAL_APP_VERIFIED_ROOT_LIBRARY':
        errors.append('actual App root not proven')
    timings = report.get('library_timings', [])
    if len(timings) != 2 or {t.get('inventory_count') for t in timings} != {100, 1000}:
        errors.append('100/1000 real libraries not both measured')
    for timing in timings:
        count = timing.get('inventory_count')
        samples = timing.get('samples', [])
        if timing.get('result') != 'PASS' or len(samples) != 6:
            errors.append(f'{count}: timing samples incomplete')
        if {(s.get('kind'), s.get('repetition')) for s in samples} != {(k,i) for k in ('app_start','library_open') for i in range(3)}:
            errors.append(f'{count}: cold/warm repetitions incomplete')
        for sample in samples:
            if sample.get('target_fatal') is not False or sample.get('anr') is not False:
                errors.append(f'{count}: sample crash/ANR observation missing')
            if sample.get('count') != count or sample.get('verified') is not True or not str(sample.get('pid', '')).isdigit():
                errors.append(f'{count}: verified App identity/count missing')
            if not isinstance(sample.get('first_inventory_frame_ms'), int) or not isinstance(sample.get('library_open_to_inventory_first_ms'), int) or sample['library_open_to_inventory_first_ms'] < 0:
                errors.append(f'{count}: target-count first frame absent; empty frames do not count')
    app = report.get('app_apply', {})
    if app.get('result') != 'PASS' or app.get('task', {}).get('data', {}).get('state') != 'success' or app.get('task', {}).get('data', {}).get('font') != app.get('font_id'):
        errors.append('actual App apply task not proven')
    if not app.get('task', {}).get('data', {}).get('task') or app.get('task', {}).get('data', {}).get('bootId') != app.get('reboot', {}).get('before') or app.get('mounted', {}).get('font') != app.get('font_id'):
        errors.append('App task/boot/selected font identity binding missing')
    errors.extend(input_validation_blockers(app.get('input_events'), app.get('task', {}).get('data', {}).get('task'), app.get('reboot', {}).get('before')))
    if app.get('restore_hashes_equal_stock') is not True:
        errors.append('App-applied font exact restoration evidence missing')
    if not reboot_ok(app.get('reboot')) or not reboot_ok(app.get('restore_reboot')) or not app.get('mounted', {}).get('mount_proofs'):
        errors.append('actual App apply/reboot/restore mount proof missing')
    if app.get('restore', {}).get('data', {}).get('state') != 'success':
        errors.append('App-applied font restore did not succeed')
    if report.get('root_policy', {}).get('package') != PACKAGE or report.get('root_policy_revoked') is not True:
        errors.append('exact isolated App policy revocation missing')
    if report.get('upgrade', {}).get('result') != 'PASS':
        errors.append('upgrade preservation not proven')
    if report.get('final_ui', {}).get('result') != 'PASS' or report.get('final_ui', {}).get('target_fatal') is not False or report.get('final_ui', {}).get('anr') is not False:
        errors.append('fresh final App crash/ANR observation absent or failed')
    workspace = report.get('final_workspace', {})
    if workspace.get('result') != 'PASS' or workspace.get('entries') != []:
        errors.append('final owned transient workspace not proven empty')
    return errors


def qualification_blockers(report):
    errors = []
    if report.get('qualification') != 'PASS' or report.get('selinux_before') != 'Enforcing' or report.get('selinux_after') != 'Enforcing':
        errors.append('original runtime qualification/Enforcing missing')
    if not reboot_ok({'before': report.get('boot_id_before'), 'after': report.get('boot_id_after')}):
        errors.append('original runtime reboot not proven')
    if report.get('arm64_launcher_sha256') != 'fbd2a5491242b466f1f47600fd6a66f12199b8928d6c909f1903ca7e2eb93916':
        errors.append('original ARM64 ELF hash mismatch')
    for phase in ('before_reboot', 'after_reboot'):
        value = report.get(phase, {})
        if value.get('marker') != 'ARM64_ELF_EXECUTED' or not all(value.get(k) is True for k in ('fonttools_synthetic_roundtrip','subprocess','ctypes','subreaper','waitid_wnowait')):
            errors.append(phase + ': actual runtime capabilities absent')
    return errors


def _fail_closed(function):
    def checked(report):
        try:
            return function(report)
        except (AttributeError, TypeError, KeyError, ValueError):
            return ['malformed evidence cannot produce a passing verdict']
    return checked


preflight_blockers = _fail_closed(preflight_blockers)
delivery_blockers = _fail_closed(delivery_blockers)
qualification_blockers = _fail_closed(qualification_blockers)
