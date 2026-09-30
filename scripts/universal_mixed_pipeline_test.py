#!/usr/bin/env python3
"""Real mixed-source pipeline regression; synthetic fonts, no device claims."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'common'), str(ROOT / 'scripts')]
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
import device_font_template_base as template
import font_coverage
import font_source_profile
import font_topology_snapshot
import minimal_xml_router
import universal_font_compiler as compiler
import universal_font_compiler_test as fixture
import universal_font_cutover_gate as gate
import universal_font_deployment as deployment
import universal_font_plan
import universal_mixed_font as mixed


def write_conf(path: Path, values: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(f'{k}={v}\n' for k, v in values.items()))


def make_font(path: Path, *, marked: bool = False, variable: bool = False) -> None:
    # Real coverage thresholds and probes; avoid mocking the profile capability gate.
    points = set(range(0x20, 0x7f)) | set(range(0x4e00, 0x4e00 + font_coverage.MIN_CORE_HAN))
    points.update(font_coverage.CJK_COMMON)
    for group in template.PROBE_GROUPS.values():
        points.update(group)
    original = fixture.ASCII_POINTS
    try:
        fixture.ASCII_POINTS = tuple(sorted(points))
        fixture.make_font(path, family='Mixed Fixture' if marked else 'Stock Fixture', variable=variable)
    finally:
        fixture.ASCII_POINTS = original
    if marked:
        # Distinct topology survives metric normalization and proves donor content,
        # rather than accepting a stock-only or role-swapped output as success.
        outlines = {
            'A': [(40, -120), (570, -120), (305, 720)],
            '1': [(40, -120), (570, -120), (570, 600), (305, 720), (40, 600)],
            '中': [(40, -120), (500, -120), (570, 100), (570, 600), (305, 720), (40, 600)],
        }
        with TTFont(path) as font:
            for char, coords in outlines.items():
                pen = TTGlyphPen(None)
                pen.moveTo(coords[0])
                for point in coords[1:]:
                    pen.lineTo(point)
                pen.closePath()
                font['glyf'][font.getBestCmap()[ord(char)]] = pen.glyph()
            font.save(path)


def point_count(font: TTFont, char: str) -> int:
    glyph = font['glyf'][font.getBestCmap()[ord(char)]]
    return len(glyph.getCoordinates(font['glyf'])[0])


def plans(source: Path, stocks: dict[str, Path], roles_by_path: dict[str, str], module: Path | None = None):
    profile = font_source_profile.build([source])
    slots = {path: fixture.slot_from_stock(path, stock, family='sans-serif', source_xml=None,
             declared=Path(path).name) for path, stock in stocks.items()}
    topology = {'schema': 'device-font-topology-v1', 'topologyRevision': 3, 'state': 'ready',
                'buildKey': 'mixed-pipeline-test', 'romKind': 'hyperos', 'summary': {},
                'slots': slots, 'families': {}, 'xmlAliases': [], 'unresolvedXmlRefs': [], 'runtime': {}}
    roles = {'schema': 'device-font-roles-v1', 'roleRevision': 3, 'state': 'ready',
             'buildKey': 'mixed-pipeline-test', 'romKind': 'hyperos',
             'slots': {p: fixture.role_map(r) for p, r in roles_by_path.items()}}
    if module is not None:
        inventory = dict(schema='device-font-inventory-v1', state='ready', scannerRevision=6,
                         buildKey=topology['buildKey'], romKind=topology['romKind'], slots=slots,
                         families={}, xmlGraph={'refs': [], 'aliases': []})
        topology = font_topology_snapshot.build_topology(inventory, None, '', None, None, '')
        (module / 'config/device_font_inventory.json').write_text(json.dumps(inventory))
        (module / 'config/device_font_topology.json').write_text(json.dumps(topology))
        (module / 'config/device_font_roles.json').write_text(json.dumps(roles))
    plan = universal_font_plan.build_plan(topology, roles, profile)
    route = minimal_xml_router.build_route_plan(plan, {}, None, False)
    return plan, route


def expect_rejection(action, message: str) -> None:
    try:
        action()
    except (ValueError, deployment.DeploymentError) as error:
        assert message in str(error), error
    else:
        raise AssertionError(f'Expected rejection containing {message!r}')


def main() -> int:
    with tempfile.TemporaryDirectory(prefix='luoshu-mixed-pipeline-') as raw:
        temp = Path(raw)
        module = temp / 'module'
        source = module / 'cache/generated/composite.ttf'
        source.parent.mkdir(parents=True)
        make_font(source, marked=True)
        request = 'mix-pipeline-request-1'
        state = {'requestId': request, 'cjk': 'CJK source', 'latin': 'Latin source', 'digit': 'Digit source',
                 'cjkAxes': 'wght=400', 'latinAxes': 'wght=400', 'digitAxes': 'wght=400'}
        state_path = module / 'config/mix-stage-next.conf'
        generation_path = module / '.luoshu-mix-stage/.luoshu-mix-generation.conf'
        write_conf(state_path, state)
        generation = dict(state, compositeHash=mixed.digest(source))
        write_conf(generation_path, generation)
        durable = mixed.freeze(module, request, 'fixed', source)
        frozen = durable / 'fonts/LuoShuMix-Regular.ttf'
        assert frozen.is_file() and mixed.digest(frozen) == generation['compositeHash']
        assert json.loads((durable / 'source.json').read_text())['requestId'] == request
        source.unlink()  # The original worker may clean up immediately after staging.

        stock = temp / 'stock.ttf'
        make_font(stock)
        logical = '/system/fonts/Ui-Regular.ttf'
        protected = ['/system/fonts/NotoColorEmoji.ttf', '/system/fonts/SystemIcons.ttf']
        stocks = {p: stock for p in [logical, *protected]}
        old_hash = mixed.digest(stock)
        plan, route = plans(frozen, stocks, {logical: 'ui-sans', protected[0]: 'emoji', protected[1]: 'symbol-icon'}, module)
        artifacts = compiler.compile_all(plan, route, stocks, temp / 'compiled', False)
        fixture.assert_ready(artifacts)
        payload = temp / 'payload'
        deployed = deployment.build_deployment(plan, route, artifacts, payload)
        result = gate.evaluate(plan, route, artifacts, deployed, payload)
        assert result['eligible'] is True, result
        assert result['decision'] == 'universal' and result['summary']['replacementCount'] == 1
        assert deployed['summary']['activationReady'] is True
        assert artifacts['summary']['artifactCount'] == 1
        for path in protected:
            assert plan['targets'][path]['action'] == 'preserve'
            assert not any(f['logicalPath'] == path for f in deployed['files'])
        assert mixed.digest(stock) == old_hash  # Compile/deploy is staged, never a live mutation.
        artifact = artifacts['artifacts'][0]
        with TTFont(artifact['output']) as output:
            assert [point_count(output, c) for c in ['A', '1', '中']] == [3, 5, 6]
            assert all(ord(c) in output.getBestCmap() for c in 'Aa019中永，。')
        font_entry = next(f for f in deployed['files'] if f['kind'] != 'xml')
        assert mixed.digest(payload / font_entry['payloadPath']) == artifact['sha256']
        # Integrity tampering cannot become an apparently eligible deployment.
        with (payload / font_entry['payloadPath']).open('ab') as stream:
            stream.write(b'tampered')
        assert gate.evaluate(plan, route, artifacts, deployed, payload)['eligible'] is False

        # Real shell bridge: no mocked planner/compiler/gate and no legacy success fallback.
        source.write_bytes(frozen.read_bytes())
        (module / 'common').symlink_to(ROOT / 'common', target_is_directory=True)
        (module / 'module.prop').write_text('id=LuoShu\n')
        (module / 'logs').mkdir()
        stock_map = temp / 'stock-map.json'
        stock_map.write_text(json.dumps({p: str(f) for p, f in stocks.items()}))
        env = dict(os.environ, MODDIR=str(module), MODULE_DIR=str(module),
                   LUOSHU_REAL_MODDIR=str(module), LUOSHU_MIX_REQUEST_ID=request,
                   LUOSHU_PYTHON=sys.executable, LUOSHU_STOCK_FONT_MAP=str(stock_map))
        # A queued B must not replace the true live A identity used for rollback.
        write_conf(module / 'config/universal-font-next.conf',
                   {'font': 'Queued B', 'previousFont': 'Live A', 'previousMode': 'classic', 'previousLegacy': 'false'})
        (module / 'config/active_font.conf').write_text('Queued B\n')
        write_conf(state_path, dict(state, previousFont='Queued B'))
        started = subprocess.run(['sh', str(module / 'common/universal_mixed_font.sh'), 'fixed', str(source)],
                                 env=env, text=True, capture_output=True, timeout=90)
        assert started.returncode == 0, (started.stdout, started.stderr,
                (module / 'logs/universal-font-cutover.log').read_text() if (module / 'logs/universal-font-cutover.log').exists() else '')
        response = json.loads(started.stdout.strip().splitlines()[-1])
        assert response['pipeline'] == 'universal' and response['fallback'] is False, response
        next_state = mixed.conf(module / 'config/universal-font-next.conf')
        assert next_state['font'] == 'mix' and next_state['requestId'] == request
        assert next_state['deploymentId'] == response['deploymentId']
        assert next_state['previousFont'] == 'Live A' and next_state['previousMode'] == 'classic'
        assert (module / 'config/active_font.conf').read_text().strip() == 'mix'
        assert not (module / 'config/font-payload-next.conf').exists()
        next_hashes = {str(p.relative_to(module)): mixed.digest(p)
                       for p in (module / '.luoshu-payload-next').rglob('*') if p.is_file()}
        finalized = subprocess.run(['sh', str(module / 'common/legacy_v14_4/mix_router.sh'), 'finalize'],
                                   env=env, text=True, capture_output=True, timeout=30)
        assert finalized.returncode == 0, (finalized.stdout, finalized.stderr)
        assert json.loads(finalized.stdout)['data']['pipeline'] == 'universal'
        assert not (module / 'config/font_runtime_legacy_v14_4.conf').exists()
        assert not (module / 'config/font-payload-next.conf').exists()
        assert mixed.conf(module / 'config/universal-font-next.conf') == next_state
        assert next_hashes == {str(p.relative_to(module)): mixed.digest(p)
                               for p in (module / '.luoshu-payload-next').rglob('*') if p.is_file()}

        # The background fixed monitor must not recreate the legacy marker after
        # a successful Universal finalizer. Auto success also reaches 100 without it.
        write_conf(module / 'config/mix_task.conf', {'task': 'fixed-task', 'state': 'success', 'percent': 100})
        monitored = subprocess.run(['sh', str(module / 'common/legacy_v14_4/font_mix_runtime.sh'), 'monitor', 'fixed-task'],
                                   env=env, text=True, capture_output=True, timeout=30)
        assert monitored.returncode == 0, (monitored.stdout, monitored.stderr)
        assert mixed.conf(module / 'config/mix-finalize-state.conf')['state'] == 'success'
        assert not (module / 'config/font_runtime_legacy_v14_4.conf').exists()
        write_conf(module / 'config/axes_task.conf', dict(state, task='auto-task', state='success', percent=100))
        status = subprocess.run(['sh', str(module / 'common/legacy_v14_4/mix_router.sh'), 'status', 'auto-task'],
                                env=env, text=True, capture_output=True, timeout=30)
        status_data = json.loads(status.stdout)['data']
        assert status_data['state'] == 'success' and status_data['progress']['percent'] == 100, status_data

        # A flat fixed composite must not masquerade as MiSans variable output.
        vf = temp / 'MiSansVF.ttf'
        make_font(vf, variable=True)
        vf_logical = '/system/fonts/MiSansVF.ttf'
        vf_plan, vf_route = plans(frozen, {vf_logical: vf}, {vf_logical: 'ui-sans'})
        rejected = compiler.compile_all(vf_plan, vf_route, {vf_logical: vf}, temp / 'rejected', False)
        assert rejected['summary']['deploymentReady'] is False
        assert rejected['summary']['blockedCount'] == 1
        assert 'variable' in rejected['artifacts'][0]['reason']
        expect_rejection(lambda: deployment.build_deployment(vf_plan, vf_route, rejected, temp / 'bad-payload'), 'blocked')
        assert not (temp / 'bad-payload').exists()

        # Real auto exporter -> synthesized VF -> physical MiSansVF compile/gate/stage.
        # Keep CJK invariant and vary Latin/digit outlines at distinct rates.
        import universal_mixed_variable as variable
        auto_root = module / 'cache/auto-generated'
        (auto_root / 'fonts').mkdir(parents=True)
        auto_request = 'mix-pipeline-request-auto'
        auto_state = dict(state, requestId=auto_request, cjkMode='fixed', latinMode='auto', digitMode='auto',
                          latinAxes='wght=400,wdth=90', digitAxes='wght=400,wdth=90')
        write_conf(state_path, auto_state)
        write_conf(module / 'config/axes_task.conf', dict(auto_state, root=str(auto_root)))
        for weight, style in zip(variable.WEIGHTS, variable.STYLES):
            provenance = auto_root / 'axis-provenance' / str(weight)
            provenance.mkdir(parents=True)
            for role in ('cjk', 'latin', 'digit'):
                (provenance / f'{role}.ttf.instance.json').write_text(json.dumps({
                    'role': role, 'variable': role != 'cjk', 'location': {'wght': weight, 'wdth': 90} if role != 'cjk' else {},
                    'ignoredAxes': [], 'status': 'ok'}))
            master = auto_root / 'fonts' / f'LuoShuAutoMix-{style}.ttf'
            with TTFont(frozen) as font:
                for char, divisor in [('A', 10), ('1', 20)]:
                    glyph = font['glyf'][font.getBestCmap()[ord(char)]]
                    for index, (x, y) in enumerate(glyph.coordinates):
                        glyph.coordinates[index] = (x + (weight - 400) // divisor if x > 100 else x, y)
                font.save(master)
        plans(frozen, {vf_logical: vf}, {vf_logical: 'ui-sans'}, module)
        stock_map.write_text(json.dumps({vf_logical: str(vf)}))
        auto_env = dict(env, LUOSHU_MIX_REQUEST_ID=auto_request)
        auto_result = subprocess.run(['sh', str(module / 'common/universal_mixed_font.sh'), 'auto', str(auto_root)],
                                     env=auto_env, text=True, capture_output=True, timeout=120)
        assert auto_result.returncode == 0, (auto_result.stdout, auto_result.stderr)
        auto_response = json.loads(auto_result.stdout.strip().splitlines()[-1])
        assert auto_response['pipeline'] == 'universal' and auto_response['fallback'] is False
        auto_next = mixed.conf(module / 'config/universal-font-next.conf')
        assert auto_next['font'] == 'mix' and auto_next['requestId'] == auto_request
        with TTFont(module / '.luoshu-payload-next/system/fonts/MiSansVF.ttf') as built:
            assert 'fvar' in built and 'gvar' in built
            from fontTools.varLib.instancer import instantiateVariableFont
            widths = []
            han_outlines = []
            for weight in (100, 350, 400, 750, 900):
                instance = instantiateVariableFont(built, {'wght': weight}, inplace=False)
                try:
                    glyph = instance['glyf'][instance.getBestCmap()[ord('A')]]
                    widths.append(max(x for x, _ in glyph.getCoordinates(instance['glyf'])[0]))
                    han = instance['glyf'][instance.getBestCmap()[ord('中')]]
                    han_outlines.append(tuple(han.getCoordinates(instance['glyf'])[0]))
                    assert [point_count(instance, c) for c in ['A', '1', '中']] == [3, 5, 6]
                finally:
                    instance.close()
            assert widths == sorted(widths) and len(set(widths)) == 5, widths
            assert all(outline == han_outlines[0] for outline in han_outlines)
        # Simulate the real next-boot activation against the sealed payload (no mounts).
        boot = subprocess.run(['sh', '-c', '. "$MODDIR/common/universal_next_boot.sh"; universal_font_next_boot_activate'],
                              env=auto_env, text=True, capture_output=True, timeout=30)
        assert boot.returncode == 0, (boot.stdout, boot.stderr)
        assert not (module / 'config/universal-font-next.conf').exists()
        for name in ('universal-font-runtime.conf', 'universal-font-activated.conf'):
            activated = mixed.conf(module / 'config' / name)
            assert activated['requestId'] == auto_request and activated['font'] == 'mix', activated
            assert activated['deploymentId'] == auto_response['deploymentId']
        write_conf(module / 'config/axes_task.conf', dict(auto_state, task='auto-task', state='success', percent=100))
        after_boot = subprocess.run(['sh', str(module / 'common/legacy_v14_4/mix_router.sh'), 'status', 'auto-task'],
                                    env=auto_env, text=True, capture_output=True, timeout=30)
        after_data = json.loads(after_boot.stdout)['data']
        assert after_data['state'] == 'success' and after_data['progress']['percent'] == 100, after_data

        # Missing or clamped role provenance may retain static fallback inputs,
        # but must not yield an approved variable source.
        write_conf(module / 'config/axes_task.conf', dict(auto_state, root=str(auto_root)))
        provenance_path = auto_root / 'axis-provenance/100/latin.ttf.instance.json'
        original_provenance = provenance_path.read_text()
        provenance_path.unlink()
        missing_root = mixed.freeze(module, auto_request, 'auto', auto_root)
        missing_report = json.loads((missing_root / 'source.json').read_text())
        assert 'variable' not in missing_report and missing_report.get('variableError'), missing_report
        provenance_path.write_text(original_provenance)
        clamped = json.loads(original_provenance)
        clamped['location']['wght'] = 300
        provenance_path.write_text(json.dumps(clamped))
        clamped_root = mixed.freeze(module, auto_request, 'auto', auto_root)
        clamped_report = json.loads((clamped_root / 'source.json').read_text())
        assert 'variable' not in clamped_report and 'range' in clamped_report.get('variableError', ''), clamped_report

        provenance_path.write_text(original_provenance)
        bad_width_state = dict(auto_state, latinAxes='wght=400,wdth=150')
        write_conf(state_path, bad_width_state)
        write_conf(module / 'config/axes_task.conf', dict(bad_width_state, root=str(auto_root)))
        width_root = mixed.freeze(module, auto_request, 'auto', auto_root)
        width_report = json.loads((width_root / 'source.json').read_text())
        assert 'variable' not in width_report and ':wdth' in width_report.get('variableError', ''), width_report

        # Restore the fixed request only for the independent negative exporter cases.
        write_conf(state_path, state)

        # Exporter identity/bytes are part of the trust boundary, including reuse.
        source.write_bytes(frozen.read_bytes())
        write_conf(generation_path, dict(generation, compositeHash='0' * 64))
        expect_rejection(lambda: mixed.freeze(module, request, 'fixed', source), 'hash mismatch')
        write_conf(generation_path, generation)
        write_conf(state_path, dict(state, requestId='newer-request'))
        expect_rejection(lambda: mixed.freeze(module, request, 'fixed', source), 'superseded')
    print('universal_mixed_pipeline_test: PASS (synthetic staged pipeline; no device coverage claim)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
