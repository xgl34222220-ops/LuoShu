package io.github.xgl34222220.luoshu.ui.settings

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material.icons.rounded.Layers
import androidx.compose.material.icons.rounded.Palette
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.BuildConfig
import io.github.xgl34222220.luoshu.ui.appearance.AccentOptions
import io.github.xgl34222220.luoshu.ui.appearance.AppearanceSettings
import io.github.xgl34222220.luoshu.ui.appearance.KolorStyle
import io.github.xgl34222220.luoshu.ui.appearance.ThemeMode
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import top.yukonga.miuix.kmp.basic.BasicComponent
import top.yukonga.miuix.kmp.basic.Button
import top.yukonga.miuix.kmp.basic.Card
import top.yukonga.miuix.kmp.basic.Icon
import top.yukonga.miuix.kmp.basic.Text
import top.yukonga.miuix.kmp.preference.RadioButtonLocation
import top.yukonga.miuix.kmp.preference.RadioButtonPreference
import top.yukonga.miuix.kmp.preference.SwitchPreference
import top.yukonga.miuix.kmp.theme.MiuixTheme

@Composable
internal fun AppearanceSettingsMiuix(
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
                (slideInHorizontally { it } + fadeIn())
                    .togetherWith(slideOutHorizontally { -it / 7 } + fadeOut())
            } else {
                (slideInHorizontally { -it / 7 } + fadeIn())
                    .togetherWith(slideOutHorizontally { it } + fadeOut())
            }
        },
        label = "miuixSettingsTransition",
    ) { detail ->
        if (detail) {
            MiuixThemeSettingsPage(
                settings = settings,
                actions = actions,
                onBack = onCloseThemeSettings,
            )
        } else {
            MiuixSettingsOverviewPage(
                settings = settings,
                actions = actions,
                onOpenThemeSettings = onOpenThemeSettings,
            )
        }
    }
}

@Composable
private fun MiuixSettingsOverviewPage(
    settings: AppearanceSettings,
    actions: AppearanceActions,
    onOpenThemeSettings: () -> Unit,
) {
    val colors = MiuixTheme.colorScheme
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .background(colors.background),
        contentPadding = PaddingValues(start = 16.dp, top = 18.dp, end = 16.dp, bottom = 112.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            MiuixSettingsHeader(
                title = "设置",
                subtitle = "外观、任务与显示偏好",
                icon = Icons.Rounded.Settings,
            )
        }

        item { MiuixSettingsSectionTitle("常用") }
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                BasicComponent(
                    title = "主题设置",
                    summary = "${settings.uiStyle.label} · ${settings.themeMode.label}\nMonet、深色模式与玻璃材质",
                    startAction = { MiuixSettingsIcon(Icons.Rounded.Palette) },
                    onClick = onOpenThemeSettings,
                )
                BasicComponent(
                    title = "任务中心",
                    summary = "查看字体任务、问题与诊断日志",
                    startAction = { MiuixSettingsIcon(Icons.Rounded.Description) },
                    onClick = actions.openTaskCenter,
                )
            }
        }

        item { MiuixSettingsSectionTitle("显示与性能") }
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                SwitchPreference(
                    title = "高刷新率",
                    summary = "优先使用同分辨率高刷新率，省电模式下自动停用",
                    checked = settings.highRefreshRate,
                    onCheckedChange = actions.setHighRefreshRate,
                )
                SwitchPreference(
                    title = "悬浮玻璃底栏",
                    summary = "一级页面保持统一四项导航和手势安全区",
                    checked = settings.floatingDock,
                    onCheckedChange = actions.setFloatingDock,
                )
            }
        }

        item { MiuixSettingsSectionTitle("关于") }
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                BasicComponent(
                    title = "洛书",
                    summary = "Android 无 Hook 全局字体引擎\nv${BuildConfig.VERSION_NAME}",
                    startAction = { MiuixSettingsIcon(Icons.Rounded.Info) },
                )
                BasicComponent(
                    title = "双界面系统",
                    summary = "MIUIX 与 Material 3 独立渲染，共享字体业务层",
                    startAction = { MiuixSettingsIcon(Icons.Rounded.Layers) },
                )
            }
        }
    }
}

@Composable
private fun MiuixThemeSettingsPage(
    settings: AppearanceSettings,
    actions: AppearanceActions,
    onBack: () -> Unit,
) {
    val colors = MiuixTheme.colorScheme
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .background(colors.background),
        contentPadding = PaddingValues(start = 16.dp, top = 18.dp, end = 16.dp, bottom = 112.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Button(onClick = onBack) {
                    Icon(
                        imageVector = Icons.AutoMirrored.Rounded.ArrowBack,
                        contentDescription = null,
                        modifier = Modifier.size(21.dp),
                    )
                }
                Spacer(Modifier.size(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        text = "主题设置",
                        fontSize = 30.sp,
                        fontWeight = FontWeight.Bold,
                        color = colors.onBackground,
                    )
                    Text(
                        text = "MIUIX 与 Material 3 分别渲染",
                        fontSize = 13.sp,
                        color = colors.onSurfaceSecondary,
                    )
                }
            }
        }

        item { MiuixSettingsSectionTitle("界面风格") }
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                UiStyle.entries.forEach { option ->
                    RadioButtonPreference(
                        title = option.label,
                        summary = when (option) {
                            UiStyle.MIUIX -> "HyperOS 风格原生 Miuix 控件"
                            UiStyle.MATERIAL -> "标准 Material 3 控件与自适应布局"
                        },
                        selected = settings.uiStyle == option,
                        onClick = { actions.setUiStyle(option) },
                        radioButtonLocation = RadioButtonLocation.End,
                    )
                }
            }
        }

        item { MiuixSettingsSectionTitle("主题模式") }
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                ThemeMode.entries.forEach { option ->
                    RadioButtonPreference(
                        title = option.label,
                        selected = settings.themeMode == option,
                        onClick = { actions.setThemeMode(option) },
                        radioButtonLocation = RadioButtonLocation.End,
                    )
                }
            }
        }

        item { MiuixSettingsSectionTitle("颜色") }
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                SwitchPreference(
                    title = "使用 Monet 取色",
                    summary = "从系统壁纸提取语义色，对比不足时回退洛书蓝",
                    checked = settings.monetEnabled,
                    onCheckedChange = actions.setMonetEnabled,
                )
                AccentOptions.forEach { option ->
                    RadioButtonPreference(
                        title = option.label,
                        summary = if (settings.monetEnabled) "关闭 Monet 后可选" else "固定强调色",
                        selected = settings.seedArgb == option.argb,
                        onClick = { actions.setSeedArgb(option.argb) },
                        enabled = !settings.monetEnabled,
                        radioButtonLocation = RadioButtonLocation.End,
                        startAction = {
                            Spacer(
                                modifier = Modifier
                                    .padding(end = 12.dp)
                                    .size(30.dp)
                                    .background(Color(option.argb), RoundedCornerShape(11.dp)),
                            )
                        },
                    )
                }
            }
        }

        item { MiuixSettingsSectionTitle("色彩风格") }
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                KolorStyle.entries.forEach { option ->
                    RadioButtonPreference(
                        title = option.label,
                        summary = kolorStyleSummary(option),
                        selected = settings.kolorStyle == option,
                        onClick = { actions.setKolorStyle(option) },
                        radioButtonLocation = RadioButtonLocation.End,
                    )
                }
            }
        }

        item { MiuixSettingsSectionTitle("深色与材质") }
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                SwitchPreference(
                    title = "纯黑模式",
                    summary = "深色模式下使用 AMOLED 黑色背景",
                    checked = settings.amoledBlack,
                    onCheckedChange = actions.setAmoledBlack,
                )
                SwitchPreference(
                    title = "玻璃效果",
                    summary = "只用于悬浮底栏和临时浮层，主体卡片保持实色",
                    checked = settings.glassEnabled,
                    onCheckedChange = actions.setGlassEnabled,
                )
                SwitchPreference(
                    title = "背景模糊",
                    summary = "关闭后自动使用半透明实色与细描边",
                    checked = settings.blurEnabled,
                    onCheckedChange = actions.setBlurEnabled,
                    enabled = settings.glassEnabled,
                )
                SwitchPreference(
                    title = "悬浮底栏",
                    summary = "距系统手势区保留安全间距",
                    checked = settings.floatingDock,
                    onCheckedChange = actions.setFloatingDock,
                )
            }
        }
    }
}

@Composable
private fun MiuixSettingsHeader(
    title: String,
    subtitle: String,
    icon: ImageVector,
) {
    val colors = MiuixTheme.colorScheme
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                text = title,
                fontSize = 34.sp,
                fontWeight = FontWeight.Bold,
                color = colors.onBackground,
            )
            Text(
                text = subtitle,
                fontSize = 14.sp,
                color = colors.onSurfaceSecondary,
            )
        }
        Card {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = colors.primary,
                modifier = Modifier.padding(16.dp).size(25.dp),
            )
        }
    }
}

@Composable
private fun MiuixSettingsIcon(icon: ImageVector) {
    Icon(
        imageVector = icon,
        contentDescription = null,
        tint = MiuixTheme.colorScheme.primary,
        modifier = Modifier.padding(end = 16.dp).size(24.dp),
    )
}

@Composable
private fun MiuixSettingsSectionTitle(title: String) {
    Text(
        text = title,
        color = MiuixTheme.colorScheme.onBackground,
        fontSize = 20.sp,
        fontWeight = FontWeight.Bold,
        modifier = Modifier.padding(start = 4.dp, top = 12.dp, bottom = 2.dp),
    )
}

private fun kolorStyleSummary(style: KolorStyle): String = when (style) {
    KolorStyle.SOFT -> "低饱和、柔和背景与舒适对比"
    KolorStyle.VIBRANT -> "更鲜明的强调色和状态色"
    KolorStyle.NEUTRAL -> "减少彩度，突出内容层级"
}
