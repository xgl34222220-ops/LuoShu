#!/usr/bin/env python3
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
shell_path = root / "android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuAppShell.kt"
settings_path = root / "android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/settings/AppearanceSettingsScreen.kt"
test_path = root / "scripts/font_library_ui_layout_test.sh"

shell = shell_path.read_text(encoding="utf-8")

shell = shell.replace(
    "import androidx.compose.ui.geometry.Offset\nimport androidx.compose.ui.graphics.Brush\n",
    "import androidx.compose.ui.geometry.CornerRadius\nimport androidx.compose.ui.geometry.Offset\nimport androidx.compose.ui.graphics.Brush\nimport androidx.compose.ui.graphics.drawscope.Stroke\n",
)

backdrop = '''@Composable
private fun AppBackdrop(appearance: AppearanceSettings, dark: Boolean) {
    val scheme = MaterialTheme.colorScheme
    val miuix = appearance.uiStyle == UiStyle.MIUIX
    val base = when {
        miuix -> listOf(LocalMiuixTokens.current.pageBackground, LocalMiuixTokens.current.pageBackground)
        dark -> listOf(scheme.background, scheme.surfaceContainerLow, scheme.background)
        else -> listOf(scheme.background, scheme.surfaceContainerLowest, scheme.background)
    }
    Box(
        Modifier
            .fillMaxSize()
            .background(Brush.verticalGradient(base))
            .drawBehind {
                if (miuix) {
                    // A subtle accent field behind the floating dock gives Haze real pixels to
                    // sample instead of blurring a perfectly flat page background.
                    drawRect(
                        Brush.radialGradient(
                            listOf(
                                scheme.primary.copy(alpha = if (dark) .13f else .11f),
                                scheme.secondary.copy(alpha = if (dark) .06f else .05f),
                                Color.Transparent,
                            ),
                            center = Offset(size.width * .52f, size.height * 1.03f),
                            radius = size.width * .88f,
                        ),
                    )
                    drawRect(
                        Brush.radialGradient(
                            listOf(scheme.primary.copy(alpha = if (dark) .055f else .045f), Color.Transparent),
                            center = Offset(size.width * .92f, size.height * .08f),
                            radius = size.width * .58f,
                        ),
                    )
                } else {
                    drawRect(
                        Brush.radialGradient(
                            listOf(scheme.secondary.copy(alpha = if (dark) .13f else .20f), Color.Transparent),
                            center = Offset(size.width * .9f, size.height * .06f),
                            radius = size.width * .72f,
                        ),
                    )
                    drawRect(
                        Brush.radialGradient(
                            listOf(scheme.primary.copy(alpha = if (dark) .10f else .16f), Color.Transparent),
                            center = Offset(size.width * .02f, size.height * .54f),
                            radius = size.width * .82f,
                        ),
                    )
                }
            },
    )
}
'''

shell, count = re.subn(
    r'@Composable\nprivate fun AppBackdrop\(appearance: AppearanceSettings, dark: Boolean\) \{.*?\n\}\n\n(?=@OptIn\(ExperimentalHazeMaterialsApi::class\)\n@Composable\nprivate fun MaterialAppDock)',
    backdrop + "\n",
    shell,
    flags=re.S,
)
if count != 1:
    raise SystemExit(f"AppBackdrop replacement count={count}")

miuix_dock = '''@OptIn(ExperimentalHazeMaterialsApi::class)
@Composable
private fun MiuixAppDock(
    current: AppPage,
    onSelect: (AppPage) -> Unit,
    appearance: AppearanceSettings,
    hazeState: HazeState,
    modifier: Modifier = Modifier,
) {
    val scheme = MaterialTheme.colorScheme
    val tokens = LocalMiuixTokens.current
    val dark = scheme.background.luminance() < .5f
    val bottomInset = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
    val floating = appearance.floatingDock
    val shape = if (floating) RoundedCornerShape(29.dp) else RoundedCornerShape(topStart = 29.dp, topEnd = 29.dp)
    val activeGlass = appearance.glassEnabled
    val activeHaze = activeGlass && appearance.blurEnabled
    val hazeModifier = if (activeHaze) {
        Modifier.hazeEffect(state = hazeState, style = HazeMaterials.ultraThin()) {
            blurRadius = 36.dp
            noiseFactor = .06f
        }
    } else Modifier
    val glassBrush = when {
        activeGlass && dark -> Brush.verticalGradient(
            listOf(
                Color.White.copy(alpha = .16f),
                tokens.elevatedCardBackground.copy(alpha = .22f),
                scheme.primary.copy(alpha = .10f),
            ),
        )
        activeGlass -> Brush.verticalGradient(
            listOf(
                Color.White.copy(alpha = .72f),
                Color.White.copy(alpha = .30f),
                scheme.primary.copy(alpha = .10f),
            ),
        )
        else -> Brush.verticalGradient(
            listOf(tokens.elevatedCardBackground.copy(alpha = .98f), tokens.elevatedCardBackground.copy(alpha = .98f)),
        )
    }

    AppDockLayout(
        pages = dockPages,
        current = current,
        onSelect = onSelect,
        itemHeight = 56.dp,
        modifier = modifier
            .then(if (floating) Modifier.padding(horizontal = 14.dp).padding(bottom = bottomInset + 8.dp) else Modifier)
            .fillMaxWidth()
            .shadow(if (floating) if (activeGlass) 20.dp else 12.dp else 5.dp, shape, clip = false)
            .clip(shape)
            .then(hazeModifier)
            .background(glassBrush)
            .drawBehind {
                if (activeGlass) {
                    val radius = 29.dp.toPx()
                    drawRoundRect(
                        brush = Brush.linearGradient(
                            colors = listOf(
                                Color.White.copy(alpha = if (dark) .34f else .90f),
                                Color.Transparent,
                                scheme.primary.copy(alpha = if (dark) .16f else .13f),
                            ),
                            start = Offset.Zero,
                            end = Offset(size.width, size.height),
                        ),
                        cornerRadius = CornerRadius(radius, radius),
                        style = Stroke(width = 1.2.dp.toPx()),
                    )
                    drawLine(
                        color = Color.White.copy(alpha = if (dark) .24f else .68f),
                        start = Offset(radius * .78f, 1.4.dp.toPx()),
                        end = Offset(size.width - radius * .78f, 1.4.dp.toPx()),
                        strokeWidth = .9.dp.toPx(),
                    )
                }
            }
            .border(
                if (activeGlass) .7.dp else 1.dp,
                if (activeGlass) {
                    if (dark) Color.White.copy(alpha = .18f) else Color.White.copy(alpha = .76f)
                } else if (dark) Color.White.copy(alpha = .10f) else Color.White.copy(alpha = .58f),
                shape,
            )
            .padding(start = 5.dp, top = 5.dp, end = 5.dp, bottom = if (floating) 5.dp else bottomInset + 5.dp),
        indicatorColor = if (activeGlass) {
            Color.White.copy(alpha = if (dark) .12f else .34f)
        } else {
            scheme.primary.copy(alpha = if (dark) .20f else .12f)
        },
        indicatorBorderColor = if (activeGlass) {
            Color.White.copy(alpha = if (dark) .24f else .72f)
        } else {
            Color.Transparent
        },
        indicatorShadow = if (activeGlass) 6.dp else 0.dp,
        selectedColor = scheme.primary,
        unselectedColor = scheme.onSurfaceVariant.copy(alpha = .82f),
        label = "luoshuMiuixDockIndicator",
    )
}
'''

shell, count = re.subn(
    r'@OptIn\(ExperimentalHazeMaterialsApi::class\)\n@Composable\nprivate fun MiuixAppDock\(.*?\n\}\n\n(?=@Composable\nprivate fun AppDockLayout)',
    miuix_dock + "\n",
    shell,
    flags=re.S,
)
if count != 1:
    raise SystemExit(f"MiuixAppDock replacement count={count}")

old_signature = '''    indicatorColor: Color,
    selectedColor: Color,
    unselectedColor: Color,
    label: String,
) {'''
new_signature = '''    indicatorColor: Color,
    indicatorBorderColor: Color = Color.Transparent,
    indicatorShadow: androidx.compose.ui.unit.Dp = 0.dp,
    selectedColor: Color,
    unselectedColor: Color,
    label: String,
) {'''
if old_signature not in shell:
    raise SystemExit("AppDockLayout signature marker missing")
shell = shell.replace(old_signature, new_signature, 1)

old_indicator = '''                .offset(x = indicatorX + 5.dp)
                .width(itemWidth - 10.dp)
                .height(itemHeight)
                .clip(RoundedCornerShape(20.dp))
                .background(indicatorColor),'''
new_indicator = '''                .offset(x = indicatorX + 5.dp)
                .width(itemWidth - 10.dp)
                .height(itemHeight)
                .shadow(indicatorShadow, RoundedCornerShape(20.dp), clip = false)
                .clip(RoundedCornerShape(20.dp))
                .background(indicatorColor)
                .border(1.dp, indicatorBorderColor, RoundedCornerShape(20.dp)),'''
if old_indicator not in shell:
    raise SystemExit("AppDockLayout indicator marker missing")
shell = shell.replace(old_indicator, new_indicator, 1)

shell_path.write_text(shell, encoding="utf-8")

settings = settings_path.read_text(encoding="utf-8")
settings = settings.replace(
    'MiuixSwitchRow("玻璃半透明", "控制悬浮层透明质感", settings.glassEnabled, actions.setGlassEnabled)',
    'MiuixSwitchRow("底栏液态玻璃效果", "真实背景采样、折射高光与透明质感", settings.glassEnabled, actions.setGlassEnabled)',
)
settings = settings.replace(
    'MiuixSwitchRow("背景模糊", "使用 Haze 模糊悬浮底栏背景", settings.blurEnabled, actions.setBlurEnabled, settings.glassEnabled)',
    'MiuixSwitchRow("背景模糊", "模糊液态玻璃后方的页面内容", settings.blurEnabled, actions.setBlurEnabled, settings.glassEnabled)',
)
settings_path.write_text(settings, encoding="utf-8")

test = test_path.read_text(encoding="utf-8")
if 'SETTINGS=' not in test:
    test = test.replace(
        'SHELL="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuAppShell.kt"\n',
        'SHELL="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuAppShell.kt"\nSETTINGS="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/settings/AppearanceSettingsScreen.kt"\n',
    )
test = test.replace(
    "printf '%s\\n' \"$MIUIX_DOCK\" | grep -q 'blurRadius = 24.dp'",
    "printf '%s\\n' \"$MIUIX_DOCK\" | grep -q 'blurRadius = 36.dp'\nprintf '%s\\n' \"$MIUIX_DOCK\" | grep -q 'activeGlass'\nprintf '%s\\n' \"$MIUIX_DOCK\" | grep -q 'drawRoundRect'\nprintf '%s\\n' \"$MIUIX_DOCK\" | grep -q 'indicatorBorderColor'\ngrep -q '底栏液态玻璃效果' \"$SETTINGS\"\ngrep -q '真实背景采样、折射高光与透明质感' \"$SETTINGS\"",
)
test_path.write_text(test, encoding="utf-8")

print("Liquid glass dock patch applied.")
