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

[Guard candidate build 37121394598](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37121394598)
at `fe1e7f4d21d7875b1859e2efc22d3336409e78c2` passed all mandatory source,
supplemental, readiness, App JVM/lint and packaging checks at 20:11 CST. Its raw
log has no traceback or failing test suite. All 20 generator regressions passed;
the independent Noto/FreeType check again passed all 10 indexes. Its CID output
digest remained exactly `3733d095f16899cffcfd7bd45238bea0094d98f0abab86307b7f1fa9ff979a14`,
confirming that this dependency guard leaves the tested Noto-CID output unchanged.
The downloaded artifact's provenance, six reviewed runtime files, module/APK
digests, embedded APK and all 17 frozen mounting hashes matched again.
Module SHA-256: `3beca660d158e7bc1b63bc8466085584789427548f96f8321c0bba9c8ad02c42`.
APK SHA-256: `640345af640252436fef1c5ea2246ed980414197e493ef72a397648f962e9242`.

[Actual Android run 37120493760](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37120493760)
finished with an overall failure / `delivery_gate: BLOCKED` at 20:04 CST.
It used the exact earlier `339046f` module, not the later guard package. All ten
baseline/candidate installation, A/B switch, injected-failure and stock-restore
reboots completed with changed kernel IDs; the candidate's final restore returned
the original stock hashes. Android fd/lock transport checks also passed.

The actual CLI composite started and then failed in preparation with
`本机 CJK 集合含可变目标面，当前集合编译器不能保留其完整轴契约`.
This is the explicit fvar/CFF2 target rejection, before the engine's composite
config/next-payload commit. The harness did not attempt the composite reboot;
there was no 11th boot in this run. Axis/table details were not captured, so the
exact variable outline kind must not be inferred from this combined guard.
It does not establish successful Android activation of the static compiler,
completion of the variable compiler, or a fix for every device's boot behavior.

The composite log additionally contains three un-attributed `Segmentation fault`
lines before that explicit rejection. The saved system log contains no matching
native crash record or process identity; this evidence cannot identify their
caller or cause. They remain an open runtime/AVD diagnostic item. Actual App
root/library timing, App apply and final cleanup acceptance were not reached.
Do not describe the full Android gate, latest guard package, or OEM phones as
qualified. The draft and immutable reproduction pin remain, with no release.

## Variable collection and Android progress fix (23:00 CST continuation)

Diagnostic [Root run 37129497468](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37129497468)
used the preceding static-only candidate. Its ten baseline/candidate lifecycle
boots passed and restored stock fonts, then the composite correctly failed on
the stock variable collection. The exact untouched Android 15 stock TTC was
preserved: 32,355,424 bytes, SHA-256
`3e7e5afaac2c6d872592d76abedac03a51c6f0fc42d11e311ff2816a6c368afe`.
It contains five ordered JP/KR/SC/TC/HK CFF2 faces with `wght=400..900`.

The compiler now handles variable glyf/CFF2 collections while retaining the
original indexes, variation metadata, untouched glyph variation, and the stock
layout/metric contract. Replaced slots use the selected donor's fixed outlines
and advances at every target-axis position; this does not create a new varying
donor family. Original HVAR rows are retained, with only replacement slots
mapped to added zero rows. For glyf, original vertical phantom-point deltas and
origins remain bound and new unhinted glyphs receive adequate maxp capacity.
CFF2 keeps original FD/private dictionaries and variation stores while inserting
valid widthless CFF2 charstrings. A CFF2 target without VORG and a glyf target
with independent VVAR top-side-bearing maps still fail before publication.

The same Android diagnostic captured four native SIGSEGVs in system toybox
`sed`'s greedy UTF-8 progress regex (`mstep`, `mwalk`, `regexec`), rather than
in the font compiler or bundled Python. Both mix pollers now use a finite
ASCII numeric-token reader; the remaining progress-message regex uses the C
locale. The Root composite gate also rejects a current task's native-crash
log even if its engine reports success. No frozen mount file changes.

Local checks passed all 27 compiler regressions and all 70 Root-harness tests.
The exact stock five-face CFF2 fixture compiled and independently loaded with
FreeType at default, minimum, midpoint and maximum axis positions. Its fixture
output was 102,657,856 bytes, taking 32.698 seconds and a 298,860 KiB peak RSS
on this host. The ten-face static upstream fixture also passed: five faces
compiled and five retained. These synthetic-donor host figures are not Android
or phone performance measurements.

The candidate workflow now requires the exact Android 15 CFF2 fixture, fetched
from immutable AOSP commit `1763da7de494446263d6e6b7b9e9328eac8ecdd8`
and checked against the captured stock digest before testing. A missing font,
failed variation comparison or failed FreeType load blocks candidate packaging.
The new runtime source is `d3002e830f10977a263701864fd1c2ee19f0e8d7`.
Its own complete candidate CI, artifact verification and Root activation/restore
results are required; earlier static-only package results do not qualify it.

[Candidate CI 37131915487](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37131915487)
completed successfully at 23:17 CST: source checks, mandatory supplemental gates,
27 compiler regressions, both real static/variable font checks, readiness checks,
Android JVM tests/lint and App/module packaging passed. Independent download
verification matched the source's nine reviewed runtime files, all 17 immutable
mount-file digests, APK/module checksums, source provenance and bundled APK.
Module SHA-256: `0c8edb56379eb06ac94214167be835a87159a34edfd8111beb1e02428242eb98`.
APK SHA-256: `0cbfde8bb044f15be56ab05323bbc42586b79ca85dc4f030c8861c41effd24ab`.
The Root workflow now pins this exact run, source and module digest. Its next
full gate must demonstrate generation, completed activation boot, stock restore,
App checks and cleanup; this CI pass alone does not close Android activation.

## Continued remote verification and stock-alias correction

A fresh remote check found the original branch at
`a2b24d7db1df1e6ebe0048a28b24aba54a52964c`, PR #264 still open as a draft,
and no in-progress build or Root run. The worktree was restored from that same
branch after automated workspace maintenance. No replacement implementation or
new branch was created.

The freshly downloaded evidence for
[Root run 37132842902](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37132842902)
was checked against artifact digest
`f6736991111ec1211ae1b8d0f23a05a62c95d16b960d4e3efc5d1f88665918af`.
All five original CFF2 faces compiled with their original variation axes. The
background engine/finalizer completed, three concurrent finalizers retained the
same generation, worker sidecars cleared, and the composite reboot completed
with a new kernel identity and Enforcing SELinux. Eleven recorded module boots
passed. The current composite task had a complete crash-free generation log.

The run nevertheless FAILED at the post-boot assertion:
`Live target differs from committed payload: /system/fonts/DroidSans-Bold.ttf`.
Earlier actual mount evidence proves this original AOSP alias resolves to
`/system/fonts/Roboto-Regular.ttf`. The generic composite publishes that
canonical slot; demanding another payload file named after the alias falsely
rejects these identical live/canonical bytes.

The gate now records every original font's canonical path before installation,
requires that alias identity to survive, compares the changed font with the
committed canonical slot, and requires the exact file or parent-directory mount
to map to that module payload path. Missing bytes, changed original aliases,
conflicting alias payloads, wrong sources and lookalike destinations still fail.
This is an assertion correction; the candidate runtime and all 17 frozen
mounting files remain unchanged. The actual restore/App checks still must run
in a new full gate, and the preceding partial run cannot satisfy them.

This continuation reran 77 host harness regressions, including seven new alias
cases, and the 17-file immutable boundary. All passed. Twelve previously
captured A/B mount proofs also passed a diagnostic replay of the corrected
predicate; this replay is not a new Android delivery qualification. The candidate
artifact was downloaded again, with provenance, ZIP/APK digests, eleven runtime
files, all 17 frozen files and the bundled APK identity independently verified.
It remains the exact runtime commit `d3002e8`, CI run `37131915487`, module
digest `0c8edb56379eb06ac94214167be835a87159a34edfd8111beb1e02428242eb98`.

Native evidence is kept scoped: the progress-reader SIGSEGVs from diagnostic
run `37129497468` identify toybox/bionic regex execution, and the candidate's
current composite log contains none. The later run's one remaining tombstone
belongs to the immutable baseline's injected commit-failure task
`1791041277-7064`, before candidate installation; both candidate error-path
crash buffers are empty. The reference baseline is not patched to erase this
observation. OEM phones, native ARM64 execution and physical-device font
coverage/geometry/performance remain unverified.

## Complete qualification result — run 37152531513

[The full Root run](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37152531513)
completed successfully on 2026-10-03 at 21:10 UTC (14:10 America/Los_Angeles).
Its harness commit is `85af499fb850ba4974b43a9fc55ea242cb3c0a7e`; the
runtime remains the independently verified candidate `d3002e8` from build
`37131915487`. The complete downloaded artifact is 22,156,863 bytes with SHA-256
`06931b7789d34117102d4df363cf4c1ed9aea91c56380cddf9f9bcf1a931fad6`.
It was verified again against the current source's fail-closed predicates.
All blockers are empty. [Structured evidence](ROOT_ANDROID_QUALIFICATION_37152531513.json)
records current-run proofs and all twelve measured UI samples.

| Current-run check | Result |
| --- | --- |
| Root harness regressions in CI and local continuation | 77 passed |
| Immutable v1.1.1 mounting/commit boundary | All 17 files unchanged |
| Actual stock five-face CFF2 compilation, indexes and axes | PASS |
| Current composite engine/monitor, commit lock and three finalizer replays | PASS |
| Baseline/candidate lifecycle, composite and actual-App boots | 14 completed kernel reboots, Enforcing |
| Original aliases, actual bytes and exact mount source | 19 proofs independently recomputed; two original aliases preserved |
| Composite activation and restoration to original system-font hashes | PASS |
| Actual App Root access, 100/1000 synthetic libraries, three cold/warm repetitions each | PASS, twelve verified target-count frames, no target fatal/ANR |
| Actual App selected-font input validation, apply, completed boot and stock restore | PASS |
| Installed Magisk task/request ownership and descendant cleanup | 4 task cases and 8 request cases passed |
| Final transient task space and temporary App policy | Empty workspace; policy revoked |
| Emulator ownership/cleanup and KVM security metadata | Both emulators reaped; metadata unchanged |

The generated variable collection has SHA-256
`b8c9cba7c6c48a27f5d5f7a16234dde55910cf35824ee5247411748d73ba6da9`.
It is the actual mounted payload verified after the completed composite boot,
rather than a renamed single-face font or host-only compiler result. Replaced
glyphs retain the selected fixed donor weight; untouched glyph variation and
original variation-axis metadata remain bound as described above.

The first verified target-count library frame, measured from the actual library
open, took 433–520 ms for the 100-file cold-launch samples and 342–401 ms on
reopen; the 1000-file samples took 456–1091 ms and 341–374 ms respectively.
The app_start sample also includes scripted navigation before opening the
library; its whole elapsed time is not a direct phone cold-start metric.
These are synthetic libraries containing two unique TTF contents in the
x86_64/nativebridge AVD. They do not establish a physical-phone latency or
1000-distinct-real-font result.

Fresh inspection of diagnostic run `37129497468` resolves the earlier
unlabelled progress fault reports. The complete capture contains four progress
faults, plus separate baseline error-message faults; the earlier reported
three lines are not the final event count.

| Progress fault PID | UTC timestamp | Actual process/backtrace |
| --- | --- | --- |
| 6204 | 2026-10-03 14:48:25 | toybox sed on composite_progress.json; bionic mstep → mwalk → regexec |
| 6378 | 2026-10-03 14:48:27 | Same reader and native regex stack |
| 6504 | 2026-10-03 14:48:29 | Same reader and native regex stack |
| 6716 | 2026-10-03 14:48:34 | Additional capture of the same reader and stack |

The current candidate's generation log is crash-free, both candidate error-path
crash buffers are empty, and independent native-command classification found
no unexpected candidate/module/App crash. Two current-run tombstones belong
to the original baseline's invalid-switch/commit-failure tasks
`1791060592-4432` and `1791060601-7070`; they are recorded as baseline
observations, not removed or described as candidate faults.

The AOSP disposable Root gate is now closed successfully. Physical OnePlus 15 /
Redmi K80 Ultra coverage on ColorOS/HyperOS, pixel geometry, real phone/native
ARM64 startup latency and backup-restore API remain unverified. The unsupported
CFF2-without-VORG and independent-VVAR-top-bearing cases still fail closed.
No hook, new mounting strategy, device mutation, expanded permission, merge
to main, formal release or deployment is part of this continuation.
