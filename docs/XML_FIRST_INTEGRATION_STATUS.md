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
| Static compiler | 19 focused host tests | Synthetic fonts; no phone performance claim |
| Exact XML representation | 11 host tests | Actual platform parser still covered separately |
| Planner → compiler → payload → runtime | 10 host tests | Includes originals/tamper/membership/dynamic change; consumer remains pending |
| Existing source gate | Full local and exact-head candidate CI passed at `9643c61` | Host and packaged-runtime checks; no OEM device claim |
| API36 system proof | Earlier `2eaa285`, separate experimental rewrite | Not this production generator |
| Production-output API36 proof | `9643c61`, run `36803617022`: default A/1/中 provenance, reboot, exact configuration and raster restoration passed | Mixed representation: CJK uses new static route; default Latin/digit use existing adapter. Host compiler, not Android Python or root-manager mounting |

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

Run `36798047398` stopped in the actual SDK full/probe equivalence gate before
application. A hinted CFF2 fixture reproduces the same FontTools 4.63 failure:
removing hints leaves optional Private arrays as `None`, and the later variable
instancer iterates them. Read-only CFF2 measurement now preserves these hint
dictionaries. Outline measurement does not execute raster hinting. The expanded
five-location profile/readback regression passes with BlueValues, OtherBlues and
StemSnapH present. The native comparison tries the optimized path first and records
full exception chains, so a format incompatibility fails before the expensive
reference measurement. Whole-plan fatal conditions also precede all static-route
measurements; a blocked-plan regression requires zero measurement calls.

## Production-output result (2026-10-01)

[Run 36803617022](https://github.com/xgl34222220-ops/LuoShu/actions/runs/36803617022)
passed on exact commit `9643c61a053d713b659ef65398ae2895fe4b26b4`.
Production planner, compiler and deployment generated 60 artifacts from 58
fixed-static operations and the retained adapter routes, yielding 44 unique
compiled files and a 71,564,763-byte payload including immutable originals.
After actual AOSP/API36 reboot, default A/1/中 used the expected artifact file,
face and byte hash. A/1/中 pixels changed; Ω and emoji pixels did not. Restoring
both original XML files and rebooting restored all five raster hashes and font
provenance exactly. Emulator termination is recorded in the completed job log.

The real SDK CFF2 font had 65,535 glyphs. At weight 650, full instancing took
141.897 seconds; the 192-glyph probe instance took 0.981 seconds. Complete probe
profiles and selected vertical metrics/origins matched; input bytes were unchanged.
Total host preparation was 267.796 seconds, including that full comparison.
Arithmetic subtraction gives 125.899 seconds excluding the full reference, or
124.918 seconds excluding both measured comparison paths. These are not separate
benchmark runs. Trace-observed measurement of 58 routes took 55.077 seconds and
processing of 60 artifacts took 28.029 seconds; remaining work includes planning,
source profiling, original copies and deployment validation. No phone timing is
inferred from these numbers.

The three representation deferrals are `font_fallback.xml` nodes 0, 6 and 7:
`sans-serif`, `sans-serif-condensed` and `roboto`, each with implicit
`supportedAxes="wght,ital"`. Default Latin and digits therefore used the existing
UF original-shell adapter; Chinese used the new standalone fixed-static asset.
This is a passing mixed production pipeline, not full new-representation coverage.

Next gates remain explicit weight/style expansion with actual default consumer
proof (normal/bold/italic/bold-italic and intermediate weights), production module
asset mounting before FontManager starts, cancellation/reapply/OTA recovery, and
an App consumer-evidence handoff. The ordinary phone bridge remains opt-in/off.

## Opt-in style expansion under native verification

Route revision 2 is currently selected only by the explicit CI style experiment.
The ordinary router call continues producing revision 1. Revision 2 expands an
otherwise eligible implicit wght node into 100–900 declarations plus 450 and 520.
Each normal asset is measured against its own original reference coordinate.
For a real wght+ital original, explicit italic references keep the sealed OEM
container with weight and ital=1 axes. Pure wght CJK fonts retain platform
synthetic italic behavior; they are not relabeled as genuine italic donors.

This distinction follows AOSP
[SystemFonts.resolveVarFamilyType](https://github.com/aosp-mirror/platform_frameworks_base/blob/master/graphics/java/android/graphics/fonts/SystemFonts.java):
a family containing a static entry no longer receives the automatic variable
family treatment. Retaining one implicit italic entry beside static normals
therefore would not establish all requested style/weight behavior.

Five host regressions exercise production compile/deployment, unchanged original
italic bytes, weight-only behavior, missing italic capability, ambiguous peers and
tampered mapping. The CI-only public API consumer adds 54 bounded cases spanning
default and named families, 100/300/400/450/520/700/900 requests, both styles, and
protected Greek/emoji. Every passing case must have an expected path, SHA, face,
FontStyle and raster contract. An observation-only result cannot pass this gate.
Run `36806453735` applied this candidate, then failed the normal-weight-450
Latin source-path assertion. Default A/1/中 used new static assets, but the wider
matrix did not pass. All original XML bytes and all 54 baseline style cases were
restored successfully; the VM was terminated. Discrete declarations therefore
cannot yet be presented as correct intermediate-weight selection.

## Static weight matching limitation and isolated alternative

The failed run registered 450 and 520 successfully in FontManager. Android 16
[Minikin FontFamily](https://android.googlesource.com/platform/frameworks/minikin/+/refs/heads/android16-release/libs/minikin/FontFamily.cpp)
scores static fonts by hundred-weight buckets and retains the first equal score.
Thus an earlier 400 entry can shadow 450, and 500 can shadow 520; reordering
cannot make both members of a bucket independently reachable. The next probe
retains every observed case and failure detail instead of losing partial results
at the first assertion. No failed expectation is changed into a success.

A separate, non-deployable experiment adds a constant-response wght selection
axis to an already static upright asset. This axis is explicitly NOT donor weight
variation, nor an assertion that a physical OEM VF has been reproduced. All glyph
coordinates, advances, line metrics and static shaping tables must remain
unchanged at eight coordinates including 450/520. Existing variable fonts cannot
enter this constructor. The experiment stays outside production helpers.

The next native run is App-only: public API35+ `buildVariableFamily` combines the
constant normal candidate with the original variable italic, and separately tests
a CJK normal candidate with platform synthetic italic. Forty-eight cases compare
actual source files/hashes and independently constructed raster references before
and after reboot. It changes no system XML, performs no root/remount test, and
does not establish OEM geometry or module deployment. Production integration must
wait for a sound geometry contract and explicit fixed-selection semantics.
