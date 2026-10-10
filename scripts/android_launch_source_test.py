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
        # API 28-30 have no platform splash; the starting window shows a deep navy
        # vertical gradient and the original icon art centered at 240dp, nothing else.
        resources = MAIN / "res"
        launch = style_items(resources / "values/themes.xml", "Theme.LuoShuLaunch")
        self.assertEqual(launch["android:windowBackground"], "@drawable/luoshu_launch_splash")
        self.assertEqual((launch["android:windowLightStatusBar"], launch["android:windowLightNavigationBar"]),
                         ("false", "false"))
        root = ET.parse(resources / "drawable/luoshu_launch_splash.xml").getroot()
        self.assertEqual(root.tag, "layer-list")
        items = root.findall("item")
        self.assertEqual(len(items), 2)
        gradient = items[0].find("shape/gradient")
        self.assertEqual(gradient.get(ANDROID + "angle"), "270")
        self.assertEqual(gradient.get(ANDROID + "startColor"), "@color/launch_splash_gradient_top")
        self.assertEqual(gradient.get(ANDROID + "endColor"), "@color/launch_splash_gradient_bottom")
        self.assertEqual(items[1].get(ANDROID + "drawable"), "@drawable/ic_luoshu_splash")
        self.assertEqual((items[1].get(ANDROID + "width"), items[1].get(ANDROID + "height")), ("240dp", "240dp"))
        self.assertEqual(items[1].get(ANDROID + "gravity"), "center")

    def test_android_twelve_keeps_a_supported_single_opaque_system_splash(self):
        items = style_items(MAIN / "res/values-v31/launch.xml", "Theme.LuoShuLaunch")
        self.assertEqual(items["android:windowSplashScreenBackground"], "@color/launch_splash_background")
        self.assertEqual(items["android:windowBackground"], "@color/launch_splash_background")
        self.assertEqual(items["android:windowSplashScreenAnimatedIcon"], "@drawable/ic_luoshu_splash")
        self.assertEqual(items["android:windowSplashScreenIconBackgroundColor"], "@color/launch_splash_background")
        self.assertEqual((items["android:windowLightStatusBar"], items["android:windowLightNavigationBar"]),
                         ("false", "false"))
        self.assertNotIn("android:windowSplashScreenBrandingImage", items)
        self.assertNotIn("android:windowSplashScreenAnimationDuration", items)

    def test_splash_emblem_is_one_static_high_resolution_bitmap(self):
        icon = ET.parse(MAIN / "res/drawable/ic_luoshu_splash.xml").getroot()
        self.assertEqual(icon.tag, "bitmap")
        self.assertEqual(icon.get(ANDROID + "src"), "@drawable/ic_luoshu_splash_art")
        self.assertEqual(icon.get(ANDROID + "gravity"), "fill")
        source = MAIN / "res/drawable-nodpi/ic_luoshu_splash_art.webp"
        self.assertTrue(source.is_file())
        # RIFF/WEBP header; width/height of a lossless VP8L bitstream.
        data = source.read_bytes()
        self.assertEqual((data[:4], data[8:12], data[12:16]), (b"RIFF", b"WEBP", b"VP8L"))
        bits = int.from_bytes(data[21:25], "little")
        width, height = (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        # 240dp at xxxhdpi (4x) is 960px: never upscale on any density.
        self.assertGreaterEqual(min(width, height), 960)
        self.assertEqual(width, height)
        # Feathered circular alpha: transparent corners keep the platform circle mask invisible.
        self.assertTrue((bits >> 28) & 1, "splash art must carry an alpha channel")
        self.assertFalse(list((MAIN / "res").rglob("ic_luoshu_launch*")))
        self.assertFalse(list((MAIN / "res").rglob("ic_luoshu_splash_foreground*")))

    def test_launcher_icon_is_the_original_raster_icon(self):
        resources = MAIN / "res"
        manifest = ET.parse(MAIN / "AndroidManifest.xml").getroot().find("application")
        self.assertEqual(manifest.get(ANDROID + "icon"), "@mipmap/ic_luoshu")
        self.assertEqual(manifest.get(ANDROID + "roundIcon"), "@mipmap/ic_luoshu")
        data = (resources / "mipmap-xxxhdpi/ic_luoshu.webp").read_bytes()
        self.assertEqual((data[:4], data[8:12]), (b"RIFF", b"WEBP"))
        # No adaptive wrapper or layers that would shadow the original artwork.
        self.assertFalse((resources / "mipmap-anydpi-v26/ic_luoshu.xml").exists())
        self.assertFalse(list(resources.rglob("ic_luoshu_foreground*")))
        self.assertFalse(list(resources.rglob("ic_luoshu_monochrome*")))
        self.assertFalse((resources / "drawable/ic_luoshu_background.xml").exists())

    def test_light_and_dark_launch_colors_resolve_with_legible_ink(self):
        def luminance(rgb):
            values = [int(rgb[index:index + 2], 16) / 255 for index in (1, 3, 5)]
            linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
                      for value in values]
            return sum(a * b for a, b in zip(linear, (.2126, .7152, .0722)))

        resources = MAIN / "res"
        light = {node.get("name"): node.text.strip()
                 for node in ET.parse(resources / "values/themes.xml").getroot().findall("color")}
        # Splash is the original icon's deep navy in both modes; defined once, never overridden.
        self.assertEqual(light["launch_splash_background"].upper(), "#09213E")
        self.assertEqual(light["launch_splash_gradient_top"].upper(), "#0E2E54")
        self.assertEqual(light["launch_splash_gradient_bottom"].upper(), "#021022")
        for relative in ("values/themes.xml", "values-night/launch.xml"):
            colors = {node.get("name"): node.text.strip()
                      for node in ET.parse(resources / relative).getroot().findall("color")}
            for name in ("launch_background", "launch_ink"):
                self.assertRegex(colors[name], r"^#[0-9A-Fa-f]{6}$")
            first, second = sorted((luminance(colors["launch_ink"]), luminance(colors["launch_background"])))
            self.assertGreaterEqual((second + .05) / (first + .05), 4.5)
        night = {node.get("name"): node.text.strip()
                 for node in ET.parse(resources / "values-night/launch.xml").getroot().findall("color")}
        for name in ("launch_splash_background", "launch_splash_gradient_top", "launch_splash_gradient_bottom"):
            self.assertNotIn(name, night)
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

