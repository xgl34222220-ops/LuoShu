package io.github.xgl34222220.luoshu.ui.studio

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.ListAlt
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import top.yukonga.miuix.kmp.basic.BasicComponent
import top.yukonga.miuix.kmp.basic.Button
import top.yukonga.miuix.kmp.basic.Card
import top.yukonga.miuix.kmp.basic.Icon
import top.yukonga.miuix.kmp.basic.Text
import top.yukonga.miuix.kmp.overlay.OverlayDialog
import top.yukonga.miuix.kmp.theme.MiuixTheme

@Composable
internal fun StudioToolLauncherMiuix(
    enabled: Boolean,
    onPreview: () -> Unit,
    onProfile: () -> Unit,
    onGlyphs: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var menuVisible by remember { mutableStateOf(false) }

    Button(
        onClick = { menuVisible = true },
        enabled = enabled,
        modifier = modifier,
    ) {
        Icon(
            imageVector = Icons.Rounded.AutoAwesome,
            contentDescription = null,
            modifier = Modifier.size(21.dp),
        )
        Text(
            text = "工具",
            modifier = Modifier.padding(start = 7.dp),
            fontWeight = FontWeight.Bold,
        )
    }

    if (menuVisible) {
        OverlayDialog(
            title = "组合工具",
            summary = "预览、方案管理与字形浏览",
            show = true,
            onDismissRequest = { menuVisible = false },
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Card(modifier = Modifier.fillMaxWidth()) {
                    MiuixStudioToolItem(
                        label = "最终组合预览",
                        description = "对照系统字体并切换混排、正文、界面和金额场景",
                        icon = Icons.Rounded.AutoAwesome,
                        onClick = {
                            menuVisible = false
                            onPreview()
                        },
                    )
                    MiuixStudioToolItem(
                        label = "方案管理",
                        description = "导入、导出和恢复三个槽位的组合配置",
                        icon = Icons.Rounded.Description,
                        onClick = {
                            menuVisible = false
                            onProfile()
                        },
                    )
                    MiuixStudioToolItem(
                        label = "字形浏览",
                        description = "浏览中文、拉丁、数字、标点和 Unicode 码位",
                        icon = Icons.Rounded.ListAlt,
                        onClick = {
                            menuVisible = false
                            onGlyphs()
                        },
                    )
                }
                Button(
                    onClick = { menuVisible = false },
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("关闭", fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
private fun MiuixStudioToolItem(
    label: String,
    description: String,
    icon: ImageVector,
    onClick: () -> Unit,
) {
    BasicComponent(
        title = label,
        summary = description,
        startAction = {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = MiuixTheme.colorScheme.primary,
                modifier = Modifier.padding(end = 16.dp).size(24.dp),
            )
        },
        onClick = onClick,
    )
}
