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
