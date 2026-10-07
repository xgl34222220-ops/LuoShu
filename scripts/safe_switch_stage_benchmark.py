#!/usr/bin/env python3
"""Compare host mapping and warm cache stages on one identical byte fixture.

No Android mount, boot or application rendering time is measured. GNU wc may
use file metadata itself; this benchmark does not assume it reads font contents.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def source_at(ref: str, name: str) -> str:
    return subprocess.run(['git', 'show', ref + ':' + name], cwd=ROOT,
                          text=True, capture_output=True, check=True).stdout


def function_bodies(source: str) -> str:
    return '\n'.join(re.findall(r'^[A-Za-z_]\w*\(\) \{.*?^\}', source, re.M | re.S))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', default='17888663a0fb64a7a63ed96c56f423d94a36a76d')
    parser.add_argument('--trials', type=int, default=7)
    parser.add_argument('--font-mib', type=int, default=32)
    args = parser.parse_args()
    if not 3 <= args.trials <= 30 or not 1 <= args.font_mib <= 128:
        parser.error('trials must be 3..30 and font-mib 1..128')
    baseline = {name: source_at(args.baseline_ref, 'common/legacy_v14_4/' + name)
                for name in ('font_switch_safe.sh', 'rom_adapters.sh')}
    current = {name: (ROOT / 'common/legacy_v14_4' / name).read_text() for name in baseline}
    versions = {}
    for command in ('cksum', 'wc', 'stat'):
        completed = subprocess.run([command, '--version'], text=True, capture_output=True)
        versions[command] = completed.stdout.splitlines()[0] if completed.returncode == 0 else 'unknown'
    results = {'baselineRef': args.baseline_ref, 'scope': 'host-sh; synthetic physical-map and warm-cache stages; no device mounts',
               'sourceSha256': {label: {name: hashlib.sha256(source.encode('utf-8')).hexdigest()
                                        for name, source in sources.items()}
                                for label, sources in (('baseline', baseline), ('current', current))},
               'environment': {'python': sys.version.split()[0], 'shell': str(Path(shutil.which('sh')).resolve()),
                               'system': os.uname().sysname, 'machine': os.uname().machine,
                               'cksum': shutil.which('cksum'), 'wc': shutil.which('wc'),
                               'stat': shutil.which('stat'), 'versions': versions, 'fixtureDonorCount': 2},
               'fontMiB': args.font_mib, 'trials': args.trials, 'stages': {}}
    with tempfile.TemporaryDirectory(prefix='luoshu-stage-benchmark-') as directory:
        root = Path(directory); module = root / 'module'
        shutil.copytree(ROOT / 'common', module / 'common',
                        ignore=shutil.ignore_patterns('python', '__pycache__'))
        (module / 'config').mkdir(); (module / 'logs').mkdir()
        public = root / 'public'; fonts = public / 'fonts'; fonts.mkdir(parents=True)
        payload = b'fixture-font-bytes-' * (args.font_mib * 1024 * 1024 // 19 + 1)
        payload = payload[:args.font_mib * 1024 * 1024]
        for role in ('Regular', 'Bold'):
            (fonts / f'Demo-{role}.ttf').write_bytes(payload)
        results['fixtureSha256'] = hashlib.sha256(payload).hexdigest()
        scripts = {}
        for label, sources in (('baseline', baseline), ('current', current)):
            variant = root / label; variant.mkdir()
            schema = re.search(r'^SWITCH_CACHE_SCHEMA="([^"]+)"', sources['font_switch_safe.sh'], re.M).group(1)
            env = {**os.environ, 'MODULE_DIR': str(module), 'MODDIR': str(module),
                   'LEGACY_DIR': str(module / 'common/legacy_v14_4'), 'LUOSHU_PUBLIC_DIR': str(public),
                   'USER_FONTS_DIR': str(fonts), 'CONFIG_DIR': str(module / 'config'),
                   'STAGE_PAYLOAD': str(variant / 'stage'), 'SWITCH_CACHE_ROOT': str(variant / 'cache'),
                   'SWITCH_VALIDATION_CACHE_ROOT': str(variant / 'validation'),
                   'PREWARM_LOCK': str(variant / 'absent-prewarm.lock'),
                   'SWITCH_CACHE_SCHEMA': schema, 'FONT': str(fonts / 'Demo-Regular.ttf'),
                   'LUOSHU_BUILD_KEY': 'same-fixture-build'}
            script = variant / 'run.sh'
            script.write_text(function_bodies(sources['font_switch_safe.sh']) + '\n' +
                              '. "$MODDIR/common/font_switch_lock.sh"\n' +
                              (ROOT / 'common/legacy_v14_4/util_functions.sh').read_text() + '\n' +
                              function_bodies(sources['rom_adapters.sh']) + r'''
IS_HYPEROS=true
_rom_exact_target_exists() { return 0; }
_log_step() { :; }
case "$1" in
  map)
    rm -rf "$STAGE_PAYLOAD"
    mkdir -p "$STAGE_PAYLOAD/system/fonts" || exit 1
    apply_font_by_rom "$FONT" "$STAGE_PAYLOAD/system/fonts" quick Demo || exit 1
    ;;
  seed)
    key=$(safe_switch_cache_key "$FONT" Demo) || exit 1
    mkdir -p "$SWITCH_CACHE_ROOT/$key/tree/system"
    cp -al "$STAGE_PAYLOAD/system/fonts" "$SWITCH_CACHE_ROOT/$key/tree/system/fonts" || exit 1
    {
      printf 'schema=%s\nfont=Demo\n' "$SWITCH_CACHE_SCHEMA"
      printf 'sourceIdentity=%s\n' "$(safe_source_identity "$FONT")"
      if type safe_family_identity >/dev/null 2>&1; then
        printf 'familyIdentity=%s\n' "$(safe_family_identity Demo)"
      fi
      printf 'inventoryIdentity=%s\n' "$(safe_inventory_identity)"
      printf 'rom=%s\n' "$(safe_rom_identity)"
      printf 'mapperIdentity=%s\n' "$(safe_mapper_identity)"
    } > "$SWITCH_CACHE_ROOT/$key/cache.conf"
    safe_validation_store "$FONT" || exit 1
    ;;
  warm)
    safe_validation_restore "$FONT" || exit 1
    wait_for_prewarm_cache "$FONT" Demo || true
    safe_switch_cache_restore "$FONT" Demo || exit 1
    ;;
  *) exit 2 ;;
esac
''')
            scripts[label] = (script, env)
            for mode in ('map', 'seed', 'warm'):
                subprocess.run(['sh', str(script), mode], env=env, capture_output=True, check=True)
        for stage, mode in (('physicalMapping', 'map'), ('warmValidationLookupRestore', 'warm')):
            samples = {'baseline': [], 'current': []}
            for trial in range(args.trials):
                order = ('baseline', 'current') if trial % 2 == 0 else ('current', 'baseline')
                for label in order:
                    script, env = scripts[label]
                    start = time.perf_counter()
                    subprocess.run(['sh', str(script), mode], env=env, capture_output=True, check=True)
                    samples[label].append((time.perf_counter() - start) * 1000)
                    aliases = list((Path(env['STAGE_PAYLOAD']) / 'system/fonts').glob('*.ttf'))
                    if not aliases or any(path.stat().st_size != len(payload) for path in aliases):
                        raise RuntimeError('mapping/restoration changed the fixture aliases')
            results['stages'][stage] = {label: {'medianMs': round(statistics.median(values), 3),
                                               'samplesMs': [round(value, 3) for value in values]}
                                        for label, values in samples.items()}
            before, after = (results['stages'][stage][label]['medianMs'] for label in ('baseline', 'current'))
            results['stages'][stage]['changePercent'] = round((after / before - 1) * 100, 2)
        results['aliasesPerMappedTree'] = len(aliases)
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
