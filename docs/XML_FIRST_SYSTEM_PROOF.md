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
