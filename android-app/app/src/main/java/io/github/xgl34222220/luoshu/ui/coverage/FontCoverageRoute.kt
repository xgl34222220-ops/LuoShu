package io.github.xgl34222220.luoshu.ui.coverage

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AutoFixHigh
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.ErrorOutline
import androidx.compose.material.icons.rounded.ExpandLess
import androidx.compose.material.icons.rounded.ExpandMore
import androidx.compose.material.icons.rounded.FilterAlt
import androidx.compose.material.icons.rounded.HourglassTop
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Security
import androidx.compose.material.icons.rounded.Verified
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.RootShell
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuDetailBar
import io.github.xgl34222220.luoshu.ui.theme.LuoShuHeaderAction
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject

private const val COVERAGE_BRIDGE = "/data/adb/modules/LuoShu/common/app_bridge.sh"

private enum class CoverageFilter(val label: String) {
    ALL("全部"),
    REPLACED("已替换"),
    UNREPLACED("未替换"),
    REMEDIABLE("可补齐"),
    PROTECTED("系统保护"),
    PENDING("待验证"),
}

private enum class CoverageGroup(val label: String) {
    STATUS("按状态"),
    PARTITION("按分区"),
}

internal data class CoverageRouteInfo(
    val family: String = "",
    val targetPath: String = "",
    val generatedFile: String = "",
    val route: String = "",
    val planReason: String = "",
)

internal data class CoverageSlot(
    val path: String,
    val name: String,
    val partition: String,
    val format: String,
    val weight: Int,
    val style: String,
    val source: String,
    val families: List<String>,
    val state: String,
    val category: String,
    val reason: String,
    val safeToRetry: Boolean,
    val routes: List<CoverageRouteInfo>,
    val replacementRoles: List<String> = emptyList(),
    val capabilityKnown: Boolean = false,
    val faceDetails: List<String> = emptyList(),
)

internal data class CoverageSummary(
    val total: Int = 0,
    val scanned: Int = 0,
    val textInventory: Int = 0,
    val dynamic: Int = 0,
    val runtime: Int = 0,
    val partial: Int = 0,
    val estimated: Int = 0,
    val replaceable: Int = 0,
    val replaced: Int = 0,
    val protected: Int = 0,
    val pending: Int = 0,
    val issues: Int = 0,
    val remediable: Int = 0,
)

internal data class CoverageData(
    val rom: String = "generic",
    val activeFont: String = "",
    val verificationState: String = "not-run",
    val summary: CoverageSummary = CoverageSummary(),
    val slots: List<CoverageSlot> = emptyList(),
)

private data class CoverageUiState(
    val loading: Boolean = true,
    val busy: Boolean = false,
    val data: CoverageData? = null,
    val message: String = "",
    val error: String = "",
    val exportPath: String = "",
)

private fun JSONObject.stringList(name: String): List<String> {
    val array = optJSONArray(name) ?: return emptyList()
    return buildList {
        for (index in 0 until array.length()) {
            array.optString(index).trim().takeIf { it.isNotBlank() }?.let(::add)
        }
    }
}

private fun JSONArray.routeList(): List<CoverageRouteInfo> = buildList {
    for (index in 0 until length()) {
        val item = optJSONObject(index) ?: continue
        add(
            CoverageRouteInfo(
                family = item.optString("family"),
                targetPath = item.optString("targetPath"),
                generatedFile = item.optString("generatedFile"),
                route = item.optString("route"),
                planReason = item.optString("planReason"),
            ),
        )
    }
}

private fun fallbackCategory(state: String): String = when (state) {
    "loaded" -> "replaced"
    "mount-visible", "mapped-unverified", "unconfirmed" -> "pending"
    "preserved", "protected" -> "protected"
    else -> "issue"
}

internal fun coverageDetectionLabel(rom: String): String =
    if (rom.isBlank() || rom.equals("generic", ignoreCase = true)) "自动检测" else rom

internal fun coverageSourceLabel(source: String): String = when (source) {
    "dynamic-font" -> "动态字体"
    "runtime-font" -> "运行容器"
    "xml" -> "系统字体配置与文件检测"
    "verified-scan" -> "字体文件内容检测"
    "census" -> "全系统字体普查"
    "heuristic" -> "旧版扫描记录"
    else -> "系统字体归档"
}

private fun coverageStyleLabel(style: String): String = when (style) {
    "normal", "regular", "" -> "常规"
    "italic" -> "斜体"
    "oblique" -> "倾斜"
    else -> style
}

private fun coverageRouteLabel(route: String): String = when (route) {
    "physical-safe", "physical" -> "系统文件替换"
    "xml" -> "系统字体配置"
    "stock" -> "原厂字体"
    else -> "字体处理记录"
}

internal fun coverageRoleLabels(roles: List<String>): String = roles.mapNotNull {
    when (it) {
        "cjk" -> "中文"
        "latin" -> "英文"
        "digit" -> "数字"
        else -> null
    }
}.distinct().joinToString(" · ")

private fun axisNumber(value: Double): String =
    if (value == value.toLong().toDouble()) value.toLong().toString() else value.toString()

private fun JSONObject.fontFaceDetails(): List<String> = buildList {
    val faces = optJSONArray("fontFaces") ?: return@buildList
    for (index in 0 until faces.length()) {
        val face = faces.optJSONObject(index) ?: continue
        val axes = face.optJSONObject("variationAxes") ?: JSONObject()
        val axisDescriptions = axes.keys().asSequence().sorted().mapNotNull { tag ->
            val axis = axes.optJSONObject(tag) ?: return@mapNotNull null
            val minimum = axis.optDouble("min")
            val maximum = axis.optDouble("max")
            if (!minimum.isFinite() || !maximum.isFinite()) return@mapNotNull null
            val name = when (tag) {
                "wght" -> "字重"
                "wdth" -> "字宽"
                "ital" -> "斜体"
                "slnt" -> "倾斜"
                "opsz" -> "字号"
                else -> tag
            }
            name + " " + axisNumber(minimum) + "–" + axisNumber(maximum)
        }.toList()
        add(buildString {
            append("第 ").append(face.optInt("faceIndex", index) + 1).append(" 面")
            val roles = coverageRoleLabels(face.stringList("replacementRoles"))
            if (roles.isNotBlank()) append(" · ").append(roles)
            append(" · ").append(coverageStyleLabel(face.optString("style", "normal")))
            if (axisDescriptions.isEmpty()) {
                append(" · 字重 ").append(face.optInt("weight", 400))
            } else {
                append("\n可变字体：").append(axisDescriptions.joinToString(" · "))
            }
            val reason = face.optString("preservedReason")
            if (reason.isNotBlank()) append("\n").append(reasonLabel(reason))
        })
    }
}

internal fun parseCoverage(root: JSONObject): CoverageData {
    require(root.optString("schema") == "device-font-slot-trace-v1") {
        "模块返回了不支持的字体覆盖数据"
    }
    val array = root.optJSONArray("slots") ?: JSONArray()
    val slots = buildList {
        for (index in 0 until array.length()) {
            val item = array.optJSONObject(index) ?: continue
            val state = item.optString("state", "unconfirmed")
            val path = item.optString("path")
            add(
                CoverageSlot(
                    path = path,
                    name = item.optString("slotName").ifBlank { path.substringAfterLast('/') },
                    partition = item.optString("partition"),
                    format = item.optString("format"),
                    weight = item.optInt("weight", 400),
                    style = item.optString("style", "normal"),
                    source = item.optString("source"),
                    families = item.stringList("families"),
                    state = state,
                    category = item.optString("category").ifBlank { fallbackCategory(state) },
                    reason = item.optString("reason"),
                    safeToRetry = item.optBoolean("safeToRetry", false),
                    routes = (item.optJSONArray("routes") ?: JSONArray()).routeList(),
                    replacementRoles = item.stringList("replacementRoles"),
                    capabilityKnown = item.optBoolean("capabilityKnown", false),
                    faceDetails = item.fontFaceDetails(),
                ),
            )
        }
    }
    val summaryJson = root.optJSONObject("summary") ?: JSONObject()
    val fallback = slots.groupingBy { it.category }.eachCount()
    return CoverageData(
        rom = root.optString("inventoryRomKind", "generic"),
        activeFont = root.optString("activeFont", ""),
        verificationState = root.optString("verificationState", "not-run"),
        summary = CoverageSummary(
            total = summaryJson.optInt("inventorySlots", slots.size),
            scanned = summaryJson.optInt("censusSlots", summaryJson.optInt("inventorySlots", slots.size)),
            textInventory = summaryJson.optInt("textInventorySlots", summaryJson.optInt("inventorySlots", slots.size)),
            dynamic = summaryJson.optInt("dynamicSlots", slots.count { it.source == "dynamic-font" }),
            runtime = summaryJson.optInt("runtimeSlots", slots.count { it.source == "runtime-font" }),
            partial = summaryJson.optInt("partial", slots.count { it.state == "partial" }),
            estimated = summaryJson.optInt("replaceableEstimatedSlots", 0),
            replaceable = summaryJson.optInt("replaceableSlots", summaryJson.optInt("inventorySlots", slots.size)),
            replaced = summaryJson.optInt("replaced", fallback["replaced"] ?: 0),
            protected = summaryJson.optInt("protected", fallback["protected"] ?: 0),
            pending = summaryJson.optInt("pending", fallback["pending"] ?: 0),
            issues = summaryJson.optInt("issues", fallback["issue"] ?: 0),
            remediable = summaryJson.optInt("remediable", slots.count { it.safeToRetry }),
        ),
        slots = slots,
    )
}

private fun extractJson(stdout: String, stderr: String): JSONObject {
    val line = sequenceOf(stdout, stderr)
        .flatMap { it.lineSequence() }
        .map { it.trim() }
        .lastOrNull { it.startsWith("{") && it.endsWith("}") }
        ?: error(stderr.ifBlank { stdout }.trim().ifBlank { "模块没有返回 JSON 数据" })
    return JSONObject(line)
}

private suspend fun readCoverage(command: String, timeoutMs: Long): CoverageData {
    val shell = "sh " + RootShell.quote(COVERAGE_BRIDGE) + " " + RootShell.quote(command)
    val result = RootShell.exec(shell, timeoutMs = timeoutMs)
    val json = extractJson(result.stdout, result.stderr)
    if (result.code != 0 || json.optString("status") == "error") {
        error(json.optString("message").ifBlank { result.stderr.ifBlank { "字体覆盖数据读取失败" } })
    }
    return parseCoverage(json)
}

private suspend fun runCoverageAction(command: String, timeoutMs: Long): JSONObject {
    val shell = "sh " + RootShell.quote(COVERAGE_BRIDGE) + " " + RootShell.quote(command)
    val result = RootShell.exec(shell, timeoutMs = timeoutMs)
    val json = extractJson(result.stdout, result.stderr)
    if (result.code != 0 || json.optString("status") == "error") {
        error(json.optString("message").ifBlank { result.stderr.ifBlank { "操作失败" } })
    }
    return json
}

private fun CoverageSlot.matches(filter: CoverageFilter, query: String): Boolean {
    val categoryMatch = when (filter) {
        CoverageFilter.ALL -> true
        CoverageFilter.REPLACED -> category == "replaced"
        CoverageFilter.UNREPLACED -> category == "issue"
        CoverageFilter.REMEDIABLE -> safeToRetry
        CoverageFilter.PROTECTED -> category == "protected"
        CoverageFilter.PENDING -> category == "pending"
    }
    if (!categoryMatch) return false
    val needle = query.trim()
    if (needle.isEmpty()) return true
    return listOf(
        name,
        path,
        partition,
        format,
        reason,
        source,
        families.joinToString(" "),
        routes.joinToString(" ") { it.family + " " + it.targetPath + " " + it.planReason },
    ).any { it.contains(needle, ignoreCase = true) }
}

private fun slotStatusLabel(slot: CoverageSlot): String = when (slot.state) {
    "loaded" -> "已替换"
    "mount-visible" -> "已挂载待确认"
    "mapped-unverified" -> "等待重启验证"
    "unconfirmed" -> "待确认"
    "preserved", "protected" -> "系统保护"
    "not-consumed" -> "未进入负载"
    "mapping-missing" -> "映射缺失"
    "missing-mount" -> "未挂载"
    "mismatch" -> "文件不一致"
    "partial" -> "部分生效"
    "source-unavailable" -> "当前字体不匹配"
    "not-inspected" -> "尚未替换"
    "unreplaced-dynamic" -> "动态字体未替换"
    "unreplaced-runtime" -> "运行容器未替换"
    else -> "需要检查"
}

private fun reasonLabel(reason: String): String = when (reason) {
    "" -> "暂无额外说明"
    "preserved-collection" -> "字体集合信息不完整，保持原厂"
    "preserved-style" -> "特殊样式保持原厂"
    "source-weight-missing" -> "当前字体缺少真实对应字重，保持原厂"
    "physical-safe-current-payload" -> "已生成对应系统文件的替换字体"
    "mutable-theme-font" -> "主题动态字体，尚未替换"
    "runtime-font-container", "runtime-font-alias" -> "运行容器字体需要独立挂载支持，尚未替换"
    "unreadable-dynamic-font" -> "无法读取动态字体，尚未替换"
    "unreadable-runtime-font" -> "无法读取运行容器字体，尚未替换"
    "unsupported-mount-root-path" -> "已识别字体，但当前挂载方式尚不支持此目录路径"
    "specialized-name" -> "Emoji、图标、符号或专用字体，系统保护"
    "not-promoted-to-ui-inventory" -> "已扫描到，但未判定为系统 UI 可替换字体"
    "visible-mount-evidence-missing" -> "重启后没有发现该目标的可见挂载"
    "visible-font-hash-mismatch" -> "可见字体与生成负载不一致"
    "visible-bytes-match-font-manager-unconfirmed" -> "挂载字节一致，但 FontManager 尚未确认"
    "visible-bytes-and-font-manager-confirmed" -> "挂载与 FontManager 均确认"
    "generated-slot-not-in-overlay" -> "已经生成，但没有进入最终挂载层"
    "inventory-slot-not-present-in-payload" -> "扫描到了，但当前字体负载没有消费这个槽位"
    "boot-verification-not-available" -> "等待完整重启后的加载验证"
    "slot-runtime-evidence-missing" -> "缺少该槽位的运行时加载证据"
    "physical-payload-present-but-partition-mount-failed" ->
        "补齐文件已经生成，但对应系统字体目录没有成功挂载；这属于挂载故障，不会再重复提交同一份补齐任务"
    "active-physical-payload-awaiting-mount-confirmation" -> "补齐文件已进入当前负载，等待挂载验证"
    "next-boot-payload-awaiting-reboot" -> "新字体已准备好，完整重启后验证，无需重复补齐"
    "active-physical-payload-and-mount-confirmed" -> "当前负载与系统挂载均已确认"
    "active-physical-payload-missing-slot" -> "当前负载缺少该字体槽，可通过补齐重新生成"
    else -> reason.replace('-', ' ')
}

private fun statusAccent(slot: CoverageSlot): Color = when (slot.category) {
    "replaced" -> Color(0xFF21966C)
    "protected" -> Color(0xFF687386)
    "pending" -> Color(0xFFB7791F)
    else -> Color(0xFFC74A4A)
}

private data class MetricSpec(
    val label: String,
    val value: Int,
    val icon: ImageVector,
    val accent: Color,
)

@Composable
internal fun FontCoverageRoute(
    style: UiStyle,
    activeFont: String,
    taskState: String,
    taskMessage: String,
    taskProgress: Int,
    rebootRequired: Boolean,
    onBack: () -> Unit,
    onTaskStarted: (String, Boolean) -> Unit,
    onReboot: () -> Unit,
) {
    var state by remember { mutableStateOf(CoverageUiState()) }
    var filterName by rememberSaveable { mutableStateOf(CoverageFilter.ALL.name) }
    var groupName by rememberSaveable { mutableStateOf(CoverageGroup.STATUS.name) }
    var query by rememberSaveable { mutableStateOf("") }
    var expandedPath by rememberSaveable { mutableStateOf("") }
    var confirmReapply by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    fun load(verify: Boolean = false) {
        if (state.busy) return
        state = state.copy(
            loading = state.data == null,
            busy = verify,
            error = "",
            message = if (verify) "正在重新验证挂载与 FontManager…" else "",
        )
        scope.launch {
            runCatching {
                readCoverage(
                    command = if (verify) "coverage_verify" else "coverage",
                    timeoutMs = if (verify) 120_000L else 45_000L,
                )
            }.onSuccess { data ->
                state = state.copy(
                    loading = false,
                    busy = false,
                    data = data,
                    message = if (verify) "验证完成，列表已刷新" else "",
                    error = "",
                )
            }.onFailure { error ->
                state = state.copy(
                    loading = false,
                    busy = false,
                    error = error.message.orEmpty().ifBlank { "字体覆盖读取失败" },
                )
            }
        }
    }

    val taskRunning = taskState in setOf("queued", "running")
    LaunchedEffect(activeFont, taskState, rebootRequired) {
        if (!taskRunning) load()
    }

    val filter = runCatching { CoverageFilter.valueOf(filterName) }.getOrDefault(CoverageFilter.ALL)
    val group = runCatching { CoverageGroup.valueOf(groupName) }.getOrDefault(CoverageGroup.STATUS)
    val visibleSlots = remember(state.data, filter, query) {
        state.data?.slots.orEmpty().filter { it.matches(filter, query) }
    }
    val groupedSlots = remember(visibleSlots, group) {
        when (group) {
            CoverageGroup.STATUS -> visibleSlots
                .groupBy { slotStatusLabel(it) }
                .toList()
                .sortedBy { (label, _) -> statusSortKey(label) }
            CoverageGroup.PARTITION -> visibleSlots
                .groupBy { it.partition.ifBlank { "unknown" } }
                .toList()
                .sortedBy { (label, _) -> label.lowercase() }
        }
    }
    val tokens = LocalMiuixTokens.current
    val data = state.data
    val coverageActiveFont = data?.activeFont?.takeIf { it.isNotBlank() } ?: activeFont
    val canReapply = coverageActiveFont !in setOf("", "default") &&
        !state.busy &&
        !taskRunning &&
        !rebootRequired &&
        (data?.summary?.remediable ?: 0) > 0
    val needsCoverageBootstrap = data == null &&
        activeFont !in setOf("", "default") &&
        (
            state.error.contains("重新应用一次") ||
                state.error.contains("没有可追踪的设备对齐负载")
            )

    Box(Modifier.fillMaxSize()) {
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(start = 18.dp, end = 18.dp, bottom = 122.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item(key = "top") {
                LuoShuDetailBar(title = "字体覆盖", onBack = onBack) {
                    LuoShuHeaderAction(
                        icon = Icons.Rounded.Refresh,
                        contentDescription = "刷新字体覆盖",
                        onClick = { load() },
                        enabled = !state.busy,
                        loading = state.loading,
                        containerColor = tokens.cardBackground,
                    )
                }
            }

            if (data != null) {
                item(key = "hero") {
                    CoverageHero(
                        data = data,
                        activeFont = coverageActiveFont,
                        rebootRequired = rebootRequired,
                    )
                }
                item(key = "search") {
                    OutlinedTextField(
                        value = query,
                        onValueChange = { query = it },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(20.dp),
                        singleLine = true,
                        leadingIcon = { Icon(Icons.Rounded.Search, null) },
                        placeholder = { Text("搜索字体名、路径、分区或原因") },
                    )
                }
                item(key = "filters") {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Row(
                            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            CoverageFilter.values().forEach { item ->
                                FilterChip(
                                    selected = filter == item,
                                    onClick = { filterName = item.name },
                                    label = { Text(item.label) },
                                    leadingIcon = if (filter == item) {
                                        { Icon(Icons.Rounded.FilterAlt, null, Modifier.size(16.dp)) }
                                    } else null,
                                )
                            }
                        }
                        Row(
                            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            CoverageGroup.values().forEach { item ->
                                FilterChip(
                                    selected = group == item,
                                    onClick = { groupName = item.name },
                                    label = { Text(item.label) },
                                )
                            }
                        }
                    }
                }
                if (state.message.isNotBlank() || state.error.isNotBlank()) {
                    item(key = "message") {
                        CoverageMessage(state.error.ifBlank { state.message }, state.error.isNotBlank())
                    }
                }
                if (visibleSlots.isEmpty()) {
                    item(key = "empty") { CoverageEmptyState() }
                } else {
                    groupedSlots.forEach { (label, slots) ->
                        item(key = "group-" + group.name + "-" + label) {
                            CoverageGroupHeader(label = label, count = slots.size)
                        }
                        items(slots, key = { it.path }) { slot ->
                            CoverageSlotCard(
                                slot = slot,
                                expanded = expandedPath == slot.path,
                                onToggle = {
                                    expandedPath = if (expandedPath == slot.path) "" else slot.path
                                },
                            )
                        }
                    }
                }
            } else if (state.loading) {
                item(key = "loading") {
                    Box(
                        Modifier.fillMaxWidth().height(240.dp),
                        contentAlignment = Alignment.Center,
                    ) {
                        CircularProgressIndicator()
                    }
                }
            } else {
                item(key = "error") {
                    Surface(
                        shape = RoundedCornerShape(24.dp),
                        color = MaterialTheme.colorScheme.errorContainer,
                    ) {
                        Column(
                            Modifier.fillMaxWidth().padding(20.dp),
                            verticalArrangement = Arrangement.spacedBy(10.dp),
                        ) {
                            Text(
                                "字体覆盖暂不可用",
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.onErrorContainer,
                            )
                            Text(
                                state.error.ifBlank {
                                    state.message.ifBlank { "当前字体还没有生成可追踪的设备负载" }
                                },
                                color = MaterialTheme.colorScheme.onErrorContainer,
                                fontSize = 12.sp,
                            )
                            if (needsCoverageBootstrap) {
                                FilledTonalButton(
                                    onClick = { confirmReapply = true },
                                    enabled = !state.busy,
                                ) {
                                    Icon(Icons.Rounded.AutoFixHigh, null, Modifier.size(18.dp))
                                    Spacer(Modifier.width(8.dp))
                                    Text("重建当前字体覆盖数据")
                                }
                            }
                            TextButton(
                                onClick = { load() },
                                enabled = !state.busy && !taskRunning,
                            ) {
                                Text("重新读取")
                            }
                        }
                    }
                }
            }
        }

        if (data != null) {
            val liveStatusText = when {
                taskRunning -> taskMessage.ifBlank { "字体补齐正在后台处理" } +
                    " · " + taskProgress.coerceIn(0, 100) + "%"
                taskState == "failed" -> taskMessage.ifBlank { "字体补齐任务失败" }
                rebootRequired -> "补齐负载已生成并提交。现在完整重启一次，开机后会自动验证实际覆盖结果。"
                else -> state.error.ifBlank { state.message }
            }
            CoverageActionBar(
                remediable = data.summary.remediable,
                busy = state.busy,
                taskState = taskState,
                taskProgress = taskProgress,
                rebootRequired = rebootRequired,
                canReapply = canReapply,
                statusText = liveStatusText,
                statusIsError = state.error.isNotBlank() || taskState == "failed",
                onReapply = { confirmReapply = true },
                onReboot = onReboot,
                onVerify = { load(verify = true) },
                onExport = {
                    if (state.busy) return@CoverageActionBar
                    state = state.copy(busy = true, exportPath = "", error = "")
                    scope.launch {
                        runCatching {
                            runCoverageAction("coverage_export", 60_000L)
                        }.onSuccess { json ->
                            val path = json.optJSONObject("data")?.optString("path").orEmpty()
                            state = state.copy(
                                busy = false,
                                exportPath = path,
                                message = if (path.isNotBlank()) "覆盖报告已导出" else "",
                            )
                        }.onFailure { error ->
                            state = state.copy(
                                busy = false,
                                error = error.message.orEmpty().ifBlank { "覆盖报告导出失败" },
                            )
                        }
                    }
                },
                modifier = Modifier.align(Alignment.BottomCenter),
            )
        }
    }

    if (confirmReapply) {
        AlertDialog(
            onDismissRequest = { confirmReapply = false },
            shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 32.dp else 26.dp),
            icon = {
                Icon(
                    Icons.Rounded.AutoFixHigh,
                    null,
                    tint = MaterialTheme.colorScheme.primary,
                )
            },
            title = {
                Text(
                    if (data == null) "重建当前字体覆盖数据" else "补齐所有可安全替换项",
                    fontWeight = FontWeight.Bold,
                )
            },
            text = {
                Text(
                    if (data == null) {
                        "当前字体来自升级保留负载，缺少新版本的逐槽追踪信息。洛书会按当前字体方案重新生成设备对齐负载与覆盖索引；完成后完整重启，再回到这里查看哪些字体已替换、未替换或被系统保护。"
                    } else {
                        "洛书会使用当前字体方案重新生成完整负载，并重试扫描到但尚未正确替换的安全 UI 槽位。Emoji、系统图标、数学/音乐符号、危险 TTC/OTC 集合与缺失真实字重的槽位仍保持原厂。完成后需要完整重启。"
                    },
                    fontSize = 13.sp,
                    lineHeight = 19.sp,
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        confirmReapply = false
                        if (state.busy) return@TextButton
                        state = state.copy(
                            busy = true,
                            error = "",
                            message = "正在实时检查任务状态并启动补齐…",
                        )
                        scope.launch {
                            runCatching {
                                runCoverageAction("coverage_reapply", 30_000L)
                            }.onSuccess { json ->
                                val taskId = json.optJSONObject("data")?.optString("task").orEmpty()
                                if (taskId.isBlank()) {
                                    state = state.copy(
                                        busy = false,
                                        error = "补齐任务没有返回任务 ID，已拒绝进入无法跟踪的后台状态",
                                        message = "",
                                    )
                                    return@onSuccess
                                }
                                state = state.copy(
                                    busy = false,
                                    error = "",
                                    message = if (data == null) {
                                        "覆盖数据重建已启动 · " + taskId
                                    } else {
                                        "字体补齐已启动 · " + taskId
                                    },
                                )
                                onTaskStarted(taskId, coverageActiveFont == "mix")
                            }.onFailure { error ->
                                state = state.copy(
                                    busy = false,
                                    error = error.message.orEmpty().ifBlank {
                                        "字体补齐任务启动失败"
                                    },
                                )
                            }
                        }
                    },
                ) {
                    Text(if (data == null) "开始重建" else "开始补齐")
                }
            },
            dismissButton = {
                TextButton(onClick = { confirmReapply = false }) {
                    Text("取消")
                }
            },
        )
    }

    if (state.exportPath.isNotBlank()) {
        AlertDialog(
            onDismissRequest = { state = state.copy(exportPath = "") },
            shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 32.dp else 26.dp),
            icon = {
                Icon(
                    Icons.Rounded.Description,
                    null,
                    tint = MaterialTheme.colorScheme.primary,
                )
            },
            title = {
                Text("字体覆盖报告已导出", fontWeight = FontWeight.Bold)
            },
            text = {
                Surface(
                    shape = RoundedCornerShape(16.dp),
                    color = MaterialTheme.colorScheme.surfaceContainer,
                ) {
                    Text(
                        state.exportPath,
                        Modifier.padding(13.dp),
                        fontSize = 12.sp,
                    )
                }
            },
            confirmButton = {
                TextButton(onClick = { state = state.copy(exportPath = "") }) {
                    Text("完成")
                }
            },
        )
    }
}

@Composable
private fun CoverageHero(
    data: CoverageData,
    activeFont: String,
    rebootRequired: Boolean,
) {
    val tokens = LocalMiuixTokens.current
    Surface(
        shape = RoundedCornerShape(30.dp),
        color = tokens.cardBackground,
        shadowElevation = 3.dp,
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .background(
                    Brush.linearGradient(
                        listOf(
                            MaterialTheme.colorScheme.primaryContainer.copy(alpha = .58f),
                            tokens.cardBackground,
                        ),
                    ),
                )
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(50.dp),
                    shape = RoundedCornerShape(18.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = .12f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(
                            Icons.Rounded.Verified,
                            null,
                            tint = MaterialTheme.colorScheme.primary,
                        )
                    }
                }
                Spacer(Modifier.width(13.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        "系统字体覆盖图",
                        fontSize = 20.sp,
                        fontWeight = FontWeight.Bold,
                        color = tokens.textPrimary,
                    )
                    Text(
                        coverageDetectionLabel(data.rom) + " · " +
                            verificationLabel(data.verificationState, rebootRequired),
                        color = tokens.textSecondary,
                        fontSize = 11.sp,
                    )
                }
                Surface(
                    shape = CircleShape,
                    color = MaterialTheme.colorScheme.primary.copy(alpha = .10f),
                ) {
                    Text(
                        when {
                            activeFont == "mix" -> "复合字体"
                            activeFont.isBlank() || activeFont == "default" -> "系统默认"
                            else -> activeFont
                        },
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
                        color = MaterialTheme.colorScheme.primary,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 1,
                    )
                }
            }

            val summary = data.summary
            val metrics = listOf(
                MetricSpec("扫描路径", summary.total, Icons.Rounded.Search, MaterialTheme.colorScheme.primary),
                MetricSpec("可替换", summary.replaceable, Icons.Rounded.AutoFixHigh, Color(0xFF6A67CE)),
                MetricSpec("已替换", summary.replaced, Icons.Rounded.CheckCircle, Color(0xFF21966C)),
                MetricSpec("未完全替换", summary.issues, Icons.Rounded.ErrorOutline, Color(0xFFC74A4A)),
                MetricSpec("系统保护", summary.protected, Icons.Rounded.Security, Color(0xFF687386)),
                MetricSpec("待验证", summary.pending, Icons.Rounded.HourglassTop, Color(0xFFB7791F)),
            )
            metrics.chunked(3).forEach { row ->
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    row.forEach { metric ->
                        CoverageMetric(metric, Modifier.weight(1f))
                    }
                }
            }

            Text(
                buildString {
                    append("已归档 ").append(summary.textInventory).append(" 个系统文字字体文件。")
                    append("可替换数量按本机中英数能力统计，当前字体缺少字重或字形不会减少此数。")
                    if (summary.dynamic > 0 || summary.runtime > 0) {
                        append("另有动态字体 ").append(summary.dynamic)
                        append(" 个、运行容器字体 ").append(summary.runtime).append(" 个，已单列原因。")
                    }
                    if (summary.partial > 0) append("其中 ").append(summary.partial).append(" 个文件部分生效。")
                    if (summary.estimated > 0) append("旧清单中 ").append(summary.estimated).append(" 项仍按旧记录估算。")
                },
                color = tokens.textSecondary,
                fontSize = 11.sp,
                lineHeight = 16.sp,
            )

            if (summary.remediable > 0) {
                Surface(
                    shape = RoundedCornerShape(16.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = .08f),
                ) {
                    Text(
                        "发现 " + summary.remediable +
                            " 个可安全重试的未替换项。补齐会重建当前字体负载，系统保护字体保持原厂。",
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp),
                        color = tokens.textPrimary,
                        fontSize = 11.sp,
                        lineHeight = 16.sp,
                    )
                }
            }
        }
    }
}

@Composable
private fun CoverageMetric(spec: MetricSpec, modifier: Modifier = Modifier) {
    val tokens = LocalMiuixTokens.current
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(18.dp),
        color = spec.accent.copy(alpha = .08f),
    ) {
        Column(
            Modifier.padding(horizontal = 10.dp, vertical = 11.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Icon(spec.icon, null, tint = spec.accent, modifier = Modifier.size(18.dp))
            Text(
                spec.value.toString(),
                color = tokens.textPrimary,
                fontSize = 19.sp,
                fontWeight = FontWeight.Bold,
            )
            Text(
                spec.label,
                color = tokens.textSecondary,
                fontSize = 10.sp,
                maxLines = 1,
            )
        }
    }
}

@Composable
private fun CoverageSlotCard(
    slot: CoverageSlot,
    expanded: Boolean,
    onToggle: () -> Unit,
) {
    val tokens = LocalMiuixTokens.current
    val clipboard = LocalClipboardManager.current
    val accent = statusAccent(slot)
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(24.dp))
            .clickable(onClick = onToggle),
        shape = RoundedCornerShape(24.dp),
        color = tokens.cardBackground,
        shadowElevation = 1.dp,
    ) {
        Column(
            Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(9.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(42.dp),
                    shape = RoundedCornerShape(15.dp),
                    color = accent.copy(alpha = .10f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(
                            when (slot.category) {
                                "replaced" -> Icons.Rounded.CheckCircle
                                "protected" -> Icons.Rounded.Security
                                "pending" -> Icons.Rounded.HourglassTop
                                else -> Icons.Rounded.ErrorOutline
                            },
                            null,
                            tint = accent,
                            modifier = Modifier.size(22.dp),
                        )
                    }
                }
                Spacer(Modifier.width(11.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        slot.name,
                        color = tokens.textPrimary,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        slot.path,
                        color = tokens.textSecondary,
                        fontSize = 10.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                Surface(
                    shape = CircleShape,
                    color = accent.copy(alpha = .10f),
                ) {
                    Text(
                        slotStatusLabel(slot),
                        Modifier.padding(horizontal = 9.dp, vertical = 5.dp),
                        color = accent,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
                Spacer(Modifier.width(4.dp))
                Icon(
                    if (expanded) Icons.Rounded.ExpandLess else Icons.Rounded.ExpandMore,
                    null,
                    tint = tokens.textSecondary,
                )
            }

            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                SlotTag(slot.partition.ifBlank { "unknown" })
                SlotTag(slot.format.ifBlank { "FONT" })
                SlotTag(slot.weight.toString())
                if (slot.safeToRetry) {
                    SlotTag("可补齐", MaterialTheme.colorScheme.primary)
                }
            }

            Text(
                reasonLabel(slot.reason),
                color = if (slot.category == "issue") {
                    MaterialTheme.colorScheme.error
                } else {
                    tokens.textSecondary
                },
                fontSize = 11.sp,
                lineHeight = 16.sp,
            )

            AnimatedVisibility(expanded) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    HorizontalDivider(
                        color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = .45f),
                    )
                    CoverageDetailRow("来源", coverageSourceLabel(slot.source))
                    CoverageDetailRow("样式", coverageStyleLabel(slot.style))
                    if (slot.capabilityKnown) {
                        CoverageDetailRow("文件能力", coverageRoleLabels(slot.replacementRoles).ifBlank { "不含中英数字形" })
                    }
                    slot.faceDetails.forEach { detail ->
                        CoverageDetailRow("字体面", detail)
                    }
                    if (slot.families.isNotEmpty()) {
                        CoverageDetailRow("字体族", slot.families.joinToString(" · "))
                    }
                    if (slot.routes.isEmpty()) {
                        CoverageDetailRow("处理路径", "保持原厂 / 未进入当前负载")
                    } else {
                        slot.routes.forEachIndexed { index, route ->
                            val value = buildString {
                                append(coverageRouteLabel(route.route))
                                if (route.family.isNotBlank()) {
                                    append(" · ")
                                    append(route.family)
                                }
                                if (route.targetPath.isNotBlank()) {
                                    append("\n")
                                    append(route.targetPath)
                                }
                                if (route.generatedFile.isNotBlank()) {
                                    append("\n生成：")
                                    append(route.generatedFile)
                                }
                                if (route.planReason.isNotBlank()) {
                                    append("\n")
                                    append(reasonLabel(route.planReason))
                                }
                            }
                            CoverageDetailRow(
                                if (slot.routes.size > 1) {
                                    "路由 " + (index + 1)
                                } else {
                                    "处理路由"
                                },
                                value,
                            )
                        }
                    }
                    TextButton(
                        onClick = {
                            clipboard.setText(AnnotatedString(slotCopyText(slot)))
                        },
                        modifier = Modifier.align(Alignment.End),
                    ) {
                        Text("复制此项信息")
                    }
                }
            }
        }
    }
}

@Composable
private fun CoverageGroupHeader(label: String, count: Int) {
    val tokens = LocalMiuixTokens.current
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            label,
            modifier = Modifier.weight(1f),
            color = tokens.textPrimary,
            fontSize = 13.sp,
            fontWeight = FontWeight.SemiBold,
        )
        Text(
            count.toString(),
            color = tokens.textSecondary,
            fontSize = 11.sp,
        )
    }
}

private fun statusSortKey(label: String): Int = when (label) {
    "未进入负载", "映射缺失", "未挂载", "文件不一致", "部分生效", "需要检查" -> 0
    "等待重启验证", "已挂载待确认", "待确认" -> 1
    "已替换" -> 2
    "系统保护" -> 3
    else -> 4
}

private fun slotCopyText(slot: CoverageSlot): String = buildString {
    append("字体：").append(slot.name).append('\n')
    append("路径：").append(slot.path).append('\n')
    append("状态：").append(slotStatusLabel(slot)).append('\n')
    append("原因：").append(reasonLabel(slot.reason)).append('\n')
    append("分区：").append(slot.partition.ifBlank { "unknown" }).append('\n')
    append("格式：").append(slot.format.ifBlank { "FONT" }).append('\n')
    append("字重：").append(slot.weight).append('\n')
    append("样式：").append(coverageStyleLabel(slot.style)).append('\n')
    if (slot.families.isNotEmpty()) {
        append("字体族：").append(slot.families.joinToString(" · ")).append('\n')
    }
    if (slot.routes.isNotEmpty()) {
        slot.routes.forEachIndexed { index, route ->
            append("路由").append(index + 1).append("：")
            append(route.route.ifBlank { "unknown" })
            if (route.targetPath.isNotBlank()) append(" -> ").append(route.targetPath)
            if (route.generatedFile.isNotBlank()) append(" [").append(route.generatedFile).append(']')
            append('\n')
        }
    }
}

@Composable
private fun SlotTag(
    text: String,
    accent: Color = MaterialTheme.colorScheme.onSurfaceVariant,
) {
    Surface(
        shape = CircleShape,
        color = MaterialTheme.colorScheme.surfaceContainerHigh,
    ) {
        Text(
            text,
            Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
            color = accent,
            fontSize = 9.sp,
            fontWeight = FontWeight.Medium,
        )
    }
}

@Composable
private fun CoverageDetailRow(label: String, value: String) {
    val tokens = LocalMiuixTokens.current
    Row(
        Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.Top,
    ) {
        Text(
            label,
            modifier = Modifier.width(64.dp),
            color = tokens.textSecondary,
            fontSize = 10.sp,
        )
        Text(
            value,
            modifier = Modifier.weight(1f),
            color = tokens.textPrimary,
            fontSize = 10.sp,
            lineHeight = 15.sp,
        )
    }
}

@Composable
private fun CoverageMessage(message: String, failed: Boolean) {
    val tokens = LocalMiuixTokens.current
    Surface(
        shape = RoundedCornerShape(18.dp),
        color = if (failed) {
            MaterialTheme.colorScheme.errorContainer
        } else {
            MaterialTheme.colorScheme.primaryContainer.copy(alpha = .55f)
        },
    ) {
        Text(
            message,
            modifier = Modifier.padding(14.dp),
            color = if (failed) {
                MaterialTheme.colorScheme.onErrorContainer
            } else {
                tokens.textPrimary
            },
            fontSize = 12.sp,
        )
    }
}

@Composable
private fun CoverageEmptyState() {
    val tokens = LocalMiuixTokens.current
    Surface(
        shape = RoundedCornerShape(24.dp),
        color = tokens.cardBackground,
    ) {
        Column(
            Modifier.fillMaxWidth().padding(28.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Icon(Icons.Rounded.Search, null, tint = tokens.textSecondary)
            Text(
                "没有符合条件的字体槽位",
                color = tokens.textPrimary,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                "调整筛选条件或清空搜索关键词",
                color = tokens.textSecondary,
                fontSize = 12.sp,
            )
        }
    }
}

@Composable
private fun CoverageActionBar(
    remediable: Int,
    busy: Boolean,
    taskState: String,
    taskProgress: Int,
    rebootRequired: Boolean,
    canReapply: Boolean,
    statusText: String,
    statusIsError: Boolean,
    onReapply: () -> Unit,
    onReboot: () -> Unit,
    onVerify: () -> Unit,
    onExport: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val tokens = LocalMiuixTokens.current
    Surface(
        modifier = modifier
            .padding(horizontal = 14.dp, vertical = 12.dp)
            .fillMaxWidth(),
        shape = RoundedCornerShape(28.dp),
        color = tokens.elevatedCardBackground.copy(alpha = .98f),
        shadowElevation = 12.dp,
    ) {
        Column(
            Modifier.padding(8.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            if (statusText.isNotBlank()) {
                Text(
                    statusText,
                    color = if (statusIsError) {
                        MaterialTheme.colorScheme.error
                    } else {
                        tokens.textSecondary
                    },
                    fontSize = 11.5.sp,
                    lineHeight = 16.sp,
                    maxLines = 2,
                    modifier = Modifier.padding(horizontal = 5.dp),
                )
            }
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(7.dp),
            ) {
                val taskRunning = taskState in setOf("queued", "running")
                Button(
                    onClick = if (rebootRequired && !taskRunning) onReboot else onReapply,
                    enabled = when {
                        taskRunning -> false
                        rebootRequired -> !busy
                        else -> canReapply
                    },
                    modifier = Modifier.weight(1.25f).heightIn(min = 48.dp),
                    shape = RoundedCornerShape(19.dp),
                ) {
                    if (busy || taskRunning) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(18.dp),
                            strokeWidth = 2.dp,
                            color = MaterialTheme.colorScheme.onPrimary,
                        )
                    } else {
                        Icon(
                            if (rebootRequired) Icons.Rounded.Refresh else Icons.Rounded.AutoFixHigh,
                            null,
                            Modifier.size(19.dp),
                        )
                    }
                    Spacer(Modifier.width(6.dp))
                    Text(
                        when {
                            busy -> "正在启动…"
                            taskRunning -> "补齐中 " + taskProgress.coerceIn(0, 100) + "%"
                            rebootRequired -> "完整重启"
                            remediable > 0 -> "补齐 " + remediable
                            else -> "无需补齐"
                        },
                        maxLines = 1,
                    )
                }
                FilledTonalButton(
                    onClick = onVerify,
                    enabled = !busy && !taskRunning && !rebootRequired,
                    modifier = Modifier.weight(1f).heightIn(min = 48.dp),
                    shape = RoundedCornerShape(19.dp),
                ) {
                    Icon(Icons.Rounded.Verified, null, Modifier.size(19.dp))
                    Spacer(Modifier.width(5.dp))
                    Text("重新验证", maxLines = 1)
                }
                Surface(
                    onClick = onExport,
                    enabled = !busy,
                    shape = RoundedCornerShape(19.dp),
                    color = MaterialTheme.colorScheme.surfaceContainerHigh,
                    modifier = Modifier.size(48.dp),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(Icons.Rounded.Description, "导出字体覆盖报告")
                    }
                }
            }
        }
    }
}

internal fun verificationLabel(state: String, rebootRequired: Boolean): String = when {
    rebootRequired || state == "pending-reboot" -> "等待完整重启"
    state == "verified" -> "启动验证完成"
    state == "partial" -> "部分字体生效"
    state == "pending" -> "等待验证"
    state == "failed" -> "启动验证异常"
    state == "not-run" -> "尚未验证"
    else -> "验证结果待确认"
}
