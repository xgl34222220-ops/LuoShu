# Fixed-static preparation measurement, 2026-10-02

The reported phone failure stopped at “measuring original slot 17/67”, before
outline rendering. This change reduces repeated work in that phase; it does not
increase the deadline, alter outlines, add a runtime hook, or claim phone success.

## Changes

- Frozen stock contract validation still rechecks provenance, digest, face and
  line metadata for each route. It no longer draws canonical outline probes that
  this metadata-only caller discarded. Actual geometry is measured separately.
- Reuse only immutable measured profile values within one compile request, capped
  at 32 entries. The key includes stock digest, face, effective axes, source
  digest/face/selection, role, exact selected codepoints and compiler/probe revisions.
- Keep per-route identity/style/XML/coverage validation, geometry planning and
  outlined-probe gates. Cache hits receive deep copies. No live font objects or
  generated glyph buffers are retained. New/overflow keys are measured normally.
- Source and stock digest checks before/after preparation remain unchanged.

## Reproduce

Use the existing synthetic driver with the same generated source/stock files for
baseline e3b7d0f and the changed code. Use the bundled FontTools 4.63.0 on both:

```sh
PYTHONPATH=common/python/lib/python3.14/site-packages python3 scripts/fixed_static_prepare_benchmark.py \
  --han 20000 --contours 16 --slots 67 --cache --output-dir /tmp/fixed-prepare
PYTHONPATH=common/python/lib/python3.14/site-packages python3 scripts/fixed_static_prepare_benchmark.py \
  --render-only --cache --output-dir /tmp/fixed-prepare
python3 scripts/fixed_static_measurement_cache_test.py
```

The 67-route fixture contains eight distinct geometry keys (three variable
locations, UI/CJK/Latin roles and static references). It intentionally exercises
reuse, not 67 unrelated fonts. The generated fonts are synthetic, not device or
commercial font files. JSON alongside this document records the measured stages.

## Results and limits

- Preparation: 16.77 s before, 4.70 s after (72% lower on this host).
- Probe calls: 1,682 to 150; variable instances: 34 to 6.
- Hash checks: 335 on both; 1,513,770,376 bytes hashed on both.
- All 67 render bindings and contract hashes are equal.
- One full 20k-Han UI render is byte-identical: 4,002,460 bytes,
  SHA256 `e37ec01ca80a05b8107b3996f6cd660956c55d3915a1139a2040d480ba0e8868`.
  Reopened output validation reports are also equal.

Regression tests cover 67 repeated routes, uncached/cached output equality,
distinct roles/axes/TTC faces, changed or corrupt stock/source bytes, frozen
metrics, new request selections, deep-copy isolation, 32-entry overflow, and
per-route identity/geometry gates. Generic compiler probe defaults stay enabled.

These are synthetic Linux-host results. Real ROM coverage, memory pressure,
Android CPU speed and 67 distinct geometry keys may behave differently. The
original handset still needs a staged test before calling the timeout resolved.
