from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    file = ROOT / path
    text = file.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one occurrence, found {count}: {old[:80]!r}")
    file.write_text(text.replace(old, new, 1))


# Task-center header actions use identical dimensions.
replace_once(
    "android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/DiagnosticExportUi.kt",
    "modifier = modifier.size(if (style == UiStyle.MIUIX) 56.dp else 52.dp),\n        shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 18.dp else 17.dp),",
    "modifier = modifier.size(50.dp),\n        shape = RoundedCornerShape(17.dp),",
)

# The studio keeps only one in-flow final action and moves the tools beside refresh.
route_path = ROOT / "android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/FontStudioRoute.kt"
route = route_path.read_text()
old_layout = re.compile(
    r"    Box\(Modifier\.fillMaxSize\(\)\) \{.*?\n    \}\n\n    if \(showCompositePreview\)",
    re.S,
)
new_layout = '''    Box(Modifier.fillMaxSize()) {
        when (style) {
            UiStyle.MATERIAL -> FontStudioScreenMaterial(state, stableActions)
            UiStyle.MIUIX -> FontStudioScreenMiuix(state, stableActions)
        }

        StudioToolLauncher(
            style = style,
            enabled = state.hasFonts && !state.loading,
            onPreview = { showCompositePreview = true },
            onProfile = { showProfileTransfer = true },
            onGlyphs = { showGlyphBrowser = true },
            modifier = Modifier
                .align(Alignment.TopEnd)
                .statusBarsPadding()
                .padding(end = 82.dp, top = 12.dp),
        )
    }

    if (showCompositePreview)'''
route, count = old_layout.subn(new_layout, route, count=1)
if count != 1:
    raise SystemExit("FontStudioRoute.kt: failed to replace overlay layout")
if "import androidx.compose.foundation.layout.statusBarsPadding" not in route:
    route = route.replace(
        "import androidx.compose.foundation.layout.padding\n",
        "import androidx.compose.foundation.layout.padding\nimport androidx.compose.foundation.layout.statusBarsPadding\n",
        1,
    )
# Imports used only by the removed floating CTA.
for line in (
    "import androidx.compose.foundation.layout.Row\n",
    "import androidx.compose.foundation.layout.Spacer\n",
    "import androidx.compose.foundation.layout.fillMaxWidth\n",
    "import androidx.compose.foundation.layout.height\n",
    "import androidx.compose.foundation.layout.navigationBarsPadding\n",
    "import androidx.compose.foundation.layout.width\n",
    "import androidx.compose.material3.Button\n",
    "import androidx.compose.material3.CircularProgressIndicator\n",
    "import androidx.compose.material3.MaterialTheme\n",
    "import androidx.compose.material3.Surface\n",
):
    route = route.replace(line, "")
route_path.write_text(route)

# Font importing belongs to the library. Remove the Studio-only floating import control.
shell_path = ROOT / "android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuAppShell.kt"
shell = shell_path.read_text()
native_overlay = re.compile(
    r"\n            if \(page == AppPage\.Studio\) \{\n                NativeImportOverlay\(.*?\n                \)\n            \}\n",
    re.S,
)
shell, count = native_overlay.subn("\n", shell, count=1)
if count != 1:
    raise SystemExit("LuoShuAppShell.kt: failed to remove Studio NativeImportOverlay")

# Replace the opaque white selected block with a Monet-tinted transparent capsule.
old_indicator = '''        indicatorColor = if (activeGlass) {
            Color.White.copy(alpha = if (dark) .12f else .34f)
        } else {
            scheme.primary.copy(alpha = if (dark) .20f else .12f)
        },
        indicatorBorderColor = if (activeGlass) {
            Color.White.copy(alpha = if (dark) .24f else .72f)
        } else {
            Color.Transparent
        },
        indicatorShadow = if (activeGlass) 6.dp else 0.dp,'''
new_indicator = '''        indicatorColor = scheme.primary.copy(
            alpha = if (activeGlass) {
                if (dark) .18f else .12f
            } else {
                if (dark) .20f else .12f
            },
        ),
        indicatorBorderColor = if (activeGlass) {
            scheme.primary.copy(alpha = if (dark) .30f else .20f)
        } else {
            Color.Transparent
        },
        indicatorShadow = 0.dp,'''
if shell.count(old_indicator) != 1:
    raise SystemExit("LuoShuAppShell.kt: selected indicator block not found")
shell_path.write_text(shell.replace(old_indicator, new_indicator, 1))

# Regression checks for the exact screenshot failures.
test_path = ROOT / "scripts/font_library_ui_layout_test.sh"
test = test_path.read_text()
old = "grep -q 'if (page == AppPage.Studio)' \"$SHELL\"\n"
new = '''! grep -q 'if (page == AppPage.Studio)' "$SHELL"
printf '%s\\n' "$MIUIX_DOCK" | grep -q 'indicatorShadow = 0.dp'
printf '%s\\n' "$MIUIX_DOCK" | grep -q 'scheme.primary.copy(alpha = if (dark) .30f else .20f)'
grep -q 'align(Alignment.TopEnd)' "$STUDIO_ROUTE"
grep -q 'statusBarsPadding()' "$STUDIO_ROUTE"
! grep -q 'align(Alignment.BottomStart)' "$STUDIO_ROUTE"
! grep -q 'padding(start = 16.dp, end = 16.dp, bottom = 94.dp)' "$STUDIO_ROUTE"
grep -q 'modifier = modifier.size(50.dp)' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/DiagnosticExportUi.kt"
'''
if old not in test:
    raise SystemExit("font_library_ui_layout_test.sh: old Studio overlay assertion not found")
test_path.write_text(test.replace(old, new, 1))
