# Fixed XML and original-file coverage

Route revision 5 adds a separately sealed original-file contract to eligible
XML-backed text fonts. This closes the path where a consumer opens the original
ROM filename directly and bypasses the generated XML asset.

The compiler emits two independent assets:

- XML routes keep their existing fixed-selection representation and immutable
  original fallback copies.
- The original logical path receives an independently validated stock-shell
  artifact. Selected source outlines are copied into the OEM shell; unselected
  scripts remain stock. It is never an alias of the generated XML face.

## Supported initial scope

Standalone TrueType/glyf face zero; fixed composite source; independently
routable normal UI/Latin/CJK text targets; sealed non-alias ROM paths; complete
original `wght`, `wdth`, or `opsz` domains. Compilation and saved-artifact checks
preserve face/container, axis ranges, and canonical `fvar`, `avar`, `STAT`, and
`name` selector tables. Existing geometry, line-budget, shaping, hash and
provenance gates still run.

Collections, protected/scoped containers, mixed normal/italic references,
italic/slant or unknown axes, specialized roles, dynamic `/data/fonts` paths,
ROM aliases without a terminal mount contract, and unsupported outline engines
are not silently substituted. The route records a reason for uncovered original
paths and the preparation summary reports that partial coverage.

`directPathTargets` is separately sealed from `physicalOnlyTargets`. Compiled
manifest membership and runtime deployment membership require one independent
physical artifact for each planned direct target. Missing or altered physical
files fail runtime verification even when the XML assets are present. The
immutable original fallback copies keep their captured bytes.

## Verification

`python3 scripts/fixed_direct_path_pipeline_test.py` covers a static original
path, a variable original path at weights 100/400/900, selected-source outline
identity, preserved selectors, retained fallback bytes, XML style coexistence,
unsupported cases, tampered contracts, missing runtime files/artifacts, and old
revision-4 compatibility. The aggregate source gate runs this test.

A synthetic host full compile of 20,000 Han glyphs, 16 contours per glyph and
67 uniquely named XML families, plus one independent variable original path,
produced four ready artifacts in 29.09 seconds, with 192 MiB peak RSS. This is
not Android timing, and is a different workload from the preparation-only
benchmark. No commercial or phone-extracted fonts were used.

File-level coverage is not proof that every app consumed the font. Packaged app
fonts, late-created theme/provider files, and unverified consumers remain outside
this claim. Runtime verification keeps `fixed-static-consumer-proof-pending`;
there are no new hooks, continuous watchers, or wholesale XML replacement paths.
