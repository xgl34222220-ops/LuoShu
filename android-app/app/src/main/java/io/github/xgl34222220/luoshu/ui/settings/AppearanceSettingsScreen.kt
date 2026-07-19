package io.github.xgl34222220.luoshu.ui.settings

import androidx.compose.animation.core.animateDpAsState
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
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.ui.appearance.AccentOptions
import io.github.xgl34222220.luoshu.ui.appearance.AppearanceSettings
import io.github.xgl34222220.luoshu.ui.appearance.KolorStyle
import io.github.xgl34222220.luoshu.ui.appearance.ThemeMode
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens

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
)

@Composable
fun AppearanceSettingsRoute(
    settings: AppearanceSettings,
    actions: AppearanceActions,
) {
    when (settings.uiStyle) {
        UiStyle.MATERIAL -> AppearanceSettingsMaterial(settings, actions)
        UiStyle.MIUIX -> AppearanceSettingsMiuix(settings, actions)
    }
}

@Composable
private fun AppearanceSettingsMaterial(
    settings: AppearanceSettings,
    actions: AppearanceActions,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 18.dp, top = 10.dp, end = 18.dp, bottom = 132.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item { SettingsHeader("Material 3 Glass") }
        item {
            MaterialSettingCard("界面风格", "切换后整个 App 立即换皮") {
                ChoiceRow(UiStyle.entries, settings.uiStyle, { it.label }, actions.setUiStyle)
            }
        }
        item {
            MaterialSettingCard("深色模式", "跟随系统、浅色或深色") {
                ChoiceRow(ThemeMode.entries, settings.themeMode, { it.label }, actions.setThemeMode)
            }
        }
        item {
            MaterialSettingCard("取色风格", "MaterialKolor 算法色板") {
                ChoiceRow(KolorStyle.entries, settings.kolorStyle, { it.label }, actions.setKolorStyle)
            }
        }
        item {
            MaterialSettingCard("种子色", "Material 与 Miuix 共用") {
                AccentSelector(settings, actions.setSeedArgb)
            }
        }
        item {
            MaterialSettingCard("视觉效果", "动态色、纯黑和玻璃层") {
                MaterialSwitchRow("Monet 动态取色", settings.monetEnabled, actions.setMonetEnabled)
                MaterialSwitchRow("纯黑深色模式", settings.amoledBlack, actions.setAmoledBlack)
                MaterialSwitchRow("玻璃半透明", settings.glassEnabled, actions.setGlassEnabled)
                MaterialSwitchRow("背景模糊", settings.blurEnabled, actions.setBlurEnabled, settings.glassEnabled)
                MaterialSwitchRow("悬浮底栏", settings.floatingDock, actions.setFloatingDock)
            }
        }
    }
}

@Composable
private fun AppearanceSettingsMiuix(
    settings: AppearanceSettings,
    actions: AppearanceActions,
) {
    val tokens = LocalMiuixTokens.current
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, top = 10.dp, end = 16.dp, bottom = 132.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { SettingsHeader("Miuix · HyperOS") }
        item {
            MiuixSettingGroup("界面风格", "切换后整个 App 立即换皮") {
                ChoiceRow(UiStyle.entries, settings.uiStyle, { it.label }, actions.setUiStyle)
            }
        }
        item {
            MiuixSettingGroup("颜色与模式", "两套皮肤共用同一色彩配置") {
                MiuixChoiceLine("深色模式", settings.themeMode.label) {
                    ChoiceRow(ThemeMode.entries, settings.themeMode, { it.label }, actions.setThemeMode)
                }
                MiuixChoiceLine("取色风格", settings.kolorStyle.label) {
                    ChoiceRow(KolorStyle.entries, settings.kolorStyle, { it.label }, actions.setKolorStyle)
                }
                Spacer(Modifier.height(10.dp))
                AccentSelector(settings, actions.setSeedArgb)
            }
        }
        item {
            Card(
                shape = RoundedCornerShape(34.dp),
                colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),
                elevation = CardDefaults.cardElevation(defaultElevation = 6.dp),
            ) {
                Column(modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp)) {
                    MiuixSwitchRow("Monet 动态取色", "跟随系统壁纸强调色", settings.monetEnabled, actions.setMonetEnabled)
                    MiuixSwitchRow("纯黑深色模式", "深色时使用 AMOLED 黑色背景", settings.amoledBlack, actions.setAmoledBlack)
                    MiuixSwitchRow("玻璃半透明", "控制悬浮层透明质感", settings.glassEnabled, actions.setGlassEnabled)
                    MiuixSwitchRow("背景模糊", "使用 Haze 模糊悬浮底栏背景", settings.blurEnabled, actions.setBlurEnabled, settings.glassEnabled)
                    MiuixSwitchRow("悬浮底栏", "关闭后底栏贴合屏幕底部", settings.floatingDock, actions.setFloatingDock)
                }
            }
        }
    }
}

@Composable
private fun SettingsHeader(subtitle: String) {
    Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = "APPEARANCE",
                color = MaterialTheme.colorScheme.primary,
                fontSize = 10.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 2.2.sp,
            )
            Spacer(Modifier.height(4.dp))
            Text("界面设置", fontSize = 34.sp, lineHeight = 39.sp, fontWeight = FontWeight.Black)
            Text(subtitle, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
        }
        Surface(
            modifier = Modifier.size(56.dp),
            shape = RoundedCornerShape(18.dp),
            color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
        ) {
            Box(contentAlignment = Alignment.Center) {
                Icon(Icons.Rounded.Settings, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            }
        }
    }
}

@Composable
private fun MaterialSettingCard(
    title: String,
    subtitle: String,
    content: @Composable () -> Unit,
) {
    Card(
        shape = MaterialTheme.shapes.extraLarge,
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceContainerLow.copy(alpha = .82f),
        ),
    ) {
        Column(modifier = Modifier.padding(18.dp)) {
            Text(title, fontSize = 18.sp, fontWeight = FontWeight.Black)
            Text(subtitle, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
            Spacer(Modifier.height(14.dp))
            content()
        }
    }
}

@Composable
private fun MiuixSettingGroup(
    title: String,
    subtitle: String,
    content: @Composable () -> Unit,
) {
    val tokens = LocalMiuixTokens.current
    Card(
        shape = RoundedCornerShape(34.dp),
        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),
        elevation = CardDefaults.cardElevation(defaultElevation = 6.dp),
    ) {
        Column(modifier = Modifier.padding(18.dp)) {
            Text(title, color = tokens.textPrimary, fontSize = 18.sp, fontWeight = FontWeight.Black)
            Text(subtitle, color = tokens.textSecondary, fontSize = 11.sp)
            Spacer(Modifier.height(14.dp))
            content()
        }
    }
}

@Composable
private fun <T> ChoiceRow(
    entries: List<T>,
    selected: T,
    label: (T) -> String,
    onSelected: (T) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        entries.forEach { item ->
            val active = item == selected
            Surface(
                modifier = Modifier.clip(RoundedCornerShape(999.dp)).clickable { onSelected(item) },
                shape = RoundedCornerShape(999.dp),
                color = if (active) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceContainerHigh,
            ) {
                Text(
                    text = label(item),
                    modifier = Modifier.padding(horizontal = 15.dp, vertical = 9.dp),
                    color = if (active) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                )
            }
        }
    }
}

@Composable
private fun AccentSelector(settings: AppearanceSettings, onSelected: (Int) -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        AccentOptions.forEach { option ->
            val active = settings.seedArgb == option.argb
            Column(
                modifier = Modifier.clip(RoundedCornerShape(18.dp)).clickable { onSelected(option.argb) }.padding(6.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Box(
                    modifier = Modifier
                        .size(if (active) 42.dp else 36.dp)
                        .clip(CircleShape)
                        .background(Color(option.argb)),
                    contentAlignment = Alignment.Center,
                ) {
                    if (active) {
                        Box(
                            Modifier
                                .size(14.dp)
                                .clip(CircleShape)
                                .background(Color.White.copy(alpha = .78f)),
                        )
                    }
                }
                Spacer(Modifier.height(5.dp))
                Text(option.label, fontSize = 9.sp, fontWeight = if (active) FontWeight.Bold else FontWeight.Normal)
            }
        }
    }
}

@Composable
private fun MaterialSwitchRow(
    title: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    enabled: Boolean = true,
) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(title, modifier = Modifier.weight(1f), fontWeight = FontWeight.Medium)
        Switch(checked = checked, onCheckedChange = onCheckedChange, enabled = enabled)
    }
}

@Composable
private fun MiuixChoiceLine(title: String, value: String, content: @Composable () -> Unit) {
    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(title, modifier = Modifier.weight(1f), fontWeight = FontWeight.Bold)
            Text(value, color = MaterialTheme.colorScheme.primary, fontSize = 11.sp, fontWeight = FontWeight.Bold)
        }
        Spacer(Modifier.height(9.dp))
        content()
    }
}

@Composable
private fun MiuixSwitchRow(
    title: String,
    description: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    enabled: Boolean = true,
) {
    val tokens = LocalMiuixTokens.current
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(enabled = enabled) { onCheckedChange(!checked) }
            .padding(vertical = 13.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(title, color = tokens.textPrimary, fontSize = 15.sp, fontWeight = FontWeight.Bold)
            Text(description, color = tokens.textSecondary, fontSize = 10.sp)
        }
        MiuixSuperSwitch(checked = checked, enabled = enabled, onCheckedChange = onCheckedChange)
    }
}

@Composable
private fun MiuixSuperSwitch(
    checked: Boolean,
    enabled: Boolean,
    onCheckedChange: (Boolean) -> Unit,
) {
    val thumbOffset by animateDpAsState(
        targetValue = if (checked) 23.dp else 3.dp,
        label = "miuixSuperSwitch",
    )
    val track = when {
        !enabled -> MaterialTheme.colorScheme.onSurface.copy(alpha = .10f)
        checked -> MaterialTheme.colorScheme.primary
        else -> MaterialTheme.colorScheme.onSurface.copy(alpha = .13f)
    }
    Box(
        modifier = Modifier
            .width(50.dp)
            .height(30.dp)
            .clip(RoundedCornerShape(15.dp))
            .background(track)
            .clickable(enabled = enabled) { onCheckedChange(!checked) },
    ) {
        Box(
            modifier = Modifier
                .offset(x = thumbOffset, y = 3.dp)
                .size(24.dp)
                .clip(RoundedCornerShape(9.dp))
                .background(if (checked) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.surface),
        )
    }
}
