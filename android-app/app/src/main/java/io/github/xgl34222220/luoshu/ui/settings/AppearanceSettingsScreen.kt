package io.github.xgl34222220.luoshu.ui.settings

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Animation
import androidx.compose.material.icons.rounded.ColorLens
import androidx.compose.material.icons.rounded.DarkMode
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material.icons.rounded.Layers
import androidx.compose.material.icons.rounded.Palette
import androidx.compose.material.icons.rounded.PhoneAndroid
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material.icons.rounded.Speed
import androidx.compose.material.icons.rounded.Style
import androidx.compose.material.icons.rounded.ViewCarousel
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import io.github.xgl34222220.luoshu.BuildConfig
import io.github.xgl34222220.luoshu.ui.appearance.AccentOptions
import io.github.xgl34222220.luoshu.ui.appearance.AppearanceSettings
import io.github.xgl34222220.luoshu.ui.appearance.KolorStyle
import io.github.xgl34222220.luoshu.ui.appearance.ThemeMode
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.design.LuoShuBackButton
import io.github.xgl34222220.luoshu.ui.design.LuoShuDivider
import io.github.xgl34222220.luoshu.ui.design.LuoShuEnterEasing
import io.github.xgl34222220.luoshu.ui.design.LuoShuExitEasing
import io.github.xgl34222220.luoshu.ui.design.LuoShuGroupCard
import io.github.xgl34222220.luoshu.ui.design.LuoShuPageHeader
import io.github.xgl34222220.luoshu.ui.design.LuoShuSectionTitle
import io.github.xgl34222220.luoshu.ui.design.LuoShuSettingRow
import io.github.xgl34222220.luoshu.ui.theme.LocalLuoShuTokens

data class AppearanceActions(
    val setUiStyle: (UiStyle) -> Unit,
    val setThemeMode: (ThemeMode) -> Unit,
    val setSeedArgb: (Int) -> Unit,
    val setKolorStyle: (KolorStyle) -> Unit,
    val setMonetEnabled: (Boolean) -> Unit,
    val setAmoledBlack: (Boolean) -> Unit,
    val setBlurEnabled: (Boolean) -> Unit,
    val setGlassEnabled: (Boolean) -> Unit,
    val setFloatingDock: (Boolean) -> Unit,
    val setHighRefreshRate: (Boolean) -> Unit,
    val openTaskCenter: () -> Unit = {},
)

@Composable
fun AppearanceSettingsRoute(
    settings: AppearanceSettings,
    actions: AppearanceActions,
    showThemeSettings: Boolean = false,
    onOpenThemeSettings: () -> Unit = {},
    onCloseThemeSettings: () -> Unit = {},
) {
    when (settings.uiStyle) {
        UiStyle.MIUIX -> AppearanceSettingsMiuix(
            settings = settings,
            actions = actions,
            showThemeSettings = showThemeSettings,
            onOpenThemeSettings = onOpenThemeSettings,
            onCloseThemeSettings = onCloseThemeSettings,
        )
        UiStyle.MATERIAL -> AppearanceSettingsMaterial(
            settings = settings,
            actions = actions,
            showThemeSettings = showThemeSettings,
            onOpenThemeSettings = onOpenThemeSettings,
            onCloseThemeSettings = onCloseThemeSettings,
        )
    }
}

@Composable
private fun AppearanceSettingsMaterial(
    settings: AppearanceSettings,
    actions: AppearanceActions,
    showThemeSettings: Boolean,
    onOpenThemeSettings: () -> Unit,
    onCloseThemeSettings: () -> Unit,
) {
    AnimatedContent(
        targetState = showThemeSettings,
        modifier = Modifier.fillMaxSize(),
        transitionSpec = {
            if (targetState) {
                (slideInHorizontally(tween(300, easing = LuoShuEnterEasing)) { it } + fadeIn(tween(180)))
                    .togetherWith(slideOutHorizontally(tween(220, easing = LuoShuExitEasing)) { -it / 8 } + fadeOut(tween(150)))
            } else {
                (slideInHorizontally(tween(260, easing = LuoShuEnterEasing)) { -it / 8 } + fadeIn(tween(170)))
                    .togetherWith(slideOutHorizontally(tween(220, easing = LuoShuExitEasing)) { it } + fadeOut(tween(150)))
            }
        },
        label = "settingsDetailTransition",
    ) { detail ->
        if (detail) {
            ThemeSettingsPage(settings, actions, onCloseThemeSettings)
        } else {
            SettingsOverviewPage(settings, actions, onOpenThemeSettings)
        }
    }
}

@Composable
private fun SettingsOverviewPage(
    settings: AppearanceSettings,
    actions: AppearanceActions,
    onOpenThemeSettings: () -> Unit,
) {
    val tokens = LocalLuoShuTokens.current
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(
            start = tokens.pagePadding,
            top = 2.dp,
            end = tokens.pagePadding,
            bottom = 112.dp,
        ),
        verticalArrangement = Arrangement.spacedBy(tokens.compactGap),
    ) {
        item {
            LuoShuPageHeader(
                title = "设置",
                subtitle = "外观、任务与显示偏好",
                actions = {
                    Surface(
                        modifier = Modifier.size(48.dp),
                        shape = RoundedCornerShape(tokens.fieldRadius),
                        color = MaterialTheme.colorScheme.primary.copy(alpha = .10f),
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            androidx.compose.material3.Icon(
                                Icons.Rounded.Settings,
                                contentDescription = null,
                                tint = MaterialTheme.colorScheme.primary,
                            )
                        }
                    }
                },
            )
        }

        item { LuoShuSectionTitle("常用") }
        item {
            LuoShuGroupCard {
                Column {
                    LuoShuSettingRow(
                        icon = Icons.Rounded.Palette,
                        title = "主题设置",
                        description = "Miuix、Material 3、Monet 与深色模式",
                        value = "${settings.uiStyle.label} · ${settings.themeMode.label}",
                        showChevron = true,
                        onClick = onOpenThemeSettings,
                    )
                    LuoShuDivider(Modifier.padding(start = 64.dp))
                    LuoShuSettingRow(
                        icon = Icons.Rounded.Description,
                        title = "任务中心",
                        description = "查看字体任务、问题与诊断日志",
                        value = "查看",
                        showChevron = true,
                        onClick = actions.openTaskCenter,
                    )
                }
            }
        }

        item { LuoShuSectionTitle("显示与性能") }
        item {
            LuoShuGroupCard {
                Column {
                    LuoShuSettingRow(
                        icon = Icons.Rounded.Speed,
                        title = "高刷新率",
                        description = "优先使用同分辨率高刷新率，省电模式下自动停用",
                        trailing = {
                            Switch(
                                checked = settings.highRefreshRate,
                                onCheckedChange = actions.setHighRefreshRate,
                            )
                        },
                    )
                    LuoShuDivider(Modifier.padding(start = 64.dp))
                    LuoShuSettingRow(
                        icon = Icons.Rounded.ViewCarousel,
                        title = "悬浮玻璃底栏",
                        description = "一级页面保持统一四项导航和安全区",
                        trailing = {
                            Switch(
                                checked = settings.floatingDock,
                                onCheckedChange = actions.setFloatingDock,
                            )
                        },
                    )
                }
            }
        }

        item { LuoShuSectionTitle("关于") }
        item {
            LuoShuGroupCard {
                Column {
                    LuoShuSettingRow(
                        icon = Icons.Rounded.Info,
                        title = "洛书",
                        description = "Android 无 Hook 全局字体引擎",
                        value = "v${BuildConfig.VERSION_NAME}",
                    )
                    LuoShuDivider(Modifier.padding(start = 64.dp))
                    LuoShuSettingRow(
                        icon = Icons.Rounded.Layers,
                        title = "统一界面系统",
                        description = "MIUIX × Material 3 × Monet × Glass",
                        value = "V1.1",
                    )
                }
            }
        }
    }
}

@Composable
private fun ThemeSettingsPage(
    settings: AppearanceSettings,
    actions: AppearanceActions,
    onBack: () -> Unit,
) {
    val tokens = LocalLuoShuTokens.current
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(
            start = tokens.pagePadding,
            top = 2.dp,
            end = tokens.pagePadding,
            bottom = 112.dp,
        ),
        verticalArrangement = Arrangement.spacedBy(tokens.compactGap),
    ) {
        item {
            LuoShuPageHeader(
                title = "主题设置",
                subtitle = "同一业务层，两套独立系统级控件",
                leading = { LuoShuBackButton(onBack) },
            )
        }

        item { LuoShuSectionTitle("界面风格") }
        item {
            LuoShuGroupCard(contentPadding = 12.dp) {
                ChoiceRow(
                    values = UiStyle.entries,
                    selected = settings.uiStyle,
                    label = { it.label },
                    onSelect = actions.setUiStyle,
                )
            }
        }

        item { LuoShuSectionTitle("主题模式") }
        item {
            LuoShuGroupCard(contentPadding = 12.dp) {
                ChoiceRow(
                    values = ThemeMode.entries,
                    selected = settings.themeMode,
                    label = { it.label },
                    onSelect = actions.setThemeMode,
                )
            }
        }

        item { LuoShuSectionTitle("颜色") }
        item {
            LuoShuGroupCard {
                Column {
                    LuoShuSettingRow(
                        icon = Icons.Rounded.ColorLens,
                        title = "使用 Monet 取色",
                        description = "从系统壁纸提取语义色，对比不足时回退洛书蓝",
                        trailing = {
                            Switch(
                                checked = settings.monetEnabled,
                                onCheckedChange = actions.setMonetEnabled,
                            )
                        },
                    )
                    LuoShuDivider(Modifier.padding(start = 64.dp))
                    Column(Modifier.padding(horizontal = 14.dp, vertical = 12.dp)) {
                        Text("固定强调色", color = tokens.textPrimary, style = MaterialTheme.typography.titleSmall)
                        Text(
                            if (settings.monetEnabled) "关闭 Monet 后可选" else "当前：${settings.accent.label}",
                            color = tokens.textSecondary,
                            style = MaterialTheme.typography.bodySmall,
                        )
                        Spacer(Modifier.height(10.dp))
                        AccentSelector(settings, actions.setSeedArgb, enabled = !settings.monetEnabled)
                    }
                    LuoShuDivider(Modifier.padding(start = 64.dp))
                    Column(Modifier.padding(horizontal = 14.dp, vertical = 12.dp)) {
                        Text("色彩风格", color = tokens.textPrimary, style = MaterialTheme.typography.titleSmall)
                        Spacer(Modifier.height(10.dp))
                        ChoiceRow(
                            values = KolorStyle.entries,
                            selected = settings.kolorStyle,
                            label = { it.label },
                            onSelect = actions.setKolorStyle,
                        )
                    }
                }
            }
        }

        item { LuoShuSectionTitle("深色与材质") }
        item {
            LuoShuGroupCard {
                Column {
                    ThemeSwitchRow(
                        icon = Icons.Rounded.DarkMode,
                        title = "纯黑模式",
                        description = "深色模式下使用 AMOLED 黑色背景",
                        checked = settings.amoledBlack,
                        onCheckedChange = actions.setAmoledBlack,
                    )
                    LuoShuDivider(Modifier.padding(start = 64.dp))
                    ThemeSwitchRow(
                        icon = Icons.Rounded.Style,
                        title = "玻璃效果",
                        description = "只用于悬浮底栏和临时浮层，主体卡片保持实色",
                        checked = settings.glassEnabled,
                        onCheckedChange = actions.setGlassEnabled,
                    )
                    LuoShuDivider(Modifier.padding(start = 64.dp))
                    ThemeSwitchRow(
                        icon = Icons.Rounded.Animation,
                        title = "背景模糊",
                        description = "低性能设备关闭后自动使用半透明实色与细描边",
                        checked = settings.blurEnabled,
                        enabled = settings.glassEnabled,
                        onCheckedChange = actions.setBlurEnabled,
                    )
                    LuoShuDivider(Modifier.padding(start = 64.dp))
                    ThemeSwitchRow(
                        icon = Icons.Rounded.PhoneAndroid,
                        title = "悬浮底栏",
                        description = "距系统手势区保留安全间距",
                        checked = settings.floatingDock,
                        onCheckedChange = actions.setFloatingDock,
                    )
                }
            }
        }
    }
}

@Composable
private fun ThemeSwitchRow(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    title: String,
    description: String,
    checked: Boolean,
    enabled: Boolean = true,
    onCheckedChange: (Boolean) -> Unit,
) {
    LuoShuSettingRow(
        icon = icon,
        title = title,
        description = description,
        enabled = enabled,
        trailing = {
            Switch(
                checked = checked,
                enabled = enabled,
                onCheckedChange = onCheckedChange,
            )
        },
    )
}

@Composable
private fun <T> ChoiceRow(
    values: List<T>,
    selected: T,
    label: (T) -> String,
    onSelect: (T) -> Unit,
) {
    val tokens = LocalLuoShuTokens.current
    Row(
        modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        values.forEach { value ->
            val active = value == selected
            Surface(
                modifier = Modifier
                    .height(42.dp)
                    .clickable { onSelect(value) },
                shape = RoundedCornerShape(tokens.smallRadius),
                color = if (active) MaterialTheme.colorScheme.primaryContainer else tokens.surfaceAlt,
                border = androidx.compose.foundation.BorderStroke(
                    1.dp,
                    if (active) MaterialTheme.colorScheme.primary.copy(alpha = .30f) else tokens.outline.copy(alpha = .42f),
                ),
            ) {
                Box(contentAlignment = Alignment.Center, modifier = Modifier.padding(horizontal = 16.dp)) {
                    Text(
                        label(value),
                        color = if (active) MaterialTheme.colorScheme.primary else tokens.textPrimary,
                        style = MaterialTheme.typography.labelLarge,
                    )
                }
            }
        }
    }
}

@Composable
private fun AccentSelector(
    settings: AppearanceSettings,
    onSelect: (Int) -> Unit,
    enabled: Boolean,
) {
    val tokens = LocalLuoShuTokens.current
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState())
            .alpha(if (enabled) 1f else .42f),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        AccentOptions.forEach { option ->
            val active = settings.seedArgb == option.argb
            Column(
                modifier = Modifier.clickable(enabled = enabled) { onSelect(option.argb) },
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Surface(
                    modifier = Modifier.size(if (active) 42.dp else 38.dp),
                    shape = CircleShape,
                    color = Color(option.argb),
                    border = androidx.compose.foundation.BorderStroke(
                        if (active) 3.dp else 1.dp,
                        if (active) MaterialTheme.colorScheme.onSurface else tokens.outline,
                    ),
                ) {}
                Spacer(Modifier.height(5.dp))
                Text(
                    option.label,
                    color = if (active) tokens.textPrimary else tokens.textSecondary,
                    style = MaterialTheme.typography.labelSmall,
                    textAlign = TextAlign.Center,
                )
            }
        }
    }
}
