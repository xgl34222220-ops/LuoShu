#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(relative: str, old: str, new: str) -> None:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{relative}: expected one match, found {count}: {old[:90]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_regex_once(relative: str, pattern: str, replacement: str) -> None:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"{relative}: regex expected one match, found {count}: {pattern[:90]!r}")
    path.write_text(updated, encoding="utf-8")


MIUIX = "android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryScreenMiuix.kt"
MATERIAL = "android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryScreenMaterial.kt"
ROUTE = "android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryRoute.kt"
OVERLAY = "android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportOverlay.kt"
SHELL = "android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuAppShell.kt"
CHECK = "scripts/check.sh"

replace_once(
    MIUIX,
    "import androidx.compose.foundation.layout.Column\n"
    "import androidx.compose.foundation.layout.PaddingValues\n",
    "import androidx.compose.foundation.layout.Column\n"
    "import androidx.compose.foundation.layout.PaddingValues\n"
    "import androidx.compose.foundation.layout.defaultMinSize\n",
)
replace_once(
    MIUIX,
    "import androidx.compose.foundation.layout.height\n"
    "import androidx.compose.foundation.layout.padding\n",
    "import androidx.compose.foundation.layout.height\n"
    "import androidx.compose.foundation.layout.heightIn\n"
    "import androidx.compose.foundation.layout.padding\n",
)
replace_once(
    MIUIX,
    """internal fun FontLibraryScreenMiuix(
    state: FontLibraryUiState,
    actions: FontLibraryActions,
) {
""",
    """internal fun FontLibraryScreenMiuix(
    state: FontLibraryUiState,
    actions: FontLibraryActions,
    topActions: @Composable () -> Unit = {},
) {
""",
)
replace_once(
    MIUIX,
    """        contentPadding = PaddingValues(start = 16.dp, top = 8.dp, end = 16.dp, bottom = 132.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { MiuixLibraryHeader(state, actions.refresh) }
        item { MiuixBrowsePanel(state, actions) }
""",
    """        contentPadding = PaddingValues(start = 16.dp, top = 8.dp, end = 16.dp, bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item { MiuixLibraryHeader(state, actions.refresh) }
        item { topActions() }
        item { MiuixBrowsePanel(state, actions) }
""",
)
replace_once(MIUIX, "                fontSize = 42.sp,\n                lineHeight = 47.sp,\n", "                fontSize = 38.sp,\n                lineHeight = 43.sp,\n")
replace_once(MIUIX, "        shape = RoundedCornerShape(34.dp),\n        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),\n        elevation = CardDefaults.cardElevation(defaultElevation = 7.dp),\n", "        shape = RoundedCornerShape(30.dp),\n        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),\n        elevation = CardDefaults.cardElevation(defaultElevation = 4.dp),\n")
replace_once(MIUIX, "        shape = RoundedCornerShape(32.dp),\n        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),\n        elevation = CardDefaults.cardElevation(defaultElevation = 6.dp),\n", "        shape = RoundedCornerShape(28.dp),\n        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),\n        elevation = CardDefaults.cardElevation(defaultElevation = 3.dp),\n")

new_card = r"""@Composable
private fun MiuixFontCard(
    font: FontItem,
    active: Boolean,
    busy: Boolean,
    onDetails: () -> Unit,
    onApply: () -> Unit,
    onDelete: () -> Unit,
) {
    val tokens = LocalMiuixTokens.current
    val shape = RoundedCornerShape(28.dp)
    Card(
        modifier = Modifier.fillMaxWidth().shadow(if (active) 8.dp else 3.dp, shape, clip = false),
        shape = shape,
        colors = CardDefaults.cardColors(
            containerColor = if (font.valid) tokens.cardBackground else MaterialTheme.colorScheme.errorContainer.copy(alpha = .42f),
        ),
    ) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(52.dp).clickable(onClick = onDetails),
                    shape = RoundedCornerShape(18.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = .10f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text("Aa", color = MaterialTheme.colorScheme.primary, fontSize = 17.sp, fontWeight = FontWeight.Black)
                    }
                }
                Spacer(Modifier.width(12.dp))
                Column(
                    modifier = Modifier
                        .weight(1f)
                        .heightIn(min = 52.dp)
                        .clickable(onClick = onDetails),
                    verticalArrangement = Arrangement.Center,
                ) {
                    Text(
                        font.name,
                        color = tokens.textPrimary,
                        fontSize = 18.sp,
                        lineHeight = 22.sp,
                        fontWeight = FontWeight.Black,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Spacer(Modifier.height(2.dp))
                    Text(
                        listOf(font.format, font.size, font.date).filter { it.isNotBlank() }.joinToString(" · "),
                        color = tokens.textSecondary,
                        fontSize = 10.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                if (!active) {
                    Spacer(Modifier.width(6.dp))
                    Surface(
                        onClick = onDelete,
                        enabled = !busy,
                        modifier = Modifier.size(40.dp),
                        shape = RoundedCornerShape(14.dp),
                        color = tokens.textPrimary.copy(alpha = .055f),
                        contentColor = tokens.textSecondary,
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Icon(
                                Icons.Rounded.Delete,
                                contentDescription = "删除字体",
                                modifier = Modifier.size(20.dp),
                            )
                        }
                    }
                }
            }

            Spacer(Modifier.height(13.dp))
            Surface(
                modifier = Modifier.fillMaxWidth().clickable(onClick = onDetails),
                shape = RoundedCornerShape(22.dp),
                color = tokens.textPrimary.copy(alpha = .035f),
            ) {
                NativeFontPreview(
                    font = font,
                    text = fontPreviewText(font),
                    axes = if (font.variable) mapOf("wght" to 400f) else emptyMap(),
                    modifier = Modifier.fillMaxWidth().height(88.dp).padding(horizontal = 15.dp, vertical = 14.dp),
                    textSizeSp = 22f,
                    maxLines = 1,
                )
            }

            if (!font.valid && font.error.isNotBlank()) {
                Spacer(Modifier.height(10.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        Icons.Rounded.Warning,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.error,
                        modifier = Modifier.size(16.dp),
                    )
                    Spacer(Modifier.width(6.dp))
                    Text(
                        font.error,
                        color = MaterialTheme.colorScheme.error,
                        fontSize = 10.sp,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }

            Spacer(Modifier.height(12.dp))
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = .34f))
            Spacer(Modifier.height(11.dp))
            MiuixCapabilityStrip(fontCapabilityLabel(font))
            Spacer(Modifier.height(10.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                MiuixCardAction(
                    label = "查看详情",
                    primary = false,
                    enabled = true,
                    onClick = onDetails,
                    modifier = Modifier.weight(1f),
                )
                if (active) {
                    MiuixCurrentAction(modifier = Modifier.weight(1f), color = tokens.success)
                } else {
                    MiuixCardAction(
                        label = "应用字体",
                        primary = true,
                        enabled = font.valid && !busy,
                        onClick = onApply,
                        modifier = Modifier.weight(1f),
                    )
                }
            }
        }
    }
}

@Composable
private fun MiuixCapabilityStrip(text: String) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = MaterialTheme.colorScheme.primary.copy(alpha = .075f),
    ) {
        Text(
            text = text,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 9.dp),
            color = MaterialTheme.colorScheme.primary,
            fontSize = 10.sp,
            lineHeight = 14.sp,
            fontWeight = FontWeight.Black,
            maxLines = 1,
            softWrap = false,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun MiuixCardAction(
    label: String,
    primary: Boolean,
    enabled: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val scheme = MaterialTheme.colorScheme
    val container = when {
        primary && enabled -> scheme.primary
        primary -> scheme.surfaceVariant
        else -> scheme.surfaceContainerHigh
    }
    val content = when {
        primary && enabled -> scheme.onPrimary
        primary -> scheme.onSurfaceVariant
        else -> scheme.onSurface
    }
    Surface(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.defaultMinSize(minHeight = 44.dp),
        shape = RoundedCornerShape(16.dp),
        color = container,
        contentColor = content,
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                label,
                color = content,
                fontSize = 12.sp,
                fontWeight = FontWeight.Black,
                maxLines = 1,
                softWrap = false,
            )
            if (primary) {
                Spacer(Modifier.width(4.dp))
                Icon(
                    Icons.Rounded.ChevronRight,
                    contentDescription = null,
                    modifier = Modifier.size(17.dp),
                    tint = content,
                )
            }
        }
    }
}

@Composable
private fun MiuixCurrentAction(modifier: Modifier = Modifier, color: Color) {
    Surface(
        modifier = modifier.defaultMinSize(minHeight = 44.dp),
        shape = RoundedCornerShape(16.dp),
        color = color.copy(alpha = .11f),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.Rounded.CheckCircle, contentDescription = null, tint = color, modifier = Modifier.size(17.dp))
            Spacer(Modifier.width(6.dp))
            Text(
                "正在使用",
                color = color,
                fontSize = 12.sp,
                fontWeight = FontWeight.Black,
                maxLines = 1,
                softWrap = false,
            )
        }
    }
}

"""
replace_regex_once(
    MIUIX,
    r"@Composable\nprivate fun MiuixFontCard\(.*?\n@Composable\nprivate fun MiuixLibraryNotice",
    new_card + "@Composable\nprivate fun MiuixLibraryNotice",
)
replace_regex_once(
    MIUIX,
    r"@Composable\nprivate fun MiuixLibraryPill\(text: String, color: Color\) \{.*?\n\}\s*$",
    r"""@Composable
private fun MiuixLibraryPill(text: String, color: Color) {
    Surface(shape = RoundedCornerShape(999.dp), color = color.copy(alpha = .12f)) {
        Text(
            text,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            color = color,
            fontSize = 10.sp,
            fontWeight = FontWeight.Black,
            maxLines = 1,
            softWrap = false,
            overflow = TextOverflow.Ellipsis,
        )
    }
}
""",
)

replace_once(
    MATERIAL,
    """internal fun FontLibraryScreenMaterial(
    state: FontLibraryUiState,
    actions: FontLibraryActions,
) {
""",
    """internal fun FontLibraryScreenMaterial(
    state: FontLibraryUiState,
    actions: FontLibraryActions,
    topActions: @Composable () -> Unit = {},
) {
""",
)
replace_once(
    MATERIAL,
    """        contentPadding = PaddingValues(start = 18.dp, top = 8.dp, end = 18.dp, bottom = 132.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item { MaterialLibraryHeader(state, actions.refresh) }
        item { MaterialLibraryOverview(state) }
        item { MaterialBrowsePanel(state, actions) }
""",
    """        contentPadding = PaddingValues(start = 18.dp, top = 8.dp, end = 18.dp, bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item { MaterialLibraryHeader(state, actions.refresh) }
        item { topActions() }
        item { MaterialLibraryOverview(state) }
        item { MaterialBrowsePanel(state, actions) }
""",
)

replace_once(
    ROUTE,
    """internal fun FontLibraryRoute(
    style: UiStyle,
    state: FontLibraryUiState,
    actions: FontLibraryActions,
) {
""",
    """internal fun FontLibraryRoute(
    style: UiStyle,
    state: FontLibraryUiState,
    actions: FontLibraryActions,
    topActions: @Composable () -> Unit = {},
) {
""",
)
replace_once(
    ROUTE,
    """    when (style) {
        UiStyle.MATERIAL -> FontLibraryScreenMaterial(displayState, displayActions)
        UiStyle.MIUIX -> FontLibraryScreenMiuix(displayState, displayActions)
    }
""",
    """    when (style) {
        UiStyle.MATERIAL -> FontLibraryScreenMaterial(displayState, displayActions, topActions)
        UiStyle.MIUIX -> FontLibraryScreenMiuix(displayState, displayActions, topActions)
    }
""",
)

replace_once(
    OVERLAY,
    """internal fun NativeImportOverlay(
    viewModel: LuoShuViewModel,
    style: UiStyle,
    modifier: Modifier = Modifier,
) {
""",
    """internal fun NativeImportOverlay(
    viewModel: LuoShuViewModel,
    style: UiStyle,
    modifier: Modifier = Modifier,
    embedded: Boolean = false,
) {
""",
)
replace_once(
    OVERLAY,
    """    LaunchedEffect(state.busy, state.paused, state.processed, state.total) {
        if (state.busy || state.paused) {
            expanded = true
        } else {
            expanded = true
            delay(2_400L)
            expanded = false
        }
    }
""",
    """    LaunchedEffect(embedded, state.busy, state.paused, state.processed, state.total) {
        if (embedded || state.busy || state.paused) {
            expanded = true
        } else {
            expanded = true
            delay(2_400L)
            expanded = false
        }
    }
""",
)
old_overlay_row = """    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.End,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        FontMetadataInspector(
            viewModel = viewModel,
            style = style,
        )
        Spacer(Modifier.width(10.dp))
        ImportActionButton(
            style = style,
            state = state,
            expanded = expanded || state.busy || state.paused,
            enabled = viewModel.snapshot.installed &&
                !viewModel.operationBusy &&
                !viewModel.mixState.busy &&
                (!state.busy || state.paused),
            onImport = {
                if (state.paused) {
                    importViewModel.resumeImport()
                } else {
                    launcher.launch(arrayOf("*/*"))
                }
            },
        )
    }
"""
new_overlay_row = """    val importEnabled = viewModel.snapshot.installed &&
        !viewModel.operationBusy &&
        !viewModel.mixState.busy &&
        (!state.busy || state.paused)
    val onImport = {
        if (state.paused) {
            importViewModel.resumeImport()
        } else {
            launcher.launch(arrayOf("*/*"))
        }
    }

    if (embedded) {
        val tokens = LocalMiuixTokens.current
        Surface(
            modifier = modifier.fillMaxWidth(),
            shape = RoundedCornerShape(28.dp),
            color = if (style == UiStyle.MIUIX) tokens.cardBackground else MaterialTheme.colorScheme.surfaceContainerLow,
            shadowElevation = if (style == UiStyle.MIUIX) 4.dp else 2.dp,
            border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = .08f)),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                FontMetadataInspector(
                    viewModel = viewModel,
                    style = style,
                )
                ImportActionButton(
                    style = style,
                    state = state,
                    expanded = true,
                    enabled = importEnabled,
                    onImport = onImport,
                    modifier = Modifier.weight(1f),
                    embedded = true,
                )
            }
        }
    } else {
        Row(
            modifier = modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.End,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            FontMetadataInspector(
                viewModel = viewModel,
                style = style,
            )
            Spacer(Modifier.width(10.dp))
            ImportActionButton(
                style = style,
                state = state,
                expanded = expanded || state.busy || state.paused,
                enabled = importEnabled,
                onImport = onImport,
            )
        }
    }
"""
replace_once(OVERLAY, old_overlay_row, new_overlay_row)
replace_once(
    OVERLAY,
    """private fun ImportActionButton(
    style: UiStyle,
    state: NativeImportState,
    expanded: Boolean,
    enabled: Boolean,
    onImport: () -> Unit,
) {
""",
    """private fun ImportActionButton(
    style: UiStyle,
    state: NativeImportState,
    expanded: Boolean,
    enabled: Boolean,
    onImport: () -> Unit,
    modifier: Modifier = Modifier,
    embedded: Boolean = false,
) {
""",
)
replace_once(
    OVERLAY,
    """    val targetWidth = when {
        !expanded -> 54.dp
        taskVisible -> 180.dp
        else -> 148.dp
    }
    val targetHeight = if (taskVisible) 68.dp else 54.dp
""",
    """    val targetWidth = when {
        !expanded -> 54.dp
        taskVisible -> 180.dp
        else -> 148.dp
    }
    val targetHeight = when {
        embedded && taskVisible -> 68.dp
        embedded -> 56.dp
        taskVisible -> 68.dp
        else -> 54.dp
    }
""",
)
replace_once(
    OVERLAY,
    """    val glassColor = when {
        style == UiStyle.MIUIX -> tokens.elevatedCardBackground.copy(alpha = if (dark) .76f else .72f)
        dark -> scheme.surfaceContainerHigh.copy(alpha = .72f)
        else -> Color.White.copy(alpha = .70f)
    }
""",
    """    val glassColor = when {
        embedded && style == UiStyle.MIUIX -> scheme.primary.copy(alpha = if (dark) .18f else .10f)
        embedded -> scheme.primaryContainer.copy(alpha = if (dark) .46f else .62f)
        style == UiStyle.MIUIX -> tokens.elevatedCardBackground.copy(alpha = if (dark) .76f else .72f)
        dark -> scheme.surfaceContainerHigh.copy(alpha = .72f)
        else -> Color.White.copy(alpha = .70f)
    }
""",
)
replace_once(
    OVERLAY,
    """    Surface(
        onClick = onImport,
        enabled = enabled,
        modifier = Modifier.width(width).height(height),
        shape = CircleShape,
        color = glassColor,
        contentColor = scheme.primary,
        shadowElevation = if (style == UiStyle.MIUIX) 14.dp else 12.dp,
        border = BorderStroke(1.dp, borderColor),
    ) {
""",
    """    val buttonModifier = if (embedded) {
        modifier.fillMaxWidth().height(height)
    } else {
        modifier.width(width).height(height)
    }
    Surface(
        onClick = onImport,
        enabled = enabled,
        modifier = buttonModifier,
        shape = if (embedded) RoundedCornerShape(20.dp) else CircleShape,
        color = glassColor,
        contentColor = scheme.primary,
        shadowElevation = if (embedded) 0.dp else if (style == UiStyle.MIUIX) 14.dp else 12.dp,
        border = BorderStroke(1.dp, if (embedded) scheme.primary.copy(alpha = .10f) else borderColor),
    ) {
""",
)
replace_once(
    OVERLAY,
    """            Column(
                modifier = Modifier.padding(horizontal = 14.dp, vertical = if (taskVisible) 10.dp else 12.dp),
                horizontalAlignment = Alignment.End,
                verticalArrangement = Arrangement.Center,
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
""",
    """            Column(
                modifier = Modifier.padding(horizontal = 14.dp, vertical = if (taskVisible) 10.dp else 12.dp),
                horizontalAlignment = if (embedded) Alignment.CenterHorizontally else Alignment.End,
                verticalArrangement = Arrangement.Center,
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.Center,
                ) {
""",
)
replace_once(
    OVERLAY,
    """                        fontSize = 15.sp,
""",
    """                        fontSize = if (embedded) 14.sp else 15.sp,
""",
)

replace_once(
    SHELL,
    """        val hazeState = rememberHazeState(blurEnabled = materialHazeActive)
        val contentModifier = Modifier
""",
    """        val hazeState = rememberHazeState(blurEnabled = materialHazeActive)
        val navigationBottom = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
        val libraryDockClearance = navigationBottom + if (appearance.floatingDock) 84.dp else 68.dp
        val contentModifier = Modifier
""",
)
replace_once(
    SHELL,
    """                        AppPage.Library -> FontLibraryRoute(
                            style = appearance.uiStyle,
                            state = viewModel.toFontLibraryUiState(),
                            actions = libraryActions,
                        )
""",
    """                        AppPage.Library -> Box(
                            modifier = Modifier.fillMaxSize().padding(bottom = libraryDockClearance),
                        ) {
                            FontLibraryRoute(
                                style = appearance.uiStyle,
                                state = viewModel.toFontLibraryUiState(),
                                actions = libraryActions,
                                topActions = {
                                    NativeImportOverlay(
                                        viewModel = viewModel,
                                        style = appearance.uiStyle,
                                        modifier = Modifier.fillMaxWidth(),
                                        embedded = true,
                                    )
                                },
                            )
                        }
""",
)
replace_once(
    SHELL,
    """            if (page == AppPage.Library || page == AppPage.Studio) {
""",
    """            if (page == AppPage.Studio) {
""",
)
replace_once(
    SHELL,
    """    val shape = if (floating) RoundedCornerShape(34.dp) else RoundedCornerShape(topStart = 34.dp, topEnd = 34.dp)
""",
    """    val shape = if (floating) RoundedCornerShape(30.dp) else RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp)
""",
)
replace_once(
    SHELL,
    """            .then(if (floating) Modifier.padding(horizontal = 16.dp).padding(bottom = bottomInset + 10.dp) else Modifier)
            .fillMaxWidth()
            .shadow(if (floating) 22.dp else 8.dp, shape, clip = false)
""",
    """            .then(if (floating) Modifier.padding(horizontal = 14.dp).padding(bottom = bottomInset + 8.dp) else Modifier)
            .fillMaxWidth()
            .shadow(if (floating) 14.dp else 6.dp, shape, clip = false)
""",
)
replace_once(
    SHELL,
    """            .border(1.dp, if (dark) Color.White.copy(alpha = .12f) else Color.White.copy(alpha = .82f), shape)
            .padding(start = 6.dp, top = 7.dp, end = 6.dp, bottom = if (floating) 7.dp else bottomInset + 7.dp),
""",
    """            .border(1.dp, if (dark) Color.White.copy(alpha = .10f) else Color.White.copy(alpha = .62f), shape)
            .padding(start = 5.dp, top = 5.dp, end = 5.dp, bottom = if (floating) 5.dp else bottomInset + 5.dp),
""",
)
replace_once(
    SHELL,
    """                .offset(x = indicatorX + 4.dp)
                .width(itemWidth - 8.dp)
                .height(58.dp)
                .clip(RoundedCornerShape(24.dp))
                .background(
                    Brush.linearGradient(
                        listOf(
                            scheme.primary.copy(alpha = if (dark) .28f else .20f),
                            scheme.tertiary.copy(alpha = if (dark) .20f else .13f),
                        ),
                    ),
                ),
""",
    """                .offset(x = indicatorX + 6.dp)
                .width(itemWidth - 12.dp)
                .height(54.dp)
                .clip(RoundedCornerShape(20.dp))
                .background(scheme.primary.copy(alpha = if (dark) .20f else .12f)),
""",
)
replace_once(
    SHELL,
    """                        .height(58.dp)
                        .clip(RoundedCornerShape(24.dp))
""",
    """                        .height(54.dp)
                        .clip(RoundedCornerShape(20.dp))
""",
)
replace_once(
    SHELL,
    """                        modifier = Modifier.size(if (selected) 22.dp else 20.dp),
""",
    """                        modifier = Modifier.size(if (selected) 21.dp else 19.dp),
""",
)

test_script = r"""#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
MIUIX="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryScreenMiuix.kt"
MATERIAL="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryScreenMaterial.kt"
ROUTE="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryRoute.kt"
OVERLAY="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportOverlay.kt"
SHELL="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuAppShell.kt"

grep -q 'private fun MiuixCapabilityStrip' "$MIUIX"
grep -q 'label = "查看详情"' "$MIUIX"
grep -q 'label = "应用字体"' "$MIUIX"
grep -q 'maxLines = 1' "$MIUIX"
grep -q 'softWrap = false' "$MIUIX"
grep -q 'topActions()' "$MIUIX"
grep -q 'topActions()' "$MATERIAL"
grep -q 'topActions: @Composable' "$ROUTE"
grep -q 'embedded: Boolean = false' "$OVERLAY"
grep -q 'embedded = true' "$SHELL"
grep -q 'libraryDockClearance' "$SHELL"
grep -q 'if (page == AppPage.Studio)' "$SHELL"
! grep -q 'page == AppPage.Library || page == AppPage.Studio' "$SHELL"

CARD=$(sed -n '/private fun MiuixFontCard/,/private fun MiuixLibraryNotice/p' "$MIUIX")
printf '%s\n' "$CARD" | grep -q 'Arrangement.spacedBy(10.dp)'
printf '%s\n' "$CARD" | grep -q 'Modifier.weight(1f)'
! printf '%s\n' "$CARD" | grep -q 'Spacer(Modifier.weight(1f))'

echo 'Font library UI layout regression passed.'
"""
test_path = ROOT / "scripts/font_library_ui_layout_test.sh"
test_path.write_text(test_script, encoding="utf-8")
test_path.chmod(0o755)

replace_once(
    CHECK,
    """  scripts/auto_multiweight_mode_test.sh scripts/auto_multiweight_engine_test.sh scripts/mix_finalize_performance_test.sh scripts/rc3_audit.sh \\
""",
    """  scripts/auto_multiweight_mode_test.sh scripts/auto_multiweight_engine_test.sh scripts/mix_finalize_performance_test.sh scripts/font_library_ui_layout_test.sh scripts/rc3_audit.sh \\
""",
)
replace_once(
    CHECK,
    """sh "$ROOT/scripts/mix_finalize_performance_test.sh"
sh "$ROOT/scripts/stability_test.sh"
""",
    """sh "$ROOT/scripts/mix_finalize_performance_test.sh"
sh "$ROOT/scripts/font_library_ui_layout_test.sh"
sh "$ROOT/scripts/stability_test.sh"
""",
)

Path(__file__).unlink()
print("Font library UI cleanup applied.")
