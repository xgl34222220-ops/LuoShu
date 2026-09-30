# Android font contract experiment

CI-only, separate application ID. This is not part of the module payload and must
not replace the user's existing App. All fonts are original synthetic fixtures,
created with the actual LuoShu CJK/Latin/digit compositor.

Gates:
1. Native Android Font/FontFamily/Typeface raster identity for the three donors,
   fixed style declarations 100–900, unchanged emoji and unknown-script fallback.
2. Existing Android framework XML parser/family builder, through a separate
   command-line probe in the existing adb-shell context. It consumes only its
   temporary XML/assets and compares pixels with the independently verified App.
   The App-level API availability is reported separately. No hidden-API policy
   changes, rooting or hooks; a blocked shell probe still fails the gate.
3. Immutable generation path switch/return and actual emulator reboot persistence.
4. System-global module mounts, root-manager namespaces, FontManager startup and
   real HyperOS/ColorOS rendering remain **not tested by this harness**.

The workflow requires KVM and fails before boot if it is inaccessible. The
explicitly authorized one-time push marker can grant only the current runner
user an ACL on its disposable VM; later pushes do not inherit that approval. It installs a separate probe only on its disposable CI emulator.
No test APK is delivered to the user. Evidence includes JSON and original
synthetic-glyph screenshots, even when a capability gate is blocked.

The pixel oracle is built independently from explicit expected aligned glyph
coordinates and advances. Raw donors remain separate identity discriminators;
they are not expected to match after the compositor scales Latin/digits to its
826-unit UI top. Host generation checks the complete expected coordinates before
Android performs the pixel comparison.
