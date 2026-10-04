"""Check the downloaded current Root artifact against reviewed source/package."""
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

path, expected_sha, output, candidate_proof, *harness = sys.argv[1:]
repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo / 'tests/android-root-gate'))
from app_anr import target_anr
gate_root = Path(harness[0]) if harness else repo / 'tests/android-root-gate'
sys.path.insert(0, str(gate_root))
from verdict import delivery_blockers, qualification_blockers, preflight_blockers
from module_gate import payload_mount_proof
from app_axis_gate import detail_headings

candidate = json.loads(Path(candidate_proof).read_text())
assert candidate['result'] == 'PASS' and candidate['frozen_files_verified'] == 17
raw = Path(path).read_bytes()
assert sha256(raw).hexdigest() == expected_sha.removeprefix('sha256:')
with zipfile.ZipFile(path) as z:
    assert z.testzip() is None
    def read(name): return z.read(name).decode('utf-8', errors='replace')
    def report(name): return json.loads(read(name))
    m = report('module-gate.json'); runner = report('runner-lifecycle.json')
    q = report('qualification.json'); c = report('candidate-gate.json')
    errors = delivery_blockers(m) + qualification_blockers(q) + preflight_blockers(c)
    # Inspect preserved owned-stage observations, rather than trusting only a
    # boolean in module-gate.json. Initial unrooted stock-App checks are a
    # separate scope and remain explicitly BLOCKED when their own gate failed.
    owned_stages = ('app-axes/', 'library-100/', 'library-1000/', 'app-apply/', 'final-ui/')
    target_anr_files = []
    blocking_dialog_files = []
    for name in z.namelist():
        if not name.startswith(owned_stages):
            continue
        if name.endswith(('.log', '.txt')) and target_anr(read(name)):
            target_anr_files.append(name)
        if name.endswith('.xml'):
            tree = ET.fromstring(read(name))
            if any(node.get('resource-id') == 'android:id/alertTitle' and
                   ("isn't responding" in node.get('text', '') or
                    'is not responding' in node.get('text', '')) for node in tree.iter('node')):
                blocking_dialog_files.append(name)
    if target_anr_files:
        errors.append('raw owned-stage evidence records target App ANR')
    if blocking_dialog_files:
        errors.append('raw owned-stage XML contains an unresolved ANR dialog')
    module_sha = candidate['module_sha256']
    apk_sha = candidate['apk_sha256']
    source = candidate['runtime_source']
    if read('candidate-source.txt').strip() != 'Collection candidate commit: ' + source:
        errors.append('runtime source identity changed')
    if c.get('candidate_zip_sha256') != module_sha or any(
            v.get('zip_sha256') != module_sha for v in m.get('cycles', []) if v.get('label') == 'candidate'):
        errors.append('runtime module identity changed')
    if m.get('candidate_apk_sha256') != apk_sha or c.get('candidate_apk_sha256') != apk_sha:
        errors.append('candidate APK identity changed')
    preview = m.get('magisk_preview_source', {})
    preview_steps = [step for step in m.get('steps', [])
                     if any('luoshu-preview-source-contract.py --module ' in str(arg)
                            for arg in step.get('argv', []))]
    if not preview:
        pass  # Older pinned harness versions did not implement this gate.
    elif len(preview_steps) != 1 or preview_steps[0].get('exit') != 0:
        errors.append('actual installed preview selection command missing or failed')
    else:
        preview_stdout = json.loads(preview_steps[0].get('stdout', ''))
        if {k:v for k,v in preview.items() if k not in ('boot_id', 'selinux')} != preview_stdout:
            errors.append('preview selection report differs from actual ARM64 command stdout')
    if preview and preview.get('boot_id') != m.get('magisk_mix_handoff', {}).get('boot_id'):
        errors.append('preview and handoff boot context changed')
    engine_error = m.get('magisk_composite_error')
    if engine_error is not None:
        error_steps = [step for step in m.get('steps', [])
                       if any('luoshu-composite-error-contract.py --module ' in str(arg)
                              for arg in step.get('argv', []))]
        if len(error_steps) != 1 or error_steps[0].get('exit') != 0:
            errors.append('actual installed composite error function command missing or failed')
        else:
            error_stdout = json.loads(error_steps[0].get('stdout', ''))
            if {k:v for k,v in engine_error.items() if k not in ('boot_id', 'selinux')} != error_stdout:
                errors.append('composite error function report differs from actual ARM64 command stdout')
        if engine_error.get('boot_id') != preview.get('boot_id'):
            errors.append('composite error and preview boot context changed')
    for name in ('emulator-cleanup.json', 'magisk-emulator-cleanup.json'):
        if report(name).get('emulator_reaped') is not True:
            errors.append(name + ': owned emulator not reaped')
    if runner.get('result') != 'PASS' or runner.get('module_delivery_gate') != 'PASS' or runner.get('launcher_reaped') is not True:
        errors.append('runner or complete module gate did not pass')
    if runner.get('kvm_before') != runner.get('kvm_after'):
        errors.append('KVM metadata changed')
    attempts = m.get('boot_attempts', [])
    if len(attempts) < 14 or any(v.get('result') != 'PASS' or not v.get('after') or v.get('before') == v.get('after') for v in attempts):
        errors.append('all fourteen module/composite/App kernel reboots unproven')
    after_ids = [v.get('after') for v in attempts]
    if (len(set(after_ids)) != len(after_ids) or any(
            not isinstance(value, str) or not re.fullmatch('[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}', value)
            for value in after_ids)):
        errors.append('kernel reboot identities are duplicated or malformed')
    stock = m.get('stock_collection_source', {})
    if stock.get('sha256') != '3e7e5afaac2c6d872592d76abedac03a51c6f0fc42d11e311ff2816a6c368afe' or stock.get('bytes') != 32355424:
        errors.append('actual stock differs from reviewed CFF2 fixture')
    g = m.get('legacy_composite', {}); build = g.get('collection_build', {})
    faces = build.get('faces', [])
    if build.get('stockFaces') != 5 or len(faces) != 5 or any(
            f.get('mode') != 'compiled' or f.get('outline') != 'CFF2' or f.get('retainedVariationAxes') is not True for f in faces):
        errors.append('five original variable CFF2 faces unproven')
    stock_paths = m.get('stock_font_canonical_paths', {})
    mounted = [v.get(k, {}) for v in m.get('cycles', []) for k in ('mounted_a', 'mounted_b')]
    mounted += [g.get('mounted', {}), m.get('app_apply', {}).get('mounted', {})]
    proofs_checked = 0
    for view in mounted:
        for p in view.get('changed', []):
            proof = view.get('mount_proofs', {}).get(p, {})
            try:
                recomputed = payload_mount_proof(p, proof.get('canonical'), stock_paths,
                    proof.get('payload_sha256'), view.get('payload_hashes', {}),
                    [line.split() for line in view.get('mountinfo', '').splitlines() if ' - ' in line])
                if any(proof.get(k) != recomputed.get(k) for k in ('stock_canonical', 'payload_path', 'payload_sha256')):
                    raise RuntimeError('reported canonical proof differs from recomputation')
                proofs_checked += 1
            except Exception as error:
                errors.append('canonical mount proof: ' + p + ': ' + str(error))
    if not stock_paths or len(mounted) != 6 or not proofs_checked:
        errors.append('stock aliases or complete actual mount proof set missing')
    if m.get('native_diagnostic_errors'):
        errors.append('native diagnostics incomplete')
    baseline_tasks = {v.get('data', {}).get('task') for cycle in m.get('cycles', [])
                      if cycle.get('label') == 'baseline' for v in cycle.values() if isinstance(v, dict)}
    native = read('module-final-tombstones.txt')
    commands = [l.removeprefix('Cmdline: ') for l in native.splitlines() if l.startswith('Cmdline: ')]
    known_baseline = []; unexpected_native = []
    for command in commands:
        task = re.search(r'switch_task\.conf\.output\.([^ ]+)', command)
        if task and task[1] in baseline_tasks:
            known_baseline.append(command)
        elif '/data/adb/modules/LuoShu' in command or 'io.github.xgl34222220.luoshu.stabletest' in command:
            unexpected_native.append(command)
    if unexpected_native:
        errors.append('candidate/module native crash remains')
    axes = m.get('app_axes', {})
    ui = report('app-axes/report.json')
    if any(axes.get(k) != v for k, v in ui.items()):
        errors.append('App axis report differs from preserved original UI report')
    labels = set()
    actual_detail_endpoints = set()
    for frame in ui.get('frames', []):
        name = 'app-axes/' + frame['path']
        tree = ET.fromstring(read(name))
        actual = [n.get('text', '') for n in tree.iter('node')
                  if n.get('package') == 'io.github.xgl34222220.luoshu.stabletest']
        if actual != frame.get('app_texts'):
            errors.append('App axis frame labels differ from actual XML: ' + name)
        labels.update(actual)
        actual_detail_endpoints.update(n.get('bounds') for n in detail_headings(tree, '英文字形'))
    if labels != set(ui.get('observed_labels', [])):
        # Early navigation frames contain headings and picker rows; the final
        # observed set intentionally covers only the post-selection card.
        if not set(ui.get('observed_labels', [])).issubset(labels):
            errors.append('Reported axis labels have no actual XML evidence')
    if not all(label in labels for label in ('纹理细节', 'XTRA', '字宽', '可变字体')):
        errors.append('Real App font axis labels absent')
    if any(label in labels for label in ('HIDN', '内置参数')):
        errors.append('Hidden font axes became visible in actual XML')
    if axes.get('next_slot_detail_bounds') not in actual_detail_endpoints:
        errors.append('Complete-card endpoint is not an actual following detailed heading')
    screenshot = z.read('app-axes/actual-axis-ui.png')
    if not screenshot.startswith(b'\x89PNG\r\n\x1a\n'):
        errors.append('Actual axis screenshot has invalid PNG bytes')
    import_steps = [step for step in m['steps']
                    if any('app_bridge.sh import_file ' in str(arg) and 'LuoShuAxisGate.ttf' in str(arg)
                           for arg in step.get('argv', []))]
    if len(import_steps) != 1 or import_steps[0].get('exit') != 0:
        errors.append('Exact native import command evidence absent')
    else:
        parsed = [json.loads(line) for line in import_steps[0].get('stdout', '').splitlines()
                  if line.strip().startswith('{')]
        if not parsed or parsed[-1] != axes.get('import_result'):
            errors.append('Native import result differs from actual command stdout')
    result = dict(result='FAIL' if errors else 'PASS', blockers=errors,
        artifact_sha256=sha256(raw).hexdigest(), runtime_source=source,
        module_sha256=module_sha, apk_sha256=apk_sha, verified_module_reboots=len(attempts),
        collection_faces=len(faces), collection_output_sha256=build.get('outputSha256'),
        generation_runtime=g.get('generation_runtime'), canonical_mount_proofs=proofs_checked,
        alias_count=sum(p != target for p, target in stock_paths.items()),
        composite_result=g.get('result'), app_apply_result=m.get('app_apply', {}).get('result'),
        library_timings=m.get('library_timings'), final_workspace=m.get('final_workspace'),
        root_policy_revoked=m.get('root_policy_revoked'), runner_result=runner.get('result'),
        baseline_native_commands=known_baseline, unexpected_native_commands=unexpected_native,
        actual_android_mix_handoff=m.get('magisk_mix_handoff'),
        actual_android_preview_source=preview,
        actual_android_composite_error=engine_error,
        preview_selection_command_seconds=preview_steps[0].get('elapsed_seconds') if preview_steps else None,
        actual_cff2_axis_metadata=m.get('axis_metadata'), actual_app_axes=axes,
        app_axis_screenshot_sha256=sha256(screenshot).hexdigest(),
        actual_app_axis_frames_verified=len(ui.get('frames', [])),
        raw_target_anr_files=target_anr_files, raw_blocking_dialog_files=blocking_dialog_files,
        scope_limits=m.get('scope_limits'))
Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({k:v for k,v in result.items() if k != 'library_timings'}, ensure_ascii=False, indent=2))
raise SystemExit(0 if not errors else 1)
