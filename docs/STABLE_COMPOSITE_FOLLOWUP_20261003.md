# Stable candidate follow-up — 2026-10-03

The 08:42 CST root gate (`37081290739`, candidate `9576301`) generated and
committed a composite, passed its actual Android lock checks, then timed out at
the composite reboot. It did not capture logcat from that failed reboot, so the
timeout alone cannot establish a specific native crash or an OEM-device cause.

Source inspection confirms a separate structural defect: the legacy generic
mapper hardlinks the single SFNT composite under `NotoSansCJK-Regular.ttc`.
Multiple collection indexes cannot be satisfied by renaming a single face.
Alias creation now refuses that operation before the engine commits its config.
Previously generated collection stages are also validated before a finalizer
can replace an existing next-boot payload. Reports bind failures to the request
and path. The guard does not generate stock-compatible collection faces and
must not be described as completing generic CJK, HyperOS or ColorOS coverage.

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
