#!/usr/bin/env python3
"""Host-side guards for MIUIx material hierarchy and accessible layout.

These source checks complement, rather than replace, Android compilation and
device screenshot review. Opacity ranges allow visual tuning while preserving
the explicit translucent light/dark roles and bounded card rendering cost.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui"


def source(relative: str) -> str:
    return (UI / relative).read_text(encoding="utf-8")


def section(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


class GlassVisualHierarchyTest(unittest.TestCase):
    def test_host_reveals_window_without_duplicate_backdrop_layers(self):
        host = (UI.parent / "LuoShuHost.kt").read_text(encoding="utf-8")
        self.assertIn("Box(modifier = Modifier.fillMaxSize())", host)
        self.assertNotRegex(host, r"\.background\(|drawBehind|drawWithCache|RuntimeShader|RenderEffect")
        self.assertNotRegex(host, r"AppBackdrop\(|LuoShuGlassBackdropDrawable\(")
        self.assertIn(".windowInsetsPadding(contentInsets)", host)
        self.assertIn(".consumeWindowInsets(contentInsets)", host)
        self.assertIn("LuoShuAppShell(model, features, appearanceViewModel)", host)
        # The shell's backdrop must remain inside the existing capture region;
        # making the Host clear must not sacrifice the floating dock's sample.
        shell = (UI.parent / "LuoShuAppShell.kt").read_text(encoding="utf-8")
        capture = section(shell, "val contentModifier =", "// Only the destination page")
        self.assertIn("Modifier.hazeSource(state = hazeState)", capture)
        self.assertIn("Modifier.layerBackdrop(liquidBackdrop)", capture)
        self.assertIn("Box(modifier = contentModifier)", capture)
        self.assertIn("AppBackdrop(appearance, dark)", capture)
        backdrop = section(shell, "private fun AppBackdrop(", "private fun MiuixAppDock(")
        self.assertIn("if (appearance.glassEnabled)", backdrop)
        self.assertIn(".background(LocalMiuixTokens.current.pageBackground)", backdrop)

    def test_card_material_retains_light_dark_translucency(self):
        theme = source("theme/LuoShuTheme.kt")
        card = section(theme, "cardBackground = when {", "elevatedCardBackground =")
        for role in (r"glass && dark -> darkFill", r"glass -> lightFill"):
            match = re.search(role + r"\.copy\(alpha = ([.\d]+)f\)", card)
            self.assertIsNotNone(match, f"Missing translucent material role: {role}")
            self.assertGreaterEqual(float(match.group(1)), .76)
            self.assertLessEqual(float(match.group(1)), .90)
        self.assertIn("dark -> darkFill", card)
        self.assertIn("else -> lightFill", card)
        self.assertIn("LocalContentColor provides tokens.textPrimary", theme)
        self.assertIn("textPrimary = scheme.onSurface", theme)
        self.assertIn("textSecondary = scheme.onSurfaceVariant", theme)

    def test_inset_material_is_separate_and_bounded(self):
        theme = source("theme/LuoShuTheme.kt")
        inset = section(theme, "insetBackground = when {", "insetOutline =")
        self.assertIn("glass && dark ->", inset)
        self.assertIn("glass ->", inset)
        self.assertIn("dark ->", inset)
        self.assertIn("else ->", inset)
        match = re.search(r"cardShadowElevation = if \(glass\) ([.\d]+)\.dp else 0\.dp", theme)
        self.assertIsNotNone(match)
        self.assertGreater(float(match.group(1)), 0)
        self.assertLessEqual(float(match.group(1)), 1.25)
        surfaces = source("theme/LuoShuSurfaces.kt")
        panel = section(surfaces, "internal fun LuoShuInsetPanel(", "/** A shared translucent")
        self.assertIn("color = tokens.insetBackground", panel)
        self.assertIn("contentColor = tokens.textPrimary", panel)
        self.assertIn("border = BorderStroke(1.dp, tokens.insetOutline)", panel)
        self.assertIn("tonalElevation = 0.dp", panel)
        self.assertIn("shadowElevation = 0.dp", panel)
        for relative in ("theme/LuoShuSurfaces.kt", "home/HomeScreenMiuix.kt",
                         "library/FontLibraryScreenMiuix.kt", "studio/FontStudioScreenMiuix.kt"):
            with self.subTest(relative=relative):
                text = source(relative)
                self.assertNotRegex(text, r"RuntimeShader|RenderEffect|rememberInfiniteTransition|hazeEffect")

    def test_home_retains_state_action_and_preview_hierarchy(self):
        home = source("home/HomeScreenMiuix.kt")
        hero = section(home, 'item(key = "current-font")', 'if (state.taskRunning')
        self.assertEqual(hero.count("Button("), 1)
        self.assertIn("onClick = next.onClick", hero)
        self.assertIn("enabled = next.enabled", hero)
        self.assertIn("LuoShuInsetPanel {", hero)
        self.assertIn("Text(state.currentFont", hero)
        self.assertIn("字里行间，自有风格。", hero)
        self.assertIn("maxLines = 2, overflow = TextOverflow.Ellipsis", hero)
        for key in ("task-status", "font-actions", "device-details", "restore"):
            self.assertIn(f'item(key = "{key}")', home)

    def test_library_compact_filter_retains_touch_and_selection(self):
        library = source("library/FontLibraryScreenMiuix.kt")
        choice = section(library, "private fun ChoicePill(", "private fun NoticeCard(")
        self.assertIn("defaultMinSize(minHeight = 48.dp)", choice)
        self.assertIn("heightIn(min = 40.dp)", choice)
        self.assertIn("selected = active, role = Role.Tab, onClick = onClick", choice)
        self.assertIn("if (active) Icon(Icons.Rounded.Check", choice)
        self.assertIn("scheme.onPrimary", choice)
        self.assertIn("LocalMiuixTokens.current.textPrimary", choice)
        self.assertIn("rememberLazyListState()", library)
        self.assertIn("contentType = { \"font\" }", library)
        self.assertIn("else LocalMiuixTokens.current.insetOutline", library)

    def test_studio_summaries_and_settings_inset_preserve_state(self):
        studio = source("studio/FontStudioScreenMiuix.kt")
        self.assertIn("height(IntrinsicSize.Min)", studio)
        summary = section(studio, "private fun MiuixSlotSummary(", "private fun MiuixStudioTask(")
        self.assertIn("modifier = modifier.fillMaxHeight()", summary)
        self.assertIn("onClick = onSelect", summary)
        self.assertIn("enabled = enabled", summary)
        self.assertIn("if (slot.font != null)", summary)
        self.assertIn('slot.font?.name ?: "未选择"', summary)
        self.assertIn("overflow = TextOverflow.Ellipsis", summary)
        settings = source("settings/SettingsHubScreen.kt")
        overview = section(settings, "private fun SettingsOverviewCard(", "private fun SettingsGroup(")
        self.assertIn("LuoShuInsetPanel {", overview)
        self.assertIn("if (health.rebootRequired)", overview)
        self.assertIn("color = accent", overview)
        self.assertIn("onClick = onClick", overview)


if __name__ == "__main__":
    unittest.main(verbosity=2)
