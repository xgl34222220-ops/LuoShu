package io.github.xgl34222220.luoshu.ui.home

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ChevronRight
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.xgl34222220.luoshu.RootShell
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuGlyph
import io.github.xgl34222220.luoshu.ui.theme.LuoShuIconTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuSmoothShape
import io.github.xgl34222220.luoshu.ui.theme.luoShuGlassHighlight
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

internal class HyperOsCoverageModel : ViewModel() {
    var status by mutableStateOf<HyperOsCoverageStatus?>(null)
        private set
    var settingBusy by mutableStateOf(false)
        private set
    var settingMessage by mutableStateOf("")
        private set
    var locateBusy by mutableStateOf(false)
        private set
    var locateResult by mutableStateOf<CoverageLocateResult?>(null)
        private set
    var locateError by mutableStateOf("")
        private set
    private var loaded = false

    fun load(force: Boolean = false) {
        if (loaded && !force) return
        loaded = true
        viewModelScope.launch {
            try {
                val result = RootShell.exec(hyperOsCoverageStatusCommand(), timeoutMs = 30_000L)
                status = if (result.code == 0) runCatching { parseHyperOsCoverageStatus(result.stdout) }.getOrNull() else null
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                status = null
            }
        }
    }

    fun set(setting: HyperOsSetting, enabled: Boolean) {
        val current = status ?: return
        if (settingBusy) return
        settingBusy = true
        settingMessage = ""
        viewModelScope.launch {
            try {
                val result = RootShell.exec(hyperOsSettingCommand(setting, enabled), timeoutMs = 30_000L)
                val ok = result.code == 0 &&
                    runCatching { bridgeJson(result.stdout).optString("status") == "ok" }.getOrDefault(false)
                if (ok) {
                    status = current.with(setting, enabled)
                    settingMessage = settingChangeMessage(setting)
                } else {
                    settingMessage = "保存失败，请确认已授予 Root 权限后重试。"
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                settingMessage = "保存失败，请确认已授予 Root 权限后重试。"
            } finally {
                settingBusy = false
            }
        }
    }

    fun locate(packageName: String) {
        if (locateBusy) return
        if (!isValidCoveragePackage(packageName)) {
            locateError = "包名格式不正确，例如 com.android.systemui"
            return
        }
        locateBusy = true
        locateError = ""
        locateResult = null
        viewModelScope.launch {
            try {
                val result = RootShell.exec(coverageLocateCommand(packageName), timeoutMs = 60_000L)
                locateResult = parseCoverageLocate(result.stdout)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                locateError = error.message ?: "定位失败，请重试。"
            } finally {
                locateBusy = false
            }
        }
    }
}

/** Home section: strong theme-store hint plus the 未覆盖界面定位 / HyperOS 覆盖设置 entry. */
@Composable
internal fun HyperOsCoverageSection(model: HyperOsCoverageModel) {
    val status = model.status ?: return
    if (!status.hyperOs) return
    val tokens = LocalMiuixTokens.current
    val shape = LuoShuSmoothShape(24.dp)
    var dialogOpen by rememberSaveable { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        themeWarningText(status.theme)?.let { warning ->
            Surface(
                color = tokens.cardBackground,
                shape = shape,
                border = BorderStroke(1.dp, tokens.warning.copy(alpha = .5f)),
                shadowElevation = tokens.cardShadowElevation,
                modifier = Modifier.fillMaxWidth().luoShuGlassHighlight(shape),
            ) {
                Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        LuoShuGlyph(Icons.Rounded.Warning, null, LuoShuIconTokens.StatusGlyph, tint = tokens.warning)
                        Text("主题商店字体正在接管系统字体", style = MaterialTheme.typography.titleSmall,
                            color = tokens.textPrimary, fontWeight = FontWeight.SemiBold)
                    }
                    Text(warning, style = MaterialTheme.typography.bodySmall, color = tokens.textPrimary)
                    if (status.theme.names.isNotEmpty()) {
                        Text("主题字体：" + status.theme.names.take(4).joinToString("、"),
                            style = MaterialTheme.typography.bodySmall, color = tokens.textSecondary)
                    }
                }
            }
        }
        Surface(
            color = tokens.cardBackground,
            shape = shape,
            border = BorderStroke(1.dp, tokens.glassOutlineBrush),
            shadowElevation = tokens.cardShadowElevation,
            modifier = Modifier.fillMaxWidth().luoShuGlassHighlight(shape),
        ) {
            Row(
                Modifier.fillMaxWidth().clickable(role = Role.Button) { dialogOpen = true }.padding(18.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                LuoShuGlyph(Icons.Rounded.Search, null, LuoShuIconTokens.StatusGlyph, tint = MaterialTheme.colorScheme.primary)
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text("未覆盖界面定位", style = MaterialTheme.typography.titleSmall, color = tokens.textPrimary)
                    Text("哪里没换字体？选界面查原因 · HyperOS 覆盖设置",
                        style = MaterialTheme.typography.bodySmall, color = tokens.textSecondary)
                }
                LuoShuGlyph(Icons.Rounded.ChevronRight, null, LuoShuIconTokens.ToolGlyph, tint = tokens.textSecondary)
            }
        }
    }
    if (dialogOpen) {
        HyperOsCoverageDialog(model = model, status = status, onDismiss = { dialogOpen = false })
    }
}

@Composable
private fun HyperOsCoverageDialog(model: HyperOsCoverageModel, status: HyperOsCoverageStatus, onDismiss: () -> Unit) {
    val tokens = LocalMiuixTokens.current
    var packageName by rememberSaveable { mutableStateOf(COVERAGE_PRESETS.first().packageName) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("未覆盖界面定位") },
        text = {
            Column(
                Modifier.fillMaxWidth().heightIn(max = 520.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Text("先打开没有换字体的界面，再回到这里选择它。洛书只读取该进程实际加载的字体文件，不做任何修改。",
                    style = MaterialTheme.typography.bodySmall, color = tokens.textSecondary)
                COVERAGE_PRESETS.forEach { preset ->
                    val selected = preset.packageName == packageName
                    Text(
                        (if (selected) "● " else "○ ") + preset.label,
                        style = MaterialTheme.typography.bodyMedium,
                        color = if (selected) MaterialTheme.colorScheme.primary else tokens.textPrimary,
                        modifier = Modifier.fillMaxWidth().clickable(role = Role.RadioButton) { packageName = preset.packageName }
                            .padding(vertical = 4.dp),
                    )
                }
                OutlinedTextField(
                    value = packageName,
                    onValueChange = { packageName = it.trim() },
                    singleLine = true,
                    label = { Text("包名") },
                    modifier = Modifier.fillMaxWidth(),
                )
                Button(onClick = { model.locate(packageName) }, enabled = !model.locateBusy,
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
                    if (model.locateBusy) CircularProgressIndicator(strokeWidth = 2.dp, modifier = Modifier.heightIn(max = 20.dp))
                    else Text("开始定位")
                }
                if (model.locateError.isNotBlank()) {
                    Text(model.locateError, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                }
                model.locateResult?.let { result ->
                    result.findings.forEach { finding ->
                        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(finding.title, style = MaterialTheme.typography.titleSmall, color = tokens.textPrimary)
                            if (finding.detail.isNotBlank()) {
                                Text(finding.detail, style = MaterialTheme.typography.bodySmall, color = tokens.textSecondary)
                            }
                            if (finding.files.isNotEmpty()) {
                                Text(finding.files.take(6).joinToString("\n"),
                                    style = MaterialTheme.typography.bodySmall, color = tokens.textSecondary)
                            }
                            Text("建议：" + finding.action, style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.primary)
                        }
                    }
                    if (result.keptByDesign.isNotEmpty()) {
                        Text("按设计保留原厂：" + result.keptByDesign.take(4).joinToString("；"),
                            style = MaterialTheme.typography.bodySmall, color = tokens.textSecondary)
                    }
                }
                Text(COVERAGE_SCOPE_NOTE, style = MaterialTheme.typography.bodySmall, color = tokens.textSecondary)
                Text("HyperOS 覆盖设置", style = MaterialTheme.typography.titleSmall, color = tokens.textPrimary,
                    modifier = Modifier.padding(top = 8.dp))
                HyperOsSetting.entries.forEach { setting ->
                    val checked = status.valueOf(setting)
                    Row(
                        Modifier.fillMaxWidth().clickable(role = Role.Switch, enabled = !model.settingBusy) {
                            model.set(setting, !checked)
                        }.padding(vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text(setting.title, style = MaterialTheme.typography.bodyMedium, color = tokens.textPrimary)
                            Text(setting.hint, style = MaterialTheme.typography.bodySmall, color = tokens.textSecondary)
                        }
                        Switch(checked = checked, onCheckedChange = null, enabled = !model.settingBusy)
                    }
                }
                if (model.settingMessage.isNotBlank()) {
                    Text(model.settingMessage, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary)
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("完成") } },
        dismissButton = { OutlinedButton(onClick = { model.load(force = true) }) { Text("刷新状态") } },
    )
}
