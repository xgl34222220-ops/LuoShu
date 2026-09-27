package io.github.xgl34222220.luoshu.ui.studio

import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
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
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuGlyph
import io.github.xgl34222220.luoshu.ui.theme.LuoShuHeaderAction
import io.github.xgl34222220.luoshu.ui.theme.LuoShuIconTokens

@Composable
@OptIn(ExperimentalMaterial3Api::class)
internal fun StudioToolLauncher(
    style: UiStyle,
    enabled: Boolean,
    childLayerActive: Boolean,
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
    val parentScale by animateFloatAsState(
        targetValue = if (childLayerActive) .95f else 1f,
        animationSpec = spring(dampingRatio = .85f, stiffness = Spring.StiffnessMediumLow),
        label = "studioToolParentScale",
    )
    val parentAlpha by animateFloatAsState(
        targetValue = if (childLayerActive) .82f else 1f,
        animationSpec = spring(dampingRatio = .90f, stiffness = Spring.StiffnessMedium),
        label = "studioToolParentAlpha",
    )
    val background = when {
        style == UiStyle.MIUIX -> tokens.elevatedCardBackground
        enabled -> scheme.surfaceContainerHigh
        else -> scheme.surfaceVariant
    }

    LuoShuHeaderAction(
        icon = Icons.Rounded.AutoAwesome,
        contentDescription = "组合工具",
        onClick = { menuVisible = true },
        enabled = enabled,
        containerColor = background,
        modifier = modifier,
        opticalScale = 1.08f,
        contentColor = if (enabled) scheme.primary else scheme.onSurfaceVariant,
    )

    if (menuVisible) {
        ModalBottomSheet(
            onDismissRequest = { if (!childLayerActive) menuVisible = false },
            sheetState = sheetState,
            sheetGesturesEnabled = !childLayerActive,
            shape = RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp),
            containerColor = if (style == UiStyle.MIUIX) tokens.cardBackground else scheme.surface,
            tonalElevation = 0.dp,
            scrimColor = scheme.scrim.copy(alpha = .20f),
            dragHandle = {
                Surface(
                    modifier = Modifier.padding(top = 10.dp).width(36.dp).height(4.dp),
                    shape = RoundedCornerShape(999.dp),
                    color = scheme.onSurfaceVariant.copy(alpha = .26f),
                ) {}
            },
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .graphicsLayer {
                        scaleX = parentScale
                        scaleY = parentScale
                        alpha = parentAlpha
                    }
                    .padding(start = 20.dp, end = 20.dp, bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
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
                            LuoShuGlyph(
                                imageVector = Icons.Rounded.AutoAwesome,
                                contentDescription = null,
                                size = LuoShuIconTokens.ToolGlyph,
                                opticalScale = 1.08f,
                            )
                        }
                    }
                    Spacer(Modifier.width(12.dp))
                    Column {
                        Text("组合工具", fontWeight = FontWeight.SemiBold, fontSize = 20.sp)
                        Text("预览、方案、历史与字形工具", color = scheme.onSurfaceVariant, fontSize = 12.sp)
                    }
                }
                StudioToolMenuItem("最终组合预览", "对照系统字体并切换混排、正文、界面和金额场景", Icons.Rounded.AutoAwesome, 1.08f) {
                    onPreview()
                }
                StudioToolMenuItem("本地方案库", "保存、收藏和载入常用组合，并按最近使用快速回滚", Icons.Rounded.History) {
                    onPresets()
                }
                StudioToolMenuItem("成功切换历史", "回看最近 10 次成功切换，快速恢复喜欢的字体", Icons.Rounded.History) {
                    onHistory()
                }
                StudioToolMenuItem("方案导入导出", "备份或分享所选字体、字重和调节参数", Icons.Rounded.Description, .96f) {
                    onProfile()
                }
                StudioToolMenuItem("字形浏览", "查看中文、英文、数字和标点的实际字形", Icons.Rounded.ListAlt, .98f) {
                    onGlyphs()
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
    opticalScale: Float = 1f,
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
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Surface(
                modifier = Modifier.size(40.dp),
                shape = RoundedCornerShape(14.dp),
                color = scheme.primary.copy(alpha = .09f),
                contentColor = scheme.primary,
            ) {
                Box(contentAlignment = Alignment.Center) {
                    LuoShuGlyph(
                    imageVector = icon,
                    contentDescription = null,
                    size = LuoShuIconTokens.ToolGlyph,
                    opticalScale = opticalScale,
                )
                }
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(label, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                Text(
                    description,
                    color = scheme.onSurfaceVariant,
                    fontSize = 12.sp,
                    lineHeight = 18.sp,
                )
            }
            Spacer(Modifier.width(8.dp))
            LuoShuGlyph(
                imageVector = Icons.Rounded.ChevronRight,
                contentDescription = null,
                size = LuoShuIconTokens.TrailingGlyph,
                tint = scheme.onSurfaceVariant.copy(alpha = .72f),
            )
        }
    }
}
