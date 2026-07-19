package io.github.xgl34222220.luoshu.ui.home

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.ChevronRight
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.Layers
import androidx.compose.material.icons.rounded.List
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.RestartAlt
import androidx.compose.material.icons.rounded.Security
import androidx.compose.material.icons.rounded.Tune
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
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens

@Composable
fun HomeScreenMiuix(
    state: HomeUiState,
    actions: HomeActions,
) {
    val tokens = LocalMiuixTokens.current
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, top = 10.dp, end = 16.dp, bottom = 132.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { MiuixPageHeader(state = state, onRefresh = actions.refresh) }
        item { MiuixFontHero(state) }

        if (state.error.isNotBlank()) {
            item {
                Surface(
                    shape = RoundedCornerShape(24.dp),
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

        item { MiuixSectionTitle("SYSTEM STATUS", "运行状态", "Root 与字体挂载") }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                MiuixMetricCard(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Rounded.Security,
                    label = "Root",
                    value = if (state.rootGranted) state.rootManager else "未授权",
                    positive = state.rootGranted,
                )
                MiuixMetricCard(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Rounded.Layers,
                    label = "挂载引擎",
                    value = state.mountEngine,
                    positive = state.moduleInstalled,
                )
            }
        }

        item { MiuixSectionTitle("QUICK ACCESS", "常用入口", "字体管理与诊断") }
        item {
            MiuixActionGroup(
                items = listOf(
                    MiuixHomeAction(
                        icon = Icons.Rounded.List,
                        title = "字体库",
                        description = "导入、预览和直接应用字体",
                        onClick = actions.openFontLibrary,
                    ),
                    MiuixHomeAction(
                        icon = Icons.Rounded.Tune,
                        title = "字体组合",
                        description = "中文、英文、数字与可变轴",
                        onClick = actions.openFontStudio,
                    ),
                    MiuixHomeAction(
                        icon = Icons.Rounded.Description,
                        title = "运行日志",
                        description = "查看任务进度与错误原因",
                        onClick = actions.openLogs,
                    ),
                ),
            )
        }

        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(
                    onClick = actions.restoreDefault,
                    enabled = !state.taskRunning,
                    modifier = Modifier.weight(1f).height(54.dp),
                    shape = RoundedCornerShape(20.dp),
                ) {
                    Text("恢复系统字体", fontWeight = FontWeight.Bold)
                }
                Button(
                    onClick = actions.reboot,
                    enabled = state.rebootRequired && !state.taskRunning,
                    modifier = Modifier.weight(1f).height(54.dp),
                    shape = RoundedCornerShape(20.dp),
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
private fun MiuixPageHeader(state: HomeUiState, onRefresh: () -> Unit) {
    Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = "FONT ENGINE",
                color = MaterialTheme.colorScheme.primary,
                fontSize = 10.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 2.4.sp,
            )
            Spacer(Modifier.height(4.dp))
            Text(
                text = "洛书",
                color = LocalMiuixTokens.current.textPrimary,
                fontSize = 42.sp,
                lineHeight = 47.sp,
                fontWeight = FontWeight.Black,
            )
            Text(
                text = "Miuix · ${state.version}",
                color = LocalMiuixTokens.current.textSecondary,
                fontSize = 12.sp,
            )
        }
        Card(
            shape = RoundedCornerShape(18.dp),
            colors = CardDefaults.cardColors(containerColor = LocalMiuixTokens.current.elevatedCardBackground),
            elevation = CardDefaults.cardElevation(defaultElevation = 6.dp),
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
private fun MiuixFontHero(state: HomeUiState) {
    val tokens = LocalMiuixTokens.current
    val scheme = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(36.dp)
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .shadow(12.dp, shape, clip = false),
        shape = shape,
        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .drawBehind {
                    drawCircle(
                        brush = Brush.radialGradient(
                            listOf(scheme.primary.copy(alpha = .18f), Color.Transparent),
                            center = Offset(size.width, 0f),
                            radius = size.width * .78f,
                        ),
                        radius = size.width * .78f,
                        center = Offset(size.width, 0f),
                    )
                    drawRoundRect(
                        brush = Brush.verticalGradient(
                            listOf(Color.White.copy(alpha = .24f), Color.Transparent),
                        ),
                        cornerRadius = androidx.compose.ui.geometry.CornerRadius(36.dp.toPx()),
                        size = size.copy(height = size.height * .36f),
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
                                color = if (state.moduleInstalled && state.rootGranted) tokens.success else tokens.warning,
                                shape = CircleShape,
                            ),
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(
                        text = if (state.moduleInstalled) "模块与字体引擎已连接" else "正在等待模块连接",
                        color = tokens.textSecondary,
                        fontWeight = FontWeight.Bold,
                        fontSize = 12.sp,
                    )
                }
                Spacer(Modifier.height(25.dp))
                Text("当前字体", color = tokens.textSecondary, fontSize = 12.sp)
                Text(
                    text = state.currentFont,
                    color = tokens.textPrimary,
                    fontSize = 42.sp,
                    lineHeight = 47.sp,
                    fontWeight = FontWeight.Black,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.height(21.dp))
                Surface(
                    shape = RoundedCornerShape(22.dp),
                    color = tokens.textPrimary.copy(alpha = .045f),
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(horizontal = 15.dp, vertical = 13.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(
                            imageVector = if (state.taskRunning) Icons.Rounded.Refresh else Icons.Rounded.CheckCircle,
                            contentDescription = null,
                            tint = if (state.moduleInstalled && state.rootGranted) tokens.success else scheme.primary,
                        )
                        Spacer(Modifier.width(11.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text(state.taskTitle, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                            Text(
                                text = state.taskMessage,
                                color = tokens.textSecondary,
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
private fun MiuixMetricCard(
    modifier: Modifier,
    icon: ImageVector,
    label: String,
    value: String,
    positive: Boolean,
) {
    val tokens = LocalMiuixTokens.current
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(30.dp),
        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),
        elevation = CardDefaults.cardElevation(defaultElevation = 5.dp),
    ) {
        Column(modifier = Modifier.padding(18.dp)) {
            Surface(
                modifier = Modifier.size(44.dp),
                shape = RoundedCornerShape(17.dp),
                color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                }
            }
            Spacer(Modifier.height(14.dp))
            Text(label, color = tokens.textSecondary, fontSize = 10.sp)
            Text(
                text = value,
                color = tokens.textPrimary,
                fontSize = 16.sp,
                fontWeight = FontWeight.Black,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                text = if (positive) "运行正常" else "需要检查",
                color = if (positive) tokens.success else MaterialTheme.colorScheme.error,
                fontSize = 10.sp,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

private data class MiuixHomeAction(
    val icon: ImageVector,
    val title: String,
    val description: String,
    val onClick: () -> Unit,
)

@Composable
private fun MiuixActionGroup(items: List<MiuixHomeAction>) {
    val tokens = LocalMiuixTokens.current
    Card(
        shape = RoundedCornerShape(34.dp),
        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),
        elevation = CardDefaults.cardElevation(defaultElevation = 7.dp),
    ) {
        Column(modifier = Modifier.padding(horizontal = 15.dp, vertical = 5.dp)) {
            items.forEachIndexed { index, item ->
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable(onClick = item.onClick)
                        .padding(horizontal = 2.dp, vertical = 14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Surface(
                        modifier = Modifier.size(48.dp),
                        shape = RoundedCornerShape(17.dp),
                        color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Icon(
                                imageVector = item.icon,
                                contentDescription = null,
                                tint = MaterialTheme.colorScheme.primary,
                                modifier = Modifier.size(25.dp),
                            )
                        }
                    }
                    Spacer(Modifier.width(13.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Text(item.title, color = tokens.textPrimary, fontSize = 17.sp, fontWeight = FontWeight.Black)
                        Text(
                            text = item.description,
                            color = tokens.textSecondary,
                            fontSize = 11.sp,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                    Icon(
                        imageVector = Icons.Rounded.ChevronRight,
                        contentDescription = null,
                        tint = tokens.textSecondary,
                    )
                }
                if (index != items.lastIndex) {
                    HorizontalDivider(
                        modifier = Modifier.padding(start = 61.dp),
                        color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = .55f),
                    )
                }
            }
        }
    }
}

@Composable
private fun MiuixSectionTitle(eyebrow: String, title: String, subtitle: String) {
    val tokens = LocalMiuixTokens.current
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 3.dp),
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
            Text(title, color = tokens.textPrimary, fontSize = 25.sp, fontWeight = FontWeight.Black)
        }
        Text(subtitle, color = tokens.textSecondary, fontSize = 11.sp)
    }
}
