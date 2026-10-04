"""Read-only review of a pinned Root artifact; a review job is not Android acceptance."""
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
import zipfile

REPOSITORY = 'xgl34222220-ops/LuoShu'
PREFIX = 'LUOSHU_REVIEW_JSON '


def emit(kind, value):
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    chunks = [encoded[i:i+6000] for i in range(0, len(encoded), 6000)]
    for i, chunk in enumerate(chunks):
        print(PREFIX + json.dumps(dict(kind=kind, index=i, total=len(chunks), value=chunk),
                                  ensure_ascii=False), flush=True)


def download(artifact, expected_run, expected_source, temp, token):
    if type(artifact['id']) is not int or artifact['id'] <= 0:
        raise ValueError('Artifact ID must be a positive integer')
    if not re.fullmatch('[0-9a-f]{64}', artifact['sha256']):
        raise ValueError('A reviewed external SHA-256 is required')
    endpoint = f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/{artifact['id']}"
    def fetch(url, path):
        command = ['curl', '--fail', '--silent', '--show-error', '--location', '--retry', '3',
                   '--connect-timeout', '20', '--max-time', '180',
                   '--header', 'Accept: application/vnd.github+json',
                   '--header', 'X-GitHub-Api-Version: 2026-03-10',
                   '--header', 'Authorization: Bearer ' + token,
                   '--output', str(path), url]
        # Never echo the token-bearing argv, including on a download failure.
        if subprocess.run(command).returncode:
            raise RuntimeError('Pinned artifact download failed')
    metadata_path = temp / (str(artifact['id']) + '.metadata.json')
    fetch(endpoint, metadata_path)
    metadata = json.loads(metadata_path.read_text())
    if (metadata.get('id') != artifact['id'] or metadata.get('expired') is not False or
            metadata.get('digest') != 'sha256:' + artifact['sha256'] or
            metadata.get('workflow_run', {}).get('id') != expected_run or
            metadata.get('workflow_run', {}).get('head_sha') != expected_source):
        raise ValueError('Artifact metadata differs from reviewed run/source/digest')
    archive = temp / (str(artifact['id']) + '.zip')
    fetch(endpoint + '/zip', archive)
    if archive.stat().st_size != metadata['size_in_bytes'] or sha256(archive.read_bytes()).hexdigest() != artifact['sha256']:
        raise ValueError('Downloaded original artifact ZIP differs from reviewed metadata')
    return archive


def main(pin_path, output_path):
    repo = Path(__file__).resolve().parents[2]
    pin = json.loads(Path(pin_path).read_text())
    if pin.get('schema') != 'luoshu-reviewed-root-artifact-v1':
        raise ValueError('Unknown artifact-review pin schema')
    candidate_only = pin.get('review_scope') == 'CANDIDATE_ONLY'
    for key in (('runtime_source',) if candidate_only else ('runtime_source', 'harness_commit')):
        if not re.fullmatch('[0-9a-f]{40}', pin[key]):
            raise ValueError('Immutable source and harness commits are required')
    for key in (('candidate_run',) if candidate_only else ('root_run', 'candidate_run')):
        if type(pin[key]) is not int or pin[key] <= 0:
            raise ValueError('Positive immutable run IDs are required')
    if not candidate_only and pin['expected_root_result'] not in ('PASS', 'FAIL'):
        raise ValueError('Expected preserved verdict must be explicit')
    token = os.environ['REVIEW_TOKEN']
    output = Path(output_path)
    output.mkdir(parents=True, exist_ok=True)
    temp = Path(os.environ['RUNNER_TEMP']) / ('luoshu-artifact-review-' + uuid.uuid4().hex)
    temp.mkdir()
    candidate_zip = download(pin['candidate_artifact'], pin['candidate_run'], pin['runtime_source'], temp, token)
    candidate_proof = output / 'candidate-proof.json'
    with (output / 'candidate-verifier.txt').open('w') as log:
        subprocess.run([sys.executable, str(repo / 'tests/reviewed-artifacts/verify_candidate.py'),
                        str(candidate_zip), pin['runtime_source'], str(pin['candidate_run']),
                        str(pin['candidate_artifact']['id']), pin['candidate_artifact']['sha256'],
                        str(candidate_proof)], cwd=repo, stdout=log, stderr=subprocess.STDOUT, check=True)
    verified_candidate = json.loads(candidate_proof.read_text())
    emit('CANDIDATE_PROOF', verified_candidate)
    if candidate_only:
        summary = dict(result='REVIEW_COMPLETED', candidate_run=pin['candidate_run'],
                       scope='READ_ONLY_CANDIDATE_ARCHIVE_NOT_ANDROID_EXECUTION',
                       review_commit=os.environ['GITHUB_SHA'])
        (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        emit('SUMMARY', summary)
        return
    root_zip = download(pin['root_artifact'], pin['root_run'], pin['harness_commit'], temp, token)
    harness = temp / 'pinned-harness'
    harness.mkdir()
    archive = temp / 'pinned-harness.tar'
    subprocess.run(['git', 'archive', '--format=tar', '--output', str(archive),
                    pin['harness_commit'], 'tests/android-root-gate', 'scripts'], cwd=repo, check=True)
    subprocess.run(['tar', '-xf', str(archive), '-C', str(harness)], check=True)
    root_proof = output / 'root-proof.json'
    with (output / 'root-verifier.txt').open('w') as log:
        result = subprocess.run([sys.executable, str(repo / 'tests/reviewed-artifacts/verify_root.py'),
                                 str(root_zip), pin['root_artifact']['sha256'], str(root_proof),
                                 str(candidate_proof), str(harness / 'tests/android-root-gate')],
                                cwd=repo, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode not in (0, 1) or not root_proof.is_file():
        raise RuntimeError('Pinned verifier aborted; no reviewed Android verdict exists')
    proof = json.loads(root_proof.read_text())
    if (proof['result'] != pin['expected_root_result'] or
            result.returncode != (0 if proof['result'] == 'PASS' else 1)):
        raise ValueError('Preserved Android verdict differs from the reviewed expectation')
    proof.update(run_id=pin['root_run'], artifact_id=pin['root_artifact']['id'],
                 harness_commit=pin['harness_commit'],
                 artifact_review_scope='READ_ONLY_ORIGINAL_ARCHIVE_NOT_NEW_ANDROID_EXECUTION')
    root_proof.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n')
    with zipfile.ZipFile(root_zip) as z:
        module = json.loads(z.read('module-gate.json'))
        stage = json.loads(z.read('app-axes/report.json')) if 'app-axes/report.json' in z.namelist() else {}
        failed = [s for s in module.get('steps', []) if s.get('exit') != 0][-6:]
        diagnostics = dict(root_run=pin['root_run'], module_error=module.get('error'),
                           app_axis_stage=stage,
                           raw_axis_runtime_log=z.read('app-axes/runtime.log').decode('utf-8', errors='replace')
                           if 'app-axes/runtime.log' in z.namelist() else None,
                           raw_axis_commands=z.read('app-axes/commands.jsonl').decode('utf-8', errors='replace')
                           if 'app-axes/commands.jsonl' in z.namelist() else None,
                           failed_commands=[{k:s.get(k) for k in ('argv','exit','elapsed_seconds','stdout','stderr')}
                                            for s in failed],
                           owned_stage_files=[n for n in z.namelist() if n.startswith(
                               ('app-axes/', 'library-100/', 'library-1000/', 'app-apply/', 'app-composite/', 'final-ui/'))])
    (output / 'diagnostics.json').write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2) + '\n')
    summary = dict(result='REVIEW_COMPLETED', preserved_android_result=proof['result'],
                   root_run=pin['root_run'], candidate_run=pin['candidate_run'],
                   scope='READ_ONLY_ORIGINAL_ARCHIVE_NOT_NEW_ANDROID_EXECUTION',
                   review_commit=os.environ['GITHUB_SHA'])
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    emit('ROOT_PROOF', proof)
    emit('DIAGNOSTICS', diagnostics)
    emit('SUMMARY', summary)


if __name__ == '__main__':
    main(*sys.argv[1:])
