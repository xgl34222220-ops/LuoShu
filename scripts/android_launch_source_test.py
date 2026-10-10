#!/usr/bin/env python3
"""Guard platform-owned launch wiring/resources; raw frames verify visible ordering."""

from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "android-app/app/src/main"
JAVA = MAIN / "java/io/github/xgl34222220/luoshu"
ANDROID = "{http://schemas.android.com/apk/res/android}"
AAPT = "{http://schemas.android.com/aapt}"


def method(source: str, marker: str) -> str:
    """Return a balanced Kotlin body, avoiding accidentally checking a neighboring method."""
    start = source.index("{", source.index(marker))
    depth = 1
    end = start + 1
    while depth and end < len(source):
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    if depth:
        raise AssertionError(f"Unbalanced Kotlin body after {marker}")
    return source[start + 1:end - 1]


def style_items(file: Path, name: str) -> dict[str, str]:
    root = ET.parse(file).getroot()
    style = next(node for node in root.findall("style") if node.get("name") == name)
    return {item.attrib["name"]: item.text.strip() for item in style.findall("item")}


class SingleStageLaunchSourceTest(unittest.TestCase):
    def setUp(self):
        self.controller = (JAVA / "ui/launch/LuoShuLaunchController.kt").read_text()
        self.activity = (JAVA / "MainActivity.kt").read_text()

    def test_no_second_brand_page_or_custom_launch_motion_is_reachable(self):
        self.assertFalse((JAVA / "ui/launch/LuoShuLaunchArtView.kt").exists())
        sources = self.controller + self.activity
        for obsolete in ("attachArtwork", "artworkEnabled", "skipExitAnimation", "SCHEDULE_FADE", "START_FADE"):
            self.assertNotIn(obsolete, sources)
        self.assertNotRegex(self.controller, r"ValueAnimator|AnimatorListener|PathInterpolator|postDelayed|postOnAnimation|\.animate\(|addView\(")

    def test_window_gets_the_real_shared_backdrop_before_compose_content(self):
        create = method(self.activity, "override fun onCreate(")
        self.assertLess(create.index("launchController.install("), create.index("setContent(content = appContent)"))
        install = method(self.controller, "fun install(")
        self.assertIn("applyAppearance(dark, pureBlack = false)", install)
        appearance = method(self.controller, "fun applyAppearance(")
        self.assertIn("window.setBackgroundDrawable(LuoShuGlassBackdropDrawable(dark, pureBlack))", appearance)

    def test_native_shell_submission_is_separate_from_real_content(self):
        install = method(self.activity, "private fun installNativeShell(")
        self.assertIn("policy.onShellSubmitted()", install)
        for release in ("deliverFirstFrame(", "firstContentDrawn =", "firstFrameCommitted =",
                        "onContentDrawn()", "requestImportNotificationPermissionWhenReady()"):
            self.assertNotIn(release, install)
        handoff = method(self.activity, "private fun scheduleNativeShellHandoff(")
        self.assertIn("policy.beginContent(softwareFallback)", handoff)
        self.assertIn("if (isFinishing || isDestroyed", handoff)
        self.assertLess(handoff.index("root.addView(content"), handoff.index("observeFirstDraw(startedAt)"))
        self.assertNotIn("SystemClock.elapsedRealtime()\n", handoff)
        self.assertNotIn("setContentView(", handoff)
        self.assertIn("setContent(appContent)", handoff)
        self.assertEqual(self.activity.count("if (openTaskCenter) TaskCenterHost() else LuoShuHost(firstFrameCommitted)"), 1)
        self.assertIn("private val appContent: @Composable () -> Unit", self.activity)
        self.assertNotIn("postDelayed", handoff)
        self.assertIn("nativeShellPolicy?.dispose()", method(self.activity, "override fun onDestroy("))
        self.assertIn("removeNativeShellObservers()", method(self.activity, "override fun onDestroy("))

    def test_shell_is_opaque_system_color_without_logo_or_glass_shader(self):
        shell = (JAVA / "ui/launch/LuoShuNativeShellView.kt").read_text()
        self.assertIn("setBackgroundColor(context.getColor(R.color.launch_background))", shell)
        self.assertIn('text = "洛书"', shell)
        self.assertIn('text = "正在准备界面"', shell)
        for forbidden in ("ic_luoshu_splash", "LuoShuGlassBackdropDrawable", "Shader", "animate", "postDelayed"):
            self.assertNotIn(forbidden, shell)
        install = method(self.controller, "fun install(")
        self.assertIn("if (nativeShell)", install)
        self.assertIn("ColorDrawable(activity.getColor(", install)

    def test_shell_appearance_is_buffered_and_seeded_into_same_activity_vm(self):
        observer = method(self.activity, "private fun observeDisplayPreference(")
        self.assertIn("Phase.SHELL_SUBMITTED", observer)
        self.assertIn("pendingAppearance = settings", observer)
        self.assertNotIn("setHighRefreshEnabled", observer)
        self.assertIn("setHighRefreshEnabled(settings.highRefreshRate)",
                      method(self.activity, "private fun applyWindowAppearance("))
        handoff = method(self.activity, "private fun scheduleNativeShellHandoff(")
        self.assertLess(handoff.index("InitialAppearanceFactory"), handoff.index("val content = ComposeView"))
        self.assertLess(handoff.index("applyWindowAppearance("), handoff.index("root.addView(content"))
        model = (JAVA / "ui/appearance/AppearanceViewModel.kt").read_text()
        self.assertIn("@JvmOverloads constructor", model)
        self.assertIn("initialValue = initialSettings", model)
        self.assertIn("return AppearanceViewModel(application, settings) as T", model)
        for method_name in ("override fun onResume(", "override fun onNewIntent("):
            self.assertNotIn("installNativeShell", method(self.activity, method_name))

    def test_software_does_not_submit_or_wait_for_preparation_frame(self):
        install = method(self.activity, "private fun installNativeShell(")
        self.assertIn("ViewTreeObserver.OnPreDrawListener", install)
        self.assertIn("if (!decor.isHardwareAccelerated)", install)
        self.assertIn("softwareFallback = true", install)
        self.assertRegex(install, r"softwareFallback = true\)\s*false")

    def test_native_splash_keeps_default_platform_exit_without_client_transfer(self):
        # A synchronously removed exit callback still transfers a copied logo to
        # the decor before that callback, which can cover an already drawn home.
        # Guard every production Kotlin entry point, not just this controller.
        for file in JAVA.rglob("*.kt"):
            source = file.read_text()
            self.assertNotRegex(source, r"setOnExitAnimationListener\s*[(\{]", str(file))
            self.assertNotRegex(source, r"clearOnExitAnimationListener\s*\(", str(file))
        self.assertNotIn("activity.splashScreen", self.controller)

    def test_first_system_glass_frame_uses_window_backdrop_without_hiding_content(self):
        shell = (JAVA / "LuoShuAppShell.kt").read_text()
        self.assertIn("val windowOwnsFirstBackdrop = !firstFrameCommitted && appearance.glassEnabled &&", shell)
        self.assertIn("appearance.themeMode == ThemeMode.SYSTEM && !appearance.amoledBlack", shell)
        self.assertIn("if (!windowOwnsFirstBackdrop) AppBackdrop(appearance, dark)", shell)
        # The condition gates only the duplicated backdrop. It must never gate
        # page semantics, the dock or a replacement startup/loading surface.
        gated = shell.index("if (!windowOwnsFirstBackdrop) AppBackdrop(appearance, dark)")
        page = shell.index("pageStateHolder.SaveableStateProvider(page.name)", gated)
        self.assertNotIn("{", shell[gated:page])
        self.assertIn("HomeRoute(", shell[page:])
        self.assertIn("MiuixAppDock(", shell[page:])
        self.assertIn("val blurActive = firstFrameCommitted &&", shell)
        # Saved explicit/AMOLED/solid choices retain their own first-frame draw.
        for committed in (False, True):
            for glass in (False, True):
                for theme in ("SYSTEM", "LIGHT", "DARK"):
                    for amoled in (False, True):
                        window_owned = not committed and glass and theme == "SYSTEM" and not amoled
                        self.assertEqual(window_owned, (committed, glass, theme, amoled) ==
                                         (False, True, "SYSTEM", False))

    def test_window_backdrop_reports_opaque_only_without_alpha_or_filter(self):
        drawable = (JAVA / "ui/launch/LuoShuGlassBackdropDrawable.kt").read_text()
        self.assertRegex(drawable, r"override fun getOpacity\(\): Int =\s*"
                         r"if \(drawableAlpha == 255 && drawableFilter == null\) PixelFormat.OPAQUE\s*"
                         r"else PixelFormat.TRANSLUCENT")
        self.assertIn("return (255 shl 24)", drawable)
        self.assertIn("color = 0xFF000000.toInt()", drawable)
        self.assertIn("drawableAlpha = alpha.coerceIn(0, 255)", drawable)
        self.assertIn("drawableFilter = colorFilter", drawable)

    def test_lifecycle_and_task_entry_cannot_replay_or_retain_the_launch(self):
        self.assertIn('fun stop() = complete("stop")', self.controller)
        self.assertIn('fun finishForTaskEntry() = complete("task_entry")', self.controller)
        self.assertIn("launchController.stop()", method(self.activity, "override fun onStop("))
        self.assertIn("launchController.finishForTaskEntry()", method(self.activity, "override fun onNewIntent("))
        destroy = method(self.controller, "fun dispose(")
        self.assertIn("onComplete = null", destroy)
        activity_destroy = method(self.activity, "override fun onDestroy(")
        self.assertIn("removeCallbacks", activity_destroy)
        self.assertIn("removeFirstDrawListener()", activity_destroy)
        self.assertIn("launchController.dispose()", activity_destroy)

    def test_first_draw_measurement_and_permission_safety_remain_present(self):
        first_draw = method(self.activity, "private fun observeFirstDraw(")
        self.assertIn("ViewTreeObserver.OnDrawListener", first_draw)
        self.assertIn("event=first_decor_draw", first_draw)
        self.assertIn("activityFirstDrawMs=", first_draw)
        self.assertIn("view.post(it)", first_draw)
        self.assertIn("!isFinishing && !isDestroyed", first_draw)
        ready = method(self.activity, "private fun requestImportNotificationPermissionWhenReady(")
        for guard in ("!firstContentDrawn", "!launchController.isComplete", "openTaskCenter", "Lifecycle.State.RESUMED"):
            self.assertIn(guard, ready)

    def test_real_theme_keeps_the_unbranded_gradient_backdrop(self):
        resources = MAIN / "res"
        self.assertEqual(style_items(resources / "values/themes.xml", "Theme.LuoShuHybrid")["android:windowBackground"],
                         "@drawable/luoshu_launch_background")
        root = ET.parse(resources / "drawable/luoshu_launch_background.xml").getroot()
        self.assertEqual(root.tag, "shape")
        self.assertEqual(root.attrib[ANDROID + "shape"], "rectangle")
        gradient = root.find("gradient")
        self.assertIsNotNone(gradient)
        for stop in ("startColor", "centerColor", "endColor"):
            self.assertTrue(gradient.attrib[ANDROID + stop].startswith("@color/launch_gradient_"))
        self.assertIsNone(root.find("item"))
        for folder, file in (("values", "themes.xml"), ("values-night", "launch.xml")):
            colors = {node.get("name"): node.text for node in ET.parse(resources / folder / file).getroot().findall("color")}
            for stop in ("start", "center", "end"):
                self.assertRegex(colors["launch_gradient_" + stop], r"^#[0-9A-Fa-f]{6}$")

    def test_legacy_starting_window_mirrors_the_platform_splash(self):
        # API 28-30 have no platform splash; the starting window shows the same
        # opaque launch color, cream icon circle and emblem, and nothing else.
        resources = MAIN / "res"
        self.assertEqual(style_items(resources / "values/themes.xml", "Theme.LuoShuLaunch")["android:windowBackground"],
                         "@drawable/luoshu_launch_splash")
        root = ET.parse(resources / "drawable/luoshu_launch_splash.xml").getroot()
        self.assertEqual(root.tag, "layer-list")
        items = root.findall("item")
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0].find("shape/solid").get(ANDROID + "color"), "@color/launch_background")
        self.assertEqual(items[1].find("shape").get(ANDROID + "shape"), "oval")
        self.assertEqual(items[1].find("shape/solid").get(ANDROID + "color"), "@color/launch_icon_background")
        self.assertEqual((items[1].get(ANDROID + "width"), items[1].get(ANDROID + "height")), ("160dp", "160dp"))
        self.assertEqual(items[2].get(ANDROID + "drawable"), "@drawable/ic_luoshu_splash")
        self.assertEqual((items[2].get(ANDROID + "width"), items[2].get(ANDROID + "height")), ("240dp", "240dp"))
        for item in items[1:]:
            self.assertEqual(item.get(ANDROID + "gravity"), "center")

    def test_android_twelve_keeps_a_supported_single_opaque_system_splash(self):
        items = style_items(MAIN / "res/values-v31/launch.xml", "Theme.LuoShuLaunch")
        self.assertEqual(items["android:windowSplashScreenBackground"], "@color/launch_background")
        self.assertEqual(items["android:windowBackground"], "@color/launch_background")
        self.assertEqual(items["android:windowSplashScreenAnimatedIcon"], "@drawable/ic_luoshu_splash")
        self.assertEqual(items["android:windowSplashScreenIconBackgroundColor"], "@color/launch_icon_background")
        self.assertNotIn("android:windowSplashScreenBrandingImage", items)
        self.assertNotIn("android:windowSplashScreenAnimationDuration", items)

    def test_splash_emblem_is_one_static_high_resolution_bitmap(self):
        icon = ET.parse(MAIN / "res/drawable/ic_luoshu_splash.xml").getroot()
        self.assertEqual(icon.tag, "bitmap")
        self.assertEqual(icon.get(ANDROID + "src"), "@drawable/ic_luoshu_splash_foreground")
        self.assertEqual(icon.get(ANDROID + "gravity"), "fill")
        source = MAIN / "res/drawable-nodpi/ic_luoshu_splash_foreground.webp"
        self.assertTrue(source.is_file())
        # RIFF/WEBP header; width/height of a lossless VP8L bitstream.
        data = source.read_bytes()
        self.assertEqual((data[:4], data[8:12], data[12:16]), (b"RIFF", b"WEBP", b"VP8L"))
        bits = int.from_bytes(data[21:25], "little")
        width, height = (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        # 240dp at xxxhdpi (4x) is 960px: never upscale on any density.
        self.assertGreaterEqual(min(width, height), 960)
        self.assertEqual(width, height)
        self.assertFalse(list((MAIN / "res").rglob("ic_luoshu_launch*")))

    def test_launcher_icon_is_adaptive_with_monochrome_layer(self):
        resources = MAIN / "res"
        manifest = ET.parse(MAIN / "AndroidManifest.xml").getroot().find("application")
        self.assertEqual(manifest.get(ANDROID + "icon"), "@mipmap/ic_luoshu")
        self.assertEqual(manifest.get(ANDROID + "roundIcon"), "@mipmap/ic_luoshu")
        root = ET.parse(resources / "mipmap-anydpi-v26/ic_luoshu.xml").getroot()
        self.assertEqual(root.tag, "adaptive-icon")
        self.assertEqual(root.find("background").get(ANDROID + "drawable"), "@drawable/ic_luoshu_background")
        self.assertEqual(root.find("foreground").get(ANDROID + "drawable"), "@mipmap/ic_luoshu_foreground")
        self.assertEqual(root.find("monochrome").get(ANDROID + "drawable"), "@mipmap/ic_luoshu_monochrome")
        background = ET.parse(resources / "drawable/ic_luoshu_background.xml").getroot()
        self.assertEqual(background.tag, "vector")
        self.assertEqual((background.get(ANDROID + "viewportWidth"), background.get(ANDROID + "viewportHeight")), ("108", "108"))
        for density, size in (("mdpi", 108), ("hdpi", 162), ("xhdpi", 216), ("xxhdpi", 324), ("xxxhdpi", 432)):
            folder = resources / f"mipmap-{density}"
            # A raster with the adaptive icon's name would shadow it on some launchers.
            self.assertFalse(list(folder.glob("ic_luoshu.*")), density)
            for layer in ("foreground", "monochrome"):
                data = (folder / f"ic_luoshu_{layer}.webp").read_bytes()
                self.assertEqual(data[12:16], b"VP8L", (density, layer))
                bits = int.from_bytes(data[21:25], "little")
                self.assertEqual(((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1), (size, size), (density, layer))

    def test_light_and_dark_launch_colors_resolve_with_legible_ink(self):
        def luminance(rgb):
            values = [int(rgb[index:index + 2], 16) / 255 for index in (1, 3, 5)]
            linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
                      for value in values]
            return sum(a * b for a, b in zip(linear, (.2126, .7152, .0722)))

        resources = MAIN / "res"
        light = {node.get("name"): node.text.strip()
                 for node in ET.parse(resources / "values/themes.xml").getroot().findall("color")}
        self.assertEqual(light["launch_background"].upper(), "#F6EFDD")
        self.assertEqual(light["launch_icon_background"].upper(), "#F6EFDD")
        for relative in ("values/themes.xml", "values-night/launch.xml"):
            colors = {node.get("name"): node.text.strip()
                      for node in ET.parse(resources / relative).getroot().findall("color")}
            for name in ("launch_background", "launch_ink"):
                self.assertRegex(colors[name], r"^#[0-9A-Fa-f]{6}$")
            first, second = sorted((luminance(colors["launch_ink"]), luminance(colors["launch_background"])))
            self.assertGreaterEqual((second + .05) / (first + .05), 4.5)
        night = {node.get("name"): node.text.strip()
                 for node in ET.parse(resources / "values-night/launch.xml").getroot().findall("color")}
        self.assertEqual(night["launch_background"].upper(), "#181A20")
        self.assertNotIn("launch_icon_background", night)
        bools = {node.get("name"): node.text.strip()
                 for folder, file in (("values", "themes.xml"),) for node in ET.parse(resources / folder / file).getroot().findall("bool")}
        night_bools = {node.get("name"): node.text.strip()
                       for node in ET.parse(resources / "values-night/launch.xml").getroot().findall("bool")}
        self.assertEqual((bools["launch_light_system_bars"], night_bools["launch_light_system_bars"]), ("true", "false"))

    def test_single_launcher_activity_and_platform_api_are_preserved(self):
        manifest = ET.parse(MAIN / "AndroidManifest.xml").getroot()
        application = manifest.find("application")
        launchers = [activity for activity in application.findall("activity")
                     if any(category.get(ANDROID + "name") == "android.intent.category.LAUNCHER"
                            for category in activity.findall("intent-filter/category"))]
        self.assertEqual(len(launchers), 1)
        self.assertEqual(launchers[0].get(ANDROID + "theme"), "@style/Theme.LuoShuLaunch")
        launch_sources = "\n".join(path.read_text() for path in (JAVA / "ui/launch").glob("*.kt"))
        self.assertNotRegex(launch_sources, r"getDeclared|Class\.forName|Xposed|LSPosed|setKeepOnScreenCondition")


if __name__ == "__main__":
    unittest.main()

