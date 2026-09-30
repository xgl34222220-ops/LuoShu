# Android font contract experiment

CI-only, separate application ID. This is not part of the module payload and must
not replace the user's existing App. All fonts are original synthetic fixtures,
created with the actual LuoShu CJK/Latin/digit compositor.

Gates:
1. Native Android Font/FontFamily/Typeface raster identity for the three donors,
   fixed style declarations 100–900, unchanged emoji and unknown-script fallback.
2. Existing Android framework XML parser/family builder, when normally exposed.
   Reflection only calls available methods; no hidden-API policy changes, rooting
   or method hooks. Unavailable/failed parsing is a blocked gate, not a pass.
3. Immutable generation path switch/return and actual emulator reboot persistence.
4. System-global module mounts, root-manager namespaces, FontManager startup and
   real HyperOS/ColorOS rendering remain **not tested by this harness**.

The workflow uses existing KVM permissions only, with software acceleration as a
fallback. It installs a separate probe only on its disposable CI emulator.
No test APK is delivered to the user. Evidence includes JSON and original
synthetic-glyph screenshots, even when a capability gate is blocked.
