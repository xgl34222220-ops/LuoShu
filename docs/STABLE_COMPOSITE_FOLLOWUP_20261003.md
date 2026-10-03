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
