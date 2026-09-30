"""Safe normalized-domain MVAR envelopes for fixed outlines in OEM VF shells.

Continuous region scalars are piecewise multilinear. Their sums attain extrema
on the Cartesian grid of region breakpoints. If exact enumeration is unsuitable,
retain the independently safe signed-delta bound; never discard the line gate.
"""
from __future__ import annotations
import itertools
import math
from fontTools.varLib.varStore import VarStoreInstancer

MAX_LOCATIONS = 4096


def mvar_ranges(font, tags):
    wanted = set(str(tag) for tag in tags)
    ranges = {tag: (0, 0) for tag in wanted}
    report = {'method': 'no-mvar', 'domain': 'normalized-axis-cube', 'pointCount': 0,
              'pointBudget': MAX_LOCATIONS}
    if 'MVAR' not in font:
        return ranges, report
    table = font['MVAR'].table
    records = {}
    supports = []
    store = table.VarStore
    axes = font['fvar'].axes if 'fvar' in font else []
    for record in table.ValueRecord:
        tag, index = str(record.ValueTag), int(record.VarIdx)
        if tag not in wanted or index == 0xFFFFFFFF:
            continue
        if tag in records:
            raise ValueError('duplicate MVAR metric record: ' + tag)
        data = store.VarData[index >> 16]
        deltas = data.Item[index & 0xFFFF]
        if len(deltas) != len(data.VarRegionIndex) or not all(math.isfinite(d) for d in deltas):
            raise ValueError('invalid MVAR delta row: ' + tag)
        ranges[tag] = (sum(min(0, d) for d in deltas), sum(max(0, d) for d in deltas))
        records[tag] = index
        supports.extend(store.VarRegionList.Region[i] for i in data.VarRegionIndex)
    if not records:
        return ranges, report
    report['method'] = 'conservative-mvar-signed-deltas'
    def fallback(reason, count=0):
        return ranges, dict(report, fallbackReason=reason, candidatePointCount=count)
    if not axes:
        return fallback('missing-variation-axes')
    grid = {}
    for region in supports:
        if len(region.VarRegionAxis) != len(axes):
            return fallback('variation-axis-count-mismatch')
        for axis, support in region.get_support(axes).items():
            lower, peak, upper = map(float, support)
            if not (-1 <= lower <= peak <= upper <= 1):
                return fallback('unsupported-region-coordinates')
            # Interior vertical sides need one-sided limits, not only vertex
            # values. Preserve the conservative bound instead of underestimating.
            if (lower == peak and -1 < peak < 1) or (peak == upper and -1 < peak < 1):
                return fallback('interior-discontinuous-region')
            grid.setdefault(axis, {-1.0, 0.0, 1.0}).update((lower, peak, upper))
    count = math.prod(len(points) for points in grid.values())
    if count > MAX_LOCATIONS:
        return fallback('point-budget-exceeded', count)
    order = sorted(grid)
    exact = {tag: [math.inf, -math.inf] for tag in records}
    for point in itertools.product(*(sorted(grid[axis]) for axis in order)):
        instancer = VarStoreInstancer(store, axes, dict(zip(order, point)))
        for tag, index in records.items():
            value = float(instancer[index])
            if not math.isfinite(value):
                raise ValueError('non-finite MVAR interpolation: ' + tag)
            exact[tag][0] = min(exact[tag][0], value)
            exact[tag][1] = max(exact[tag][1], value)
    # Outward integer rounding is conservative for OpenType metric rounding and
    # for tiny floating-point interpolation error at grid vertices.
    ranges.update({tag: (math.floor(low), math.ceil(high)) for tag, (low, high) in exact.items()})
    report.update(method='exact-mvar-breakpoint-grid', pointCount=count, axisCount=len(order),
                  rounding='outward-integer')
    return ranges, report
