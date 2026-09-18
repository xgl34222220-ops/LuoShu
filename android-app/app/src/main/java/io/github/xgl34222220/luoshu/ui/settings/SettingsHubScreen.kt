package io.github.xgl34222220.luoshu.ui.settings

import android.content.Intent
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.animation.core.tween
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Backup
import androidx.compose.material.icons.rounded.Build
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.ContentCopy
import androidx.compose.material.icons.rounded.ChevronRight
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.Error
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material.icons.rounded.OpenInNew
import androidx.compose.material.icons.rounded.Palette
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Restore
import androidx.compose.material.icons.rounded.Security
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material.icons.rounded.SystemUpdate
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import io.github.xgl34222220.luoshu.BuildConfig
import io.github.xgl34222220.luoshu.ui.appearance.AccentOptions
import io.github.xgl34222220.luoshu.ui.appearance.AppearanceSettings
import io.github.xgl34222220.luoshu.ui.appearance.KolorStyle
import io.github.xgl34222220.luoshu.ui.appearance.ThemeMode
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuLayoutTokens
import io.github.xgl34222220.luoshu.ui.theme.LocalDockContentPadding
import io.github.xgl34222220.luoshu.ui.theme.LuoShuDetailBar
import io.github.xgl34222220.luoshu.ui.theme.LuoShuGlyph
import io.github.xgl34222220.luoshu.ui.theme.LuoShuIconTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuTopBar
import io.github.xgl34222220.luoshu.ui.theme.LuoShuSectionHeading

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
)

private enum class SettingsSection(
    val label: String,
    val description: String,
    val icon: ImageVector,
    val opticalScale: Float,
) {
    OVERVIEW("洛书状态", "版本、Root、挂载与当前字体", Icons.Rounded.Settings, .94f),
    APPEARANCE("外观与主题", "颜色、深色模式与界面效果", Icons.Rounded.Palette, 1.00f),
    SAFETY("安全与维护", "字体加载检查、冲突与安全清理", Icons.Rounded.Security, .96f),
    GOOGLE("Google 字体兼容", "谷歌英数回退处理、状态与中文说明", Icons.Rounded.Build, .96f),
    BACKUP("备份与恢复", "完整备份洛书数据和组合方案", Icons.Rounded.Backup, 1.08f),
    UPDATE("软件更新", "稳定版、预发行版与下载说明", Icons.Rounded.SystemUpdate, 1.03f),
}

@Composable
fun AppearanceSettingsRoute(
    settings: AppearanceSettings,
    actions: AppearanceActions,
    onOpenTasks: () -> Unit = {},
    onDetailChanged: (Boolean) -> Unit = {},
) {
    SettingsHubRoute(settings, actions, onOpenTasks, onDetailChanged)
}

@Composable
internal fun SettingsHubRoute(
    settings: AppearanceSettings,
    actions: AppearanceActions,
    onOpenTasks: () -> Unit,
    onDetailChanged: (Boolean) -> Unit,
) {
    val model: SystemCenterViewModel = viewModel()
    var sectionName by rememberSaveable { mutableStateOf<String?>(null) }
    val section = sectionName?.let { runCatching { SettingsSection.valueOf(it) }.getOrNull() }
    LaunchedEffect(Unit) {
        model.refreshHealth()
        model.checkUpdate()
    }
    LaunchedEffect(section) { onDetailChanged(section != null) }
    BackHandler(enabled = section != null) { sectionName = null }

    fun openSection(item: SettingsSection) {
        sectionName = item.name
        if (item == SettingsSection.SAFETY) model.refreshHealth()
        if (item == SettingsSection.UPDATE) model.checkUpdate()
    }

    AnimatedContent(
        targetState = section,
        modifier = Modifier.fillMaxSize(),
        transitionSpec = {
            if (targetState != null) {
                (fadeIn(tween(250)) + slideInHorizontally(tween(340)) { it })
                    .togetherWith(
                        fadeOut(tween(210), targetAlpha = .52f) + slideOutHorizontally(tween(340)) { -it / 7 },
                    )
            } else {
                (fadeIn(tween(230)) + slideInHorizontally(tween(340)) { -it / 7 })
                    .togetherWith(fadeOut(tween(210)) + slideOutHorizontally(tween(340)) { it })
            }
        },
        label = "settingsDetailTransition",
    ) { target ->
        if (target == null) {
            SettingsHome(
                model = model,
                onOpenSection = ::openSection,
                onOpenTasks = onOpenTasks,
            )
        } else {
            val detailShape = RoundedCornerShape(topStart = 32.dp, bottomStart = 32.dp)
            Column(
                Modifier
                    .fillMaxSize()
                    .navigationBarsPadding()
                    .padding(start = if (settings.uiStyle == UiStyle.MIUIX) 6.dp else 0.dp)
                    .then(
                        if (settings.uiStyle == UiStyle.MIUIX) {
                            Modifier
                                .shadow(22.dp, detailShape, clip = false)
                                .clip(detailShape)
                                .background(LocalMiuixTokens.current.pageBackground)
                        } else {
                            Modifier
                        },
                    ),
            ) {
                LuoShuDetailBar(title = target.label, onBack = { sectionName = null })
                Box(Modifier.weight(1f)) {
                    when (target) {
                        SettingsSection.OVERVIEW -> OverviewPage(model)
                        SettingsSection.APPEARANCE -> AppearancePage(settings, actions)
                        SettingsSection.SAFETY -> SafetyPage(model, settings.uiStyle)
                        SettingsSection.GOOGLE -> GoogleFontCompatibilityPage()
                        SettingsSection.BACKUP -> pageList { item { FullBackupCard(settings, actions) } }
                        SettingsSection.UPDATE -> UpdatePage(model)
                    }
                }
            }
        }
    }
}

@Composable
private fun SettingsHome(
    model: SystemCenterViewModel,
    onOpenSection: (SettingsSection) -> Unit,
    onOpenTasks: () -> Unit,
) {
    val tokens = LocalMiuixTokens.current
    val h = model.health
    val bottom = maxOf(LocalDockContentPadding.current, LuoShuLayoutTokens.FloatingDockSafeBottom)
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(
            start = LuoShuLayoutTokens.PageHorizontal,
            top = 0.dp,
            end = LuoShuLayoutTokens.PageHorizontal,
            bottom = bottom,
        ),
        verticalArrangement = Arrangement.spacedBy(LuoShuLayoutTokens.ItemGap),
    ) {
        item { LuoShuTopBar("设置") }
        item {
            SettingsOverviewCard(h) { onOpenSection(SettingsSection.OVERVIEW) }
        }
        item { LuoShuSectionHeading("你的洛书", "调整喜欢的样子，查看每次字体任务") }
        item {
            SettingsGroup {
                SettingsNavigationRow(
                    section = SettingsSection.APPEARANCE,
                    onClick = { onOpenSection(SettingsSection.APPEARANCE) },
                )
                SettingsDivider()
                SettingsNavigationRow(
                    icon = Icons.Rounded.Description,
                    iconScale = .96f,
                    title = "任务与日志",
                    subtitle = "任务进度、失败记录与运行日志",
                    onClick = onOpenTasks,
                )
            }
        }
        item { LuoShuSectionHeading("管理与维护") }
        item {
            SettingsGroup {
                SettingsNavigationRow(
                    section = SettingsSection.SAFETY,
                    onClick = { onOpenSection(SettingsSection.SAFETY) },
                )
                SettingsDivider()
                SettingsNavigationRow(
                    section = SettingsSection.GOOGLE,
                    onClick = { onOpenSection(SettingsSection.GOOGLE) },
                )
                SettingsDivider()
                SettingsNavigationRow(
                    section = SettingsSection.BACKUP,
                    onClick = { onOpenSection(SettingsSection.BACKUP) },
                )
                SettingsDivider()
                SettingsNavigationRow(
                    section = SettingsSection.UPDATE,
                    subtitle = model.updateInfo.version.takeIf { model.updateInfo.hasUpdate }
                        ?.let { "新版本 $it 可用" }
                        ?: SettingsSection.UPDATE.description,
                    onClick = { onOpenSection(SettingsSection.UPDATE) },
                )
            }
        }
        item {
            Column(
                Modifier.fillMaxWidth().padding(vertical = 8.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Text("洛书 · ${BuildConfig.VERSION_NAME}", color = tokens.textSecondary, fontSize = 12.sp)
                Text("让每一行文字，都有你的风格", color = tokens.textSecondary, fontSize = 12.sp)
            }
        }
    }
}

@Composable
private fun SettingsOverviewCard(health: SystemHealthSnapshot, onClick: () -> Unit) {
    val tokens = LocalMiuixTokens.current
    val accent = when {
        health.loading -> MaterialTheme.colorScheme.primary
        health.level == HealthLevel.ERROR -> MaterialTheme.colorScheme.error
        health.level == HealthLevel.WARNING -> tokens.warning
        else -> tokens.success
    }
    Surface(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(28.dp),
        color = tokens.cardBackground,
        shadowElevation = 1.dp,
    ) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(52.dp),
                    shape = RoundedCornerShape(18.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = .10f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text("洛", color = MaterialTheme.colorScheme.primary, fontSize = 25.sp, fontWeight = FontWeight.SemiBold)
                    }
                }
                Spacer(Modifier.width(14.dp))
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text("洛书状态", color = tokens.textPrimary, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                    Text(
                        if (health.loading) "正在读取模块状态…" else health.summary,
                        color = accent,
                        fontSize = 12.sp,
                        lineHeight = 18.sp,
                    )
                }
                Icon(Icons.Rounded.ChevronRight, null, tint = tokens.textSecondary, modifier = Modifier.size(22.dp))
            }
            Surface(shape = RoundedCornerShape(16.dp), color = MaterialTheme.colorScheme.primary.copy(alpha = .045f)) {
                Column(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp)) {
                    Text("当前字体", color = tokens.textSecondary, fontSize = 12.sp)
                    Spacer(Modifier.height(3.dp))
                    Text(
                        if (health.loading) "正在读取…" else if (health.activeFont == "default") "系统默认" else health.activeFont.ifBlank { "尚未选择" },
                        color = tokens.textPrimary,
                        fontSize = 16.sp,
                        lineHeight = 22.sp,
                        fontWeight = FontWeight.Medium,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    if (health.rebootRequired) {
                        Spacer(Modifier.height(5.dp))
                        Text("字体变更等待重启生效", color = MaterialTheme.colorScheme.primary, fontSize = 12.sp)
                    }
                }
            }
        }
    }
}

@Composable
private fun SettingsGroup(content: @Composable () -> Unit) {
    val tokens = LocalMiuixTokens.current
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(24.dp),
        color = tokens.cardBackground,
        tonalElevation = 0.dp,
        shadowElevation = 0.dp,
    ) {
        Column { content() }
    }
}

@Composable
private fun SettingsDivider() {
    HorizontalDivider(
        modifier = Modifier.padding(start = 74.dp, end = 18.dp),
        color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = .20f),
    )
}

@Composable
private fun SettingsNavigationRow(
    section: SettingsSection,
    subtitle: String = section.description,
    onClick: () -> Unit,
) = SettingsNavigationRow(
    icon = section.icon,
    iconScale = section.opticalScale,
    title = section.label,
    subtitle = subtitle,
    onClick = onClick,
)

@Composable
private fun SettingsNavigationRow(
    icon: ImageVector,
    iconScale: Float,
    title: String,
    subtitle: String,
    onClick: () -> Unit,
) {
    val tokens = LocalMiuixTokens.current
    Surface(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth(),
        color = androidx.compose.ui.graphics.Color.Transparent,
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().heightIn(min = 80.dp).padding(horizontal = 16.dp, vertical = 15.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Surface(
                modifier = Modifier.size(42.dp),
                shape = RoundedCornerShape(13.dp),
                color = MaterialTheme.colorScheme.primary.copy(alpha = .10f),
                contentColor = MaterialTheme.colorScheme.primary,
            ) {
                Box(contentAlignment = Alignment.Center) {
                    LuoShuGlyph(
                        imageVector = icon,
                        contentDescription = null,
                        size = LuoShuIconTokens.SectionGlyph,
                        opticalScale = iconScale,
                    )
                }
            }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(title, color = tokens.textPrimary, fontSize = 16.sp, lineHeight = 22.sp, fontWeight = FontWeight.Medium)
                Text(
                    subtitle,
                    color = tokens.textSecondary,
                    fontSize = 12.sp,
                    lineHeight = 18.sp,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Spacer(Modifier.width(8.dp))
            LuoShuGlyph(
                imageVector = Icons.Rounded.ChevronRight,
                contentDescription = null,
                size = LuoShuIconTokens.TrailingGlyph,
                tint = tokens.textSecondary.copy(alpha = .66f),
            )
        }
    }
}

@Composable
private fun pageList(content: androidx.compose.foundation.lazy.LazyListScope.() -> Unit) {
    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 20.dp, top = 8.dp, end = 20.dp, bottom = 32.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
        content = content,
    )
}

@Composable
private fun OverviewPage(model: SystemCenterViewModel) = pageList {
    val h = model.health
    item {
        StatusCard("洛书状态", h.summary, h.level, h.loading) {
            InfoLine("App", BuildConfig.VERSION_NAME)
            InfoLine("模块", h.moduleVersion.ifBlank { if (h.modulePresent) "已安装" else "未检测到" })
            InfoLine("Root", h.rootManager)
            InfoLine("挂载", mountSummary(h))
            InfoLine("当前字体", if (h.activeFont == "default") "系统默认" else h.activeFont)
        }
    }
    item {
        SettingCard("需要关注") {
            val notices = buildList {
                if (h.rebootRequired) add("存在等待重启后生效的字体变更")
                if (h.lockState == "stale") add("检测到失效字体切换锁，可在安全页一键清理")
                if (h.cachePending) add("设备字体缓存仍在等待完成")
                if (h.selfMountState == "degraded") add("洛书自挂载正在使用 OverlayFS + Bind 降级路径")
                if (h.conflicts.isNotEmpty()) add("发现 ${h.conflicts.size} 个其它模块字体覆盖目标")
                if (h.recentErrors > 0) add("最近日志中有 ${h.recentErrors} 条错误记录")
            }
            if (notices.isEmpty()) Text("暂未发现需要处理的提醒", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
            else notices.forEach { NoticeLine(it) }
        }
    }
}

@Composable
private fun AppearancePage(settings: AppearanceSettings, actions: AppearanceActions) = pageList {
    item {
        SettingCard("外观预览") {
            Text("让文字更悦目", color = MaterialTheme.colorScheme.primary, fontSize = 24.sp, lineHeight = 32.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(5.dp))
            Text("Aa 0123456789 · 洛书", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 15.sp, lineHeight = 22.sp)
            Spacer(Modifier.height(16.dp))
            ChoiceRow(UiStyle.entries, settings.uiStyle, { it.label }, actions.setUiStyle)
        }
    }
    item {
        SettingCard("颜色与模式") {
            Text("深色模式", fontSize = 13.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(7.dp))
            ChoiceRow(ThemeMode.entries, settings.themeMode, { it.label }, actions.setThemeMode)
            Spacer(Modifier.height(13.dp))
            Text("取色风格", fontSize = 13.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(7.dp))
            ChoiceRow(KolorStyle.entries, settings.kolorStyle, { it.label }, actions.setKolorStyle)
        }
    }
    item {
        SettingCard("主题色") {
            Text(
                if (settings.monetEnabled) "已跟随壁纸取色；关闭动态取色后可选择主题色。" else "为界面选择一种喜欢的颜色。",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 12.sp,
                lineHeight = 18.sp,
            )
            Row(
                Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).selectableGroup().padding(top = 14.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                AccentOptions.forEach { option ->
                    val active = settings.seedArgb == option.argb
                    Column(
                        Modifier.clip(RoundedCornerShape(16.dp)).selectable(
                            selected = active,
                            enabled = !settings.monetEnabled,
                            role = Role.RadioButton,
                            onClick = { actions.setSeedArgb(option.argb) },
                        ).padding(horizontal = 5.dp, vertical = 5.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        Surface(
                            modifier = Modifier.size(46.dp),
                            shape = RoundedCornerShape(16.dp),
                            color = Color(option.argb).copy(alpha = if (settings.monetEnabled) .35f else 1f),
                        ) {
                            Box(contentAlignment = Alignment.Center) {
                                if (active) Icon(Icons.Rounded.CheckCircle, null, tint = Color.White, modifier = Modifier.size(22.dp))
                            }
                        }
                        Text(option.label, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                    }
                }
            }
        }
    }
    item {
        SettingCard("视觉与显示") {
            ToggleLine("Monet 动态取色", "跟随系统壁纸强调色", settings.monetEnabled, actions.setMonetEnabled)
            ToggleLine("纯黑深色模式", "AMOLED 黑色背景", settings.amoledBlack, actions.setAmoledBlack)
            ToggleLine("玻璃半透明", "用于悬浮底栏和弹层，内容卡片保持清晰", settings.glassEnabled, actions.setGlassEnabled)
            ToggleLine("背景模糊", "模糊底栏后方经过的内容", settings.blurEnabled, actions.setBlurEnabled, settings.glassEnabled)
            ToggleLine("悬浮底栏", "关闭后贴合屏幕底部", settings.floatingDock, actions.setFloatingDock)
            ToggleLine("高刷新率", "优先同分辨率高刷新模式", settings.highRefreshRate, actions.setHighRefreshRate)
        }
    }
}

@Composable
private fun SafetyPage(model: SystemCenterViewModel, style: UiStyle) {
    val h = model.health
    val m = model.maintenance
    var confirmRestore by remember { mutableStateOf(false) }
    pageList {
        item {
            StatusCard("洛书安全体检", h.summary, h.level, h.loading) {
                if (h.error.isNotBlank()) Text(h.error, color = MaterialTheme.colorScheme.error, fontSize = 13.sp)
                else {
                    InfoLine("Root 管理器", h.rootManager)
                    InfoLine("Android API", h.androidSdk.takeIf { it > 0 }?.toString() ?: "未知")
                    InfoLine("引擎 / 模板", "${h.engineState.ifBlank { "?" }} · ${h.templateState.ifBlank { "?" }}")
                    InfoLine("字体加载", h.alignmentState.ifBlank { "待确认" })
                    InfoLine("自挂载", selfMountSummary(h))
                    InfoLine("Payload 字体", h.payloadFonts.toString())
                    InfoLine("切换锁", when (h.lockState) { "idle" -> "空闲"; "active" -> "切换中"; "stale" -> "失效残留"; else -> h.lockState })
                    InfoLine("最近日志", "${h.recentWarnings} 警告 · ${h.recentErrors} 错误")
                }
                Spacer(Modifier.height(10.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(model::refreshHealth, Modifier.weight(1f), enabled = !h.loading && !m.busy) { Icon(Icons.Rounded.Refresh, null, Modifier.size(17.dp)); Spacer(Modifier.width(5.dp)); Text("重新体检") }
                    Button(model::clearStaleState, Modifier.weight(1f), enabled = !m.busy) { Icon(Icons.Rounded.Build, null, Modifier.size(17.dp)); Spacer(Modifier.width(5.dp)); Text("安全清理") }
                }
                if (m.message.isNotBlank() || m.error.isNotBlank()) Text(m.error.ifBlank { m.message }, color = if (m.error.isNotBlank()) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary, fontSize = 13.sp)
            }
        }
        item {
            SettingCard("模块冲突检测") {
                if (h.conflicts.isEmpty()) Text("未发现其它启用模块覆盖洛书关注的字体目录或 fonts.xml。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
                else {
                    Text("发现 ${h.conflicts.size} 个覆盖目标，只报告不自动禁用。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
                    h.conflicts.forEach { ConflictLine(it) }
                }
            }
        }
        item {
            SettingCard("恢复与保护") {
                Text("将当前字体恢复为系统默认，完成后需要重启手机。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
                Spacer(Modifier.height(10.dp))
                OutlinedButton({ confirmRestore = true }, Modifier.fillMaxWidth(), enabled = !m.busy) { Icon(Icons.Rounded.Restore, null); Spacer(Modifier.width(6.dp)); Text("恢复系统默认字体") }
            }
        }
    }
    if (confirmRestore) AlertDialog(
        onDismissRequest = { confirmRestore = false },
        shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 34.dp else 28.dp),
        icon = { Icon(Icons.Rounded.Restore, null, tint = MaterialTheme.colorScheme.primary) },
        title = { Text("恢复系统默认字体？", fontWeight = FontWeight.Black) },
        text = { Text("完成后需要完整重启手机。") },
        dismissButton = { TextButton({ confirmRestore = false }) { Text("取消") } },
        confirmButton = { TextButton({ confirmRestore = false; model.restoreDefault() }) { Text("恢复", fontWeight = FontWeight.Bold) } },
    )
}

@Composable
private fun UpdatePage(model: SystemCenterViewModel) {
    val info = model.updateInfo
    val context = LocalContext.current
    fun open(url: String) { if (url.startsWith("https://")) runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) } }
    pageList {
        item {
            SettingCard("更新通道") {
                Text(if (model.updateChannel == UpdateChannel.STABLE) "只接收正式稳定版本。" else "接收 Alpha / Beta / RC，适合参与兼容性验证。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
                Spacer(Modifier.height(10.dp))
                ChoiceRow(UpdateChannel.entries, model.updateChannel, { it.label }, model::selectUpdateChannel)
            }
        }
        item {
            StatusCard("在线版本", when { info.loading -> "正在检查更新…"; info.error.isNotBlank() -> "检查失败"; info.hasUpdate -> "发现新版本 ${info.version}"; info.available -> "当前已经是最新版本"; else -> "尚未检查" }, if (info.error.isNotBlank()) HealthLevel.WARNING else HealthLevel.HEALTHY, info.loading) {
                InfoLine("当前 App", BuildConfig.VERSION_NAME)
                if (info.available) { InfoLine("在线版本", info.version); InfoLine("版本代码", info.versionCode.toString()); if (info.sha256.isNotBlank()) InfoLine("模块 SHA-256", info.sha256); if (info.appSha256.isNotBlank()) InfoLine("App SHA-256", info.appSha256) }
                if (info.error.isNotBlank()) Text(info.error, color = MaterialTheme.colorScheme.error, fontSize = 13.sp)
                Spacer(Modifier.height(10.dp))
                OutlinedButton(model::checkUpdate, Modifier.fillMaxWidth(), enabled = !info.loading) { Icon(Icons.Rounded.Refresh, null, Modifier.size(17.dp)); Spacer(Modifier.width(6.dp)); Text("检查更新") }
            }
        }
        if (info.available) item {
            SettingCard("下载与说明") {
                DownloadButton("模块 ZIP", info.zipUrl, info.sha256) { open(info.zipUrl) }
                if (info.appUrl.isNotBlank()) { Spacer(Modifier.height(8.dp)); DownloadButton("原生 App APK", info.appUrl, info.appSha256) { open(info.appUrl) } }
                if (info.changelogUrl.isNotBlank()) { Spacer(Modifier.height(8.dp)); OutlinedButton({ open(info.changelogUrl) }, Modifier.fillMaxWidth()) { Icon(Icons.Rounded.OpenInNew, null, Modifier.size(17.dp)); Spacer(Modifier.width(6.dp)); Text("查看更新说明") } }
            }
        }
    }
}

@Composable
private fun <T> ChoiceRow(entries: List<T>, selected: T, label: (T) -> String, onSelected: (T) -> Unit) {
    Row(
        Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).selectableGroup(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        entries.forEach { item ->
            val active = item == selected
            Surface(
                modifier = Modifier.clip(RoundedCornerShape(15.dp)).selectable(
                    selected = active,
                    role = Role.RadioButton,
                    onClick = { onSelected(item) },
                ),
                shape = RoundedCornerShape(15.dp),
                color = if (active) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceContainerHigh,
                contentColor = if (active) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSurfaceVariant,
            ) {
                Box(Modifier.heightIn(min = 48.dp).padding(horizontal = 16.dp, vertical = 12.dp), contentAlignment = Alignment.Center) {
                    Text(label(item), fontSize = 13.sp, fontWeight = if (active) FontWeight.SemiBold else FontWeight.Medium)
                }
            }
        }
    }
}

@Composable
private fun ToggleLine(title: String, description: String, checked: Boolean, onChange: (Boolean) -> Unit, enabled: Boolean = true) {
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).toggleable(
            value = checked,
            enabled = enabled,
            role = Role.Switch,
            onValueChange = onChange,
        ).heightIn(min = 76.dp).padding(vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f).padding(end = 12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(title, fontSize = 15.sp, lineHeight = 21.sp, fontWeight = FontWeight.Medium, color = MaterialTheme.colorScheme.onSurface.copy(alpha = if (enabled) 1f else .45f))
            Text(description, color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = if (enabled) 1f else .45f), fontSize = 12.sp, lineHeight = 18.sp)
        }
        Switch(checked = checked, onCheckedChange = null, enabled = enabled)
    }
}

@Composable
private fun SettingCard(title: String, content: @Composable () -> Unit) {
    val tokens = LocalMiuixTokens.current
    val dark = MaterialTheme.colorScheme.background.luminance() < .5f
    Card(
        shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),
        border = BorderStroke(
            0.5.dp,
            if (dark) Color.Transparent else LuoShuLayoutTokens.LightCardOutline,
        ),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
    ) {
        Column(Modifier.fillMaxWidth().padding(LuoShuLayoutTokens.CardPadding)) {
            Text(title, fontSize = 18.sp, lineHeight = 24.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(12.dp))
            content()
        }
    }
}

@Composable
private fun StatusCard(title: String, subtitle: String, level: HealthLevel, loading: Boolean, content: @Composable () -> Unit) {
    val accent = when (level) { HealthLevel.HEALTHY -> MaterialTheme.colorScheme.primary; HealthLevel.WARNING -> MaterialTheme.colorScheme.tertiary; HealthLevel.ERROR -> MaterialTheme.colorScheme.error }
    val tokens = LocalMiuixTokens.current
    val dark = MaterialTheme.colorScheme.background.luminance() < .5f
    Card(
        shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),
        border = BorderStroke(
            0.5.dp,
            if (dark) Color.Transparent else LuoShuLayoutTokens.LightCardOutline,
        ),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
    ) {
        Column(Modifier.fillMaxWidth().padding(LuoShuLayoutTokens.CardPadding)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(Modifier.size(38.dp), RoundedCornerShape(13.dp), color = accent.copy(alpha = .11f), contentColor = accent) {
                    Box(contentAlignment = Alignment.Center) { if (loading) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp) else Icon(when (level) { HealthLevel.HEALTHY -> Icons.Rounded.CheckCircle; HealthLevel.WARNING -> Icons.Rounded.Info; HealthLevel.ERROR -> Icons.Rounded.Error }, null, Modifier.size(21.dp)) }
                }
                Spacer(Modifier.width(10.dp)); Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) { Text(title, fontSize = 18.sp, lineHeight = 24.sp, fontWeight = FontWeight.SemiBold); Text(if (loading) "正在读取状态…" else subtitle, color = accent, fontSize = 12.sp, lineHeight = 18.sp) }
            }
            Spacer(Modifier.height(13.dp)); content()
        }
    }
}

private fun mountEngineLabel(value: String): String = when (value) {
    "self-mount" -> "洛书自挂载"
    "native-module-mount" -> "Root 原生挂载"
    "meta-overlayfs", "dual-dir-metamodule" -> "Meta OverlayFS"
    "hybrid-mount" -> "Hybrid Mount"
    "magic-mount", "magic-mount-rs" -> "Magic Mount"
    "mountify" -> "Mountify"
    "unknown", "" -> ""
    else -> value
}

private fun mountBackendLabel(value: String): String = when (value) {
    "self-overlay" -> "OverlayFS"
    "self-overlay-bind" -> "OverlayFS + Bind"
    "self-existing", "external-mount" -> "已接管"
    "overlayfs" -> "OverlayFS"
    "magic-mount" -> "Magic Mount"
    "mountify" -> "Mountify"
    "none", "unknown", "" -> ""
    else -> value
}

private fun mountStateLabel(value: String): String = when (value) {
    "mounted" -> "已挂载"
    "degraded" -> "降级"
    "failed" -> "失败"
    "idle" -> "待命"
    "unknown", "" -> ""
    else -> value
}

private fun mountSummary(state: SystemHealthSnapshot): String = listOf(
    mountEngineLabel(state.mountEngine),
    mountBackendLabel(state.selfMountBackend),
).filter { it.isNotBlank() }.joinToString(" · ").ifBlank { "待检测" }

private fun selfMountSummary(state: SystemHealthSnapshot): String = listOf(
    mountStateLabel(state.selfMountState),
    mountBackendLabel(state.selfMountBackend),
).filter { it.isNotBlank() }.joinToString(" · ").ifBlank { "待确认" }

@Composable
private fun InfoLine(label: String, value: String) {
    val technical = label.contains("SHA", ignoreCase = true) || label.endsWith(" ID")
    val scheme = MaterialTheme.colorScheme
    Row(
        Modifier.fillMaxWidth().padding(vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, color = scheme.onSurfaceVariant, fontSize = 13.sp)
        Spacer(Modifier.width(12.dp))
        if (technical && value.isNotBlank()) {
            val clipboard = LocalClipboardManager.current
            Surface(
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(12.dp),
                color = if (scheme.background.luminance() < .5f) {
                    scheme.surfaceContainerHigh
                } else {
                    LuoShuLayoutTokens.TechnicalSurface
                },
                border = BorderStroke(0.5.dp, scheme.outlineVariant.copy(alpha = .42f)),
            ) {
                Row(
                    modifier = Modifier.padding(start = 10.dp, top = 6.dp, bottom = 6.dp, end = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        value,
                        modifier = Modifier.weight(1f),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        fontSize = 12.sp,
                        lineHeight = 18.sp,
                        fontFamily = FontFamily.Monospace,
                    )
                    IconButton(
                        onClick = { clipboard.setText(AnnotatedString(value)) },
                        modifier = Modifier.size(34.dp),
                    ) {
                        Icon(
                            Icons.Rounded.ContentCopy,
                            contentDescription = "复制 $label",
                            modifier = Modifier.size(16.dp),
                            tint = scheme.onSurfaceVariant,
                        )
                    }
                }
            }
        } else {
            Text(
                value.ifBlank { "—" },
                Modifier.weight(1f),
                textAlign = TextAlign.End,
                maxLines = 3,
                overflow = TextOverflow.Ellipsis,
                fontSize = 13.sp,
                lineHeight = 19.sp,
                fontWeight = FontWeight.Medium,
            )
        }
    }
}

@Composable
private fun NoticeLine(text: String) = Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.Top) { Icon(Icons.Rounded.Info, null, tint = MaterialTheme.colorScheme.tertiary, modifier = Modifier.size(16.dp)); Spacer(Modifier.width(7.dp)); Text(text, Modifier.weight(1f), fontSize = 13.sp) }

@Composable
private fun ConflictLine(c: ModuleConflict) = Surface(Modifier.fillMaxWidth().padding(vertical = 4.dp), RoundedCornerShape(18.dp), color = MaterialTheme.colorScheme.errorContainer.copy(alpha = .48f)) {
    Column(Modifier.fillMaxWidth().padding(11.dp)) { Text(c.moduleName, fontSize = 12.sp, fontWeight = FontWeight.Black); Text("${c.moduleId} · ${c.target}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp, maxLines = 2, overflow = TextOverflow.Ellipsis); Text(if (c.type == "directory") "目录覆盖 · ${c.fileCount} 个字体/配置文件" else "配置文件覆盖", color = MaterialTheme.colorScheme.error, fontSize = 12.sp, fontWeight = FontWeight.Bold) }
}

@Composable
private fun DownloadButton(label: String, url: String, sha: String, onClick: () -> Unit) = Button(
    onClick = onClick,
    modifier = Modifier.fillMaxWidth().heightIn(min = 64.dp),
    enabled = url.startsWith("https://"),
    shape = RoundedCornerShape(18.dp),
) {
    Icon(Icons.Rounded.OpenInNew, null, Modifier.size(18.dp))
    Spacer(Modifier.width(9.dp))
    Column(Modifier.weight(1f), verticalArrangement = Arrangement.Center) {
        Text(label, fontSize = 15.sp, lineHeight = 22.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
        if (sha.isNotBlank()) {
            Text(
                "SHA-256 ${sha.take(16)}…",
                color = MaterialTheme.colorScheme.onPrimary.copy(alpha = .78f),
                fontSize = 12.sp,
                lineHeight = 18.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}
