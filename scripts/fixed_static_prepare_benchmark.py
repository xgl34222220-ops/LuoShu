#!/usr/bin/env python3
"""Time the actual fixed-static XML preparation phase on synthetic large fonts.

No device inputs, private fonts, network, deployment or Android speed claims.
The kernel stock-origin seam is mocked only for generated fixture bytes.
Stage totals overlap; exclusiveSeconds removes time spent in wrapped children.
"""
from collections import defaultdict
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import argparse
import hashlib
import json
import resource
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'common'), str(ROOT / 'scripts')]
import fontTools
import fixed_static_xml_compiler as fixed
import fixed_static_xml_compiler_test as fixture
import universal_font_compiler as compiler
import universal_mixed_performance_test as generator
import universal_fixed_batch_benchmark as batch


class Timings:
    def __init__(self):
        self.stages = defaultdict(lambda: {'calls': 0, 'seconds': 0.0, 'exclusiveSeconds': 0.0})
        self.stack = []
        self.hash_bytes = 0

    def wrap(self, name, fn):
        def measured(*args, **kwargs):
            stage = self.stages[name]
            stage['calls'] += 1
            if name == 'sha256':
                self.hash_bytes += Path(args[0]).stat().st_size
            frame = [time.monotonic(), 0.0]
            self.stack.append(frame)
            try:
                return fn(*args, **kwargs)
            finally:
                elapsed = time.monotonic() - frame[0]
                self.stack.pop()
                stage['seconds'] += elapsed
                stage['exclusiveSeconds'] += elapsed - frame[1]
                if self.stack:
                    self.stack[-1][1] += elapsed
        return measured


def render_sample(root, cache_enabled):
    """One full large UI asset: byte comparison is separate from timing."""
    case = fixture.FixedStaticCompilerTest('test_honest_static_source_at_different_xml_weight')
    case.setUp()
    try:
        case.source = root / 'source.ttf'
        stock = root / 'stock-variable.ttf'
        logical = '/system/fonts/Synthetic-ui-sans-0.ttf'
        unit = case.unit(role='ui-sans', stock=stock, logical=logical)
        unit['artifact']['originalStockAxes'] = [{'tag': 'wght', 'stylevalue': 100}]
        with patch('stock_font_provenance.verify_stock_path',
                return_value={'schema': 'stock-view-proof-v1', 'verified': True, 'testFixture': True}):
            prepared = (fixed.prepare_unit(unit, {logical: stock}, False, cache={}) if cache_enabled
                        else fixed.prepare_unit(unit, {logical: stock}, False))
            output = root / ('render-cached' if cache_enabled else 'render-baseline')
            output.mkdir(exist_ok=True)
            result = fixed.compile_prepared(prepared, output, {})
        path = Path(result['output'])
        report = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size,
            'binding': prepared['binding'], 'contractSha256': hashlib.sha256(
                json.dumps(prepared['contract'], sort_keys=True).encode()).hexdigest(),
            'validation': result['report']['validation'], 'synthetic': True, 'androidValidated': False}
        (output / 'equivalence.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)
        return report
    finally:
        case.tearDown()


def run(root, han, contours, slots, cache_enabled, lazy_source=False):
    root.mkdir(parents=True, exist_ok=True)
    source, variable = root / 'source.ttf', root / 'stock-variable.ttf'
    if not source.exists():
        generator.make_cjk_font(source, han, contours)
    if not variable.exists():
        batch.variable_copy(source, variable)
    case = fixture.FixedStaticCompilerTest('test_honest_static_source_at_different_xml_weight')
    case.setUp()
    case.source = source
    units = []
    stock_map = {}
    try:
        bases = []
        for kind, (role, stock) in enumerate([('ui-sans', variable), ('cjk', variable), ('latin', source), ('cjk', source)]):
            logical = '/system/fonts/Synthetic-' + role + '-' + str(kind) + '.ttf'
            base = case.unit(role=role, stock=stock, logical=logical)
            bases.append(base)
            stock_map[logical] = stock
        for index in range(slots):
            unit = deepcopy(bases[index % len(bases)])
            unit['artifact']['artifactId'] = 'synthetic-measure-' + str(index)
            unit['routeNodes'][0]['ordinal'] = index
            unit['routeNodes'][0]['nodeFingerprint'] = 'sha256:synthetic-' + str(index)
            if index % len(bases) < 2:
                unit['artifact']['originalStockAxes'] = [{'tag': 'wght', 'stylevalue': [100, 400, 700][index // 4 % 3]}]
            units.append(unit)
        timing = Timings()
        cache = {} if cache_enabled else None
        prepared = []
        start = time.monotonic()
        with ExitStack() as stack:
            stack.enter_context(patch('stock_font_provenance.verify_stock_path',
                return_value={'schema': 'stock-view-proof-v1', 'verified': True, 'testFixture': True}))
            if lazy_source:
                original_open = compiler._open_face
                def lazy_open(path, face, *, lazy=False):
                    return original_open(path, face, lazy=True if Path(path) == source else lazy)
                stack.enter_context(patch.object(compiler, '_open_face', lazy_open))
            for name, module, attribute in [
                ('sha256', compiler, '_sha256'), ('openFace', compiler, '_open_face'),
                ('validateStock', compiler, '_validate_stock_contract'),
                ('stockGeometry', compiler, '_stock_geometry_font'),
                ('pairedProfiles', compiler, '_paired_geometry_profiles'),
                ('glyphGroup', compiler.template_engine, 'glyph_group'),
                ('instantiate', compiler, 'instantiateVariableFont'),
                ('prepare', fixed, 'prepare_unit'),
            ]:
                stack.enter_context(patch.object(module, attribute, timing.wrap(name, getattr(module, attribute))))
            for index, unit in enumerate(units):
                begin = time.monotonic()
                if cache_enabled:
                    value = fixed.prepare_unit(unit, stock_map, False, cache=cache)
                else:
                    value = fixed.prepare_unit(unit, stock_map, False)
                prepared.append(value)
                print(json.dumps({'index': index, 'role': unit['target']['role'],
                    'seconds': round(time.monotonic() - begin, 6),
                    'binding': value['binding']['renderContractId']}), flush=True)
        result = {
            'synthetic': True, 'androidValidated': False, 'fontTools': fontTools.__version__,
            'han': han, 'contours': contours, 'slots': slots, 'cache': cache_enabled, 'lazySource': lazy_source,
            'sourceBytes': source.stat().st_size, 'variableBytes': variable.stat().st_size,
            'seconds': time.monotonic() - start, 'hashBytes': timing.hash_bytes,
            'stages': dict(timing.stages),
            'peakRssMiBProcessLifetime': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
            'bindings': [p['binding'] for p in prepared],
            'contractsSha256': [hashlib.sha256(json.dumps(p['contract'], sort_keys=True).encode()).hexdigest() for p in prepared],
        }
        out = root / ('cached.json' if cache_enabled else 'lazy-source.json' if lazy_source else 'baseline.json')
        out.write_text(json.dumps(result, indent=2))
        print(json.dumps({key: result[key] for key in ['seconds', 'hashBytes', 'stages', 'peakRssMiBProcessLifetime']}), flush=True)
        return result
    finally:
        case.tearDown()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--han', type=int, default=20000)
    parser.add_argument('--contours', type=int, default=16)
    parser.add_argument('--slots', type=int, default=16)
    parser.add_argument('--cache', action='store_true')
    parser.add_argument('--lazy-source', action='store_true', help='Controlled read-only source-opening ablation')
    parser.add_argument('--render-only', action='store_true', help='Render one generated large UI asset for byte equality')
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    if not 6000 <= args.han <= 65000 or not 1 <= args.contours <= 48 or not 1 <= args.slots <= 100:
        parser.error('Use 6000..65000 Han, 1..48 contours and 1..100 slots')
    if args.render_only:
        render_sample(args.output_dir, args.cache)
    else:
        run(args.output_dir, args.han, args.contours, args.slots, args.cache, args.lazy_source)
