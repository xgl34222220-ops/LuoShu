#!/usr/bin/env python3
"""Real Magisk module lifecycle on the explicitly authorized disposable AVD.

Only the isolated .stabletest package may receive a time-bounded root policy.
Formal baseline App is never granted root. Module shell results remain distinct
from App UI results. Original module mount implementation is never patched here.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time
import tempfile
import zipfile
from adb_utils import ensure_root

PACKAGE = 'io.github.xgl34222220.luoshu.stabletest'
MODULE = '/data/adb/modules/LuoShu'
# Existing private_payload.sh partition contract; absent directories are recorded, not invented.
FONT_PARTITIONS = 'system system_ext product vendor odm oem my_product my_engineering my_company my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust hw_product'.split()


def resolve_authorized_uid(packages):
    rows = re.findall(r'package:(\S+) uid:(\d+)', packages)
    uids = {int(uid) for package, uid in rows if package == PACKAGE}
    if len(uids) != 1:
        raise RuntimeError('Isolated candidate package UID is not uniquely resolved')
    uid = uids.pop()
    if not 10000 <= uid < 20000 or any(package != PACKAGE and int(other) == uid for package, other in rows):
        raise RuntimeError('Refusing non-App, other-user or shared UID root grant')
    return uid


def run_gate(adb, magisk, baseline, candidate, output):
    output = Path(output)
    report = {'delivery_gate': 'BLOCKED', 'cycles': [], 'steps': [], 'app_root': 'NOT_PROVEN'}
    granted_uid = None
    owned_tasks = set()
    def command(args, timeout=120, required=True):
        p = subprocess.run([adb, '-s', 'emulator-5554'] + args, capture_output=True, text=True, timeout=timeout)
        report['steps'].append({'argv': args, 'exit': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
        if required and p.returncode:
            raise RuntimeError('Android command failed: ' + shlex.join(args))
        return p.stdout.strip()
    def shell(text, timeout=120, required=True):
        return command(['shell', text], timeout, required)
    def root(text, timeout=180, required=True):
        return shell(shlex.quote(magisk) + ' su -mm -c ' + shlex.quote(text), timeout, required)
    def boot():
        before = shell('cat /proc/sys/kernel/random/boot_id')
        command(['reboot']); command(['wait-for-device'], timeout=180)
        end = time.monotonic() + 240
        while time.monotonic() < end:
            if shell('getprop sys.boot_completed') == '1':
                break
            time.sleep(2)
        else:
            raise RuntimeError('Module reboot did not complete')
        ensure_root([adb, '-s', 'emulator-5554'], report['steps'])
        after = shell('cat /proc/sys/kernel/random/boot_id')
        if before == after or shell('getenforce') != 'Enforcing':
            raise RuntimeError('Boot identity/SELinux invariant failed')
        return {'before': before, 'after': after}
    def bridge(*args, prefix=""):
        text = root(prefix + 'sh ' + MODULE + '/common/app_bridge.sh ' + shlex.join(args), timeout=240)
        for line in reversed(text.splitlines()):
            try:
                return json.loads(line)
            except ValueError:
                pass
        raise RuntimeError('Module bridge returned no JSON: ' + text[-1000:])
    def switch(font, expect_success=True, prefix=""):
        start = bridge('switch_start', font, prefix=prefix)
        if start.get('status') != 'ok':
            raise RuntimeError('Font switch was not admitted: ' + json.dumps(start, ensure_ascii=False))
        task = start['data']['task']
        owned_tasks.add(task)
        task_boot = shell('cat /proc/sys/kernel/random/boot_id')
        end = time.monotonic() + 420
        while time.monotonic() < end:
            status = bridge('switch_status', task)
            data = status.get('data', {})
            if data.get('task') != task or data.get('font') != font or (data.get('bootId') != task_boot and not (data.get('state') == 'queued' and not data.get('bootId'))):
                raise RuntimeError('Switch task identity changed')
            state = data.get('state')
            if state in ('success', 'failed', 'cancelled', 'error'):
                if (state == 'success') != expect_success:
                    raise RuntimeError('Unexpected font task outcome: ' + json.dumps(status, ensure_ascii=False))
                return status
            time.sleep(1)
        raise RuntimeError('Font switch task deadline exceeded')
    def font_hashes():
        directories = ' '.join('/' + part + '/fonts' for part in FONT_PARTITIONS)
        text = root('for d in ' + directories + r'; do if [ -d "$d" ]; then find "$d" -maxdepth 1 \( -type f -o -type l \) \( -iname "*.ttf" -o -iname "*.otf" -o -iname "*.ttc" \) -exec sha256sum {} \; || exit 1; fi; done')
        values = {}
        for line in text.splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2 and re.fullmatch('[0-9a-f]{64}', parts[0]):
                values[parts[1]] = parts[0]
        if not values:
            raise RuntimeError('No system-font hash evidence')
        return values
    def assert_mounted(font, stock):
        live = font_hashes()
        if not set(stock).issubset(live):
            raise RuntimeError('System font disappeared after switch')
        changed = [path for path in stock if live[path] != stock[path]]
        if not changed:
            raise RuntimeError('No system font changed from stock')
        active = root('cat ' + MODULE + '/config/active_font.conf').strip()
        if active != font:
            raise RuntimeError('Active font does not match exact requested font')
        payload_prefix = MODULE + '/.luoshu-payload'
        payload = root('find -L ' + payload_prefix + r' -type f \( -iname "*.ttf" -o -iname "*.otf" -o -iname "*.ttc" \) -exec sha256sum {} \;')
        payload_hashes = {line.split(None, 1)[1].removeprefix(payload_prefix): line.split()[0]
                          for line in payload.splitlines() if re.match(r'^[0-9a-f]{64}  ', line)}
        for path in changed:
            if payload_hashes.get(path) != live[path]:
                raise RuntimeError('Live target differs from committed payload: ' + path)
        mounts = root('cat /proc/1/mountinfo')
        mount_records = [line.split() for line in mounts.splitlines() if ' - ' in line]
        proofs = {}
        for path in changed:
            canonical = root('readlink -f ' + shlex.quote(path))
            matching = [row for row in mount_records if len(row) > 5 and
                        (row[4] == canonical or canonical.startswith(row[4].rstrip('/') + '/')) and
                        '/adb/modules/LuoShu/.luoshu-payload/' in row[3]]
            if not matching:
                raise RuntimeError('Changed font lacks exact module-payload mount provenance: ' + path)
            proofs[path] = {'canonical': canonical, 'mount_records': matching}
        return live, {'font': active, 'changed': changed, 'payload_hashes': payload_hashes, 'mount_proofs': proofs, 'mountinfo': mounts}
    try:
        if shell('getprop ro.kernel.qemu') != '1' or shell('getenforce') != 'Enforcing':
            raise RuntimeError('Only authorized Enforcing disposable AVD is supported')
        report['font_directories'] = root('for d in ' + ' '.join('/' + part + '/fonts' for part in FONT_PARTITIONS) + '; do if [ -d "$d" ]; then echo PRESENT:$d; else echo ABSENT:$d; fi; done')
        original_fonts = font_hashes()
        for label, archive in [('baseline', baseline), ('candidate', candidate)]:
            cycle = {'label': label, 'result': 'FAIL', 'zip_sha256': hashlib.sha256(Path(archive).read_bytes()).hexdigest()}
            report['cycles'].append(cycle)
            try:
                print('Android module gate: installing ' + label, flush=True)
                command(['push', str(archive), '/data/local/tmp/luoshu-module.zip'])
                cycle['install'] = root(shlex.quote(magisk) + ' --install-module /data/local/tmp/luoshu-module.zip', timeout=300)
                cycle['install_reboot'] = boot()
                root('test -f ' + MODULE + '/module.prop')
                generator = Path(__file__).with_name('synthetic_fonts.py')
                command(['push', str(generator), '/data/local/tmp/luoshu-synthetic-fonts.py'])
                runtime = MODULE + '/common/python'
                root(f'PYTHONHOME={runtime} PYTHONPATH={runtime}/lib/python3.14:{runtime}/lib/python3.14/site-packages '
                     f'LD_LIBRARY_PATH={runtime}/lib:{runtime}/lib/python3.14/lib-dynload '
                     f'{runtime}/bin/luoshu-python /data/local/tmp/luoshu-synthetic-fonts.py --output /sdcard/LuoShu/fonts --count 2')
                inventory = bridge('fonts', 'refresh')
                cycle['inventory'] = inventory
                fonts = inventory.get('data', {}).get('fonts', [])
                ids = [f['id'] for f in fonts if 'LuoShuSyntheticGate' in json.dumps(f)]
                if len(ids) < 2:
                    raise RuntimeError('Both synthetic fonts are not visible in real module inventory')
                cycle['switch_a'] = switch(ids[0])
                cycle['font_reboot'] = boot()
                mounted_fonts, cycle['mounted_a'] = assert_mounted(ids[0], original_fonts)
                changed = [p for p in original_fonts if mounted_fonts.get(p) != original_fonts[p]]
                if not changed:
                    raise RuntimeError('Font switch did not change any real system-visible font bytes after reboot')
                cycle['changed_system_targets'] = changed
                cycle['mountinfo'] = root('cat /proc/1/mountinfo')
                cycle['live_status'] = bridge('status')
                active_before_failure = root('cat ' + MODULE + '/config/active_font.conf')
                root('dd if=/dev/zero of=/sdcard/LuoShu/fonts/LuoShuBrokenGate.ttf bs=8192 count=1')
                cycle['invalid_switch'] = switch('LuoShuBrokenGate', expect_success=False)
                cycle['prepare_failure_crashes'] = shell('logcat -b crash -d', required=False)
                cycle['prepare_failure_tombstones'] = root('ls -l /data/tombstones', required=False)
                root('rm /sdcard/LuoShu/fonts/LuoShuBrokenGate.ttf')
                if font_hashes() != mounted_fonts or root('cat ' + MODULE + '/config/active_font.conf') != active_before_failure:
                    raise RuntimeError('Failed switch changed prior active font or live mounted bytes')
                if label in ('baseline', 'candidate'):
                    from commit_fault import mv_wrapper
                    fault_dir = '/data/local/tmp/luoshu-commit-fault-' + str(time.monotonic_ns())
                    marker = fault_dir + '/hit'
                    root('mkdir ' + shlex.quote(fault_dir))
                    wrapper_file = output / 'commit-fault-mv.sh'
                    wrapper_file.write_text(mv_wrapper(MODULE, marker))
                    command(['push', str(wrapper_file), fault_dir + '/mv'])
                    root('chmod 0700 ' + shlex.quote(fault_dir + '/mv'))
                    fault_env = 'PATH=' + shlex.quote(fault_dir) + ':"$PATH" '
                    resolved = root(fault_env + 'sh -c ' + shlex.quote('command -v mv'))
                    if resolved != fault_dir + '/mv':
                        raise RuntimeError('Process-local commit fault wrapper not resolved')
                    payload_before = root('find -L ' + MODULE + '/.luoshu-payload -type f -exec sha256sum {} \\; | sort')
                    cycle['commit_failure'] = switch(ids[1], expect_success=False, prefix=fault_env)
                    cycle['commit_failure']['injection_hit'] = root('cat ' + shlex.quote(marker))
                    if (MODULE + '/.luoshu-payload-stage.') not in cycle['commit_failure']['injection_hit']:
                        raise RuntimeError('Commit failure was not injected at the exact rename')
                    cycle['commit_failure']['task_message_specific'] = '提交失败' in cycle['commit_failure'].get('data', {}).get('message', '')
                    cycle['commit_failure']['crash_buffer'] = shell('logcat -b crash -d', required=False)
                    cycle['commit_failure']['tombstone_inventory'] = root('ls -l /data/tombstones', required=False)
                    cycle['commit_failure']['core_log'] = root('tail -n 160 ' + MODULE + '/logs/fontswitch.log', required=False)
                    cycle['commit_failure']['evidence_rule'] = 'Exact one-shot rename marker plus matching failed task; UI may expose generic error. Rollback and reboot bytes must independently match.'
                    if root('find -L ' + MODULE + '/.luoshu-payload -type f -exec sha256sum {} \\; | sort') != payload_before:
                        raise RuntimeError('Commit failure changed previous payload bytes')
                    if font_hashes() != mounted_fonts or root('cat ' + MODULE + '/config/active_font.conf') != active_before_failure:
                        raise RuntimeError('Commit failure changed live fonts or active selection')
                    root('test ! -e ' + MODULE + '/.luoshu-payload-next && test ! -e ' + MODULE + '/config/font-payload-next.conf')
                    cycle['commit_failure']['reboot'] = boot()
                    if font_hashes() != mounted_fonts or root('cat ' + MODULE + '/config/active_font.conf') != active_before_failure:
                        raise RuntimeError('Failed commit was activated after reboot')
                    root('rm -f ' + shlex.quote(fault_dir + '/mv') + ' ' + shlex.quote(marker) + '; rmdir ' + shlex.quote(fault_dir))
                cycle['switch_b'] = switch(ids[1])
                cycle['switch_b_reboot'] = boot()
                mounted_b, cycle['mounted_b'] = assert_mounted(ids[1], original_fonts)
                if mounted_b == mounted_fonts:
                    raise RuntimeError('Second distinct synthetic font did not change system-visible bytes')
                cycle['restore_default'] = switch('default')
                cycle['restore_reboot'] = boot()
                if font_hashes() != original_fonts:
                    raise RuntimeError('Restoring default did not restore exact original system fonts')
                cycle['result'] = 'PASS'
            except Exception as error:
                cycle['error'] = str(error)
                if label != 'baseline':
                    raise
                cycle['result'] = 'BLOCKED'
                root('rm -f /sdcard/LuoShu/fonts/LuoShuBrokenGate.ttf')
                if font_hashes() != original_fonts:
                    raise RuntimeError('Baseline failure left modified fonts; refusing contaminated candidate comparison')
                report['baseline_compatibility'] = 'Original module failed unmodified; candidate has explicit nativebridge entry compatibility'
        # Repeat all four ownership cases in the real Magisk root context with
        # the installed candidate helper, not just the pre-Magisk adb context.
        scope_script = Path(__file__).with_name('task_scope_device.py')
        command(['push', str(scope_script), '/data/local/tmp/luoshu-module-scope.py'])
        runtime = MODULE + '/common/python'
        root(f'PYTHONHOME={runtime} PYTHONPATH={runtime}/lib/python3.14:{runtime}/lib/python3.14/site-packages '
             f'LD_LIBRARY_PATH={runtime}/lib:{runtime}/lib/python3.14/lib-dynload '
             f'{runtime}/bin/luoshu-python /data/local/tmp/luoshu-module-scope.py '
             f'--helper {MODULE}/common/task_scope.py --output /data/local/tmp/luoshu-module-scope.json', timeout=240)
        report['magisk_task_scope'] = json.loads(root('cat /data/local/tmp/luoshu-module-scope.json'))
        if report['magisk_task_scope'].get('result') != 'PASS':
            raise RuntimeError('Installed candidate task ownership failed under Magisk')
        request_script = Path(__file__).with_name('font_request_scope_device.py')
        command(['push', str(request_script), '/data/local/tmp/luoshu-request-scope.py'])
        root(f'PYTHONHOME={runtime} PYTHONPATH={runtime}/lib/python3.14:{runtime}/lib/python3.14/site-packages '
             f'LD_LIBRARY_PATH={runtime}/lib:{runtime}/lib/python3.14/lib-dynload TMPDIR=/data/local/tmp '
             f'{runtime}/bin/luoshu-python /data/local/tmp/luoshu-request-scope.py '
             f'--helper {MODULE}/common/font_request_scope.py --output /data/local/tmp/luoshu-request-scope.json', timeout=360, required=False)
        report['magisk_request_scope'] = json.loads(root('cat /data/local/tmp/luoshu-request-scope.json'))
        if report['magisk_request_scope'].get('result') != 'PASS':
            raise RuntimeError('Installed synchronous request lease cleanup failed under Magisk')
        with zipfile.ZipFile(candidate) as archive:
            apk_bytes = archive.read('bundled/LuoShu-App.apk')
            expected_apk = hashlib.sha256(apk_bytes).hexdigest()
        # The module intentionally does NOT auto-install .stabletest. Install
        # the exact test APK explicitly rather than relying on a prior boot.
        with tempfile.NamedTemporaryFile(suffix='.apk') as apk_file:
            apk_file.write(apk_bytes); apk_file.flush()
            sdk = Path(os.environ['ANDROID_HOME'])
            aapt_tools = sorted(sdk.glob('build-tools/*/aapt2'))
            if not aapt_tools:
                raise RuntimeError('Official aapt2 is needed to verify candidate package before install')
            badging = subprocess.run([str(aapt_tools[-1]), 'dump', 'badging', apk_file.name], capture_output=True, text=True, timeout=30)
            if badging.returncode or not re.search(r"^package: name='" + re.escape(PACKAGE) + r"'", badging.stdout, re.M):
                raise RuntimeError('Candidate APK manifest is not the isolated authorized package')
            command(['install', '-r', apk_file.name], timeout=120)
        apk_paths = [line.removeprefix('package:') for line in shell('pm path ' + PACKAGE).splitlines() if line.startswith('package:')]
        if len(apk_paths) != 1 or not apk_paths[0].startswith('/data/app/'):
            raise RuntimeError('Unexpected installed candidate APK layout')
        installed_apk = root('sha256sum ' + shlex.quote(apk_paths[0])).split()[0]
        if installed_apk != expected_apk:
            raise RuntimeError('Installed App bytes do not match the exact candidate module')
        report['candidate_apk_sha256'] = expected_apk
        # Resolve one exact installed UID; never grant another package/shared UID.
        packages = shell('cmd package list packages -U')
        uid = resolve_authorized_uid(packages)
        until = int(shell('date +%s')) + 3600
        query = f'INSERT OR REPLACE INTO policies(uid,policy,until,logging,notification) VALUES({uid},2,{until},1,1);'
        granted_uid = uid  # Cleanup responsibility precedes possibly committed/timed-out write.
        root(shlex.quote(magisk) + ' --sqlite ' + shlex.quote(query))
        stored_policy = root(shlex.quote(magisk) + ' --sqlite ' + shlex.quote(f'SELECT uid,policy,until FROM policies WHERE uid={uid};'))
        if f'uid={uid}|policy=2|until={until}' not in stored_policy:
            raise RuntimeError('Exact time-bounded candidate root policy did not read back')
        if resolve_authorized_uid(shell('cmd package list packages -U')) != uid:
            raise RuntimeError('Candidate UID changed while granting root')
        report['root_policy'] = {'package': PACKAGE, 'uid': uid, 'expires': until,
                                'note': 'Policy grant is not yet proof of actual App execution'}
        report['app_root'] = 'GRANTED_NOT_PROVEN'
        from app_library_gate import measure
        report['library_timings'] = []
        report['fixture_inventory'] = []
        with tempfile.TemporaryDirectory(prefix='luoshu-synthetic-inventory-') as temp:
            staging = Path(temp)
            templates = []
            for index in (0, 1):
                source = f'/sdcard/LuoShu/fonts/LuoShuSyntheticGate{index:04d}.ttf'
                target = staging / f'template-{index}.ttf'
                command(['pull', source, str(target)])
                data = target.read_bytes()
                if len(data) <= 4096 or data[:4] != b'\x00\x01\x00\x00':
                    raise RuntimeError('Original Android-generated TTF template is not valid fixture bytes')
                if root('sha256sum ' + source).split()[0] != hashlib.sha256(data).hexdigest():
                    raise RuntimeError('Pulled synthetic fixture changed in transit')
                templates.append(data)
            fixture_templates = templates
        for count in (100, 1000):
            # Only fixture duplication runs on the host. Module/runtime/App
            # parsing stays on Android using the unchanged formal ARM64 runtime.
            # This tests N independent filenames with two distinct TTF contents.
            with tempfile.TemporaryDirectory(prefix='luoshu-synthetic-inventory-') as temp:
                fonts_dir = Path(temp) / 'fonts'
                fonts_dir.mkdir()
                expected = {}
                for index in range(count):
                    name = f'LuoShuSyntheticGate{index:04d}.ttf'
                    data = fixture_templates[index % 2]
                    (fonts_dir / name).write_bytes(data)
                    expected[name] = hashlib.sha256(data).hexdigest()
                command(['push', str(fonts_dir) + '/.', '/sdcard/LuoShu/fonts/'], timeout=180)
            hashes = root('sha256sum /sdcard/LuoShu/fonts/LuoShuSyntheticGate*.ttf', timeout=180)
            actual = {line.split(None, 1)[1].rsplit('/', 1)[-1]: line.split()[0]
                      for line in hashes.splitlines() if re.match(r'^[0-9a-f]{64}  ', line)}
            if actual != expected:
                raise RuntimeError('Actual Android synthetic inventory count or bytes differ from intended fixtures')
            report['fixture_inventory'].append({'files': count, 'unique_content_hashes': sorted(set(expected.values())),
                                               'note': 'Two original Android-generated synthetic TTF contents copied into independent filenames; not N distinct font feature sets'})
            print(f'Android module gate: real App library timings for {count} synthetic fonts', flush=True)
            timing = measure(adb, output / f'library-{count}', count)
            report['library_timings'].append(timing)
            report['app_root'] = 'PROVEN_BY_ACTUAL_APP_VERIFIED_ROOT_LIBRARY'
            report.setdefault('app_verified_inventory_counts', []).append(count)
        report['app_root'] = 'PROVEN_BY_ACTUAL_APP_VERIFIED_ROOT_LIBRARY'
        from app_library_gate import apply_fixture
        def task_fields(text):
            return dict(line.split('=', 1) for line in text.splitlines() if '=' in line)
        old_task = task_fields(root('cat ' + MODULE + '/config/switch_task.conf', required=False)).get('task')
        app_boot = shell('cat /proc/sys/kernel/random/boot_id')
        report['app_apply'] = apply_fixture(adb, 'LuoShuSyntheticGate0000', output / 'app-apply')
        deadline = time.monotonic() + 420
        while time.monotonic() < deadline:
            current_task = task_fields(root('cat ' + MODULE + '/config/switch_task.conf', required=False))
            task_id = current_task.get('task')
            if task_id and task_id != old_task and current_task.get('font') == 'LuoShuSyntheticGate0000' and current_task.get('bootId') == app_boot:
                owned_tasks.add(task_id)
                state = bridge('switch_status', task_id)
                data = state.get('data', {})
                if data.get('task') != task_id or data.get('font') != 'LuoShuSyntheticGate0000' or data.get('bootId') != app_boot:
                    raise RuntimeError('App apply task identity changed')
                if state.get('data', {}).get('state') == 'success':
                    report['app_apply']['task'] = state
                    break
                if state.get('data', {}).get('state') in ('failed', 'error', 'cancelled'):
                    raise RuntimeError('Actual App font apply task failed: ' + json.dumps(state, ensure_ascii=False))
            time.sleep(1)
        else:
            raise RuntimeError('No new successful matching task followed the actual App click')
        report['app_apply']['reboot'] = boot()
        _, report['app_apply']['mounted'] = assert_mounted('LuoShuSyntheticGate0000', original_fonts)
        report['app_apply']['result'] = 'PASS'
        report['app_apply']['restore'] = switch('default')
        report['app_apply']['restore_reboot'] = boot()
        if font_hashes() != original_fonts:
            raise RuntimeError('Final actual-App apply rollback did not restore stock font bytes')
        report['delivery_gate'] = 'BLOCKED'
        report['remaining_coverage'] = ['Final artifact review of native-crash buffers, UI samples and cleanup evidence is still required']
        report['coverage_note'] = ('Baseline module is CLI/mount reference only; original baseline App was not granted root. '
                                   'App timings are candidate-only on nativebridge x86_64 AVD, not native ARM64 or OEM-ROM validation.')
    except Exception as error:
        report['error'] = str(error)
    finally:
        if granted_uid is not None:
            try:
                shell('am force-stop ' + PACKAGE)
                runtime = MODULE + '/common/python'
                for task in sorted(owned_tasks):
                    root(f'PYTHONHOME={runtime} LD_LIBRARY_PATH={runtime}/lib:{runtime}/lib/python3.14/lib-dynload {runtime}/bin/luoshu-python {MODULE}/common/task_scope.py stop {MODULE}/config/switch_task_worker.pid ' + shlex.quote(task))
                report['owned_tasks_cancelled'] = sorted(owned_tasks)
            except Exception as error:
                report['process_cleanup_error'] = str(error)
                report['delivery_gate'] = 'FAIL'
            try:
                root(shlex.quote(magisk) + ' --sqlite ' + shlex.quote(f'DELETE FROM policies WHERE uid={granted_uid};'))
                remaining = root(shlex.quote(magisk) + ' --sqlite ' + shlex.quote(f'SELECT uid FROM policies WHERE uid={granted_uid};'))
                if remaining.strip():
                    raise RuntimeError('Root policy still exists after revocation')
                report['root_policy_revoked'] = True
            except Exception as error:
                report['root_policy_cleanup_error'] = str(error)
                report['delivery_gate'] = 'FAIL'
        (output / 'module-gate.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report
