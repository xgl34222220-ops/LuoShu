"""Independently bind candidate ZIP contents to exact reviewed git source."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

path, source, run_id, artifact_id, expected_sha, output = sys.argv[1:]
repo = Path(__file__).resolve().parents[2]
digest = lambda data: hashlib.sha256(data).hexdigest()
assert digest(Path(path).read_bytes()) == expected_sha.removeprefix('sha256:')
with zipfile.ZipFile(path) as archive:
    assert archive.testzip() is None
    module_name = 'LuoShu-v1.1.1.zip'
    module_bytes = archive.read(module_name)
    apk_name, = [name for name in archive.namelist() if name.endswith('-Debug.apk')]
    apk = archive.read(apk_name)
    for name, data in ((module_name, module_bytes), (apk_name, apk)):
        assert archive.read(name + '.sha256').decode().split()[0] == digest(data)
    props = dict(line.split('=', 1) for line in archive.read('app-build-provenance.txt').decode().splitlines())
    assert props == dict(sourceCommit=source, package='io.github.xgl34222220.luoshu.stabletest', apkSha256=digest(apk))
    with zipfile.ZipFile(io.BytesIO(module_bytes)) as module:
        assert module.testzip() is None
        bundled, = [name for name in module.namelist() if name.startswith('bundled/') and name.endswith('.apk')]
        assert module.read(bundled) == apk
        manifest = json.loads((repo / 'scripts/stable_mount_sha256.json').read_text())
        for name, expected in manifest['files'].items():
            assert digest(module.read(name)) == expected, name
        sources = ['common/mix_task_handoff.sh', 'common/weighted_mix_task.sh',
                   'common/legacy_v14_4/v142_weighted_mix.sh', 'common/font_axis_info.py',
                   'common/font_metadata.py', 'common/task_scope.py', 'common/app_bridge.sh',
                   'common/util_functions_core.sh', 'common/font_mix.sh', 'common/font_manager.sh', 'common/font_inventory_batch.py', 'common/legacy_v14_4/mix_router.sh']
        for name in sources:
            expected = subprocess.check_output(['git', 'show', source + ':' + name], cwd=repo)
            assert module.read(name) == expected, name
        legacy_engine = module.read('common/legacy_v14_4/font_mix_engine.sh')
        assert digest(legacy_engine) == 'f71280c692253f70397edb275c483fad677de337bd3dfcba73bd511dfd4bcbd6'
result = dict(result='PASS', run_id=int(run_id), artifact_id=int(artifact_id),
              artifact_sha256=digest(Path(path).read_bytes()), runtime_source=source,
              module_sha256=digest(module_bytes), apk_sha256=digest(apk),
              frozen_files_verified=len(manifest['files']), source_files_verified=sources,
              provenance=props, legacy_frozen_engine=dict(sha256=digest(legacy_engine), unchanged=True))
Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(result, ensure_ascii=False, indent=2))
