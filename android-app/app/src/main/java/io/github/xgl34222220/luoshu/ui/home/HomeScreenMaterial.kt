package io.github.xgl34222220.luoshu.ui.home

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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.Layers
import androidx.compose.material.icons.rounded.List
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.RestartAlt
import androidx.compose.material.icons.rounded.Security
import androidx.compose.material.icons.rounded.Speed
import androidx.compose.material.icons.rounded.Tune
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun HomeScreenMaterial(
    state: HomeUiState,
    actions: HomeActions,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 18.dp, top = 10.dp, end = 18.dp, bottom = 132.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item { MaterialPageHeader(state = state, onRefresh = actions.refresh) }
        item { MaterialFontHero(state) }

        if (state.error.isNotBlank()) {
            item {
                Surface(
                    shape = MaterialTheme.shapes.large,
                    color = MaterialTheme.colorScheme.errorContainer,
                ) {
                    Text(
                        text = state.error,
                        modifier = Modifier.padding(16.dp),
                        color = MaterialTheme.colorScheme.onErrorContainer,
                    )
                }
            }
        }

        item { MaterialSectionTitle("SYSTEM STATUS", "运行状态", "Root 与字体挂载") }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                MaterialMetricCard(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Rounded.Security,
                    label = "Root",
                    value = if (state.rootGranted) state.rootManager else "未授权",
                    positive = state.rootGranted,
                )
                MaterialMetricCard(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Rounded.Layers,
                    label = "挂载引擎",
                    value = state.mountEngine,
                    positive = state.moduleInstalled,
                )
            }
        }

        item { MaterialSectionTitle("QUICK ACCESS", "常用入口", "字体管理与诊断") }
        item {
            MaterialActionGroup(
                items = listOf(
                    MaterialHomeAction(
                        icon = Icons.Rounded.List,
                        title = "字体库",
                        description = "导入、预览和直接应用字体",
                        onClick = actions.openFontLibrary,
                    ),
                    MaterialHomeAction(
                        icon = Icons.Rounded.Tune,
                        title = "字体组合",
                        description = "中文、英文、数字与可变轴",
                        onClick = actions.openFontStudio,
                    ),
                    MaterialHomeAction(
                        icon = Icons.Rounded.Description,
                        title = "运行日志",
                        description = "查看任务进度与错误原因",
                        onClick = actions.openLogs,
                    ),
                ),
            )
        }

        item { MaterialSectionTitle("SYSTEM WEIGHT", "全局粗细微调", "向左更细，向右更粗") }
        item { MaterialSystemWeightCard(state.systemWeight, actions) }

        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(
                    onClick = actions.restoreDefault,
                    enabled = !state.taskRunning,
                    modifier = Modifier.weight(1f).height(54.dp),
                    shape = MaterialTheme.shapes.large,
                ) {
                    Text("恢复系统字体", fontWeight = FontWeight.Bold)
                }
                Button(
                    onClick = actions.reboot,
                    enabled = state.rebootRequired && !state.taskRunning,
                    modifier = Modifier.weight(1f).height(54.dp),
                    shape = MaterialTheme.shapes.large,
                ) {
                    Icon(Icons.Rounded.RestartAlt, contentDescription = null)
                    Spacer(Modifier.width(7.dp))
                    Text("立即重启", fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
private fun MaterialPageHeader(state: HomeUiState, onRefresh: () -> Unit) {
    Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = "FONT ENGINE",
                color = MaterialTheme.colorScheme.primary,
                fontSize = 10.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 2.sp,
            )
            Spacer(Modifier.height(5.dp))
            Text("洛书", style = MaterialTheme.typography.displaySmall, fontWeight = FontWeight.Black)
            Text(
                text = "Material 3 Glass · ${state.version}",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
        Surface(
            shape = MaterialTheme.shapes.large,
            color = MaterialTheme.colorScheme.surfaceContainerHigh.copy(alpha = .74f),
            tonalElevation = 3.dp,
            shadowElevation = 8.dp,
        ) {
            IconButton(onClick = onRefresh, modifier = Modifier.size(56.dp)) {
                if (state.loading) {
                    CircularProgressIndicator(modifier = Modifier.size(23.dp), strokeWidth = 2.dp)
                } else {
                    Icon(Icons.Rounded.Refresh, contentDescription = "刷新")
                }
            }
        }
    }
}

@Composable
private fun MaterialFontHero(state: HomeUiState) {
    val scheme = MaterialTheme.colorScheme
    Card(
        shape = MaterialTheme.shapes.extraLarge,
        colors = CardDefaults.cardColors(containerColor = Color.Transparent),
        elevation = CardDefaults.cardElevation(defaultElevation = 10.dp),
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(Brush.linearGradient(listOf(scheme.primary, scheme.tertiary)))
                .drawBehind {
                    drawCircle(
                        brush = Brush.radialGradient(
                            colors = listOf(Color.White.copy(alpha = .35f), Color.Transparent),
                            center = Offset(size.width * .84f, 0f),
                            radius = size.width * .72f,
                        ),
                        center = Offset(size.width * .84f, 0f),
                        radius = size.width * .72f,
                    )
                }
                .padding(24.dp),
        ) {
            Column {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        modifier = Modifier
                            .size(10.dp)
                            .background(
                                color = if (state.moduleInstalled && state.rootGranted) {
                                    Color(0xFF56E39F)
                                } else {
                                    Color(0xFFFFCC66)
                                },
                                shape = CircleShape,
                            ),
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(
                        text = if (state.moduleInstalled) "模块与字体引擎已连接" else "正在等待模块连接",
                        color = Color.White.copy(alpha = .88f),
                        fontWeight = FontWeight.Bold,
                        fontSize = 12.sp,
                    )
                }
                Spacer(Modifier.height(25.dp))
                Text("当前字体", color = Color.White.copy(alpha = .75f), fontSize = 12.sp)
                Text(
                    text = state.currentFont,
                    color = Color.White,
                    fontSize = 38.sp,
                    lineHeight = 43.sp,
                    fontWeight = FontWeight.Black,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.height(20.dp))
                Surface(
                    shape = MaterialTheme.shapes.large,
                    color = Color.White.copy(alpha = .16f),
                    contentColor = Color.White,
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(horizontal = 15.dp, vertical = 13.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(
                            imageVector = if (state.taskRunning) Icons.Rounded.Refresh else Icons.Rounded.CheckCircle,
                            contentDescription = null,
                        )
                        Spacer(Modifier.width(11.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text(state.taskTitle, fontWeight = FontWeight.Bold)
                            Text(
                                text = state.taskMessage,
                                color = Color.White.copy(alpha = .72f),
                                fontSize = 11.sp,
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis,
                            )
                        }
                        if (state.taskRunning) {
                            Text("${state.taskProgress}%", fontWeight = FontWeight.Black)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun MaterialMetricCard(
    modifier: Modifier,
    icon: ImageVector,
    label: String,
    value: String,
    positive: Boolean,
) {
    Card(
        modifier = modifier,
        shape = MaterialTheme.shapes.extraLarge,
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceContainerLow.copy(alpha = .80f),
        ),
    ) {
        Column(modifier = Modifier.padding(18.dp)) {
            Surface(
                modifier = Modifier.size(44.dp),
                shape = MaterialTheme.shapes.large,
                color = MaterialTheme.colorScheme.primaryContainer,
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                }
            }
            Spacer(Modifier.height(14.dp))
            Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
            Text(value, fontWeight = FontWeight.Black, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(
                text = if (positive) "运行正常" else "需要检查",
                color = if (positive) Color(0xFF21966C) else MaterialTheme.colorScheme.error,
                fontSize = 10.sp,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

@Composable
private fun MaterialSystemWeightCard(weight: HomeWeightUiState, actions: HomeActions) {
    Card(
        shape = MaterialTheme.shapes.extraLarge,
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceContainerLow.copy(alpha = .82f),
        ),
    ) {
        Column(Modifier.padding(20.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(48.dp),
                    shape = MaterialTheme.shapes.large,
                    color = MaterialTheme.colorScheme.primaryContainer,
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(Icons.Rounded.Speed, null, tint = MaterialTheme.colorScheme.primary)
                    }
                }
                Spacer(Modifier.width(13.dp))
                Column(Modifier.weight(1f)) {
                    Text("当前粗细", fontWeight = FontWeight.Black, fontSize = 17.sp)
                    Text(
                        "系统最终显示时统一微调，不修改字体文件",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 10.sp,
                    )
                }
                Text(
                    if (weight.loading) "读取中" else weight.weight.toString(),
                    color = MaterialTheme.colorScheme.primary,
                    fontSize = 24.sp,
                    fontWeight = FontWeight.Black,
                )
            }
            Spacer(Modifier.height(15.dp))
            when {
                weight.loading -> LinearProgressIndicator(Modifier.fillMaxWidth())
                !weight.supported -> Text(
                    weight.error.ifBlank { "当前系统不支持全局粗细微调" },
                    color = MaterialTheme.colorScheme.error,
                    fontSize = 11.sp,
                )
                else -> {
                    Slider(
                        value = weight.weight.toFloat(),
                        onValueChange = actions.previewSystemWeight,
                        enabled = !weight.applying,
                        valueRange = weight.min.toFloat()..weight.max.toFloat(),
                        steps = (((weight.max - weight.min) / weight.step) - 1).coerceAtLeast(0),
                    )
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Text("更细 ${weight.min}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                        Spacer(Modifier.weight(1f))
                        Text("标准 400", color = MaterialTheme.colorScheme.primary, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                        Spacer(Modifier.weight(1f))
                        Text("${weight.max} 更粗", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            weight.error.ifBlank { weight.message },
                            modifier = Modifier.weight(1f),
                            color = if (weight.error.isNotBlank()) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 10.sp,
                            maxLines = 2,
                        )
                        TextButton(onClick = actions.resetSystemWeight, enabled = !weight.applying) {
                            Text("恢复原始")
                        }
                    }
                }
            }
        }
    }
}

private data class MaterialHomeAction(
    val icon: ImageVector,
    val title: String,
    val description: String,
    val onClick: () -> Unit,
)

@Composable
private fun MaterialActionGroup(items: List<MaterialHomeAction>) {
    Card(
        shape = MaterialTheme.shapes.extraLarge,
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceContainerLow.copy(alpha = .80f),
        ),
    ) {
        Column {
            items.forEachIndexed { index, item ->
                ListItem(
                    headlineContent = { Text(item.title, fontWeight = FontWeight.Bold) },
                    supportingContent = { Text(item.description) },
                    leadingContent = {
                        Surface(
                            modifier = Modifier.size(46.dp),
                            shape = MaterialTheme.shapes.large,
                            color = MaterialTheme.colorScheme.primaryContainer,
                        ) {
                            Box(contentAlignment = Alignment.Center) {
                                Icon(item.icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                            }
                        }
                    },
                    trailingContent = {
                        FilledTonalButton(
                            onClick = item.onClick,
                            contentPadding = PaddingValues(horizontal = 14.dp),
                        ) { Text("打开") }
                    },
                    colors = ListItemDefaults.colors(containerColor = Color.Transparent),
                )
                if (index != items.lastIndex) {
                    HorizontalDivider(modifier = Modifier.padding(start = 74.dp))
                }
            }
        }
    }
}

@Composable
private fun MaterialSectionTitle(eyebrow: String, title: String, subtitle: String) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(start = 2.dp, top = 4.dp, end = 2.dp),
        verticalAlignment = Alignment.Bottom,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                eyebrow,
                color = MaterialTheme.colorScheme.primary,
                fontSize = 9.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 2.sp,
            )
            Text(title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Black)
        }
        Text(subtitle, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
    }
}
