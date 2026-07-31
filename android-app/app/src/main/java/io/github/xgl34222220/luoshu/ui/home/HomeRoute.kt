package io.github.xgl34222220.luoshu.ui.home

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import kotlinx.coroutines.delay

@Composable
fun HomeRoute(
    style: UiStyle,
    state: HomeUiState,
    actions: HomeActions,
) {
    var trustState by remember { mutableStateOf(DeviceTrustState()) }
    var showTrustDetails by remember { mutableStateOf(false) }
    var showAcceptanceGuide by remember { mutableStateOf(false) }
    var trustRefreshGeneration by remember { mutableIntStateOf(0) }

    LaunchedEffect(
        state.moduleInstalled,
        state.currentFont,
        state.rebootRequired,
        state.taskRunning,
        trustRefreshGeneration,
    ) {
        if (!state.moduleInstalled) {
            trustState = DeviceTrustState(loading = false, error = "请先安装洛书模块")
            return@LaunchedEffect
        }

        var latest = loadDeviceTrustState()
        trustState = latest
        var attempt = 0
        while (latest.level == DeviceTrustLevel.PENDING && attempt < 9 && !state.taskRunning) {
            delay(5_000L)
            latest = loadDeviceTrustState()
            trustState = latest
            attempt += 1
        }
    }

    HomeScreenCompact(
        style = style,
        state = state,
        actions = actions,
        trustContent = {
            if (state.moduleInstalled) {
                HomeTrustRow(
                    state = trustState,
                    onClick = { showTrustDetails = true },
                )
            }
        },
    )

    if (showTrustDetails) {
        DeviceTrustDialog(
            style = style,
            state = trustState,
            onDismiss = { showTrustDetails = false },
            onOpenAcceptance = { showAcceptanceGuide = true },
        )
    }
    if (showAcceptanceGuide) {
        DeviceAcceptanceGuideDialog(
            style = style,
            state = state,
            trust = trustState,
            onRefresh = {
                actions.refresh()
                trustRefreshGeneration += 1
            },
            onReboot = actions.reboot,
            onDismiss = { showAcceptanceGuide = false },
        )
    }
}

private data class HomeTrustPresentation(
    val title: String,
    val subtitle: String,
    val icon: ImageVector,
    val color: Color,
)

@Composable
private fun HomeTrustRow(
    state: DeviceTrustState,
    onClick: () -> Unit,
) {
    val presentation = homeTrustPresentation(state)
    Surface(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        color = MaterialTheme.colorScheme.surfaceContainerLow,
        contentColor = presentation.color,
        border = BorderStroke(1.dp, presentation.color.copy(alpha = .12f)),
        shadowElevation = 0.dp,
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 11.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (state.loading) {
                CircularProgressIndicator(Modifier.size(17.dp), strokeWidth = 2.dp, color = presentation.color)
            } else {
                Icon(presentation.icon, contentDescription = null, modifier = Modifier.size(18.dp), tint = presentation.color)
            }
            Spacer(Modifier.width(9.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = presentation.title,
                    color = presentation.color,
                    fontSize = 10.5.sp,
                    lineHeight = 13.sp,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = presentation.subtitle,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 8.5.sp,
                    lineHeight = 11.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@Composable
private fun homeTrustPresentation(state: DeviceTrustState): HomeTrustPresentation {
    val scheme = MaterialTheme.colorScheme
    return when {
        state.loading -> HomeTrustPresentation("正在检查设备字体", "读取本次启动验证状态", Icons.Rounded.Info, scheme.primary)
        state.level == DeviceTrustLevel.SYSTEM -> HomeTrustPresentation("当前为系统字体", "没有启用洛书字体负载", Icons.Rounded.CheckCircle, scheme.primary)
        state.level == DeviceTrustLevel.VERIFIED -> HomeTrustPresentation(
            "本次启动字体已验证",
            if (state.mode == "mount-verified") "PID 1 可见字体、配置与洛书负载一致" else "字体事务与本次启动证据一致",
            Icons.Rounded.CheckCircle,
            scheme.primary,
        )
        state.level == DeviceTrustLevel.COMPATIBILITY -> HomeTrustPresentation("字体效果尚未确认", "已生成兼容映射，等待加载证据", Icons.Rounded.Info, scheme.tertiary)
        state.level == DeviceTrustLevel.ISSUE -> HomeTrustPresentation("字体应用需要处理", "点击查看加载验证说明", Icons.Rounded.Warning, scheme.error)
        else -> HomeTrustPresentation(
            if (state.reason == "awaiting-full-reboot") "字体已准备，等待重启" else "等待本次启动验证",
            "点击查看当前验证进度",
            Icons.Rounded.Info,
            scheme.secondary,
        )
    }
}
