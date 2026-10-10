# LuoShu App Icon

Official release icon for LuoShu: 「书」字 in a 米字格 on cream paper with a small vermilion seal.

- Stable path: `design/app-icons/official-icon.webp` (512×512, visible 72dp area of the adaptive icon)
- Launcher (Android adaptive icon, minSdk 28):
  - `android-app/app/src/main/res/mipmap-anydpi-v26/ic_luoshu.xml`
  - background: `drawable/ic_luoshu_background.xml` (vector of `shu-v3/bg.svg`; dashes as short segments)
  - foreground: `mipmap-<density>/ic_luoshu_foreground.webp` (108dp canvas, glyph + seal inside the safe zone)
  - monochrome (Android 13 themed icons): `mipmap-<density>/ic_luoshu_monochrome.webp` (glyph only, no seal)
- Splash: `drawable/ic_luoshu_splash.xml` → `drawable-nodpi/ic_luoshu_splash_foreground.webp` (1024px foreground)
- Sources: `shu-v3/fg_1024.png` (foreground), `shu-v3/bg.svg` (background), `shu-v3/preview.png` (mask mockups)
- Branding thumbnail: `branding/luoshu-app-icon.webp` (192px)
- Colors: paper `#F6EFDD`, guides `#C9A98A`, seal vermilion; dark splash background `#181A20`
- Approved: 2026-10 (replaces the 2026-09-18 magic-square glass icon; `luoshu-magic-square.webp` kept for history)

Use this icon for future stable releases unless it is explicitly replaced.
