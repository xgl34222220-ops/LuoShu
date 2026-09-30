# Explicit fixed-static XML integration

This path is implemented as a separate representation and remains opt-in. It is
not enabled by the phone's ordinary mixed-font bridge yet. The existing minimal
router retains its text-only invariants.

## Implemented contracts

- The new router derives exact nodes from a validated legacy route proof and
  seals each source XML, fixed selection, retained original and font-update state
- Static assets expose only source ∩ original-slot ∩ selected-role codepoints,
  with FontTools shaping closure. Greek, emoji and unrelated script coverage are
  not claimed by the new asset merely because the composite source contains them
- Original face and axes are measured from verified bytes. Every selected probe
  and saved glyph must meet its OEM geometry/line contract
- The complete render contract groups compilation before outline rendering;
  individual XML route IDs still point to and verify the shared file
- Static SFNT keeps the chosen source weight. XML weight declarations are not
  misrepresented as variable outlines. Collection output is honest face zero
- Original fallback containers are copied under sealed content-addressed names,
  preserving XML face/axes/PS contracts and staying independent of physical overlays
- Family-list fallback copies remain immediately after the selected child,
  preserving inherited context and precedence. Customization XML is not treated
  as familyset XML. Only the two proven `/system/etc` configuration paths receive
  the new adapter
- Dynamic FontManager update layers are currently excluded from this explicit
  adapter. Appearance/disappearance/change of their config invalidates activation
- Payload identity covers shared route membership, originals, generated XML and
  frozen route/artifact contracts; runtime verification recomputes those identities
- Registration text is distinct from a real consumer. Error text cannot count as
  positive registration. Without same-boot consumer evidence, this representation
  remains WARN/pending and retains the existing rollback payload

## Current verification

| Gate | Evidence | Limit |
|---|---|---|
| Static compiler | 16 focused host tests | Synthetic fonts; no phone performance claim |
| Exact XML representation | 11 host tests | Actual platform parser still covered separately |
| Planner → compiler → payload → runtime | 9 host tests | Includes originals/tamper/membership/dynamic change; consumer remains pending |
| Existing source gate | Passed before final focused additions; targeted additions rerun | CI rerun required on final snapshot |
| API36 system proof | Earlier `2eaa285`, separate experimental rewrite | Not this production generator |
| Production-output API36 proof | Next experiment uses actual production modules and root-captured SDK fonts | Host namespace proof uses a test-only capture model; not Android Python execution |

## Explicit gaps

Implicit `supportedAxes="wght,ital"`/slant style expansion remains on its existing
adapter and is counted as a representation deferral. It is not a completed
solution for every style. A separate native experiment must check normal, bold,
italic, bold-italic and explicit intermediate weights before expanding this path.

Standalone upright static glyf sources are supported initially. Other source
containers/outlines, unverified configuration adapters, special variants and
active `/data/fonts` overrides are not silently accepted by this representation.

Root-manager mount timing, app namespaces, OEM behavior, real user-font geometry
and all-app coverage remain unproven. An app using embedded/private fonts is
outside a no-hook system fallback guarantee.
