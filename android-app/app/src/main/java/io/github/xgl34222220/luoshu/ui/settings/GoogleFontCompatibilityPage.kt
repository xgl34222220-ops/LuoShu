package io.github.xgl34222220.luoshu.ui.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
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

@Composable
internal fun GoogleFontCompatibilityPage() {
    val model: GoogleFontCompatibilityModel = viewModel()
    val state = model.ui
    val owner = LocalLifecycleOwner.current
    var confirmAction by rememberSaveable { mutableStateOf<String?>(null) }
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
                if (!idle) CircularProgressIndicator(Modifier.size(24.dp), strokeWidth = 2.dp)
                Text(if (state.busy) "正在处理，请稍候…" else state.title,
                    fontSize = 18.sp, lineHeight = 26.sp, fontWeight = FontWeight.SemiBold)
                GoogleCompatibilityText(state.message)
                state.user?.let { GoogleCompatibilityText("作用范围：当前 Android 用户 $it") }
                if (state.managed) GoogleCompatibilityText("已找到恢复记录 · 兼容之前的独立脚本")
                if (state.resultMessage.isNotBlank()) {
                    Text(state.resultMessage, color = MaterialTheme.colorScheme.primary, fontSize = 14.sp, lineHeight = 22.sp)
                }
                if (state.error.isNotBlank()) {
                    Text(state.error, color = MaterialTheme.colorScheme.error, fontSize = 14.sp, lineHeight = 22.sp)
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
                GoogleCompatibilityText("用于谷歌商店等应用的英文、数字反复恢复默认，而中文仍正常的情况。不是必须开启的通用设置。")
                GoogleCompatibilityText("1. 先在洛书应用需要的自定义字体，并按提示完成重启。")
                GoogleCompatibilityText("2. 点击「开启 Google 字体兼容」，阅读提示并确认。显示已开启后，完整重启一次手机。")
                GoogleCompatibilityText("3. 检查谷歌商店；放到后台一段时间，再打开检查英文和数字是否保持。组件已停用不等于字体效果已验证。")
                GoogleCompatibilityText("之前已用脚本开启的：本页会识别原恢复记录，不用再执行命令，也不用重复开启。")
            }
        }
        item {
            GoogleCompatibilityCard("影响与恢复") {
                GoogleCompatibilityText("只停用当前用户的 Google 下载字体提供组件，不停用整个谷歌服务，不删除字体缓存、账户或应用数据。")
                GoogleCompatibilityText("会影响该用户所有依赖 GMS 下载字体的应用，可能涉及下载式表情字体；修改时相关 GMS 进程可能重启。")
                GoogleCompatibilityText("此设置跨重启保留。停用模块不会保证自动撤销：停用或卸载洛书前，请先点击「恢复原设置」并完整重启。卸载脚本也会尝试恢复有记录的设置，失败记录会保留。")
                GoogleCompatibilityText("不保证替换应用内置字体、网页指定字体或已经打开的旧字体。不自动封禁联网，不强停前台应用。")
                GoogleCompatibilityText("「默认卸载模块」请保持关闭。开启和恢复均只在你确认后执行。")
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
