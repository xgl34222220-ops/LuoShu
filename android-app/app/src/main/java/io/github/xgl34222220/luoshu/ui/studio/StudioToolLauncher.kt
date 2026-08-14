package io.github.xgl34222220.luoshu.ui.studio

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.ChevronRight
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.History
import androidx.compose.material.icons.rounded.ListAlt
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
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
@OptIn(ExperimentalMaterial3Api::class)
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
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
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
        ModalBottomSheet(
            onDismissRequest = { menuVisible = false },
            sheetState = sheetState,
            shape = RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp),
            containerColor = if (style == UiStyle.MIUIX) tokens.cardBackground else scheme.surface,
            tonalElevation = 0.dp,
            dragHandle = {
                Surface(
                    modifier = Modifier.padding(top = 10.dp).width(36.dp).height(4.dp),
                    shape = RoundedCornerShape(999.dp),
                    color = scheme.onSurfaceVariant.copy(alpha = .26f),
                ) {}
            },
        ) {
            Column(
                modifier = Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(5.dp),
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(bottom = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Surface(
                        modifier = Modifier.size(44.dp),
                        shape = RoundedCornerShape(15.dp),
                        color = scheme.primary.copy(alpha = .10f),
                        contentColor = scheme.primary,
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Icon(Icons.Rounded.AutoAwesome, contentDescription = null, modifier = Modifier.size(21.dp))
                        }
                    }
                    Spacer(Modifier.width(12.dp))
                    Column {
                        Text("组合工具", fontWeight = FontWeight.Black, fontSize = 20.sp)
                        Text("预览、方案、历史与字形工具", color = scheme.onSurfaceVariant, fontSize = 11.sp)
                    }
                }
                StudioToolMenuItem("最终组合预览", "对照系统字体并切换混排、正文、界面和金额场景", Icons.Rounded.AutoAwesome) {
                    menuVisible = false; onPreview()
                }
                StudioToolMenuItem("本地方案库", "保存、收藏和载入常用组合，并按最近使用快速回滚", Icons.Rounded.History) {
                    menuVisible = false; onPresets()
                }
                StudioToolMenuItem("成功切换历史", "最近 10 次真正完成的切换，可一键恢复并重新走安全事务", Icons.Rounded.History) {
                    menuVisible = false; onHistory()
                }
                StudioToolMenuItem("方案导入导出", "通过 JSON 迁移三个槽位、字重和变量轴配置", Icons.Rounded.Description) {
                    menuVisible = false; onProfile()
                }
                StudioToolMenuItem("字形浏览", "浏览中文、拉丁、数字、标点和 Unicode 码位", Icons.Rounded.ListAlt) {
                    menuVisible = false; onGlyphs()
                }
            }
        }
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
        shape = RoundedCornerShape(18.dp),
        color = scheme.surfaceContainerLow,
        contentColor = scheme.onSurface,
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 13.dp, vertical = 11.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Surface(
                modifier = Modifier.size(40.dp),
                shape = RoundedCornerShape(14.dp),
                color = scheme.primary.copy(alpha = .09f),
                contentColor = scheme.primary,
            ) {
                Box(contentAlignment = Alignment.Center) {
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
            Spacer(Modifier.width(8.dp))
            Icon(
                Icons.Rounded.ChevronRight,
                contentDescription = null,
                tint = scheme.onSurfaceVariant.copy(alpha = .72f),
                modifier = Modifier.size(20.dp),
            )
        }
    }
}
