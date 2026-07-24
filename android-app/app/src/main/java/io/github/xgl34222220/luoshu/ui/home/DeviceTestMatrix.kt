package io.github.xgl34222220.luoshu.ui.home

import android.content.Context
import android.net.Uri
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.FileDownload
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import java.time.Instant
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

private const val DEVICE_MATRIX_SCHEMA = 1
private const val DEVICE_MATRIX_TYPE = "luoshu-device-test-matrix"
private const val DEVICE_MATRIX_TARGET_VERSION = "v2.2.2"
private const val DEVICE_MATRIX_MAX_RECORDS = 24
private const val DEVICE_MATRIX_MAX_NOTE = 200

internal enum class DeviceTestResult {
    PASS,
    ISSUE,
}

@Immutable
internal data class DeviceTestMatrixRecord(
    val id: String,
    val recordedAt: Long,
    val moduleVersion: String,
    val androidApi: Int,
    val rootManager: String,
    val mountEngine: String,
    val trustLevel: String,
    val alignmentMode: String,
    val profileKind: String,
    val result: DeviceTestResult,
    val passedChecks: Int,
    val totalChecks: Int,
    val note: String = "",
) {
    val environmentKey: String
        get() = listOf(androidApi, rootManager, mountEngine, alignmentMode).joinToString("|")

    val replacementKey: String
        get() = listOf(moduleVersion, environmentKey, profileKind).joinToString("|")
}

internal enum class PreReleaseGateSeverity {
    READY,
    WARNING,
    BLOCKER,
}

@Immutable
internal data class PreReleaseGateCheck(
    val id: String,
    val title: String,
    val detail: String,
    val severity: PreReleaseGateSeverity,
)

@Immutable
internal data class PreReleaseReadinessReport(
    val targetVersion: String,
    val checks: List<PreReleaseGateCheck>,
) {
    val blockerCount: Int get() = checks.count { it.severity == PreReleaseGateSeverity.BLOCKER }
    val warningCount: Int get() = checks.count { it.severity == PreReleaseGateSeverity.WARNING }
    val ready: Boolean get() = blockerCount == 0
}

internal fun buildDeviceTestMatrixRecord(
    state: HomeUiState,
    trust: DeviceTrustState,
    checks: List<DeviceAcceptanceCheck>,
    note: String,
    recordedAt: Long = System.currentTimeMillis(),
    androidApi: Int = Build.VERSION.SDK_INT,
): DeviceTestMatrixRecord {
    val passed = checks.count { it.passed }
    val profileKind = if (state.currentFont.contains("默认") || state.currentFont.equals("default", ignoreCase = true)) {
        "default"
    } else {
        "custom"
    }
    val environment = listOf(androidApi, state.rootManager, state.mountEngine, trust.mode, profileKind).joinToString("|")
    return DeviceTestMatrixRecord(
        id = "${recordedAt}-${environment.hashCode().toUInt().toString(16)}",
        recordedAt = recordedAt,
        moduleVersion = state.version,
        androidApi = androidApi,
        rootManager = state.rootManager.ifBlank { "unknown" },
        mountEngine = state.mountEngine.ifBlank { "unknown" },
        trustLevel = trust.level.name.lowercase(),
        alignmentMode = trust.mode.ifBlank { "unknown" },
        profileKind = profileKind,
        result = if (checks.isNotEmpty() && passed == checks.size) DeviceTestResult.PASS else DeviceTestResult.ISSUE,
        passedChecks = passed,
        totalChecks = checks.size,
        note = note.trim().take(DEVICE_MATRIX_MAX_NOTE),
    )
}

internal fun mergeDeviceTestMatrixRecord(
    records: List<DeviceTestMatrixRecord>,
    next: DeviceTestMatrixRecord,
): List<DeviceTestMatrixRecord> = (records.filterNot { it.replacementKey == next.replacementKey } + next)
    .sortedByDescending { it.recordedAt }
    .take(DEVICE_MATRIX_MAX_RECORDS)

internal fun buildPreReleaseReadinessReport(
    state: HomeUiState,
    trust: DeviceTrustState,
    checks: List<DeviceAcceptanceCheck>,
    records: List<DeviceTestMatrixRecord>,
    targetVersion: String = DEVICE_MATRIX_TARGET_VERSION,
    now: Long = System.currentTimeMillis(),
): PreReleaseReadinessReport {
    val acceptanceReady = checks.isNotEmpty() && checks.all { it.passed }
    val versionReady = state.version.lowercase().startsWith(targetVersion.lowercase())
    val trustReady = trust.alignment == "verified" && trust.mode == "aligned"
    val runtimeReady = !state.taskRunning && !state.rebootRequired
    val passingForCurrentVersion = records.filter {
        it.moduleVersion == state.version && it.result == DeviceTestResult.PASS
    }
    val environments = passingForCurrentVersion.map { it.environmentKey }.toSet()
    val latestPass = passingForCurrentVersion.maxOfOrNull { it.recordedAt }
    val latestFresh = latestPass != null && now - latestPass <= 14L * 24L * 60L * 60L * 1000L
    val issueCount = records.count { it.moduleVersion == state.version && it.result == DeviceTestResult.ISSUE }

    return PreReleaseReadinessReport(
        targetVersion = targetVersion,
        checks = listOf(
            PreReleaseGateCheck(
                id = "version",
                title = "候选版本号",
                detail = if (versionReady) "模块版本 ${state.version} 已进入 $targetVersion 候选线" else "当前仍是 ${state.version}，发布前需要切换到 $targetVersion 预发行版本",
                severity = if (versionReady) PreReleaseGateSeverity.READY else PreReleaseGateSeverity.BLOCKER,
            ),
            PreReleaseGateCheck(
                id = "acceptance",
                title = "当前真机验收",
                detail = if (acceptanceReady) "自动证据与人工场景全部通过" else "当前仅通过 ${checks.count { it.passed }}/${checks.size} 项验收",
                severity = if (acceptanceReady) PreReleaseGateSeverity.READY else PreReleaseGateSeverity.BLOCKER,
            ),
            PreReleaseGateCheck(
                id = "trust",
                title = "设备加载证据",
                detail = if (trustReady) "开机加载验证通过，设备处于对齐模式" else "需要 verified + aligned，兼容或未知模式不能作为发布证据",
                severity = if (trustReady) PreReleaseGateSeverity.READY else PreReleaseGateSeverity.BLOCKER,
            ),
            PreReleaseGateCheck(
                id = "runtime",
                title = "候选运行状态",
                detail = if (runtimeReady) "没有执行中任务或待重启变更" else "仍有执行中任务或字体变更等待完整重启",
                severity = if (runtimeReady) PreReleaseGateSeverity.READY else PreReleaseGateSeverity.BLOCKER,
            ),
            PreReleaseGateCheck(
                id = "matrix-pass",
                title = "测试矩阵通过记录",
                detail = if (passingForCurrentVersion.isNotEmpty()) "当前版本已有 ${passingForCurrentVersion.size} 条通过记录" else "保存当前验收结果后才能形成可追溯的真机证据",
                severity = if (passingForCurrentVersion.isNotEmpty()) PreReleaseGateSeverity.READY else PreReleaseGateSeverity.BLOCKER,
            ),
            PreReleaseGateCheck(
                id = "matrix-diversity",
                title = "环境覆盖",
                detail = if (environments.size >= 2) "已覆盖 ${environments.size} 种 Android/Root/挂载环境" else "当前仅覆盖 ${environments.size} 种环境，建议至少补充第二种 Root 或挂载环境",
                severity = if (environments.size >= 2) PreReleaseGateSeverity.READY else PreReleaseGateSeverity.WARNING,
            ),
            PreReleaseGateCheck(
                id = "matrix-freshness",
                title = "验收时效",
                detail = when {
                    latestPass == null -> "尚无当前版本的通过记录"
                    latestFresh -> "最近通过记录在 14 天内"
                    else -> "最近通过记录已超过 14 天，建议重新验收候选包"
                },
                severity = if (latestFresh) PreReleaseGateSeverity.READY else PreReleaseGateSeverity.WARNING,
            ),
            PreReleaseGateCheck(
                id = "known-issues",
                title = "已记录问题",
                detail = if (issueCount == 0) "当前版本矩阵没有问题记录" else "当前版本保留 $issueCount 条问题记录，发布说明需要逐项确认",
                severity = if (issueCount == 0) PreReleaseGateSeverity.READY else PreReleaseGateSeverity.WARNING,
            ),
        ),
    )
}

internal fun encodeDeviceTestMatrix(
    records: List<DeviceTestMatrixRecord>,
    report: PreReleaseReadinessReport,
    generatedAt: Long = System.currentTimeMillis(),
): String {
    val checks = JSONArray().apply {
        report.checks.forEach { check ->
            put(
                JSONObject()
                    .put("id", check.id)
                    .put("title", check.title)
                    .put("detail", check.detail)
                    .put("severity", check.severity.name.lowercase()),
            )
        }
    }
    val matrix = JSONArray().apply {
        records.sortedByDescending { it.recordedAt }.forEach { record ->
            put(record.toJson())
        }
    }
    return JSONObject()
        .put("schema", DEVICE_MATRIX_SCHEMA)
        .put("type", DEVICE_MATRIX_TYPE)
        .put("targetVersion", report.targetVersion)
        .put("generatedAt", generatedAt)
        .put("privacy", "不包含设备型号、指纹、序列号、字体名称或文件路径")
        .put("ready", report.ready)
        .put("blockers", report.blockerCount)
        .put("warnings", report.warningCount)
        .put("checks", checks)
        .put("records", matrix)
        .toString(2)
}

internal class DeviceTestMatrixStore(context: Context) {
    private val preferences = context.applicationContext.getSharedPreferences(
        "device-test-matrix-v1",
        Context.MODE_PRIVATE,
    )

    fun load(): List<DeviceTestMatrixRecord> = runCatching {
        val root = JSONObject(preferences.getString("matrix", "{}") ?: "{}")
        val array = root.optJSONArray("records") ?: JSONArray()
        buildList {
            for (index in 0 until array.length()) {
                array.optJSONObject(index)?.toDeviceTestRecord()?.let(::add)
            }
        }.sortedByDescending { it.recordedAt }.take(DEVICE_MATRIX_MAX_RECORDS)
    }.getOrDefault(emptyList())

    fun save(records: List<DeviceTestMatrixRecord>) {
        val array = JSONArray().apply {
            records.sortedByDescending { it.recordedAt }.take(DEVICE_MATRIX_MAX_RECORDS).forEach { put(it.toJson()) }
        }
        preferences.edit().putString(
            "matrix",
            JSONObject().put("schema", DEVICE_MATRIX_SCHEMA).put("records", array).toString(),
        ).apply()
    }

    fun clear() {
        preferences.edit().remove("matrix").apply()
    }
}

@Composable
internal fun DeviceTestMatrixDialog(
    style: UiStyle,
    state: HomeUiState,
    trust: DeviceTrustState,
    checks: List<DeviceAcceptanceCheck>,
    onDismiss: () -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val store = remember(context.applicationContext) { DeviceTestMatrixStore(context.applicationContext) }
    var records by remember { mutableStateOf(store.load()) }
    var note by remember { mutableStateOf("") }
    var status by remember { mutableStateOf("") }
    var errorMessage by remember { mutableStateOf("") }
    val report = buildPreReleaseReadinessReport(state, trust, checks, records)

    val exportLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("application/json"),
    ) { uri: Uri? ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            val result = runCatching {
                withContext(Dispatchers.IO) {
                    context.contentResolver.openOutputStream(uri, "wt")?.bufferedWriter()?.use { writer ->
                        writer.write(encodeDeviceTestMatrix(records, report))
                    } ?: error("无法打开测试矩阵目标文件")
                }
            }
            errorMessage = result.exceptionOrNull()?.message.orEmpty()
            status = if (result.isSuccess) "匿名测试矩阵与预发行门禁报告已导出" else ""
        }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 34.dp else 28.dp),
        icon = {
            Icon(
                if (report.ready) Icons.Rounded.CheckCircle else Icons.Rounded.Warning,
                contentDescription = null,
                tint = if (report.ready) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
            )
        },
        title = { Text("真机测试矩阵 · v2.2.2", fontWeight = FontWeight.Black) },
        text = {
            LazyColumn(
                modifier = Modifier.fillMaxWidth().heightIn(max = 650.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                item {
                    Text(
                        "记录只保存 Android API、Root 管理器、挂载引擎、加载模式和通过结果，不保存型号、设备指纹、序列号、字体名称或路径。",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 10.sp,
                    )
                }
                item {
                    Surface(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(18.dp),
                        color = if (report.ready) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.errorContainer,
                    ) {
                        Column(Modifier.padding(11.dp)) {
                            Text(
                                if (report.ready) "本地预发行门禁通过" else "阻断 ${report.blockerCount} · 提示 ${report.warningCount}",
                                fontWeight = FontWeight.Black,
                                fontSize = 12.sp,
                            )
                            Text(
                                "当前：${state.version} · API ${Build.VERSION.SDK_INT} · ${state.rootManager} · ${state.mountEngine}",
                                fontSize = 9.sp,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis,
                            )
                        }
                    }
                }
                item { Text("预发行门禁", fontSize = 13.sp, fontWeight = FontWeight.Black) }
                items(report.checks, key = { "gate-${it.id}" }) { check -> PreReleaseGateRow(check) }
                item {
                    OutlinedTextField(
                        value = note,
                        onValueChange = { note = it.take(DEVICE_MATRIX_MAX_NOTE) },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("问题备注（可选）") },
                        supportingText = { Text("${note.length}/$DEVICE_MATRIX_MAX_NOTE；不要填写型号、序列号或私人路径") },
                        minLines = 2,
                        maxLines = 3,
                    )
                }
                item {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(
                            onClick = {
                                val record = buildDeviceTestMatrixRecord(state, trust, checks, note)
                                records = mergeDeviceTestMatrixRecord(records, record)
                                store.save(records)
                                note = ""
                                status = if (record.result == DeviceTestResult.PASS) "当前环境通过记录已保存" else "当前环境问题记录已保存"
                                errorMessage = ""
                            },
                            modifier = Modifier.weight(1f),
                        ) { Text("记录当前结果", fontSize = 10.sp) }
                        OutlinedButton(
                            onClick = { exportLauncher.launch(deviceMatrixFileName()) },
                            enabled = records.isNotEmpty(),
                            modifier = Modifier.weight(1f),
                        ) {
                            Icon(Icons.Rounded.FileDownload, contentDescription = null, modifier = Modifier.size(17.dp))
                            Spacer(Modifier.size(5.dp))
                            Text("导出报告", fontSize = 10.sp)
                        }
                    }
                }
                item { Text("已保存矩阵（${records.size}/$DEVICE_MATRIX_MAX_RECORDS）", fontSize = 13.sp, fontWeight = FontWeight.Black) }
                if (records.isEmpty()) {
                    item {
                        Text("尚无记录。完成当前验收后保存，才能形成可追溯的预发行真机证据。", fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                } else {
                    items(records, key = { it.id }) { record -> DeviceTestRecordRow(record) }
                    item {
                        TextButton(
                            onClick = {
                                records = emptyList()
                                store.clear()
                                status = "测试矩阵记录已清空"
                            },
                            modifier = Modifier.fillMaxWidth(),
                        ) { Text("清空本机矩阵记录", color = MaterialTheme.colorScheme.error) }
                    }
                }
                if (status.isNotBlank()) {
                    item {
                        Surface(Modifier.fillMaxWidth(), RoundedCornerShape(16.dp), MaterialTheme.colorScheme.primaryContainer) {
                            Text(status, modifier = Modifier.padding(10.dp), fontSize = 10.sp)
                        }
                    }
                }
                if (errorMessage.isNotBlank()) {
                    item {
                        Surface(Modifier.fillMaxWidth(), RoundedCornerShape(16.dp), MaterialTheme.colorScheme.errorContainer) {
                            Text(errorMessage, modifier = Modifier.padding(10.dp), fontSize = 10.sp, color = MaterialTheme.colorScheme.onErrorContainer)
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("完成", fontWeight = FontWeight.Black) } },
    )
}

@Composable
private fun PreReleaseGateRow(check: PreReleaseGateCheck) {
    val color = when (check.severity) {
        PreReleaseGateSeverity.READY -> MaterialTheme.colorScheme.primary
        PreReleaseGateSeverity.WARNING -> MaterialTheme.colorScheme.tertiary
        PreReleaseGateSeverity.BLOCKER -> MaterialTheme.colorScheme.error
    }
    Surface(Modifier.fillMaxWidth(), RoundedCornerShape(16.dp), color.copy(alpha = .10f)) {
        Row(Modifier.padding(9.dp), verticalAlignment = Alignment.Top) {
            Icon(
                if (check.severity == PreReleaseGateSeverity.READY) Icons.Rounded.CheckCircle else Icons.Rounded.Warning,
                contentDescription = null,
                tint = color,
                modifier = Modifier.size(19.dp),
            )
            Spacer(Modifier.size(7.dp))
            Column(Modifier.weight(1f)) {
                Text(check.title, fontSize = 10.sp, fontWeight = FontWeight.Black)
                Text(check.detail, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 9.sp, lineHeight = 13.sp)
            }
        }
    }
}

@Composable
private fun DeviceTestRecordRow(record: DeviceTestMatrixRecord) {
    val pass = record.result == DeviceTestResult.PASS
    val color = if (pass) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
    Surface(Modifier.fillMaxWidth(), RoundedCornerShape(17.dp), color.copy(alpha = .09f)) {
        Row(Modifier.padding(10.dp), verticalAlignment = Alignment.Top) {
            Icon(
                if (pass) Icons.Rounded.CheckCircle else Icons.Rounded.Warning,
                contentDescription = null,
                tint = color,
                modifier = Modifier.size(20.dp),
            )
            Spacer(Modifier.size(8.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    "${record.moduleVersion} · API ${record.androidApi} · ${record.rootManager}",
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Black,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    "${record.mountEngine} · ${record.alignmentMode} · ${record.passedChecks}/${record.totalChecks} · ${formatMatrixTime(record.recordedAt)}",
                    fontSize = 9.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                if (record.note.isNotBlank()) Text(record.note, fontSize = 9.sp, lineHeight = 13.sp)
            }
        }
    }
}

private fun DeviceTestMatrixRecord.toJson(): JSONObject = JSONObject()
    .put("id", id)
    .put("recordedAt", recordedAt)
    .put("moduleVersion", moduleVersion)
    .put("androidApi", androidApi)
    .put("rootManager", rootManager)
    .put("mountEngine", mountEngine)
    .put("trustLevel", trustLevel)
    .put("alignmentMode", alignmentMode)
    .put("profileKind", profileKind)
    .put("result", result.name.lowercase())
    .put("passedChecks", passedChecks)
    .put("totalChecks", totalChecks)
    .put("note", note)

private fun JSONObject.toDeviceTestRecord(): DeviceTestMatrixRecord? {
    val result = when (optString("result")) {
        "pass" -> DeviceTestResult.PASS
        "issue" -> DeviceTestResult.ISSUE
        else -> return null
    }
    val timestamp = optLong("recordedAt", 0L)
    val version = optString("moduleVersion").trim()
    val api = optInt("androidApi", 0)
    if (timestamp <= 0L || version.isBlank() || api <= 0) return null
    return DeviceTestMatrixRecord(
        id = optString("id").ifBlank { "$timestamp-${hashCode().toUInt().toString(16)}" },
        recordedAt = timestamp,
        moduleVersion = version,
        androidApi = api,
        rootManager = optString("rootManager", "unknown").take(80),
        mountEngine = optString("mountEngine", "unknown").take(80),
        trustLevel = optString("trustLevel", "unknown").take(24),
        alignmentMode = optString("alignmentMode", "unknown").take(24),
        profileKind = optString("profileKind", "custom").take(24),
        result = result,
        passedChecks = optInt("passedChecks", 0).coerceAtLeast(0),
        totalChecks = optInt("totalChecks", 0).coerceAtLeast(0),
        note = optString("note").trim().take(DEVICE_MATRIX_MAX_NOTE),
    )
}

private fun formatMatrixTime(timestamp: Long): String = runCatching {
    Instant.ofEpochMilli(timestamp).atZone(java.time.ZoneId.systemDefault())
        .format(DateTimeFormatter.ofPattern("MM-dd HH:mm"))
}.getOrDefault("未知时间")

private fun deviceMatrixFileName(): String {
    val timestamp = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss"))
    return "LuoShu-device-test-matrix-$timestamp.json"
}
