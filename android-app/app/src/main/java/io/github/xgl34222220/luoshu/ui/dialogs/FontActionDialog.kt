package io.github.xgl34222220.luoshu.ui.dialogs

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import io.github.xgl34222220.luoshu.ui.theme.LuoShuSmoothShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Delete
import androidx.compose.material.icons.rounded.FontDownload
import androidx.compose.material.icons.rounded.RestartAlt
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import io.github.xgl34222220.luoshu.ui.theme.luoShuGlassHighlight

internal enum class FontActionKind(
    val title: String,
    val confirmLabel: String,
    val icon: ImageVector,
    val destructive: Boolean = false,
) {
    APPLY("应用字体", "应用", Icons.Rounded.FontDownload),
    DELETE("删除字体", "删除", Icons.Rounded.Delete, destructive = true),
    RESTORE("恢复系统字体", "恢复", Icons.Rounded.RestartAlt),
}

@Composable
internal fun FontActionDialogRoute(
    style: UiStyle,
    kind: FontActionKind,
    message: String,
    onDismiss: () -> Unit,
    onConfirm: () -> Unit,
) {
    MiuixFontActionDialog(kind, message, onDismiss, onConfirm)
}

@Composable
private fun MiuixFontActionDialog(
    kind: FontActionKind,
    message: String,
    onDismiss: () -> Unit,
    onConfirm: () -> Unit,
) {
    val tokens = LocalMiuixTokens.current
    Dialog(onDismissRequest = onDismiss) {
        Surface(
            modifier = Modifier.fillMaxWidth().heightIn(max = 660.dp).luoShuGlassHighlight(LuoShuSmoothShape(32.dp)),
            shape = LuoShuSmoothShape(32.dp),
            color = tokens.glassDialogColor,
            shadowElevation = tokens.cardShadowElevation,
            border = BorderStroke(1.dp, tokens.glassOutlineBrush),
        ) {
            Column(
                modifier = Modifier.padding(22.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Surface(
                        modifier = Modifier.size(48.dp),
                        shape = LuoShuSmoothShape(18.dp),
                        color = if (kind.destructive) {
                            MaterialTheme.colorScheme.error.copy(alpha = .13f)
                        } else {
                            MaterialTheme.colorScheme.primary.copy(alpha = .13f)
                        },
                    ) {
                        androidx.compose.foundation.layout.Box(contentAlignment = Alignment.Center) {
                            Icon(
                                kind.icon,
                                contentDescription = null,
                                tint = if (kind.destructive) {
                                    MaterialTheme.colorScheme.error
                                } else {
                                    MaterialTheme.colorScheme.primary
                                },
                            )
                        }
                    }
                    Spacer(Modifier.size(14.dp))
                    Column(Modifier.weight(1f)) {
                        Text(
                            kind.title,
                            color = tokens.textPrimary,
                            fontSize = 21.sp,
                            lineHeight = 28.sp,
                            fontWeight = FontWeight.SemiBold,
                        )
                        Text(
                            if (kind.destructive) "此操作不可撤销" else "完成后建议完整重启手机",
                            color = tokens.textSecondary,
                            fontSize = 12.sp,
                            lineHeight = 18.sp,
                        )
                    }
                }

                Text(
                    message,
                    modifier = Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState()),
                    color = tokens.textSecondary,
                    fontSize = 14.sp,
                    lineHeight = 22.sp,
                )

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    OutlinedButton(
                        onClick = onDismiss,
                        modifier = Modifier
                            .weight(1f)
                            .height(52.dp),
                        shape = LuoShuSmoothShape(19.dp),
                    ) {
                        Text("取消", fontWeight = FontWeight.Bold)
                    }
                    Button(
                        onClick = onConfirm,
                        modifier = Modifier
                            .weight(1f)
                            .height(52.dp),
                        shape = LuoShuSmoothShape(19.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (kind.destructive) {
                                MaterialTheme.colorScheme.error
                            } else {
                                MaterialTheme.colorScheme.primary
                            },
                        ),
                    ) {
                        Text(kind.confirmLabel, fontWeight = FontWeight.Black)
                    }
                }
            }
        }
    }
}
