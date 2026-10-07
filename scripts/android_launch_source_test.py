#!/usr/bin/env python3
"""Guard single-stage launch wiring/resources; runtime exit ordering lives in Kotlin tests."""

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
        self.assertLess(create.index("launchController.install("), create.index("setContent {"))
        install = method(self.controller, "fun install(")
        self.assertIn("applyAppearance(dark, pureBlack = false)", install)
        appearance = method(self.controller, "fun applyAppearance(")
        self.assertIn("window.setBackgroundDrawable(LuoShuGlassBackdropDrawable(dark, pureBlack))", appearance)

    def test_native_view_is_removed_synchronously_for_every_entry_path(self):
        install = method(self.controller, "fun install(")
        self.assertIn("installPlatformExit()", install)
        self.assertNotRegex(install, r"savedInstanceState|openTaskCenter|areAnimatorsEnabled")
        callback = method(self.controller, "setOnExitAnimationListener")
        self.assertEqual(callback.count("splash.remove()"), 1)
        self.assertNotRegex(callback, r"return@|post\(|postDelayed|animate\(|setDuration|isComplete|disposed")
        self.assertIn('event("native_removed")', callback)

    def test_lifecycle_and_task_entry_cannot_replay_or_retain_the_launch(self):
        self.assertIn('fun stop() = complete("stop")', self.controller)
        self.assertIn('fun finishForTaskEntry() = complete("task_entry")', self.controller)
        self.assertIn("launchController.stop()", method(self.activity, "override fun onStop("))
        self.assertIn("launchController.finishForTaskEntry()", method(self.activity, "override fun onNewIntent("))
        destroy = method(self.controller, "fun dispose(")
        self.assertIn("onComplete = null", destroy)
        self.assertIn("clearPlatformExit()", destroy)
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

    def test_legacy_starting_window_and_real_theme_share_an_unbranded_gradient(self):
        resources = MAIN / "res"
        for theme in ("Theme.LuoShuHybrid", "Theme.LuoShuLaunch"):
            self.assertEqual(style_items(resources / "values/themes.xml", theme)["android:windowBackground"],
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

    def test_android_twelve_keeps_a_supported_single_opaque_system_splash(self):
        items = style_items(MAIN / "res/values-v31/launch.xml", "Theme.LuoShuLaunch")
        self.assertEqual(items["android:windowSplashScreenBackground"], "@color/launch_background")
        self.assertEqual(items["android:windowBackground"], "@color/launch_background")
        self.assertEqual(items["android:windowSplashScreenAnimatedIcon"], "@drawable/ic_luoshu_launch")
        self.assertNotIn("android:windowSplashScreenBrandingImage", items)

    def test_native_glass_emblem_uses_two_static_native_gradients(self):
        icon = ET.parse(MAIN / "res/drawable/ic_luoshu_launch.xml").getroot()
        self.assertEqual(icon.tag, "vector")
        for key, value in (("width", "288dp"), ("height", "288dp"),
                           ("viewportWidth", "108"), ("viewportHeight", "108")):
            self.assertEqual(icon.get(ANDROID + key), value)
        fills = icon.findall(".//" + AAPT + "attr")
        self.assertEqual(len(fills), 2)
        for fill in fills:
            self.assertEqual(fill.get("name"), "android:fillColor")
            gradient = fill.find("gradient")
            self.assertEqual(gradient.get(ANDROID + "type"), "linear")
            stops = gradient.findall("item")
            self.assertEqual([stop.get(ANDROID + "offset") for stop in stops], ["0", "0.48", "1"])
            self.assertEqual([stop.get(ANDROID + "color") for stop in stops],
                             ["@color/launch_glass_top", "@color/launch_glass_center", "@color/launch_glass_bottom"])
        self.assertIsNone(icon.find(".//animated-vector"))
        self.assertIsNone(icon.find(".//bitmap"))

    def test_glass_lens_fits_platform_safe_circle_without_enlarging_the_brand(self):
        icon = ET.parse(MAIN / "res/drawable/ic_luoshu_launch.xml").getroot()
        paths = {node.get(ANDROID + "name"): node for node in icon.findall(".//path")}
        # 288dp canvas / 108 viewport: a 35-unit radius is 186.7dp across,
        # inside the platform's 192dp safe circle. Rim adds only 0.375 units.
        self.assertEqual(paths["diffuse_lens"].get(ANDROID + "pathData"),
                         "M54,19a35,35 0,1 0,0 70a35,35 0,1 0,0 -70")
        self.assertEqual(paths["glass_lens_rim"].get(ANDROID + "strokeWidth"), "0.75")
        self.assertLessEqual(35 * 2 * 288 / 108, 192)
        group = icon.find("group")
        self.assertEqual(group.get(ANDROID + "scaleX"), "0.8")
        self.assertEqual(group.get(ANDROID + "scaleY"), "0.8")
        self.assertLessEqual(float(paths["glass_lens_rim"].get(ANDROID + "strokeAlpha")), .25)
        self.assertLessEqual(float(paths["diffuse_lens"].get(ANDROID + "fillAlpha")), .24)
        self.assertLessEqual(float(paths["glass_core_highlight"].get(ANDROID + "strokeAlpha")), .10)

    def test_light_and_dark_native_glass_colors_resolve_with_legible_gold(self):
        def luminance(rgb):
            values = [int(rgb[index:index + 2], 16) / 255 for index in (1, 3, 5)]
            linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
                      for value in values]
            return sum(a * b for a, b in zip(linear, (.2126, .7152, .0722)))

        resources = MAIN / "res"
        for relative in ("values/themes.xml", "values-night/launch.xml"):
            colors = {node.get("name"): node.text.strip()
                      for node in ET.parse(resources / relative).getroot().findall("color")}
            for name in ("launch_background", "launch_ink", "launch_gold", "launch_glass_top",
                         "launch_glass_center", "launch_glass_bottom", "launch_glass_edge", "launch_glass_shadow"):
                self.assertRegex(colors[name], r"^#[0-9A-Fa-f]{6}$")
            first, second = sorted((luminance(colors["launch_gold"]), luminance(colors["launch_background"])))
            self.assertGreaterEqual((second + .05) / (first + .05), 3)

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
