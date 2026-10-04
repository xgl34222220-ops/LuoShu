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


def payload_mount_proof(path, canonical, stock_paths, live_digest, payload_hashes, mount_records):
    """Bind stock aliases to their real target without relaxing bytes/provenance."""
    if not canonical or stock_paths.get(path) != canonical:
        raise RuntimeError('Original system font alias changed: ' + path)
    slots = [p for p, target in stock_paths.items()
             if target == canonical and p in payload_hashes]
    if canonical in payload_hashes and canonical not in slots:
        slots.append(canonical)
    if not slots or any(payload_hashes[p] != live_digest for p in slots):
        raise RuntimeError('Live target differs from committed canonical payload: ' + path)
    # Prefer the canonical slot, then the requested partition spelling. Any
    # other original alias must have identical bytes, rather than concealing a
    # conflicting per-alias payload which the actual system link cannot load.
    slot = canonical if canonical in slots else path if path in slots else sorted(slots)[0]
    expected_source = MODULE.removeprefix('/data') + '/.luoshu-payload' + slot
    matching = []
    for row in mount_records:
        if len(row) <= 5:
            continue
        destination = row[4].rstrip('/')
        if canonical == destination:
            source = row[3]
        elif canonical.startswith(destination + '/'):
            source = row[3].rstrip('/') + canonical[len(destination):]
        else:
            continue
        if source in (expected_source, '/data' + expected_source):
            matching.append(row)
    if not matching:
        raise RuntimeError('Changed font lacks exact canonical module-payload mount provenance: ' + path)
    return {'canonical': canonical, 'stock_canonical': stock_paths[path],
            'payload_path': slot, 'payload_sha256': live_digest, 'mount_records': matching}


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
    diagnostic_only = os.environ.get('LUOSHU_APP_DIAGNOSTIC_ONLY') == '1'
    report['run_scope'] = 'APP_DIAGNOSTIC_ONLY; baseline/module cycles and process gates NOT_RUN' if diagnostic_only else 'FULL_GATE'
    granted_uid = None
    owned_tasks = set()
    def command(args, timeout=120, required=True):
        started = time.monotonic()
        try:
            p = subprocess.run([adb, '-s', 'emulator-5554'] + args, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            def decoded(value):
                return value.decode(errors='replace') if isinstance(value, bytes) else (value or '')
            report['steps'].append({'argv': args, 'result': 'HOST_ADB_TIMEOUT_GUEST_COMPLETION_UNPROVEN', 'elapsed_seconds': time.monotonic() - started,
                                    'stdout': decoded(error.stdout), 'stderr': decoded(error.stderr)})
            raise
        report['steps'].append({'argv': args, 'exit': p.returncode, 'elapsed_seconds': time.monotonic() - started, 'stdout': p.stdout, 'stderr': p.stderr})
        if required and p.returncode:
            raise RuntimeError('Android command failed: ' + shlex.join(args))
        return p.stdout.strip()
    def shell(text, timeout=120, required=True):
        return command(['shell', text], timeout, required)
    def root(text, timeout=180, required=True):
        return shell(shlex.quote(magisk) + ' su -mm -c ' + shlex.quote(text), timeout, required)
    def boot():
        before = shell('cat /proc/sys/kernel/random/boot_id')
        from boot_evidence import wait_for_reboot
        return wait_for_reboot(command,
            lambda: ensure_root([adb, '-s', 'emulator-5554'], report['steps']),
            before, output, report)
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
        mounts = root('cat /proc/1/mountinfo')
        mount_records = [line.split() for line in mounts.splitlines() if ' - ' in line]
        proofs = {}
        for path in changed:
            canonical = root('readlink -f ' + shlex.quote(path))
            proofs[path] = payload_mount_proof(path, canonical, original_paths,
                                              live[path], payload_hashes, mount_records)
        return live, {'font': active, 'changed': changed, 'payload_hashes': payload_hashes, 'mount_proofs': proofs, 'mountinfo': mounts}
    try:
        if shell('getprop ro.kernel.qemu') != '1' or shell('getenforce') != 'Enforcing':
            raise RuntimeError('Only authorized Enforcing disposable AVD is supported')
        report['font_directories'] = root('for d in ' + ' '.join('/' + part + '/fonts' for part in FONT_PARTITIONS) + '; do if [ -d "$d" ]; then echo PRESENT:$d; else echo ABSENT:$d; fi; done')
        original_fonts = font_hashes()
        paths_text = root('for p in ' + shlex.join(sorted(original_fonts)) +
                          '; do c=$(readlink -f "$p") || exit 1; '
                          'printf "%s\\t%s\\n" "$p" "$c"; done')
        original_paths = {}
        for line in paths_text.splitlines():
            path, separator, canonical = line.partition('\t')
            if not separator or not canonical.startswith('/') or path in original_paths:
                raise RuntimeError('Incomplete or duplicated original font path identity')
            original_paths[path] = canonical
        if set(original_paths) != set(original_fonts):
            raise RuntimeError('Original font alias identity set differs from stock hashes')
        report['stock_font_canonical_paths'] = original_paths
        # Keep the actual untouched AOSP collection for reproducible compiler
        # diagnostics. Never pull a mounted candidate or modify the stock font.
        stock_collection = '/system/fonts/NotoSansCJK-Regular.ttc'
        stock_copy = output / 'stock-NotoSansCJK-Regular.ttc'
        command(['pull', stock_collection, str(stock_copy)])
        copied_hash = hashlib.sha256(stock_copy.read_bytes()).hexdigest()
        if copied_hash != original_fonts.get(stock_collection):
            raise RuntimeError('Diagnostic collection is not the original system font')
        report['stock_collection_source'] = {'path': stock_collection, 'sha256': copied_hash,
                                             'bytes': stock_copy.stat().st_size}
        archives = [('candidate', candidate)] if diagnostic_only else [('baseline', baseline), ('candidate', candidate)]
        for label, archive in archives:
            cycle = {'label': label, 'result': 'FAIL', 'zip_sha256': hashlib.sha256(Path(archive).read_bytes()).hexdigest()}
            report['cycles'].append(cycle)
            try:
                print('Android module gate: installing ' + label, flush=True)
                command(['push', str(archive), '/data/local/tmp/luoshu-module.zip'])
                cycle['install'] = root(shlex.quote(magisk) + ' --install-module /data/local/tmp/luoshu-module.zip', timeout=300)
                cycle['install_reboot'] = boot()
                root('test -f ' + MODULE + '/module.prop')
                if label == 'candidate' and not diagnostic_only:
                    from upgrade_evidence import verify as verify_upgrade
                    verify_upgrade(root, report['upgrade'])
                generator = Path(__file__).with_name('synthetic_fonts.py')
                command(['push', str(generator), '/data/local/tmp/luoshu-synthetic-fonts.py'])
                runtime = MODULE + '/common/python'
                root(f'PYTHONHOME={runtime} PYTHONPATH={runtime}/lib/python3.14:{runtime}/lib/python3.14/site-packages '
                     f'LD_LIBRARY_PATH={runtime}/lib:{runtime}/lib/python3.14/lib-dynload '
                     f'{runtime}/bin/luoshu-python /data/local/tmp/luoshu-synthetic-fonts.py --output /sdcard/LuoShu/fonts --count 2')
                if diagnostic_only:
                    cycle['result'] = 'INSTALL_ONLY'
                    continue
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
                cycle['restore_hashes_equal_stock'] = True
                if label == 'candidate':
                    # The existing App gate below remains an independent real UI
                    # single-font test. Exercise the previously uncovered legacy
                    # composite monitor/finalizer path before calling this green.
                    from composite_gate import run as run_composite
                    report['legacy_composite'] = {}
                    run_composite(report['legacy_composite'], MODULE, root, command,
                                  boot, font_hashes, assert_mounted, switch,
                                  original_fonts, ids, output)
                cycle['result'] = 'PASS'
                if label == 'baseline':
                    from upgrade_evidence import prepare as prepare_upgrade
                    report['upgrade'] = prepare_upgrade(root)
            except Exception as error:
                cycle['error'] = str(error)
                if label != 'baseline':
                    raise
                cycle['result'] = 'BLOCKED'
                root('rm -f /sdcard/LuoShu/fonts/LuoShuBrokenGate.ttf')
                if font_hashes() != original_fonts:
                    raise RuntimeError('Baseline failure left modified fonts; refusing contaminated candidate comparison')
                report['baseline_compatibility'] = 'Original module failed unmodified; candidate has explicit nativebridge entry compatibility'
        if not diagnostic_only:
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
            # Run exactly the new host contract cases under original ARM64
            # Python + Android mksh/toybox in this disposable Magisk context.
            handoff_script = Path(__file__).resolve().parents[2] / 'scripts/mix_handoff_contract_test.py'
            command(['push', str(handoff_script), '/data/local/tmp/luoshu-mix-handoff.py'])
            handoff_boot = root('cat /proc/sys/kernel/random/boot_id').strip()
            root(f'PYTHONHOME={runtime} PYTHONPATH={runtime}/lib/python3.14:{runtime}/lib/python3.14/site-packages '
                 f'LD_LIBRARY_PATH={runtime}/lib:{runtime}/lib/python3.14/lib-dynload TMPDIR=/data/local/tmp '
                 f'{runtime}/bin/luoshu-python /data/local/tmp/luoshu-mix-handoff.py '
                 f'--module {MODULE} --shell /system/bin/sh --output /data/local/tmp/luoshu-mix-handoff.json', timeout=240)
            report['magisk_mix_handoff'] = json.loads(root('cat /data/local/tmp/luoshu-mix-handoff.json'))
            handoff = report['magisk_mix_handoff']
            handoff['boot_id'] = root('cat /proc/sys/kernel/random/boot_id').strip()
            handoff['selinux'] = root('getenforce').strip()
            if handoff['boot_id'] != handoff_boot or handoff['selinux'] != 'Enforcing':
                raise RuntimeError('Android context changed during composite handoff verification')
            if (handoff.get('result') != 'PASS' or handoff.get('environment') != 'ANDROID'
                    or handoff.get('case_count') != 32 or len(handoff.get('cases', [])) != 32
                    or any(case.get('result') != 'PASS' for case in handoff['cases'])):
                raise RuntimeError('Installed composite handoff/UTF-8 message contract failed under Android')
            preview_script = Path(__file__).resolve().parents[2] / 'scripts/preview_source_contract_test.py'
            command(['push', str(preview_script), '/data/local/tmp/luoshu-preview-source-contract.py'])
            preview_boot = root('cat /proc/sys/kernel/random/boot_id').strip()
            root(f'PYTHONHOME={runtime} PYTHONPATH={runtime}/lib/python3.14:{runtime}/lib/python3.14/site-packages '
                 f'LD_LIBRARY_PATH={runtime}/lib:{runtime}/lib/python3.14/lib-dynload TMPDIR=/data/local/tmp '
                 f'{runtime}/bin/luoshu-python /data/local/tmp/luoshu-preview-source-contract.py '
                 f'--module {MODULE} --shell /system/bin/sh --output /data/local/tmp/luoshu-preview-source-contract.json', timeout=240)
            report['magisk_preview_source'] = json.loads(root('cat /data/local/tmp/luoshu-preview-source-contract.json'))
            preview = report['magisk_preview_source']
            preview['boot_id'] = root('cat /proc/sys/kernel/random/boot_id').strip()
            preview['selinux'] = root('getenforce').strip()
            if preview['boot_id'] != preview_boot:
                raise RuntimeError('Android boot changed during preview source selection verification')
            from verdict import preview_source_blockers
            preview_errors = preview_source_blockers(preview)
            if preview_errors:
                raise RuntimeError('; '.join(preview_errors))
            error_script = Path(__file__).resolve().parents[2] / 'scripts/composite_error_contract_test.py'
            command(['push', str(error_script), '/data/local/tmp/luoshu-composite-error-contract.py'])
            error_boot = root('cat /proc/sys/kernel/random/boot_id').strip()
            root(f'PYTHONHOME={runtime} PYTHONPATH={runtime}/lib/python3.14:{runtime}/lib/python3.14/site-packages '
                 f'LD_LIBRARY_PATH={runtime}/lib:{runtime}/lib/python3.14/lib-dynload TMPDIR=/data/local/tmp '
                 f'{runtime}/bin/luoshu-python /data/local/tmp/luoshu-composite-error-contract.py '
                 f'--module {MODULE} --shell /system/bin/sh --output /data/local/tmp/luoshu-composite-error-contract.json', timeout=240)
            report['magisk_composite_error'] = json.loads(root('cat /data/local/tmp/luoshu-composite-error-contract.json'))
            engine_error = report['magisk_composite_error']
            engine_error['boot_id'] = root('cat /proc/sys/kernel/random/boot_id').strip()
            engine_error['selinux'] = root('getenforce').strip()
            if engine_error['boot_id'] != error_boot:
                raise RuntimeError('Android boot changed during composite error function verification')
            from verdict import composite_error_blockers
            error_failures = composite_error_blockers(engine_error)
            if error_failures:
                raise RuntimeError('; '.join(error_failures))
            stock_error_script = Path(__file__).resolve().parents[2] / 'scripts/stock_error_contract_test.py'
            command(['push', str(stock_error_script), '/data/local/tmp/luoshu-stock-error-contract.py'])
            stock_error_boot = root('cat /proc/sys/kernel/random/boot_id').strip()
            root(f'PYTHONHOME={runtime} PYTHONPATH={runtime}/lib/python3.14:{runtime}/lib/python3.14/site-packages '
                 f'LD_LIBRARY_PATH={runtime}/lib:{runtime}/lib/python3.14/lib-dynload TMPDIR=/data/local/tmp '
                 f'{runtime}/bin/luoshu-python /data/local/tmp/luoshu-stock-error-contract.py '
                 f'--module {MODULE} --shell /system/bin/sh --output /data/local/tmp/luoshu-stock-error-contract.json', timeout=240)
            report['magisk_stock_error'] = json.loads(root('cat /data/local/tmp/luoshu-stock-error-contract.json'))
            stock_error = report['magisk_stock_error']
            stock_error['boot_id'] = root('cat /proc/sys/kernel/random/boot_id').strip()
            stock_error['selinux'] = root('getenforce').strip()
            installed_helper = root(f'sha256sum {MODULE}/common/task_scope.py').split()[0]
            if stock_error['boot_id'] != stock_error_boot or stock_error['helper_sha256'] != installed_helper:
                raise RuntimeError('Android stock-error boot or installed helper identity changed')
            from verdict import stock_error_blockers
            stock_errors = stock_error_blockers(stock_error)
            if stock_errors:
                raise RuntimeError('; '.join(stock_errors))
            output_script = Path(__file__).resolve().parents[2] / 'scripts/inventory_output_contract_test.py'
            command(['push', str(output_script), '/data/local/tmp/luoshu-inventory-output-contract.py'])
            output_boot = root('cat /proc/sys/kernel/random/boot_id').strip()
            root(f'PYTHONHOME={runtime} PYTHONPATH={runtime}/lib/python3.14:{runtime}/lib/python3.14/site-packages '
                 f'LD_LIBRARY_PATH={runtime}/lib:{runtime}/lib/python3.14/lib-dynload TMPDIR=/data/local/tmp '
                 f'{runtime}/bin/luoshu-python /data/local/tmp/luoshu-inventory-output-contract.py '
                 f'--module {MODULE} --shell /system/bin/sh --output /data/local/tmp/luoshu-inventory-output-contract.json', timeout=240)
            report['magisk_inventory_output'] = json.loads(root('cat /data/local/tmp/luoshu-inventory-output-contract.json'))
            output_transport = report['magisk_inventory_output']
            output_transport.update(module=MODULE, shell='/system/bin/sh',
                          boot_id=root('cat /proc/sys/kernel/random/boot_id').strip(), selinux=root('getenforce').strip())
            installed_router = root(f'sha256sum {MODULE}/common/font_manager.sh').split()[0]
            if (output_transport['boot_id'] != output_boot or output_boot != stock_error_boot or
                    output_transport['router_sha256'] != installed_router):
                raise RuntimeError('Android inventory-output boot or installed router identity changed')
            from verdict import inventory_output_blockers
            output_errors = inventory_output_blockers(output_transport)
            if output_errors:
                raise RuntimeError('; '.join(output_errors))
            report['axis_metadata'] = json.loads(root(
                f'PYTHONHOME={runtime} PYTHONPATH={runtime}/lib/python3.14:{runtime}/lib/python3.14/site-packages '
                f'LD_LIBRARY_PATH={runtime}/lib:{runtime}/lib/python3.14/lib-dynload '
                f'{runtime}/bin/luoshu-python {MODULE}/common/font_axis_info.py {stock_collection}', timeout=60))
            axis_metadata = report['axis_metadata']
            weight_axis = axis_metadata.get('weight') or {}
            if (axis_metadata.get('status') != 'ok' or not axis_metadata.get('variable')
                    or not axis_metadata.get('hasWeight') or weight_axis.get('tag') != 'wght'
                    or (weight_axis.get('min'), weight_axis.get('default'), weight_axis.get('max')) != (400, 400, 900)
                    or not weight_axis.get('name') or weight_axis.get('hidden') is not False):
                raise RuntimeError('Actual Android CFF2 collection axis/name metadata differs from stock contract')
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
        if not diagnostic_only:
            # Only our original disposable fixture enters the picker. Selecting
            # it must display real names/hidden-axis semantics without applying.
            axis_fixture = '/sdcard/LuoShu/fonts/LuoShuAxisGate.ttf'
            axis_config = '/sdcard/LuoShu/fonts/LuoShuAxisGate.conf'
            intake = f'/data/user/0/{PACKAGE}/cache/native_import/luoshu-axis-gate'
            runtime = MODULE + '/common/python'
            # Use the same trusted intake and importer as the native picker.
            # Raw public-directory copies intentionally have no fvar metadata;
            # do not fabricate an inventory cache or is_variable configuration.
            root(f'test ! -e {axis_fixture} && test ! -e {axis_config} && '
                 f'mkdir -p {intake.rsplit("/", 1)[0]} && mkdir {intake}')
            try:
                root(f'PYTHONHOME={runtime} PYTHONPATH={runtime}/lib/python3.14:{runtime}/lib/python3.14/site-packages '
                     f'LD_LIBRARY_PATH={runtime}/lib:{runtime}/lib/python3.14/lib-dynload '
                     f'{runtime}/bin/luoshu-python /data/local/tmp/luoshu-synthetic-fonts.py '
                     f'--output {intake} --axis-fixture', timeout=90)
                source_sha256 = root(f'sha256sum {intake}/LuoShuAxisGate.ttf').split()[0]
                imported = bridge('import_file', intake + '/LuoShuAxisGate.ttf', 'LuoShuAxisGate.ttf')
                imported_data = imported.get('data', {})
                if (imported.get('status') != 'ok' or imported_data.get('kind') != 'font'
                        or imported_data.get('id') != 'LuoShuAxisGate'
                        or imported_data.get('supportsCjk') is not True or imported_data.get('duplicate') is not False):
                    raise RuntimeError('Original axis fixture did not pass the actual native import path: ' + json.dumps(imported))
                if root('sha256sum ' + axis_fixture).split()[0] != source_sha256:
                    raise RuntimeError('Native import changed original axis fixture bytes')
                inventory = bridge('fonts', 'refresh')
                fonts = inventory.get('data', {}).get('fonts', [])
                selected = [font for font in fonts if font.get('id') == 'LuoShuAxisGate']
                if len(selected) != 1 or selected[0].get('valid') is not True or selected[0].get('variable') is not True:
                    raise RuntimeError('Original variable-axis fixture is not visible in actual root inventory')
                from app_axis_gate import qualify as qualify_axes
                try:
                    report['app_axes'] = qualify_axes(adb, output / 'app-axes', selected[0]['name'],
                                                      [font['name'] for font in fonts])
                except Exception:
                    # Keep the real FAIL and its import provenance in the top-level
                    # report too. Missing success fields must still block verdict.
                    failure_report = output / 'app-axes' / 'report.json'
                    if failure_report.is_file():
                        report['app_axes'] = json.loads(failure_report.read_text())
                    raise
                finally:
                    if 'app_axes' in report:
                        report['app_axes'].update(source_sha256=source_sha256, import_result=imported,
                                                  font_id=selected[0]['id'])
                        report['app_axes']['imported_sha256'] = root('sha256sum ' + axis_fixture).split()[0]
                report['app_axes']['stock_hashes_unchanged'] = font_hashes() == original_fonts
                if not report['app_axes']['stock_hashes_unchanged']:
                    raise RuntimeError('Read-only App axis inspection changed live system font bytes')
            finally:
                root(f'rm -f {axis_fixture} {axis_config} {intake}/LuoShuAxisGate.ttf {intake}/LICENSE.txt && rmdir {intake}')
                bridge('fonts', 'refresh')
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
        for count in ((1000,) if diagnostic_only else (100, 1000)):
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
        from app_library_gate import apply_fixture, capture_apply_evidence
        def task_fields(text):
            return dict(line.split('=', 1) for line in text.splitlines() if '=' in line)
        old_task = task_fields(root('cat ' + MODULE + '/config/switch_task.conf', required=False)).get('task')
        app_boot = shell('cat /proc/sys/kernel/random/boot_id')
        report['app_apply'] = {'font_id': 'LuoShuSyntheticGate0000'}
        report['app_apply'].update(apply_fixture(adb, 'LuoShuSyntheticGate0000', output / 'app-apply'))
        apply_started = time.monotonic()
        deadline = apply_started + 420
        admission_deadline = apply_started + 75
        observed_new_task = False
        next_observation = apply_started + 40
        report['app_apply']['observations'] = []
        while time.monotonic() < deadline:
            current_task = task_fields(root('cat ' + MODULE + '/config/switch_task.conf', required=False))
            task_id = current_task.get('task')
            if task_id and task_id != old_task and current_task.get('font') == 'LuoShuSyntheticGate0000' and current_task.get('bootId') == app_boot:
                observed_new_task = True
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
            if time.monotonic() >= next_observation:
                report['app_apply']['observations'].append(capture_apply_evidence(adb, output / 'app-apply', 'after-' + str(int(time.monotonic() - apply_started)) + 's'))
                next_observation = time.monotonic() + 60
            if not observed_new_task and time.monotonic() >= admission_deadline:
                raise RuntimeError('No new matching module task within 75s of App confirmation (App preflight35s + start20s); final UI/log evidence required')
            time.sleep(1)
        else:
            raise RuntimeError('Matching App task did not succeed within 420s')
        from verdict import input_validation_blockers
        input_log = root('cat ' + MODULE + '/logs/fontswitch.log')
        (output / 'app-apply' / 'fontswitch-completed.log').write_text(input_log)
        input_events = []
        for line in input_log.splitlines():
            if line.startswith('[font-switch-input] '):
                event = json.loads(line[len('[font-switch-input] '):])
                if event.get('task') == task_id:
                    input_events.append(event)
        report['app_apply']['input_events'] = input_events
        errors = input_validation_blockers(input_events, task_id, app_boot)
        if errors:
            raise RuntimeError('App input validation chain incomplete: ' + '; '.join(errors))
        report['app_apply']['completed_observation'] = capture_apply_evidence(adb, output / 'app-apply', 'task-success-before-reboot')
        report['app_apply']['reboot'] = boot()
        _, report['app_apply']['mounted'] = assert_mounted('LuoShuSyntheticGate0000', original_fonts)
        report['app_apply']['result'] = 'PASS'
        report['app_apply']['restore'] = switch('default')
        report['app_apply']['restore_reboot'] = boot()
        if font_hashes() != original_fonts:
            raise RuntimeError('Final actual-App apply rollback did not restore stock font bytes')
        report['app_apply']['restore_hashes_equal_stock'] = True
        if not diagnostic_only:
            from app_composite_gate import qualify as qualify_app_composite
            actual_inventory = bridge('fonts', 'scan')
            if actual_inventory.get('status') != 'ok':
                raise RuntimeError('Actual inventory unavailable for App composite selection')
            report['app_composite'] = {}
            qualify_app_composite(report['app_composite'], adb, MODULE, root, command, boot,
                                  font_hashes, assert_mounted, switch, original_fonts,
                                  ['LuoShuSyntheticGate0000', 'LuoShuSyntheticGate0001', 'LuoShuSyntheticGate0002'],
                                  actual_inventory.get('data', {}).get('fonts', []),
                                  output / 'app-composite')
        final_ui = measure(adb, output / 'final-ui', 1000, repetitions=1)
        report['final_ui'] = {'result': final_ui['result'], 'target_fatal': False, 'anr': False,
                              'note': 'Fresh actual App cold/warm verified library after restore reboot', 'observations': final_ui}
        report['delivery_gate'] = 'BLOCKED'
        report['scope_limits'] = ['AOSP API35 x86_64 with original ARM64 runtime via nativebridge; no native ARM64 or OEM-ROM claim',
                                  '100/1000 independent filenames contain two original synthetic TTF contents',
                                  'Baseline App performance and backup restore API not tested or counted as PASS']
        report['baseline_native_crash_observed'] = any(c.get('prepare_failure_crashes') or c.get('commit_failure', {}).get('crash_buffer') for c in report['cycles'] if c['label'] == 'baseline')
        report['coverage_note'] = ('Baseline module is CLI/mount reference only; original baseline App was not granted root. '
                                   'App timings are candidate-only on nativebridge x86_64 AVD, not native ARM64 or OEM-ROM validation.')
    except Exception as error:
        report['error'] = str(error)
        if granted_uid is not None:
            # Capture the owned App's threads before slower UI/CLI diagnostics
            # or force-stop/teardown can replace the useful failure evidence.
            from app_anr import capture_owned_anr
            report['app_anr_diagnostic'] = capture_owned_anr(adb, magisk, output / 'app-anr', 'failure')
        if 'app_apply' in report:
            from app_library_gate import capture_apply_evidence
            report['app_apply']['final_observation'] = capture_apply_evidence(adb, output / 'app-apply', 'final-failure')
            report['app_apply']['module_task'] = root('cat ' + MODULE + '/config/switch_task.conf', required=False)
            report['app_apply']['module_log'] = root('tail -n 160 ' + MODULE + '/logs/fontswitch.log', required=False)
            # This read-only administrative replay is strictly diagnostic. It
            # cannot satisfy actual-App acceptance or extend its 35s deadline.
            started = time.monotonic()
            try:
                diagnostic = root('sh ' + MODULE + '/common/app_bridge.sh validate LuoShuSyntheticGate0000', timeout=35, required=False)
                report['app_apply']['diagnostic_validate'] = {'scope': 'DIAGNOSTIC CLI ONLY', 'elapsed_seconds': time.monotonic() - started, 'stdout': diagnostic, 'command_evidence': report['steps'][-1]}
            except Exception as replay_error:
                report['app_apply']['diagnostic_validate'] = {'scope': 'DIAGNOSTIC CLI ONLY', 'elapsed_seconds': time.monotonic() - started, 'error': str(replay_error)}
            trace_started = time.monotonic()
            try:
                trace = root('sh -x ' + MODULE + '/common/font_manager_v4.sh action validate LuoShuSyntheticGate0000', timeout=35, required=False)
                report['app_apply']['diagnostic_manager_trace'] = {'scope': 'DIAGNOSTIC direct manager ONLY; after bridge replay, cache may be warm', 'elapsed_seconds': time.monotonic() - trace_started, 'stdout': trace, 'command_evidence': report['steps'][-1]}
            except Exception as trace_error:
                report['app_apply']['diagnostic_manager_trace'] = {'scope': 'DIAGNOSTIC direct manager ONLY', 'error': str(trace_error), 'command_evidence': report['steps'][-1]}
            report['app_apply']['post_diagnostic_observation'] = capture_apply_evidence(adb, output / 'app-apply', 'after-cli-diagnostic')
    finally:
        # Native crashes in finite composite children can be hidden by their
        # shell callers. Capture the active rooted guest before teardown, also
        # when generation fails before a reboot is attempted.
        for filename, query in (
                ('module-final-crash-log.txt', 'logcat -b crash -d -t 2000'),
                ('module-final-system-log.txt', 'logcat -b all -d -t 4000'),
                ('module-final-dmesg.txt', 'dmesg | tail -n 1200'),
                ('module-final-tombstones.txt', 'for f in /data/tombstones/tombstone_*; do '
                 'case "$f" in *.pb) continue;; esac; [ -f "$f" ] || continue; '
                 'echo "GATE_TOMBSTONE:$f"; head -c 262144 "$f"; done')):
            try:
                (output / filename).write_text(root(query, timeout=45, required=False) + '\n')
            except Exception as error:
                report.setdefault('native_diagnostic_errors', {})[filename] = str(error)
        if granted_uid is not None:
            try:
                shell('am force-stop ' + PACKAGE)
                runtime = MODULE + '/common/python'
                for task in sorted(owned_tasks):
                    root(f'PYTHONHOME={runtime} LD_LIBRARY_PATH={runtime}/lib:{runtime}/lib/python3.14/lib-dynload {runtime}/bin/luoshu-python {MODULE}/common/task_scope.py stop {MODULE}/config/switch_task_worker.pid ' + shlex.quote(task))
                report['owned_tasks_cancelled'] = sorted(owned_tasks)
                transient = ' '.join(MODULE + p for p in ('/.luoshu-payload-stage.*', '/.font-payload-stage.*', '/.luoshu-payload-next', '/config/font-payload-next.conf', '/config/font-requests/*', '/config/switch_task.conf.output.*', '/config/switch_task.conf.progress.*', '/cache/tasks/*', '/config/*.tmp.*', '/config/.*.tmp.*'))
                query = 'for p in ' + transient + '; do if [ -e "$p" ] || [ -L "$p" ]; then printf "%s\\n" "$p"; fi; done'
                cleanup_deadline = time.monotonic() + 30
                while True:
                    entries = root(query).splitlines()
                    if not entries:
                        time.sleep(1)
                        entries = root(query).splitlines()
                        if not entries:
                            report['final_workspace'] = {'result': 'PASS', 'entries': [], 'delayed_recheck_seconds': 1}
                            break
                    if time.monotonic() >= cleanup_deadline:
                        report['final_workspace'] = {'result': 'FAIL', 'entries': entries}
                        raise RuntimeError('Owned transient module workspaces remain after App stop and scoped cleanup')
                    time.sleep(1)
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
        from verdict import delivery_blockers
        report['blockers'] = delivery_blockers(report)
        report['delivery_gate'] = 'BLOCKED' if report['blockers'] else 'PASS'
        (output / 'module-gate.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report
