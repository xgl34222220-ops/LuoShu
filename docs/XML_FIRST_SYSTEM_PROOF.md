# Fixed-selection XML-first system proof

Verified 2026-09-30 on commit `2eaa285e61c7a66f2d79cfccd1acddb55b80acf5`.
CI: https://github.com/xgl34222220-ops/LuoShu/actions/runs/36776688848

## What passed

Disposable Android 16 / API 36 userdebug emulator, synthetic original donors only.
Both `/system/etc/fonts.xml` and the protected `/system/etc/font_fallback.xml`
were inventoried and rewritten. After a real reboot, public TextRunShaper font
provenance and independently expected raster comparisons verified `A`, `1`, and
`中` resolve to the selected composite. Greek `Ω` and emoji kept their original
fallback fonts and pixels. No Hook or hidden API exemption was used.

Both original XML byte streams were restored; after another real reboot, all
five raster hashes and font provenance returned to baseline. The experimental
font file was removed. The disposable emulator and runner were torn down.

The previous run passed takeover but restoration verification failed because
adbd dropped root after reboot. Its command log showed `Permission denied` on
font_fallback.xml even though `exec-out` exited zero. Readability is now checked
with shell-v2, root is explicitly reacquired after the restoration reboot, and
three host regressions cover these gates. This was a verification bug, not proof
that a user's phone suffered restoration failure.

## What this does NOT establish

- Magisk / KernelSU / APatch mount timing and boot-hook integration
- HyperOS / ColorOS or other OEM device acceptance
- Real user-selected font geometry, app-specific clipping, or memory consumption
- Typeface named-family, all weights/styles, locale, variable axes, and embedded
  or remotely downloaded app fonts on every application
- Readiness of the experimental XML planner as a production deployment producer

## Production integration constraints

The current universal router intentionally changes only font-reference text and
preserves collection indices, axes, PostScript names and every other XML field.
The experimental fixed-static representation changes that contract. It must get
an explicit, versioned representation; removing those validations globally would
silently invalidate physical and variable-font paths.

A complete production path needs all of:

1. Bind source selection and each XML snapshot to content hashes and exact node
   identities; select the effective configuration, including restricted files,
   through the already-authorized module Root path. Do not infer root cause on
   OEM devices from this AOSP-only experiment.
2. Compute actual role/line geometry from verified original slot/face/axis data.
   Share compilation only when the complete source AND geometry contracts match.
3. For explicitly fixed upright selections, emit honest static SFNT metadata and
   update only explicitly planned XML indices/axes/names. Preserve genuine
   italics, unrelated locale/script families and aliases.
4. Preserve original glyph fallback. If an OEM physical adapter also replaces an
   original pathname, a fallback reference to that same pathname is insufficient;
   it must reference a verified immutable original asset instead. Prevent cycles
   and ordering changes, and account for fallback copies in size estimates.
5. Keep physical-only OEM consumers on separately verified adapters. Do not
   advertise complete coverage when such consumers are unresolved.
6. Stage XML, compiled assets and retained originals as one exact hashed payload
   under existing transactional ownership/cancellation/OTA guards. Boot success
   must verify actual runtime font provenance before acknowledging application.
7. Verify interrupted application, missing/tampered assets, stale snapshots,
   reboot, reapply and recovery before offering a phone-test module. Never mask a
   new-core failure as a successful old-engine deployment.

The existing `experiments/xml-first/planner.py` remains non-deployable. Its small
host suite establishes contract grouping, not production readiness. The current
proof uses its own test XML rewrite and must not be reported as that planner's
end-to-end integration.

## Subsequent production evidence and next weight contract

Production-generated XML, compiled files and copied original fallback assets
passed the default `A` / `1` / `中` reboot-and-restoration experiment at
`9643c61a053d713b659ef65398ae2895fe4b26b4` (Actions 36803617022). That payload
still used the older verified adapter for default Latin/digits. It was a mixed
path, not complete adoption of the static XML representation.

The explicit static weight expansion at `6be17a9` failed the global 450 case
(Actions 36806453735). Android's static font matching groups weights by hundreds;
registering separate 400 and 450 files did not prove the 450 file was selected.
Original XML and all baseline cases were restored successfully. That failed
representation is not enabled for phone deployment.

The next explicit opt-in representation is
`fixed-outline-weight-match-xml-v1` / route revision 3. It gives a deliberately
fixed upright selection a constant-outline `wght` selection axis, spanning
1–1000. This is not preservation of donor variation. Geometry is measured at
an explicit frozen OEM reference (400 plus the node's other fixed axes); runtime
weight requests do not reshape the chosen fixed outlines. Genuine italics
reference the sealed original variable container. The original script fallback
family remains present. Generic variable sources and physical-only slots do not
acquire permission to use this representation.

The representation requires empty glyph variations and no variable metrics or
axis-dependent shaping, rather than relying only on sampled outlines. Payload
membership, original SHA/face proof, reopened geometry and cancellation/OTA gates
remain mandatory. Local integration tests cover positive staging and rejection of
nonconstant variations, variable layout, metric variation, wrong representation,
and changed reference coordinates. The 74-case global matrix is the next native
gate; its result must be recorded separately before claiming system success.

The earlier app-only matching-family test passed at `83eb0ec` (36809070207),
and actual Android x86 Python/FontTools execution passed at `25e1d3c`
(36811011982). Neither is ARM64 execution or module/root-manager mounting proof.
The Python API-level field describes its build target; device API level is
checked independently. Runtime consumer confirmation remains pending on phones,
and warnings retain recovery state rather than being converted to success.


The revision-3 system run `b092660` / Actions 36826607502 produced 72 passing
cases out of 74, including normal/italic selected roles and the 450/520 matching
cases. The two failures were the original Greek glyph in sans-serif-condensed:
its copied source bytes and face were correct, but a preceding global default
fallback selected wdth=100 instead of the original named-family wdth=75. All 74
baseline cases and the original XML were restored, and the VM was terminated.
The test therefore failed overall; the remaining cases were not dropped.

Revision 4 explicitly uses a local named `family-list` containing the selected
family followed by its full sealed original family. Existing named family-list
contexts stay intact. The original default copy also remains a global fallback
for other names; scoped named originals no longer depend on a later global
position. This follows Android 16 SystemFonts' named-chain-before-global-chain
construction. The next full native matrix must verify this correction. Older
platforms without this XML capability are not established by this adapter.

A separate module-mount regression found that legacy per-file bind fallback
accepted absent additive paths. Every file in a sealed Universal deployment is
now required: missing assets reject the transaction before any payload file
bind, while a complete directory overlay may introduce them. Both mount entry
points and the existing real Linux namespace suite pass locally. This remains
host evidence; the system experiment uses temporary XML/file replacement, not
root-manager module mounting.


Revision 4 passed the real system 74-case matrix at `e6acece8` / Actions
36828969013, including the two condensed Greek cases with wdth=75. All 74
original cases and XML bytes were restored, and the VM was terminated. The
host production preparation took 108.616 seconds (60 artifacts, 48 unique
compiled files, 67,828,207 payload bytes). This is not an ARM phone benchmark.
The x86 Android production-runtime smoke also passed independently.

The next experiment confines the actual production mount backend and sealed
payload to a disposable VM's private mount namespace. Its verifier explicitly
uses that namespace instead of init's view and does not claim root-manager boot
or global App consumption. It requires all payload hashes and read-only mounts,
idempotent reapplication, real rollback, partial-overlay failure rollback, and
integrity rejection before any mount. Parent-namespace original bytes and
absence of added assets must survive a reboot. SELinux and hidden API policy
remain unchanged; no root manager or init script is installed.

Preparation for this experiment reproduced unsafe cleanup after a failed lower
unmount. The backend now removes only empty mount points, records attempted
owned lower mounts before a cancellable bind, rejects failed private propagation,
and requests an explicitly read-only overlay. Four failure-injection cases and
a real Linux namespace bind/private-overlay/rollback case cover this change.
Actual Android results for this new backend are still pending.


The first Android namespace attempt (`2aa054f`, 36832614587) stopped before
font mounting: Toybox treated single-target `mount --make-rprivate /` as a
fstab lookup. Outside-namespace originals, reboot originals, staging removal
and VM destruction were verified. This was a failed gate, not mount success.
The portable form supplies an explicit ignored source: `mount -o rprivate none /`
and `mount -o private none <lower>`. The scanner's temporary recovery view had
the same single-target issue and is corrected too. Real GNU and Toybox namespace
tests inspect private propagation and read-only overlay flags; the disposable
Android script independently rejects shared/master propagation after isolation.

### Namespace propagation follow-up (cfca5dd)

Android run 36841069885 stopped before any font mount: its mountinfo still
contained master propagation after Toybox accepted `rprivate`. Toybox upstream
`toys/lsb/mount.c` maps that spelling to `MS_SLAVE|MS_REC`. A nested real Linux
namespace with an inherited shared parent reproduces the residual master; an
already-private host fixture had concealed it. The disposable probe now calls
the explicit `MS_PRIVATE|MS_REC` syscall through the staged Android Python and
independently verifies every mountinfo optional field. Same-namespace entry,
syscall failure, or remaining propagation is rejected. Production single-lower
`private` commands are unchanged. The new Android transaction remains pending.

The failed run verified outside-namespace original bytes, original bytes after
reboot, temporary stage removal, and emulator termination. It is not mount
acceptance evidence. Upstream source: https://github.com/landley/toybox/blob/master/toys/lsb/mount.c

### Casefold lower-layer compatibility (2b628ab evidence)

Android run 36845014575 established the private namespace, then the production
hook safely refused deployment. Kernel evidence reports `case-insensitive
capable filesystem ... not supported` for both payload lower directories on
`/data`. Bind/private operations succeeded; required new assets prevented an
incomplete bind fallback. Original bytes outside the namespace, their reboot
state, stage removal and VM teardown were verified. No font takeover occurred.

A scoped production fallback now retries a sealed Universal payload directory
through an owned case-sensitive tmpfs copy, only after direct overlay failure.
The total reserved size is capped at 256 MiB and one eighth of currently available
RAM; symlinks and insufficient budget are refused. Every copied file is compared
fully before the layer is remounted read-only; the original source remains intact.
The real mount journal includes the memory layer. Failed unmounts retain their
journal and block a new transaction; cleanup never recursively deletes a lower
view. Host kernel tests cover readonly overlay, corrupted-copy rejection,
failed-unmount byte preservation and subsequent rollback. Android validation is
pending; this is not yet root-manager boot or App SELinux accessibility proof.

Overlay ownership records persist both the original and newly resolved mount
IDs. They are read through an opened target FD's kernel `mnt_id`, rather than
assuming mountinfo line ordering. Rollback refuses a foreign top layer, accepts
the restored original mounted directory, and retains incomplete state. A real
SIGKILL immediately after successful overlay creation tests the pre-journal
intent recovery; a second rollback leaves the original mount ID unchanged.

### Verified production namespace transaction: 48ef641

Android run https://github.com/xgl34222220-ops/LuoShu/actions/runs/36849124616
and candidate run 36849124617 succeeded. Downloaded evidence artifact 11154314631
has ZIP SHA256 `72b1cfdbca05dbc2e10b2e0869ebe625ce17c1102db332140fa664a3e93013e6`.
The real API36 x86_64 child namespace verified all 53 sealed files read-only,
idempotent reapplication, normal rollback, rollback after a partial mount
failure, and integrity rejection before mounts. Outside-namespace originals,
the same originals after reboot, all 74 restored consumer cases, temporary stage
removal and emulator termination were verified.

Host production preparation took 120.563 seconds (60 artifacts, 48 unique files,
67,828,207 payload bytes). The Android transaction protocol took 68.483 seconds,
including repeated verification and fault cases; neither number is a phone
single-apply benchmark. Compilation ran on the host, while production payload
validation and mount scripts ran with the Android x86 runtime.

This closes private-namespace mount compatibility for this fixture. It does not
establish shipped ARM64 execution, root-manager boot integration, or ordinary
App SELinux access to the memory-backed layer. The earlier global 74-case proof
used system-file replacement and remains a separate result. Matching XML
revision 4 remains experiment-selected; no phone-wide acceptance claim follows.

### Next bounded check: ordinary App access to mounted assets

The next experiment uses the existing disposable root VM, requires adbd's
namespace to already equal init's namespace, and never enters another namespace.
SELinux must remain Enforcing. The same production transaction is temporarily
applied globally, and the ordinary test App reads every mounted font through
public file/Font APIs. Its UID/domain, full file and font-buffer hashes, actual
file device/inode identity, and selected glyph sources are checked independently
of the root verifier. Selected normal/italic weights plus representative original
Greek/emoji glyphs are exercised by direct Font.Builder consumers. This does not
claim default Typeface or boot-time takeover: the existing zygote/font-manager
map may still cache old fonts.

Only the owned test App is stopped before rollback to release its test mappings.
The production rollback, original bytes, absence of new assets, reboot baseline
consumers, staging cleanup and VM disposal remain required. Failure to roll back
prevents recursive staging deletion. No root manager, init edit, policy change,
or user device is involved. Android results for this new direct-read mode are
still pending. ARM64 execution also remains unproved; the currently available
runner/runtime experiment is x86_64, and the packaged ARM ELF requires Android's
Bionic linker, not a Linux ARM interpreter.

### Ordinary-App label failure and scoped correction pending verification

Run 36853045919 reached the real App (UID 10216, `untrusted_app`, Enforcing).
Opening the first mounted font failed with EACCES; the kernel AVC identifies its
`appdomain_tmpfs:s0` target label. Root readability therefore was insufficient.
Production rollback restored the original bytes, but a post-reboot adbd transport
closure interrupted final verification and explicit staging cleanup. Emulator
teardown was confirmed; this attempt is not recorded as a successful recovery.

The authorized correction restores labels only on owned temporary font-layer
copies (configuration XML copies are not relabeled in this phase), using the captured original counterpart or nearest existing original
directory for a new asset. Each label is read back before the memory layer becomes
read-only. Original files and SELinux policy/enforcing state are unchanged. File
modes on copies are restricted to 0644 and directories to 0755. Host label tests
mock chcon and do not substitute for Android verification. The adb root helper
now reconnects within a fixed budget and requires actual UID 0, rather than
failing solely because adbd closed the transport during its root restart.

### Font access proved; direct-style construction corrected

Run 36855896971 (0907585) read all 52 font files as UID 10216 in
`untrusted_app` under Enforcing SELinux. Their file hashes and device/inode pairs
matched the root snapshot. Temporary font labels matched the stock system_file
label; no configuration XML labels were changed. The first A/1/Han glyph cases
passed, then the first preserved italic raster check failed. Complete rollback,
reboot original-byte verification, staging removal and VM teardown succeeded.

The direct Font.Builder oracle had copied Font.getAxes output, which omits
implicit XML supportedAxes values. The corrected direct contract independently
resolves the frozen original family node, its supportedAxes and SHA-bound fvar
limits, then supplies requested/clamped wght and ital plus explicit wdth. Its
font descriptor uses the requested weight to avoid additional synthetic bold.
The preserved pixel comparison remains mandatory. Native retest is pending.

A separate real-kernel regression exposed that bare per-file bind journals could
unmount an original pre-existing bind on a second rollback. Bind transactions
now retain the original/new actual FD mount IDs and source device/inode, including
a pre-mount cancellation intent. Foreign tops and unproven legacy journals are
refused; original baselines survive repeated rollback. Host tests exercise the
actual bind-tree writer, SIGKILL window, foreign layer, legacy refusal, canonical
symlink targets and child-bind-before-parent-overlay rollback. The
next Android experiment runs these same cases in an isolated child namespace
before the ordinary-App direct-read check. This does not add root-manager boot
or ARM64 execution evidence.

The first Android bind regression attempt (f2a6e08), and its trace-only retry
(b6f7731), stopped before global publication. The trace reaches the final mixed
layer case after the original bind, foreign-top, cancellation and file-alias
assertions. Its synthetic original directory was on Android /data; unlike the
production ROM lower, it retained the casefold filesystem underneath the captured
bind. The fixture now uses a verified 1 MiB tmpfs for its synthetic original and
selected files. The production backend and every rollback assertion stay in use.
Android confirmation of that fixture correction remains pending. Both failed
attempts verified original bytes after reboot, removed their stage and destroyed
the VM; neither supplies new ordinary-App style evidence.

### Mounted fonts consumed by an ordinary App (5cabc217)

[Android run 36863726733](https://github.com/xgl34222220-ops/LuoShu/actions/runs/36863726733)
and candidate run 36863726778 completed successfully. The evidence artifact is
11162874488. On API36 x86_64, UID10216 in `untrusted_app` under Enforcing read all
52 approved font files and passed 66 direct Font.Builder/TextRunShaper cases.
The cases cover A/1/Han, protected Greek/emoji, normal/italic and requested
weights 1,100,300,400,450,520,700,900,1000 across sans-serif,
sans-serif-condensed and roboto. All 26 preserved raster references matched.
Actual buffer hashes and nonzero glyph IDs are required for every direct case.
This confirms explicit direct reads, not default Typeface registration or boot.

The same run passed the real Android bind ownership suite, including original
bind preservation, foreign top refusal, post-mount SIGKILL, repeated rollback,
logical symlink resolution and child bind before parent overlay restoration.
The production transaction validated 53 files. Normal rollback, reboot original
byte checks, owned staging deletion and VM teardown all completed. No XML-copy
label change, init file modification, SELinux policy change or root manager was
used. Host compilation took 136.319 seconds; this is not a phone latency result.
The APK remains the byte-identical 317 audit App. The checked module candidate
is retained while default-consumer and boot integration remain unproved.
