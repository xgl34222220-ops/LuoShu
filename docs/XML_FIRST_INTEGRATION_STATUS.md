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
| Static compiler | 18 focused host tests | Synthetic fonts; no phone performance claim |
| Exact XML representation | 11 host tests | Actual platform parser still covered separately |
| Planner → compiler → payload → runtime | 10 host tests | Includes originals/tamper/membership/dynamic change; consumer remains pending |
| Existing source gate | Passed at protected-family snapshot; PostScript-key correction targeted regressions rerun | CI rerun required on final snapshot |
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

## Native production preflight corrections

Run `36786654701` exposed missing protected siblings in the experiment capture;
real scanner inspection also found that physical candidates lacked sealed original
identities. The scanner now captures XML family members separately from legacy
replaceable slots. Protected siblings remain preserved, including per-face TTC
identities and immutable byte copies.

Run `36789363916` reached CJK collection measurement and rejected a valid XML
PostScript lookup key. AOSP's [FontListParser](https://android.googlesource.com/platform/frameworks/base.git/+/master/graphics/java/android/graphics/FontListParser.java)
uses that field to select an updated file, separately from its collection index.
The fixed-static contract binds this key to sealed XML and records the actual face
name separately. Original byte/face provenance and inactive-update-generation
checks remain mandatory; generated output still has its exact new PostScript name.
Both runs stopped before system-file writes and their VMs were destroyed. Neither
is a passing production-output default-consumer result.

## OEM variation coordinates

The explicit static adapter measures OEM reference coordinates using Skia's
[bounded-axis behavior](https://skia.googlesource.com/skia.git/+/d4e23f36a05f770612d6f4baca9efe403d5f6508/src/ports/SkFontHost_FreeType.cpp): a finite coordinate outside a known fvar axis is pinned to its endpoint. The
artifact reports requested/effective coordinates and actual ranges separately.
Unknown/nonfinite axes and non-upright effective locations remain rejected. This
does not permit changing the user's selected donor axes.

The next native experiment records actual SDK fvar metadata and requires public
Font/Canvas raster equivalence between each out-of-range OEM request and its
endpoint, plus a discriminating opposite endpoint, before production compilation.
A full-batch metadata preflight now precedes expensive geometry measurement.
The previous 311-second preparation ended before any system write; it is not a
successful performance benchmark or proof of phone latency.

## Confirmed SDK CFF2 measurement bottleneck

Run `36793572819` passed all twelve native OEM endpoint comparisons: the SDK CJK
font has a real 400–900 wght range, so XML requests 100/200/300 render exactly as
400 across its four used faces, and differ from 900. It then hit the workflow
limit during measurement 21/58, before any system-file write. Fifteen completed
CFF2 measurements took 124–146 seconds each (median 132 seconds).

The probe subset optimization now includes monochrome CFF2. A multi-axis fixture
with avar, MVAR, HVAR, VVAR and VORG checks complete profiles, output readback,
vertical advances/origins and unchanged input bytes at five locations. The next
experiment additionally compares a full actual SDK CFF2 instance with the probe
instance before compiling the production payload. A 600-second experimental
compile budget leaves room to record failure and dispose of the VM; the phone's
existing preparation deadline is unchanged. Global consumer/restore proof remains
pending until the new run completes.
