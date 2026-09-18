package io.github.xgl34222220.luoshu.ui.settings

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ExpandLess
import androidx.compose.material.icons.rounded.ExpandMore
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.viewmodel.compose.viewModel
import io.github.xgl34222220.luoshu.ui.theme.LocalDockContentPadding
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuLoadingSkeleton
import io.github.xgl34222220.luoshu.ui.theme.LuoShuMotionTokens

@Composable
internal fun GoogleFontCompatibilityPage() {
    val model: GoogleFontCompatibilityModel = viewModel()
    val state = model.ui
    val owner = LocalLifecycleOwner.current
    var confirmAction by rememberSaveable { mutableStateOf<String?>(null) }
    var detailsExpanded by rememberSaveable { mutableStateOf(false) }
    LaunchedEffect(Unit) { model.refresh() }
    DisposableEffect(owner, model) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) model.refresh()
        }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer) }
    }
    val idle = !state.loading && !state.busy
    LazyColumn(
        contentPadding = PaddingValues(start = 20.dp, top = 12.dp, end = 20.dp,
            bottom = maxOf(LocalDockContentPadding.current, 24.dp)),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item {
            GoogleCompatibilityCard("当前状态") {
                if (state.loading && !state.busy) {
                    LuoShuLoadingSkeleton(Modifier.fillMaxWidth(.52f).heightIn(min = 22.dp))
                    LuoShuLoadingSkeleton(Modifier.fillMaxWidth().heightIn(min = 14.dp))
                    LuoShuLoadingSkeleton(Modifier.fillMaxWidth(.76f).heightIn(min = 14.dp))
                } else {
                    if (state.busy) CircularProgressIndicator(Modifier.size(24.dp), strokeWidth = 2.dp)
                    Text(
                        if (state.busy) "正在处理，请稍候…" else state.title,
                        fontSize = 18.sp,
                        lineHeight = 26.sp,
                        fontWeight = FontWeight.SemiBold,
                    )
                    GoogleCompatibilityText(state.message)
                    state.user?.let { GoogleCompatibilityText("作用范围：当前 Android 用户 $it") }
                    if (state.managed) GoogleCompatibilityText("已找到恢复记录 · 兼容之前的独立脚本")
                    if (state.resultMessage.isNotBlank()) {
                        Text(state.resultMessage, color = MaterialTheme.colorScheme.primary, fontSize = 14.sp, lineHeight = 22.sp)
                    }
                    if (state.error.isNotBlank()) {
                        Text(state.error, color = MaterialTheme.colorScheme.error, fontSize = 14.sp, lineHeight = 22.sp)
                    }
                }
                OutlinedButton(onClick = model::refresh, enabled = idle, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
                    Text("重新检测")
                }
                Button(onClick = { confirmAction = "enable" }, enabled = idle && state.canEnable,
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) { Text("开启 Google 字体兼容") }
                OutlinedButton(onClick = { confirmAction = "restore" }, enabled = idle && state.canRestore,
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) { Text("恢复原设置") }
            }
        }
        item {
            GoogleCompatibilityCard("怎么用") {
                GoogleCompatibilityText("只在谷歌应用英文、数字反复恢复默认，而中文仍正常时使用。")
                GoogleStepCard("1", "先应用字体", "在洛书应用需要的中文、英文和数字字体，并按提示完成重启。")
                GoogleStepCard("2", "开启兼容", "点击「开启 Google 字体兼容」并确认；显示已开启后完整重启一次。")
                GoogleStepCard("3", "验证保持", "检查 Google Play 等应用，放到后台后再次打开，确认英文和数字没有恢复默认。")
                GoogleCompatibilityText("之前用独立脚本开启过的，本页会直接识别原恢复记录，不需要重复执行。")
            }
        }
        item {
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(22.dp),
                color = MaterialTheme.colorScheme.errorContainer.copy(alpha = .62f),
            ) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    Text(
                        "默认卸载模块一定要关",
                        color = MaterialTheme.colorScheme.onErrorContainer,
                        fontWeight = FontWeight.SemiBold,
                        fontSize = 15.sp,
                    )
                    Text(
                        "保持 Root 管理器中的「默认卸载模块」关闭，避免字体恢复默认或出现异常。",
                        color = MaterialTheme.colorScheme.onErrorContainer.copy(alpha = .82f),
                        fontSize = 13.sp,
                        lineHeight = 20.sp,
                    )
                }
            }
        }
        item {
            GoogleCompatibilityCard("影响与恢复") {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { detailsExpanded = !detailsExpanded }
                        .padding(vertical = 2.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(Modifier.weight(1f)) {
                        Text("详细原理与影响范围", fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                        Text(
                            if (detailsExpanded) "收起技术说明" else "需要时再展开，不影响正常操作",
                            color = LocalMiuixTokens.current.textSecondary,
                            fontSize = 12.sp,
                        )
                    }
                    Spacer(Modifier.width(8.dp))
                    Icon(
                        if (detailsExpanded) Icons.Rounded.ExpandLess else Icons.Rounded.ExpandMore,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                AnimatedVisibility(
                    visible = detailsExpanded,
                    enter = fadeIn(tween(LuoShuMotionTokens.Fast)) +
                        expandVertically(tween(LuoShuMotionTokens.Normal, easing = FastOutSlowInEasing)),
                    exit = fadeOut(tween(140)) +
                        shrinkVertically(tween(170, easing = FastOutSlowInEasing)),
                ) {
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        GoogleCompatibilityText("只停用当前用户的 Google 下载字体提供组件，不停用整个谷歌服务，不删除字体缓存、账户或应用数据。")
                        GoogleCompatibilityText("会影响该用户所有依赖 GMS 下载字体的应用，可能涉及下载式表情字体；修改时相关 GMS 进程可能重启。")
                        GoogleCompatibilityText("此设置跨重启保留。停用模块不会保证自动撤销；停用或卸载洛书前，请先点击「恢复原设置」并完整重启；卸载脚本也会尝试恢复有记录的设置。")
                        GoogleCompatibilityText("不保证替换应用内置字体、网页指定字体或已经打开的旧字体，也不会自动封禁联网或强停前台应用。")
                    }
                }
            }
        }
    }
    confirmAction?.let { action ->
        val enabling = action == "enable"
        AlertDialog(
            onDismissRequest = { confirmAction = null },
            shape = RoundedCornerShape(28.dp),
            title = { Text(if (enabling) "开启 Google 字体兼容？" else "恢复原设置？") },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(if (enabling)
                        "将停用当前 Android 用户的 Google 字体提供组件，让依赖它的应用尝试使用备用字体。影响该用户全部依赖 GMS 下载字体的应用，可能影响下载式表情字体，并可能重启相关 GMS 进程。"
                    else "将依据保存的恢复记录，还原开启前的组件状态；不会一律强制启用，也不会修改其他用户或其他组件。")
                    Text("不会清除账户、应用数据或字体缓存。完成后请完整重启手机。")
                    if (enabling) Text("停用或卸载洛书前，先在此页恢复原设置。此功能不保证所有页面永不回退。")
                }
            },
            dismissButton = { TextButton(onClick = { confirmAction = null }) { Text("取消") } },
            confirmButton = {
                TextButton(enabled = idle && (if (enabling) state.canEnable else state.canRestore), onClick = {
                    confirmAction = null
                    if (enabling) model.enable() else model.restore()
                }) { Text(if (enabling) "了解影响，确认开启" else "确认恢复") }
            },
        )
    }
}

@Composable
private fun GoogleStepCard(number: String, title: String, body: String) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        color = MaterialTheme.colorScheme.primary.copy(alpha = .07f),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 13.dp, vertical = 12.dp),
            verticalAlignment = Alignment.Top,
        ) {
            Surface(
                modifier = Modifier.size(28.dp),
                shape = RoundedCornerShape(10.dp),
                color = MaterialTheme.colorScheme.primary.copy(alpha = .13f),
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.Center,
                ) {
                    Text(number, color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                }
            }
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Text(title, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                GoogleCompatibilityText(body)
            }
        }
    }
}

@Composable
private fun GoogleCompatibilityCard(title: String, content: @Composable () -> Unit) {
    Surface(Modifier.fillMaxWidth(), shape = RoundedCornerShape(24.dp),
        color = LocalMiuixTokens.current.cardBackground, shadowElevation = 1.dp) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(title, fontSize = 16.sp, lineHeight = 24.sp, fontWeight = FontWeight.SemiBold)
            content()
        }
    }
}

@Composable
private fun GoogleCompatibilityText(text: String) {
    Text(text, color = LocalMiuixTokens.current.textSecondary, fontSize = 14.sp, lineHeight = 22.sp)
}
