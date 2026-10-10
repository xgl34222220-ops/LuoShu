#!/usr/bin/env python3
"""Guard platform-owned launch wiring/resources; raw frames verify visible ordering."""

from pathlib import Path
import importlib.util
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
        self.assertEqual(self.activity.count("if (openTaskCenter) TaskCenterHost() else LuoShuHost("), 1)
        self.assertEqual(self.activity.count("firstFrameCommitted = firstFrameCommitted,"), 1)
        self.assertIn("private val appContent: @Composable () -> Unit", self.activity)
        self.assertNotIn("postDelayed", handoff)
        self.assertIn("nativeShellPolicy?.dispose()", method(self.activity, "override fun onDestroy("))
        self.assertIn("removeNativeShellObservers()", method(self.activity, "override fun onDestroy("))

    def test_native_shell_is_the_static_first_frame_of_the_shared_launch_artwork(self):
        shell = (JAVA / "ui/launch/LuoShuNativeShellView.kt").read_text()
        self.assertIn("LuoShuLaunchArtwork.obtain(context)", shell)
        self.assertIn("LuoShuLaunchShellTimeline.first(textVisible = true)", shell)
        self.assertIn("artwork.draw(canvas, width, height, firstFrame)", method(shell, "override fun onDraw("))
        for forbidden in ("ic_luoshu_launch", "luoshu_splash_orb", "LuoShuGlassBackdropDrawable", "animate",
                          "postDelayed", "postOnAnimation", "ValueAnimator", "invalidate()", "正在准备界面"):
            self.assertNotIn(forbidden, shell)
        artwork = (JAVA / "ui/launch/LuoShuLaunchArtwork.kt").read_text()
        for text in ('TITLE = "洛书"', 'SUBTITLE = "LuoShu · 字体管理"'):
            self.assertIn(text, artwork)
        install = method(self.controller, "fun install(")
        self.assertIn("if (nativeShell)", install)
        self.assertIn("ColorDrawable(activity.getColor(", install)

    def test_launch_shell_is_a_cold_only_overlay_that_never_gates_readiness(self):
        create = method(self.activity, "override fun onCreate(")
        self.assertIn("launchShellVisible = savedInstanceState == null && !openTaskCenter", create)
        self.assertIn("launchShellTextVisible = useNativeShell", create)
        self.assertLess(create.index("launchShellVisible ="), create.index("launchController.install("))
        self.assertIn("launchShellVisible = false", method(self.activity, "override fun onNewIntent("))
        for body in ("private fun deliverFirstFrame(", "private fun requestImportNotificationPermissionWhenReady(",
                     "private fun observeFirstDraw(", "private fun scheduleNativeShellHandoff("):
            self.assertNotIn("launchShell", method(self.activity, body))
        host = (JAVA / "LuoShuHost.kt").read_text()
        self.assertIn("if (launchShellVisible) Modifier.clearAndSetSemantics {} else Modifier", host)
        # The home is composed below, in the same frame; the shell is drawn after (above) it.
        self.assertLess(host.index("LuoShuAppShell(model, features, appearanceViewModel, firstFrameCommitted)"),
                        host.index("LuoShuLaunchShell("))
        self.assertIn("contentReady = firstFrameCommitted", host)
        shell = (JAVA / "ui/launch/LuoShuLaunchShell.kt").read_text()
        self.assertIn("Settings.Global.ANIMATOR_DURATION_SCALE", shell)
        self.assertIn("LaunchedEffect(contentReady) { if (contentReady) finish() }", shell)
        self.assertIn("LuoShuLaunchArtwork.release()", shell)
        self.assertNotRegex(shell, r"delay\(|postDelayed|Thread\.sleep|setKeepOnScreenCondition")
        timeline = (JAVA / "ui/launch/LuoShuLaunchShellTimeline.kt").read_text()
        total = float(re.search(r"const val TOTAL_MS = ([0-9.]+)f", timeline).group(1))
        exit_start = float(re.search(r"const val EXIT_START_MS = ([0-9.]+)f", timeline).group(1))
        self.assertLessEqual(total, 1500)
        self.assertLess(exit_start, total)
        self.assertIn("fun first(textVisible: Boolean) = frameAt(0f, textVisible)", timeline)

    def test_kotlin_artwork_geometry_matches_the_asset_generator(self):
        artwork = (JAVA / "ui/launch/LuoShuLaunchArtwork.kt").read_text()
        generator = (ROOT / "design/launch/build_launch_assets.py").read_text()
        for kotlin, python in (("CARD_DP", "CARD_DP"), ("CARD_CANVAS_DP", "CARD_CANVAS_DP"),
                               ("CARD_START_SCALE", "CARD_START_SCALE"), ("SQUIRCLE_N", "SQUIRCLE_N")):
            kotlin_value = float(re.search(rf"const val {kotlin} = ([0-9.]+)f?", artwork).group(1))
            python_value = float(re.search(rf"^{python} = ([0-9.]+)", generator, re.MULTILINE).group(1))
            self.assertAlmostEqual(kotlin_value, python_value, places=4, msg=kotlin)
        window = ET.parse(MAIN / "res/drawable/luoshu_launch_window.xml").getroot()
        card = window.findall("item")[-1]
        self.assertEqual(card.get(ANDROID + "width"), f"{round(288 * .955)}dp")
        self.assertEqual(card.get(ANDROID + "height"), f"{round(288 * .955)}dp")
        self.assertEqual(card.get(ANDROID + "gravity"), "center")

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

    def test_legacy_starting_window_is_the_diffuse_launch_shell_without_text(self):
        resources = MAIN / "res"
        self.assertEqual(style_items(resources / "values/themes.xml", "Theme.LuoShuHybrid")["android:windowBackground"],
                         "@drawable/luoshu_launch_background")
        self.assertEqual(style_items(resources / "values/themes.xml", "Theme.LuoShuLaunch")["android:windowBackground"],
                         "@drawable/luoshu_launch_window")
        root = ET.parse(resources / "drawable/luoshu_launch_window.xml").getroot()
        self.assertEqual(root.tag, "layer-list")
        bitmaps = [item.find("bitmap") for item in root.findall("item")]
        self.assertEqual([bitmap.get(ANDROID + "src") for bitmap in bitmaps],
                         ["@drawable/luoshu_launch_backdrop", "@drawable/luoshu_launch_grain", "@drawable/luoshu_launch_card"])
        self.assertEqual(bitmaps[0].get(ANDROID + "gravity"), "fill")
        self.assertEqual(bitmaps[1].get(ANDROID + "tileMode"), "repeat")
        # The real App page keeps its own unbranded gradient (TaskCenter, rotation, recreation).
        shape = ET.parse(resources / "drawable/luoshu_launch_background.xml").getroot()
        self.assertEqual(shape.tag, "shape")
        gradient = shape.find("gradient")
        for stop in ("startColor", "centerColor", "endColor"):
            self.assertTrue(gradient.attrib[ANDROID + stop].startswith("@color/launch_gradient_"))

    def test_launch_bitmaps_exist_for_both_themes(self):
        for folder in ("drawable-nodpi", "drawable-night-nodpi"):
            for name in ("luoshu_launch_backdrop.webp", "luoshu_launch_backdrop_blur.webp", "luoshu_launch_card.webp",
                         "luoshu_launch_grain.png", "luoshu_splash_orb.webp"):
                path = MAIN / "res" / folder / name
                self.assertTrue(path.is_file(), path)
                self.assertLess(path.stat().st_size, 200_000, path)
        # The launcher icon is not part of the launch redesign.
        self.assertTrue((MAIN / "res/mipmap-xxxhdpi/ic_luoshu.webp").is_file())
        manifest = (MAIN / "AndroidManifest.xml").read_text()
        self.assertIn('android:icon="@mipmap/ic_luoshu"', manifest)

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "Pillow is required to inspect launch bitmaps")
    def test_splash_color_matches_backdrop_centre_and_orb_edge(self):
        from PIL import Image
        for folder, colors_file in (("drawable-nodpi", "values/themes.xml"), ("drawable-night-nodpi", "values-night/launch.xml")):
            colors = {node.get("name"): node.text.strip()
                      for node in ET.parse(MAIN / "res" / colors_file).getroot().findall("color")}
            splash = tuple(int(colors["launch_background"][i:i + 2], 16) for i in (1, 3, 5))
            with Image.open(MAIN / "res" / folder / "luoshu_launch_backdrop.webp") as image:
                rgb = image.convert("RGB")
                width, height = rgb.size
                centre = rgb.crop((width * 30 // 108, height * 96 // 240, width * 78 // 108, height * 144 // 240))
                mean = centre.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
            self.assertLessEqual(max(abs(a - b) for a, b in zip(mean, splash)), 3, folder)
            with Image.open(MAIN / "res" / folder / "luoshu_splash_orb.webp") as orb:
                self.assertEqual((720, 720), orb.size)
                orb = orb.convert("RGB")
                # Outside the 92dp orb but inside the platform's 96dp circle: the splash colour.
                ring = orb.getpixel((360, 360 - round(94.5 * 2.5)))
                self.assertLessEqual(max(abs(a - b) for a, b in zip(ring, splash)), 6, folder)

    def test_android_twelve_keeps_a_supported_single_opaque_system_splash(self):
        items = style_items(MAIN / "res/values-v31/launch.xml", "Theme.LuoShuLaunch")
        self.assertEqual(items["android:windowSplashScreenBackground"], "@color/launch_background")
        self.assertEqual(items["android:windowBackground"], "@color/launch_background")
        self.assertEqual(items["android:windowSplashScreenAnimatedIcon"], "@drawable/ic_luoshu_launch")
        self.assertNotIn("android:windowSplashScreenBrandingImage", items)
        self.assertNotIn("android:windowSplashScreenIconBackgroundColor", items)

    def test_splash_icon_is_one_static_orb_on_the_platform_icon_canvas(self):
        icon = ET.parse(MAIN / "res/drawable/ic_luoshu_launch.xml").getroot()
        self.assertEqual(icon.tag, "layer-list")
        items = icon.findall("item")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].get(ANDROID + "drawable"), "@drawable/luoshu_splash_orb")
        self.assertEqual(items[0].get(ANDROID + "width"), "288dp")
        self.assertEqual(items[0].get(ANDROID + "height"), "288dp")
        self.assertIsNone(icon.find(".//animated-vector"))

    def test_light_and_dark_launch_colors_resolve_with_legible_wordmark(self):
        def luminance(rgb):
            values = [int(rgb[index:index + 2], 16) / 255 for index in (1, 3, 5)]
            linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
                      for value in values]
            return sum(a * b for a, b in zip(linear, (.2126, .7152, .0722)))

        def contrast(first, second):
            low, high = sorted((luminance(first), luminance(second)))
            return (high + .05) / (low + .05)

        resources = MAIN / "res"
        for relative in ("values/themes.xml", "values-night/launch.xml"):
            colors = {node.get("name"): node.text.strip()
                      for node in ET.parse(resources / relative).getroot().findall("color")}
            for name in ("launch_background", "launch_ink", "launch_ink_secondary",
                         "launch_gradient_start", "launch_gradient_center", "launch_gradient_end"):
                self.assertRegex(colors[name], r"^#[0-9A-Fa-f]{6}$")
            self.assertGreaterEqual(contrast(colors["launch_ink"], colors["launch_background"]), 7)
            self.assertGreaterEqual(contrast(colors["launch_ink_secondary"], colors["launch_background"]), 4.5)

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

