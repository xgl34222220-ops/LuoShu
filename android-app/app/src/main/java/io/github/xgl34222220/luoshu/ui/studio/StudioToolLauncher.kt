package io.github.xgl34222220.luoshu.ui.studio

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.History
import androidx.compose.material.icons.rounded.ListAlt
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens

@Composable
internal fun StudioToolLauncher(
    style: UiStyle,
    enabled: Boolean,
    onPreview: () -> Unit,
    onPresets: () -> Unit,
    onHistory: () -> Unit,
    onProfile: () -> Unit,
    onGlyphs: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var menuVisible by remember { mutableStateOf(false) }
    val scheme = MaterialTheme.colorScheme
    val tokens = LocalMiuixTokens.current
    val background = when {
        style == UiStyle.MIUIX -> tokens.elevatedCardBackground
        enabled -> scheme.surfaceContainerHigh
        else -> scheme.surfaceVariant
    }

    Surface(
        onClick = { menuVisible = true },
        enabled = enabled,
        modifier = modifier.size(56.dp),
        shape = RoundedCornerShape(18.dp),
        color = background,
        contentColor = if (enabled) scheme.primary else scheme.onSurfaceVariant,
        tonalElevation = if (style == UiStyle.MATERIAL) 2.dp else 0.dp,
        shadowElevation = if (style == UiStyle.MIUIX) 7.dp else 3.dp,
    ) {
        androidx.compose.foundation.layout.Box(contentAlignment = Alignment.Center) {
            Icon(
                Icons.Rounded.AutoAwesome,
                contentDescription = "组合工具",
                modifier = Modifier.size(23.dp),
            )
        }
    }

    if (menuVisible) {
        AlertDialog(
            onDismissRequest = { menuVisible = false },
            shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 34.dp else 28.dp),
            icon = {
                Icon(Icons.Rounded.AutoAwesome, contentDescription = null, tint = scheme.primary)
            },
            title = { Text("组合工具", fontWeight = FontWeight.Black) },
            text = {
                Column(
                    modifier = Modifier.fillMaxWidth(),
                    verticalArrangement = Arrangement.spacedBy(9.dp),
                ) {
                    StudioToolMenuItem(
                        label = "最终组合预览",
                        description = "对照系统字体并切换混排、正文、界面和金额场景",
                        icon = Icons.Rounded.AutoAwesome,
                        onClick = {
                            menuVisible = false
                            onPreview()
                        },
                    )
                    StudioToolMenuItem(
                        label = "本地方案库",
                        description = "保存、收藏和载入常用组合，并按最近使用快速回滚",
                        icon = Icons.Rounded.History,
                        onClick = {
                            menuVisible = false
                            onPresets()
                        },
                    )
                    StudioToolMenuItem(
                        label = "成功切换历史",
                        description = "最近 10 次真正完成的切换，可一键恢复并重新走安全事务",
                        icon = Icons.Rounded.History,
                        onClick = {
                            menuVisible = false
                            onHistory()
                        },
                    )
                    StudioToolMenuItem(
                        label = "方案导入导出",
                        description = "通过 JSON 迁移三个槽位、字重和变量轴配置",
                        icon = Icons.Rounded.Description,
                        onClick = {
                            menuVisible = false
                            onProfile()
                        },
                    )
                    StudioToolMenuItem(
                        label = "字形浏览",
                        description = "浏览中文、拉丁、数字、标点和 Unicode 码位",
                        icon = Icons.Rounded.ListAlt,
                        onClick = {
                            menuVisible = false
                            onGlyphs()
                        },
                    )
                }
            },
            confirmButton = {
                TextButton(onClick = { menuVisible = false }) {
                    Text("关闭", fontWeight = FontWeight.Bold)
                }
            },
        )
    }
}

@Composable
private fun StudioToolMenuItem(
    label: String,
    description: String,
    icon: ImageVector,
    onClick: () -> Unit,
) {
    val scheme = MaterialTheme.colorScheme
    Surface(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(22.dp),
        color = scheme.primaryContainer.copy(alpha = .48f),
        contentColor = scheme.onSurface,
        border = BorderStroke(1.dp, scheme.primary.copy(alpha = .08f)),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Surface(
                modifier = Modifier.size(42.dp),
                shape = RoundedCornerShape(15.dp),
                color = scheme.primary.copy(alpha = .11f),
                contentColor = scheme.primary,
            ) {
                androidx.compose.foundation.layout.Box(contentAlignment = Alignment.Center) {
                    Icon(icon, contentDescription = null, modifier = Modifier.size(20.dp))
                }
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(label, fontWeight = FontWeight.Black, fontSize = 14.sp)
                Text(
                    description,
                    color = scheme.onSurfaceVariant,
                    fontSize = 10.sp,
                    lineHeight = 14.sp,
                )
            }
        }
    }
}
