# Stable candidate follow-up — 2026-10-03

The 08:42 CST root gate (`37081290739`, candidate `9576301`) generated and
committed a composite, passed its actual Android lock checks, then timed out at
the composite reboot. It did not capture logcat from that failed reboot, so the
timeout alone cannot establish a specific native crash or an OEM-device cause.

The new [reproduction run 37110684874](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37110684874)
finished at 17:04 CST, still using the immutable old candidate `9576301`.
Ten lifecycle reboots passed with changed kernel IDs and Enforcing SELinux.
The composite reboot (11) changed its kernel ID but never completed. All four
failure diagnostics were saved without diagnostic errors. Its system log records
`FontManagerService_create` failing with invalid font data at
`/system/fonts/NotoSansCJK-Regular.ttc`; the stack goes through
`Font$Builder.nBuild`, `SystemFonts.buildSystemFallback` and
`FontManagerService.serializeFontMap`. This directly confirms rejection of that
payload during the failed AOSP boot and supports the diagnosed container defect.
It is not a native ARM64/OEM-device qualification or a successful new-candidate
composite test.

Source inspection confirms a separate structural defect: the legacy generic
mapper hardlinks the single SFNT composite under `NotoSansCJK-Regular.ttc`.
Multiple collection indexes cannot be satisfied by renaming a single face.
Alias creation now refuses that operation before the engine commits its config.
Previously generated collection stages are also validated before a finalizer
can replace an existing next-boot payload. Reports bind failures to the request
and path. The guard does not generate stock-compatible collection faces and
must not be described as completing generic CJK, HyperOS or ColorOS coverage.
Interrupted directory-rename recovery applies the same guard before it can
publish the next-boot state file.

The 17 pinned mounting/commit files remain unchanged. Fonts.xml is not modified.
No hook, resident watcher, runtime replacement or automatic release is added.

Font inventory scan/refresh now checks its captured metadata again in the same
finite caller-owned request, and returns a matching verification record. A
directory/config/permission change fails before cache publication. Cached reads
remove old verification authority. The matching App uses that scan proof and
avoids a second Root/Python request; old modules keep the separate-check path.
This reduces process starts, not proof of phone startup latency.

The emulator reboot gate now requires a changed kernel identity AND completed
boot, verifies both again after root recovery, and saves bounded properties,
system/crash logcat and process evidence from any failing boot. Diagnostic
failures cannot turn a failed reboot into a pass or mask its original exception.

Outstanding delivery checks remain actual safe collection compilation and
activation, OEM physical-device coverage/geometry/reboot persistence, and phone
cold/warm latency. A passing source/build check does not close these checks.

The root workflow on this follow-up still intentionally pins candidate
`9576301` (run `37080258821`) to reproduce the earlier boot failure with the new
diagnostics. It is not a qualification of this branch's module/App. The candidate
build workflow builds this branch and retains the immutable mounting gate.

Local inventory, collection and reboot-harness regressions pass. The complete
local source suite cannot qualify this environment: the packaged ARM64 runtime
is absent, and executor process IDs do not match the mounted procfs. Existing
process-lifecycle tests therefore cannot run meaningfully here. CI must run the
complete source suite and Android JVM tests/build before any test-package claim.

[Candidate build 37110918225](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37110918225)
passed the full source suite, Android JVM tests, lint and APK/module packaging for
runtime code commit `be0e31e0a6ca39c01b38323627b9b0fa8d50185c`. The downloaded
artifact's provenance, ZIP/APK checksums, four changed runtime files and all 17
pinned mount files were independently compared with the source/baseline.
Module SHA-256: `4192a81ec42afe05723b8412277deddf3bd525e9aab34fbf4e3d6b93895c5e4e`.
APK SHA-256: `e4b1f34521858df530b3dae4c66ceccc0115b400023027b8e3992647ad93a3be`.
These build/structure checks leave the delivery checks above outstanding.

The subsequent 17:21 CST review found additional defects. The batch index had
ignored the `is_variable` field written by the direct import's real fvar probe;
an ordinary filename therefore hid variable-font controls. It also treated
`supports_cjk=false` with CRLF as true. Single-file families now use that import
metadata, CRLF/boolean values are normalized, and a shared multiweight config
does not reclassify every file. The scanner revision participates in its
fingerprint so an unchanged directory cannot reauthorize old cached semantics.

Both module and App reject malformed, missing or duplicate cached font IDs.
Module scans rebuild corrupt rows rather than returning the same corrupt cache
forever. Live malformed scans retain the known display list without verification;
the App cannot silently drop broken records into an apparently valid empty list.

A structurally valid TTC can still have fewer faces than its target. Collection
finalization now compares each exact partition target's existing face count.
The generic system alias helper checks the count before the legacy engine can
commit its selection/configuration, using bounded header reads rather than an
additional Python process. Counts do not certify face order, glyph coverage,
axes or metrics, and do not implement the outstanding collection compiler.

Local checks for this review: 17 inventory tests and 11 collection tests pass;
the finalizer race suite passes its 8 runnable cases (9 procfs-dependent cases
are unsupported by this executor). The 17 frozen mount hashes remain unchanged.
The new runtime changes require their own complete CI/App build result; the
earlier `be0e31e` build above is not qualification of these later changes.

Review build `37113895850` at `9009be9` passed the source checks, Android JVM
tests/lint and packaging, and its downloaded artifact matched the source and
17 frozen mounting hashes. However, inspection of its raw log found a failing
supplemental switch-worker test hidden by `continue-on-error: true`. Its overall
green status is not a pass of all candidate gates. The outdated fixture omitted
the immutable input gate and owned task workspace, so no generator was started.

The fixture now supplies a valid selected-font source and task-owned workspace,
runs the actual snapshot/validation/recheck path, and asserts that validation
and the nested generator received the same private copy before testing TERM and
descendant cleanup. Candidate supplemental gates now fail the workflow and save
their failing log as an artifact. A new mandatory CI run must pass every
supplemental check before this review's candidate can be described as passing.

Mandatory run `37115015590` at `a6a6d33` passed the corrected process test and
switch timeout/cancellation checks. It correctly blocked packaging when the
inventory scanner test could not import FontTools in its own host process:
the fixture only updated PYTHONPATH for subprocesses. The test now also adds
the prepared bundled pure-Python package directory to its own import path.

[Mandatory candidate build 37115397750](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37115397750)
at `d64b3aa7bf2cb50b933bb0664ca0c081821a59a9` completed successfully at 18:20
CST. Source checks, mandatory supplemental gates, readiness checks, Android JVM
tests/lint and APK/module packaging all passed; the raw job log contains no
suppressed failing check. All four real process tests, switch timeout/cancellation,
quick mapping, hardlink sync and the scanner fixture passed. CI still lacks
permission for the existing Google-provider mount-namespace experiment, which
reports its host limitation; this is not a physical-device mount qualification.

The downloaded artifact's provenance, outer ZIP digest, APK/module checksums,
four changed runtime files, bundled APK identity and all 17 pinned mount hashes
were independently verified against this source and the immutable baseline.
Module SHA-256: `f5c4038275a8f90035c8aaaee97a8c0fc64190ad6bebdd4b9591e21b1ea20def`.
APK SHA-256: `b01670eda2d542c19f56a39b1ec8ec1abd4e764a2c7df41181a7f423d12eaa3a`.
These are host/build and artifact checks. The collection compiler and OEM-device
delivery checks listed above remain outstanding; no release is published.

## Static collection compiler continuation (18:30 CST request)

The generic composite mapper now invokes a finite, caller-owned compiler for
its system TTC alias. The frozen `font_mix_engine.sh` and all 17 pinned mount
files remain untouched. The compiler obtains the exact target's stock view
through the existing lower/mirror resolver; an active module without a stock
view fails rather than compiling against its own mounted payload.

Each original face stays at its original index. Supported static TrueType/CFF
faces receive the selected composite's encoded CJK, Latin and digit outlines in
their existing glyph-ID slots. Cmap/UVS, glyph order, GSUB/GPOS/GDEF, names,
OS/2, line metrics, vertical metrics/origins and the stock coordinate frame are
checked before and after serialization and collection assembly. Header metric
compression counters may change when hmtx is re-encoded; the other header fields
stay bound. Lazy tables are loaded consistently before contract hashing.
CFF glyph widths use each stock private dictionary's default/nominal widths.

Monospace, serif, italic and symbol/emoji/icon faces retain stock content. Missing
donor characters, unencoded layout alternatives, and glyph slots shared with
uncovered/out-of-role characters also retain stock content. Thus preserving
stock shaping is not a claim that every shaped alternative uses the donor.
Regular variable target faces/CFF2, incompatible shared aliases and donor
geometry/advances outside the stock frame fail before publication.

Input identity/digests are rechecked before atomic output replacement. The
generated sidecar binds request, exact partition path, ordered face contracts and
output bytes; finalization rejects a mismatched present proof. Older stages
without that proof still have structural evidence only. There is no system XML
edit, hook, detached compiler, permanent worker or live source-file rewrite.

Local verification passed 17 generator regressions, 11 collection/rollback
regressions and the unchanged 17-file boundary. The real upstream Noto CJK
collection passed all 10 indexes: 5 proportional faces compiled, 5 monospace
faces retained. Independent FreeType loads and CFF/hmtx width agreement passed
for CJK, Latin and digits at every index. This host check took about 50 seconds
with a roughly 242 MiB peak RSS and produced a roughly 72 MiB collection; these
numbers describe this synthetic-donor fixture, not phone latency or memory.
The font fixture is not bundled in the module. This real-font check is now a
mandatory supplemental candidate gate, with a missing fixture/consumer or a
failed load blocking packaging.

The automatic integration currently covers the legacy generic system TTC alias.
It does not add automatic discovery/compilation for every OEM partition or
replace the separate HyperOS/ColorOS mappings. True variable collection
compilation, OEM physical-device coverage, geometry and reboot persistence
remain open. The next candidate requires its own CI/artifact and actual Android
activation results; earlier build hashes do not qualify this compiler.

[Static-collection candidate build 37119550651](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37119550651)
at `339046f19315208a352bd3e78b78164cbf6b63e9` completed successfully at 19:38
CST. Source and mandatory supplemental gates, readiness, Android JVM tests/lint,
stable-test App identity, module packaging and packaged-file checks all passed.
The raw log has no failing test suite or traceback. Its mandatory real Noto
test compiled 5/10 faces, retained 5/10, loaded all 10 through FreeType, and took
35.841 seconds with 254,768 KiB peak RSS on that runner. The original stock digest
was `b76b0433203017ca80401b2ee0dd69350349871c4b19d504c34dbdd80541690a`;
the synthetic output was 75,106,452 bytes. These remain host-fixture measurements.
An additional local curved quadratic-to-CFF fixture passed bounds/area tolerance
and independent FreeType loads, without changing candidate code.

The downloaded build's provenance, outer/module/APK hashes, six reviewed runtime
files, bundled-vs-separate APK and all 17 frozen mounting hashes matched.
Module SHA-256: `fc3f2b3fabda57909d9b453ceadb7e51e43f9431673031d9442ea5476c7be5a9`.
APK SHA-256: `49ba2092d31598db3323fc84d5d44225c2bf21c14295693f417df4f78c5aef26`.

The root workflow now pins this exact candidate build/digest instead of the old
`9576301` reproduction package. Its composite component requires the generated
collection proof, original stock digest and final payload bytes to match the
actual request before reboot; structural-only evidence cannot pass. All 69 host
reboot-harness regressions pass. The new actual Android activation result is
pending at this commit and must be reported separately when the run finishes.

The subsequent retained-glyph review reproduced another boundary issue: an
uncovered TrueType composite could reference a replaced encoded slot and change
shape even though its own record was retained. Such dependencies can also make
retained point-matching/geometry assumptions invalid. Compilation now rejects
retained TrueType and non-CID CFF/seac component dependencies before changing
outlines or output. Fully replaced composite slots remain supported; specialized
faces stay untouched. Three meaningful regressions bring the generator suite to
20 passing tests. The already-running Android gate remains bound to its exact
`339046f` Noto-CID candidate; this later guard needs its own CI/package evidence
and must not be substituted into that immutable run's provenance.
