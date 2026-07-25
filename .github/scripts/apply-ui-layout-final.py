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

# 1. Put the tool button in the screen header instead of a floating overlay.
route = read(route_path)
old_route = '''    Box(Modifier.fillMaxSize()) {
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
new_route = '''    val studioTools: @Composable () -> Unit = {
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
if old_route not in route:
    raise SystemExit('FontStudioRoute.kt: floating launcher block not found')
write(route_path, route.replace(old_route, new_route, 1))

# 2. Both style headers own tool + refresh in one Row.
for path, screen_name, header_name in [
    (miuix_path, 'FontStudioScreenMiuix', 'MiuixStudioHeader'),
    (material_path, 'FontStudioScreenMaterial', 'MaterialStudioHeader'),
]:
    text = read(path)
    old_signature = f'''internal fun {screen_name}(\n    state: FontStudioUiState,\n    actions: FontStudioActions,\n) {{'''
    new_signature = f'''internal fun {screen_name}(\n    state: FontStudioUiState,\n    actions: FontStudioActions,\n    topAction: @Composable () -> Unit,\n) {{'''
    if old_signature not in text:
        raise SystemExit(f'{path}: screen signature not found')
    text = text.replace(old_signature, new_signature, 1)
    text = text.replace(
        f'item {{ {header_name}(state.loading, actions.refresh) }}',
        f'item {{ {header_name}(state.loading, actions.refresh, topAction) }}',
        1,
    )
    text = text.replace(
        f'private fun {header_name}(loading: Boolean, onRefresh: () -> Unit) {{',
        f'private fun {header_name}(loading: Boolean, onRefresh: () -> Unit, topAction: @Composable () -> Unit) {{',
        1,
    )
    refresh_marker = '        Card(\n' if path == miuix_path else '        Surface(\n'
    header_start = text.find(f'private fun {header_name}')
    index = text.find(refresh_marker, header_start)
    if index < 0:
        raise SystemExit(f'{path}: refresh control not found')
    text = text[:index] + '        topAction()\n        Spacer(Modifier.width(10.dp))\n' + text[index:]
    text = text.replace('bottom = 132.dp)', 'bottom = 24.dp)', 1)
    write(path, text)

# 3. Tool launcher matches the refresh button and cannot become a layered circle.
launcher = read(launcher_path)
if 'io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens' not in launcher:
    launcher = launcher.replace(
        'import io.github.xgl34222220.luoshu.ui.appearance.UiStyle\n',
        'import io.github.xgl34222220.luoshu.ui.appearance.UiStyle\nimport io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens\n',
        1,
    )
old_background = '''    val scheme = MaterialTheme.colorScheme
    val background = if (enabled) {
        scheme.surfaceContainerHigh.copy(alpha = if (style == UiStyle.MIUIX) .78f else .90f)
    } else {
        scheme.surfaceVariant.copy(alpha = .64f)
    }
'''
new_background = '''    val scheme = MaterialTheme.colorScheme
    val tokens = LocalMiuixTokens.current
    val background = when {
        !enabled -> scheme.surfaceVariant.copy(alpha = .64f)
        style == UiStyle.MIUIX -> tokens.elevatedCardBackground
        else -> scheme.surfaceContainerHigh.copy(alpha = .84f)
    }
'''
if old_background not in launcher:
    raise SystemExit('StudioToolLauncher.kt: background block not found')
launcher = launcher.replace(old_background, new_background, 1)
launcher = launcher.replace('shape = CircleShape,', 'shape = RoundedCornerShape(18.dp),', 1)
old_elevation = '''        shadowElevation = if (enabled && style == UiStyle.MIUIX) 6.dp else 3.dp,
        border = BorderStroke(1.dp, scheme.primary.copy(alpha = if (enabled) .13f else .05f)),'''
if old_elevation not in launcher:
    raise SystemExit('StudioToolLauncher.kt: old elevation/border block not found')
launcher = launcher.replace(old_elevation, '        shadowElevation = 7.dp,', 1)
write(launcher_path, launcher)

# 4. The Studio viewport itself ends above the floating dock.
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

# 5. Remove stale acceptance-wizard wording and explain pending evidence correctly.
replacements = {
    '测试矩阵与 v2.2.2 预发行门禁': '测试矩阵与当前版本预发行门禁',
    '等待开机加载验证；兼容模式不能视为真机验收完成': '等待逐分区开机挂载验证；应用字体并完整重启后重新检测',
    '仍有对齐缓存等待生成': '对齐缓存尚未生成；应用字体后将自动建立',
}
found = {key: 0 for key in replacements}
for path in (root / 'android-app').rglob('*.kt'):
    text = path.read_text()
    original = text
    for old, new in replacements.items():
        found[old] += text.count(old)
        text = text.replace(old, new)
    if text != original:
        path.write_text(text)
if found['测试矩阵与 v2.2.2 预发行门禁'] < 1:
    raise SystemExit('stale v2.2.2 acceptance label not found')

# 6. Structural regression checks for the exact real-device failures.
test = read(test_path)
if 'STUDIO_TOOLS=' not in test:
    test = test.replace(
        'STUDIO_MATERIAL="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/FontStudioScreenMaterial.kt"\n',
        'STUDIO_MATERIAL="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/FontStudioScreenMaterial.kt"\nSTUDIO_TOOLS="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/StudioToolLauncher.kt"\n',
        1,
    )
obsolete_tokens = (
    "grep -q 'align(Alignment.TopEnd)'",
    "grep -q 'statusBarsPadding()'",
    "! grep -q 'align(Alignment.TopEnd)'",
    "! grep -q 'statusBarsPadding()'",
)
lines = [line for line in test.splitlines() if not any(token in line for token in obsolete_tokens)]
test = '\n'.join(lines) + '\n'
checks = '''# Final screenshot regression: controls share one header Row and the Studio viewport
# ends above the floating dock instead of merely adding scroll padding.
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
grep -R -q '测试矩阵与当前版本预发行门禁' "$ROOT/android-app/app/src/main/java"
! grep -R -q '测试矩阵与 v2.2.2 预发行门禁' "$ROOT/android-app/app/src/main/java"
'''
anchor = "echo 'LuoShu compact UI layout regression passed.'\n"
if anchor not in test:
    raise SystemExit('font_library_ui_layout_test.sh: success anchor not found')
test = test.replace(anchor, checks + '\n' + anchor, 1)
write(test_path, test)
