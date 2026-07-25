from pathlib import Path

root = Path('.')


def read(path: str) -> str:
    return (root / path).read_text()


def write(path: str, text: str) -> None:
    (root / path).write_text(text)


route_path = 'android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/FontStudioRoute.kt'
miuix_path = 'android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/FontStudioScreenMiuix.kt'
material_path = 'android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/FontStudioScreenMaterial.kt'
launcher_path = 'android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/StudioToolLauncher.kt'
shell_path = 'android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuAppShell.kt'
test_path = 'scripts/font_library_ui_layout_test.sh'

# Studio tools are a real child of the title header, never an overlay.
route = read(route_path)
old = '''    Box(Modifier.fillMaxSize()) {
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
'''
new = '''    val studioTools: @Composable () -> Unit = {
        StudioToolLauncher(
            style = style,
            enabled = state.hasFonts && !state.loading,
            onPreview = { showCompositePreview = true },
            onProfile = { showProfileTransfer = true },
            onGlyphs = { showGlyphBrowser = true },
        )
    }
    when (style) {
        UiStyle.MATERIAL -> FontStudioScreenMaterial(state, stableActions, studioTools)
        UiStyle.MIUIX -> FontStudioScreenMiuix(state, stableActions, studioTools)
    }
'''
if old not in route:
    raise SystemExit('FontStudioRoute.kt: floating launcher block not found')
write(route_path, route.replace(old, new, 1))

for path, screen, header, refresh_marker in [
    (miuix_path, 'FontStudioScreenMiuix', 'MiuixStudioHeader', '        Card(\n'),
    (material_path, 'FontStudioScreenMaterial', 'MaterialStudioHeader', '        Surface(\n'),
]:
    text = read(path)
    old_sig = f'internal fun {screen}(\n    state: FontStudioUiState,\n    actions: FontStudioActions,\n) {{'
    new_sig = f'internal fun {screen}(\n    state: FontStudioUiState,\n    actions: FontStudioActions,\n    topAction: @Composable () -> Unit,\n) {{'
    if old_sig not in text:
        raise SystemExit(f'{path}: screen signature not found')
    text = text.replace(old_sig, new_sig, 1)
    text = text.replace(
        f'item {{ {header}(state.loading, actions.refresh) }}',
        f'item {{ {header}(state.loading, actions.refresh, topAction) }}',
        1,
    )
    text = text.replace(
        f'private fun {header}(loading: Boolean, onRefresh: () -> Unit) {{',
        f'private fun {header}(loading: Boolean, onRefresh: () -> Unit, topAction: @Composable () -> Unit) {{',
        1,
    )
    start = text.find(f'private fun {header}')
    index = text.find(refresh_marker, start)
    if index < 0:
        raise SystemExit(f'{path}: refresh control not found')
    text = text[:index] + '        topAction()\n        Spacer(Modifier.width(10.dp))\n' + text[index:]
    text = text.replace('bottom = 132.dp)', 'bottom = 24.dp)', 1)
    write(path, text)

launcher = read(launcher_path)
if 'io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens' not in launcher:
    launcher = launcher.replace(
        'import io.github.xgl34222220.luoshu.ui.appearance.UiStyle\n',
        'import io.github.xgl34222220.luoshu.ui.appearance.UiStyle\nimport io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens\n',
        1,
    )
old_bg = '''    val scheme = MaterialTheme.colorScheme
    val background = if (enabled) {
        scheme.surfaceContainerHigh.copy(alpha = if (style == UiStyle.MIUIX) .78f else .90f)
    } else {
        scheme.surfaceVariant.copy(alpha = .64f)
    }
'''
new_bg = '''    val scheme = MaterialTheme.colorScheme
    val tokens = LocalMiuixTokens.current
    val background = when {
        !enabled -> scheme.surfaceVariant.copy(alpha = .64f)
        style == UiStyle.MIUIX -> tokens.elevatedCardBackground
        else -> scheme.surfaceContainerHigh.copy(alpha = .84f)
    }
'''
if old_bg not in launcher:
    raise SystemExit('StudioToolLauncher.kt: background block not found')
launcher = launcher.replace(old_bg, new_bg, 1)
launcher = launcher.replace('shape = CircleShape,', 'shape = RoundedCornerShape(18.dp),', 1)
old_shadow = '''        shadowElevation = if (enabled && style == UiStyle.MIUIX) 6.dp else 3.dp,
        border = BorderStroke(1.dp, scheme.primary.copy(alpha = if (enabled) .13f else .05f)),'''
if old_shadow not in launcher:
    raise SystemExit('StudioToolLauncher.kt: shadow block not found')
launcher = launcher.replace(old_shadow, '        shadowElevation = 7.dp,', 1)
write(launcher_path, launcher)

# Reserve a real viewport above the floating dock; padding inside LazyColumn is not enough.
shell = read(shell_path).replace('libraryDockClearance', 'dockClearance')
old_studio = '''                        AppPage.Studio -> FontStudioRoute(
                            style = appearance.uiStyle,
                            state = viewModel.toFontStudioUiState(features),
                            actions = studioActions,
                        )'''
new_studio = '''                        AppPage.Studio -> Box(
                            modifier = Modifier.fillMaxSize().padding(bottom = dockClearance),
                        ) {
                            FontStudioRoute(
                                style = appearance.uiStyle,
                                state = viewModel.toFontStudioUiState(features),
                                actions = studioActions,
                            )
                        }'''
if old_studio not in shell:
    raise SystemExit('LuoShuAppShell.kt: Studio route block not found')
write(shell_path, shell.replace(old_studio, new_studio, 1))

# Regression checks for the exact real-device layout failures.
test = read(test_path)
if 'STUDIO_TOOLS=' not in test:
    test = test.replace(
        'STUDIO_MATERIAL="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/FontStudioScreenMaterial.kt"\n',
        'STUDIO_MATERIAL="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/FontStudioScreenMaterial.kt"\nSTUDIO_TOOLS="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/StudioToolLauncher.kt"\n',
        1,
    )
remove = (
    "grep -q 'align(Alignment.TopEnd)'",
    "grep -q 'statusBarsPadding()'",
    "! grep -q 'align(Alignment.TopEnd)'",
    "! grep -q 'statusBarsPadding()'",
)
test = '\n'.join(line for line in test.splitlines() if not any(x in line for x in remove)) + '\n'
checks = '''# Final screenshot regression: the two header actions share one Row and content
# is laid out above the floating dock.
grep -q 'topAction: @Composable () -> Unit' "$STUDIO_MIUIX"
grep -q 'topAction: @Composable () -> Unit' "$STUDIO_MATERIAL"
grep -q 'topAction()' "$STUDIO_MIUIX"
grep -q 'topAction()' "$STUDIO_MATERIAL"
grep -q 'bottom = 24.dp' "$STUDIO_MIUIX"
grep -q 'bottom = 24.dp' "$STUDIO_MATERIAL"
! grep -q 'align(Alignment.TopEnd)' "$STUDIO_ROUTE"
! grep -q 'statusBarsPadding()' "$STUDIO_ROUTE"
grep -q 'RoundedCornerShape(18.dp)' "$STUDIO_TOOLS"
! grep -q 'shape = CircleShape' "$STUDIO_TOOLS"
grep -q 'padding(bottom = dockClearance)' "$SHELL"
'''
anchor = "echo 'LuoShu compact UI layout regression passed.'\n"
if anchor not in test:
    raise SystemExit('layout regression success anchor not found')
write(test_path, test.replace(anchor, checks + '\n' + anchor, 1))
