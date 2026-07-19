package io.github.xgl34222220.luoshu.ui.dialogs

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Delete
import androidx.compose.material.icons.rounded.FontDownload
import androidx.compose.material.icons.rounded.RestartAlt
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens

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
    when (style) {
        UiStyle.MATERIAL -> MaterialFontActionDialog(kind, message, onDismiss, onConfirm)
        UiStyle.MIUIX -> MiuixFontActionDialog(kind, message, onDismiss, onConfirm)
    }
}

@Composable
private fun MaterialFontActionDialog(
    kind: FontActionKind,
    message: String,
    onDismiss: () -> Unit,
    onConfirm: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        icon = {
            Surface(
                modifier = Modifier.size(52.dp),
                shape = MaterialTheme.shapes.large,
                color = if (kind.destructive) {
                    MaterialTheme.colorScheme.errorContainer
                } else {
                    MaterialTheme.colorScheme.primaryContainer
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
        },
        title = { Text(kind.title, fontWeight = FontWeight.Black) },
        text = { Text(message, color = MaterialTheme.colorScheme.onSurfaceVariant) },
        confirmButton = {
            Button(
                onClick = onConfirm,
                colors = if (kind.destructive) {
                    ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error)
                } else {
                    ButtonDefaults.buttonColors()
                },
            ) {
                Text(kind.confirmLabel, fontWeight = FontWeight.Bold)
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("取消") }
        },
        shape = MaterialTheme.shapes.extraLarge,
    )
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
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(36.dp),
            color = tokens.elevatedCardBackground,
            shadowElevation = 18.dp,
        ) {
            Column(
                modifier = Modifier.padding(22.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Surface(
                        modifier = Modifier.size(54.dp),
                        shape = RoundedCornerShape(19.dp),
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
                            fontSize = 22.sp,
                            lineHeight = 26.sp,
                            fontWeight = FontWeight.Black,
                        )
                        Text(
                            if (kind.destructive) "此操作不可撤销" else "完成后建议完整重启手机",
                            color = tokens.textSecondary,
                            fontSize = 11.sp,
                        )
                    }
                }

                Text(
                    message,
                    color = tokens.textSecondary,
                    fontSize = 13.sp,
                    lineHeight = 20.sp,
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
                        shape = RoundedCornerShape(19.dp),
                    ) {
                        Text("取消", fontWeight = FontWeight.Bold)
                    }
                    Button(
                        onClick = onConfirm,
                        modifier = Modifier
                            .weight(1f)
                            .height(52.dp),
                        shape = RoundedCornerShape(19.dp),
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
