from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, got {count}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# System weight: render cached value immediately, verify silently in background.
# ---------------------------------------------------------------------------
path = "android-app/app/src/main/java/io/github/xgl34222220/luoshu/Alpha15FeatureViewModel.kt"
text = read(path)
text = once(
    text,
    "import androidx.lifecycle.ViewModel\n",
    "import android.app.Application\nimport android.content.Context\nimport android.os.SystemClock\nimport androidx.lifecycle.AndroidViewModel\n",
    "Alpha15 imports",
)
text = once(
    text,
    "internal class Alpha15FeatureViewModel : ViewModel() {",
    "internal class Alpha15FeatureViewModel(application: Application) : AndroidViewModel(application) {",
    "Alpha15 class",
)
text = once(
    text,
    "    private var weightJob: Job? = null\n    private var lastCommittedWeight: Int? = null\n",
    "    private var weightJob: Job? = null\n    private var refreshJob: Job? = null\n    private var lastCommittedWeight: Int? = null\n    private var lastWeightRefreshElapsed = 0L\n    private val weightPrefs = application.getSharedPreferences(\"system-weight-cache-v1\", Context.MODE_PRIVATE)\n",
    "Alpha15 fields",
)
text = once(
    text,
    "    var systemWeight by mutableStateOf(SystemWeightState())\n        private set\n\n    var coverage by mutableStateOf(CoverageProbeState())",
    """    var systemWeight by mutableStateOf(SystemWeightState())
        private set

    init {
        val cachedWeight = weightPrefs.getInt("weight", Int.MIN_VALUE)
        val cachedMin = weightPrefs.getInt("min", 300)
        val cachedMax = weightPrefs.getInt("max", 700).coerceAtLeast(cachedMin)
        val cachedStep = weightPrefs.getInt("step", 10).coerceAtLeast(1)
        if (cachedWeight != Int.MIN_VALUE) {
            val safeWeight = cachedWeight.coerceIn(cachedMin, cachedMax)
            lastCommittedWeight = safeWeight
            systemWeight = SystemWeightState(
                loading = false,
                supported = weightPrefs.getBoolean("supported", true),
                weight = safeWeight,
                adjustment = weightPrefs.getInt("adjustment", safeWeight - 400),
                originalAdjustment = weightPrefs.getInt("originalAdjustment", 0),
                min = cachedMin,
                max = cachedMax,
                step = cachedStep,
                message = "已显示上次值，后台会静默校验",
            )
        }
    }

    var coverage by mutableStateOf(CoverageProbeState())""",
    "Alpha15 cache init",
)
pattern = re.compile(r"    fun refreshSystemWeight\(\) \{.*?\n    \}\n\n    fun previewSystemWeight", re.S)
replacement = """    fun refreshSystemWeight(force: Boolean = false) {
        if (systemWeight.applying || refreshJob?.isActive == true) return
        val now = SystemClock.elapsedRealtime()
        if (!force && lastWeightRefreshElapsed > 0L && now - lastWeightRefreshElapsed < 120_000L) return
        val hadCachedValue = !systemWeight.loading
        systemWeight = if (hadCachedValue) {
            systemWeight.copy(message = "正在后台校验系统粗细…", error = "")
        } else {
            systemWeight.copy(loading = true, error = "")
        }
        refreshJob = viewModelScope.launch {
            val result = RootShell.exec(
                "sh ${RootShell.quote(fontManager)} action font_weight_status",
                timeoutMs = 20_000L,
            )
            try {
                if (result.code != 0) error(result.stderr.ifBlank { "系统字体粗细读取失败" })
                val root = firstJson(result.stdout)
                if (root.optString("status") != "ok") error(root.optString("message", "系统字体粗细读取失败"))
                val data = root.getJSONObject("data")
                val minimum = data.optInt("min", 300)
                val maximum = data.optInt("max", 700).coerceAtLeast(minimum)
                val step = data.optInt("step", 10).coerceAtLeast(1)
                val weight = data.optInt("weight", 400).coerceIn(minimum, maximum)
                lastCommittedWeight = weight
                systemWeight = SystemWeightState(
                    loading = false,
                    supported = data.optBoolean("supported", false),
                    weight = weight,
                    adjustment = data.optInt("adjustment", weight - 400),
                    originalAdjustment = data.optInt("originalAdjustment", 0),
                    min = minimum,
                    max = maximum,
                    step = step,
                    message = "拖动后会自动写入，未刷新的应用重新打开即可",
                )
                persistWeightCache()
                lastWeightRefreshElapsed = SystemClock.elapsedRealtime()
            } catch (error: Throwable) {
                systemWeight = if (hadCachedValue) {
                    systemWeight.copy(
                        loading = false,
                        error = "",
                        message = "沿用缓存粗细；后台校验暂时失败",
                    )
                } else {
                    systemWeight.copy(
                        loading = false,
                        supported = false,
                        error = error.message ?: "系统字体粗细读取失败",
                        message = "",
                    )
                }
            } finally {
                refreshJob = null
            }
        }
    }

    fun previewSystemWeight"""
text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise RuntimeError(f"Alpha15 refresh function: expected one match, got {count}")
text = once(
    text,
    """                systemWeight = systemWeight.copy(
                    weight = applied,
                    adjustment = data?.optInt("adjustment", applied - 400) ?: (applied - 400),
                    applying = false,
                    message = data?.optString("message").orEmpty().ifBlank {
                        "系统粗细已更新；未刷新的应用请重新打开"
                    },
                    error = "",
                )
""",
    """                systemWeight = systemWeight.copy(
                    weight = applied,
                    adjustment = data?.optInt("adjustment", applied - 400) ?: (applied - 400),
                    applying = false,
                    message = data?.optString("message").orEmpty().ifBlank {
                        "系统粗细已更新；未刷新的应用请重新打开"
                    },
                    error = "",
                )
                persistWeightCache()
                lastWeightRefreshElapsed = SystemClock.elapsedRealtime()
""",
    "Alpha15 persist after set",
)
text = once(text, "                refreshSystemWeight()\n", "                refreshSystemWeight(force = true)\n", "Alpha15 reset refresh")
text = once(
    text,
    "    private fun snapWeight(value: Int, min: Int, max: Int, step: Int): Int {",
    """    private fun persistWeightCache() {
        val state = systemWeight
        weightPrefs.edit()
            .putBoolean("supported", state.supported)
            .putInt("weight", state.weight)
            .putInt("adjustment", state.adjustment)
            .putInt("originalAdjustment", state.originalAdjustment)
            .putInt("min", state.min)
            .putInt("max", state.max)
            .putInt("step", state.step)
            .apply()
    }

    private fun snapWeight(value: Int, min: Int, max: Int, step: Int): Int {""",
    "Alpha15 persist helper",
)
write(path, text)


# ---------------------------------------------------------------------------
# App shell: remove duplicate startup root read and slim the MIUIx dock.
# ---------------------------------------------------------------------------
path = "android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuAppShell.kt"
text = read(path)
text = once(
    text,
    "    LaunchedEffect(Unit) {\n        viewModel.refresh()\n        features.refreshSystemWeight()\n    }",
    "    LaunchedEffect(Unit) {\n        viewModel.refresh()\n    }",
    "AppShell startup refresh",
)
text = once(
    text,
    "                features.refreshSystemWeight()\n            },\n            openFontLibrary",
    "                features.refreshSystemWeight(force = true)\n            },\n            openFontLibrary",
    "AppShell manual refresh",
)
text = once(text, "val dockContentPadding = if (edgeToEdgeGlass) navigationBottom + 88.dp else 0.dp", "val dockContentPadding = if (edgeToEdgeGlass) navigationBottom + 82.dp else 0.dp", "AppShell dock clearance")
miuix_at = text.index("private fun MiuixAppDock(")
prefix, dock = text[:miuix_at], text[miuix_at:]
dock = dock.replace("RoundedCornerShape(31.dp)", "RoundedCornerShape(28.dp)", 1)
dock = dock.replace("RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp)", "RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp)", 1)
dock = dock.replace("itemHeight = 52.dp", "itemHeight = 48.dp", 1)
dock = dock.replace("Modifier.padding(horizontal = 12.dp).padding(bottom = bottomInset + 8.dp)", "Modifier.padding(horizontal = 14.dp).padding(bottom = bottomInset + 7.dp)", 1)
dock = dock.replace(".padding(start = 5.dp, top = 5.dp, end = 5.dp, bottom = if (floating) 5.dp else bottomInset + 5.dp)", ".padding(start = 4.dp, top = 4.dp, end = 4.dp, bottom = if (floating) 4.dp else bottomInset + 4.dp)", 1)
dock = dock.replace("val indicatorInset = if (liquidLens) 5.dp else 7.dp", "val indicatorInset = if (liquidLens) 6.dp else 7.dp", 1)
dock = dock.replace("val indicatorShape = RoundedCornerShape(if (liquidLens) 20.dp else 18.dp)", "val indicatorShape = RoundedCornerShape(if (liquidLens) 18.dp else 18.dp)", 1)
write(path, prefix + dock)


# ---------------------------------------------------------------------------
# Font index: cached list is authoritative until import/delete/manual refresh.
# Preview cache prewarms once per font-index fingerprint in one root call.
# ---------------------------------------------------------------------------
path = "android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt"
text = read(path)
if "import java.io.File\n" not in text:
    text = once(text, "import org.json.JSONObject\n", "import org.json.JSONObject\nimport java.io.File\n", "ViewModel File import")
text = once(
    text,
    "    private var prewarmRequested = false\n",
    "    private var prewarmRequested = false\n    private var previewPrewarmRequested = false\n    private var previewPrewarmJob: Job? = null\n",
    "ViewModel preview fields",
)
text = once(
    text,
    """    private fun requestFontPrewarm() {
        if (prewarmRequested && fonts.isNotEmpty()) return
        prewarmRequested = true
        if (fontRequestJob?.isActive == true) return
        launchFontWork(force = false, showErrors = false)
    }""",
    """    private fun requestFontPrewarm() {
        if (fonts.isNotEmpty()) {
            requestPreviewPrewarm()
            return
        }
        if (prewarmRequested) return
        prewarmRequested = true
        if (fontRequestJob?.isActive == true) return
        launchFontWork(force = false, showErrors = false)
    }""",
    "ViewModel cache-first prewarm",
)
text = once(
    text,
    "                    else -> refreshOnlyWhenChanged(showErrors = showErrors)\n",
    "                    else -> Unit // 本地索引优先：导入、删除或手动刷新才重建。\n",
    "ViewModel no page fingerprint",
)
text = once(
    text,
    "            persistFontIndex(currentFont = current)\n            fontError = \"\"\n",
    "            persistFontIndex(currentFont = current)\n            requestPreviewPrewarm(force = true)\n            fontError = \"\"\n",
    "ViewModel preview after rebuild",
)
text = once(
    text,
    "    fun refreshMixConfig() {",
    """    private fun requestPreviewPrewarm(force: Boolean = false) {
        if (!snapshot.installed || fonts.isEmpty()) return
        if (previewPrewarmJob?.isActive == true) return
        if (previewPrewarmRequested && !force) return
        previewPrewarmRequested = true
        val previewDir = File(getApplication<Application>().cacheDir, "native-font-preview")
        val marker = File(previewDir, ".font-index")
        previewPrewarmJob = viewModelScope.launch {
            val alreadyReady = withContext(Dispatchers.IO) {
                previewDir.mkdirs()
                !force && cachedFingerprint.isNotBlank() &&
                    marker.isFile && marker.readText().trim() == cachedFingerprint
            }
            if (alreadyReady) {
                previewPrewarmJob = null
                return@launch
            }
            if (force) {
                invalidateNativeFontPreviewMemoryCache()
                withContext(Dispatchers.IO) {
                    previewDir.listFiles()?.forEach { file -> if (file.isFile) file.delete() }
                }
            }
            val result = RootShell.exec(
                "sh ${RootShell.quote(bridge)} preview_export_batch ${RootShell.quote(previewDir.absolutePath)}",
                timeoutMs = 90_000L,
            )
            if (result.code == 0) {
                withContext(Dispatchers.IO) {
                    runCatching { marker.writeText(cachedFingerprint) }
                }
            }
            previewPrewarmJob = null
        }
    }

    fun refreshMixConfig() {""",
    "ViewModel preview prewarm function",
)
write(path, text)


# ---------------------------------------------------------------------------
# Native preview: list rows never spawn their own su process. They wait briefly
# for the single batch prewarm; detail/studio previews retain fallback export.
# ---------------------------------------------------------------------------
path = "android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeFontPreview.kt"
text = read(path)
text = once(text, "import kotlinx.coroutines.CancellationException\n", "import kotlinx.coroutines.CancellationException\nimport kotlinx.coroutines.delay\n", "Preview delay import")
text = once(
    text,
    "private fun previewMemoryPut(key: String, entry: PreviewMemoryEntry) = synchronized(previewMemoryCache) {\n    previewMemoryCache.put(key, entry)\n}\n",
    """private fun previewMemoryPut(key: String, entry: PreviewMemoryEntry) = synchronized(previewMemoryCache) {
    previewMemoryCache.put(key, entry)
}

internal fun invalidateNativeFontPreviewMemoryCache() = synchronized(previewMemoryCache) {
    previewMemoryCache.evictAll()
}
""",
    "Preview invalidation helper",
)
text = once(
    text,
    "    axes: Map<String, Float> = emptyMap(),\n    modifier: Modifier = Modifier,",
    "    axes: Map<String, Float> = emptyMap(),\n    rootFallback: Boolean = true,\n    modifier: Modifier = Modifier,",
    "Preview fallback parameter",
)
text = once(
    text,
    """    val sourceRevision = remember(font, requestedWeight) {
        font?.let {
            val staticRevision = if (it.variable) "" else "|wght=$requestedWeight"
            "${it.id}|${it.size}|${it.date}$staticRevision"
        }
    }""",
    """    val sourceRevision = remember(font?.id, font?.variable, requestedWeight) {
        font?.let {
            if (it.variable) it.id else "${it.id}|wght=$requestedWeight"
        }
    }""",
    "Preview stable cache key",
)
text = once(
    text,
    """    val previewKey = remember(sourceRevision, font?.valid, font?.error) {
        "${sourceRevision.orEmpty()}|${font?.valid}|${font?.error.orEmpty()}"
    }""",
    """    val previewKey = remember(sourceRevision, font?.size, font?.date, font?.valid, font?.error, rootFallback) {
        "${sourceRevision.orEmpty()}|${font?.size}|${font?.date}|${font?.valid}|${font?.error.orEmpty()}|root=$rootFallback"
    }""",
    "Preview recomposition key",
)
old = """                                var exported = false
                                if (!target.isFile || target.length() == 0L) {
                                    val command = "sh ${RootShell.quote(APP_BRIDGE)} preview_export " +
                                        "${RootShell.quote(font.id)} ${RootShell.quote(target.absolutePath)} $requestedWeight"
                                    val result = RootShell.exec(command, timeoutMs = 25_000L)
                                    val jsonLine = result.stdout.lineSequence()
                                        .firstOrNull { it.trimStart().startsWith("{") }
                                    val root = jsonLine?.let { JSONObject(it.trim()) }
                                    if (result.code != 0 || root?.optString("status") != "ok") {
                                        error(
                                            root?.optString("message").orEmpty().ifBlank {
                                                result.stderr.ifBlank { "预览字体导出失败" }
                                            },
                                        )
                                    }
                                    if (!target.isFile || target.length() == 0L) {
                                        error("预览字体文件为空")
                                    }
                                    exported = true
                                }
                                val loaded = Typeface.createFromFile(target)"""
new = """                                var exported = false
                                if ((!target.isFile || target.length() == 0L) && !rootFallback) {
                                    repeat(40) {
                                        if (target.isFile && target.length() > 0L) return@repeat
                                        delay(150L)
                                    }
                                }
                                if ((!target.isFile || target.length() == 0L) && rootFallback) {
                                    val command = "sh ${RootShell.quote(APP_BRIDGE)} preview_export " +
                                        "${RootShell.quote(font.id)} ${RootShell.quote(target.absolutePath)} $requestedWeight"
                                    val result = RootShell.exec(command, timeoutMs = 25_000L)
                                    val jsonLine = result.stdout.lineSequence()
                                        .firstOrNull { it.trimStart().startsWith("{") }
                                    val root = jsonLine?.let { JSONObject(it.trim()) }
                                    if (result.code != 0 || root?.optString("status") != "ok") {
                                        error(
                                            root?.optString("message").orEmpty().ifBlank {
                                                result.stderr.ifBlank { "预览字体导出失败" }
                                            },
                                        )
                                    }
                                    if (!target.isFile || target.length() == 0L) {
                                        error("预览字体文件为空")
                                    }
                                    exported = true
                                }
                                if (!target.isFile || target.length() == 0L) {
                                    return@withPermit PreviewTypefaceState()
                                }
                                val loaded = Typeface.createFromFile(target)"""
text = once(text, old, new, "Preview export path")
write(path, text)


# ---------------------------------------------------------------------------
# One root process scans sources and populates every list preview cache entry.
# ---------------------------------------------------------------------------
path = "common/app_bridge.sh"
text = read(path)
batch = r'''preview_cache_key() {
    _pck_value="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        printf '%s' "$_pck_value" | sha256sum 2>/dev/null | awk '{print substr($1,1,24)}'
    elif command -v busybox >/dev/null 2>&1; then
        printf '%s' "$_pck_value" | busybox sha256sum 2>/dev/null | awk '{print substr($1,1,24)}'
    else
        printf '%s' "$_pck_value" | cksum 2>/dev/null | awk '{printf "%024x", $1}'
    fi
}

preview_export_batch() {
    _peb_dest="${1:-}"
    case "$_peb_dest" in
        /data/user/0/io.github.xgl34222220.luoshu/cache/native-font-preview|/data/user/0/io.github.xgl34222220.luoshu/cache/native-font-preview/*|\
        /data/data/io.github.xgl34222220.luoshu/cache/native-font-preview|/data/data/io.github.xgl34222220.luoshu/cache/native-font-preview/*|\
        /data/user/0/io.github.xgl34222220.luoshu.debug/cache/native-font-preview|/data/user/0/io.github.xgl34222220.luoshu.debug/cache/native-font-preview/*|\
        /data/data/io.github.xgl34222220.luoshu.debug/cache/native-font-preview|/data/data/io.github.xgl34222220.luoshu.debug/cache/native-font-preview/*) ;;
        *) printf '{"status":"error","message":"批量预览目标目录不受信任"}\n'; return 1 ;;
    esac
    mkdir -p "$_peb_dest" 2>/dev/null || { printf '{"status":"error","message":"无法创建预览缓存目录"}\n'; return 1; }
    _peb_list="$MODDIR/config/.preview-families.$$"
    : > "$_peb_list" 2>/dev/null || return 1
    for _peb_file in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
        "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_peb_file" ] || continue
        _peb_name="$(basename "$_peb_file")"
        case "$_peb_name" in SysFont*|SysSans*) continue ;; esac
        _peb_family="${_peb_name%.*}"
        case "$_peb_family" in
            *-Regular|*-Bold|*-Light|*-Medium|*-Thin|*-Black|*-Heavy|*-SemiBold|*-ExtraBold|*-ExtraLight|\
            *-regular|*-bold|*-light|*-medium|*-thin|*-black|*-heavy|*-semibold|*-extrabold|*-extralight)
                _peb_family="${_peb_family%-*}"
                ;;
        esac
        printf '%s\n' "$_peb_family" >> "$_peb_list"
    done
    LC_ALL=C sort -u -o "$_peb_list" "$_peb_list" 2>/dev/null || true
    _peb_count=0
    while IFS= read -r _peb_family; do
        [ -n "$_peb_family" ] || continue
        _peb_src="$(find_preview_source "$_peb_family" 400)"
        [ -f "$_peb_src" ] || continue
        _peb_ext="${_peb_src##*.}"
        _peb_ext="$(printf '%s' "$_peb_ext" | tr '[:upper:]' '[:lower:]')"
        case "$_peb_ext" in ttf|otf|ttc) ;; *) _peb_ext=ttf ;; esac
        _peb_variable_key="$(preview_cache_key "$_peb_family")"
        _peb_static_key="$(preview_cache_key "${_peb_family}|wght=400")"
        [ -n "$_peb_variable_key" ] && [ -n "$_peb_static_key" ] || continue
        _peb_variable="$_peb_dest/${_peb_variable_key}.${_peb_ext}"
        _peb_static="$_peb_dest/${_peb_static_key}.${_peb_ext}"
        cp -f "$_peb_src" "$_peb_variable" 2>/dev/null || continue
        chmod 0644 "$_peb_variable" 2>/dev/null || true
        rm -f "$_peb_static" 2>/dev/null || true
        ln "$_peb_variable" "$_peb_static" 2>/dev/null || cp -f "$_peb_variable" "$_peb_static" 2>/dev/null || true
        chmod 0644 "$_peb_static" 2>/dev/null || true
        _peb_count=$((_peb_count + 1))
    done < "$_peb_list"
    rm -f "$_peb_list" 2>/dev/null || true
    printf '{"status":"ok","data":{"count":%s}}\n' "$_peb_count"
}

'''
text = once(text, "weight_axis_info() {", batch + "weight_axis_info() {", "app_bridge batch function")
text = once(
    text,
    '    preview_export) preview_export "${2:-}" "${3:-}" "${4:-400}" ;;\n',
    '    preview_export) preview_export "${2:-}" "${3:-}" "${4:-400}" ;;\n    preview_export_batch) preview_export_batch "${2:-}" ;;\n',
    "app_bridge batch command",
)
write(path, text)


# ---------------------------------------------------------------------------
# Library UI: denser cards, visual emphasis on name/preview; no per-row root.
# ---------------------------------------------------------------------------
path = "android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryScreenCompact.kt"
text = read(path)
text = once(text, "fontSize = 34.sp,\n                        lineHeight = 39.sp,", "fontSize = 30.sp,\n                        lineHeight = 35.sp,", "Library title")
text = text.replace("shape = RoundedCornerShape(22.dp),", "shape = RoundedCornerShape(20.dp),", 2)
text = once(text, "modifier = Modifier.fillMaxWidth().padding(14.dp),", "modifier = Modifier.fillMaxWidth().padding(12.dp),", "Library system row padding")
text = once(text, "modifier = Modifier.size(58.dp),\n                shape = RoundedCornerShape(18.dp),", "modifier = Modifier.size(52.dp),\n                shape = RoundedCornerShape(16.dp),", "Library system preview")
text = once(text, "Column(Modifier.padding(14.dp))", "Column(Modifier.padding(12.dp))", "Library font padding")
text = once(text, "modifier = Modifier.size(58.dp),\n                    shape = RoundedCornerShape(18.dp),", "modifier = Modifier.size(52.dp),\n                    shape = RoundedCornerShape(16.dp),", "Library font preview surface")
text = once(text, "modifier = Modifier.size(58.dp).padding(6.dp),", "modifier = Modifier.size(52.dp).padding(5.dp),", "Library native preview size")
text = once(text, "                                textSizeSp = 15.5f,", "                                rootFallback = false,\n                                textSizeSp = 15f,", "Library no-root preview")
text = once(text, "fontSize = 17.sp,\n                        lineHeight = 21.sp,", "fontSize = 16.sp,\n                        lineHeight = 20.sp,", "Library font title")
write(path, text)


# ---------------------------------------------------------------------------
# MIUIx home: merge Root/mount into hero; simplify weight card.
# ---------------------------------------------------------------------------
path = "android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/home/HomeScreenMiuix.kt"
text = read(path)
status_block = """        item { MiuixSectionTitle("SYSTEM STATUS", "运行状态", "Root 与字体挂载") }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                MiuixMetricCard(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Rounded.Security,
                    label = "Root",
                    value = if (state.rootGranted) state.rootManager else "未授权",
                    positive = state.rootGranted,
                )
                MiuixMetricCard(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Rounded.Layers,
                    label = "挂载引擎",
                    value = state.mountEngine,
                    positive = state.mountHealthy,
                )
            }
        }

"""
text = once(text, status_block, "", "Home duplicate status")
text = once(text, '        item { MiuixSectionTitle("SYSTEM WEIGHT", "全局粗细微调", "向左更细，向右更粗") }\n        item { MiuixSystemWeightCard(state.systemWeight, actions) }', '        item { MiuixSystemWeightCard(state.systemWeight, actions) }', "Home weight title")
text = once(text, "fontSize = 39.sp,\n                lineHeight = 44.sp,", "fontSize = 36.sp,\n                lineHeight = 41.sp,", "Home title size")
text = once(text, "fontSize = 36.sp,\n                    lineHeight = 42.sp,", "fontSize = 32.sp,\n                    lineHeight = 38.sp,", "Home current font size")
hero_tail = """                        if (state.taskRunning) {
                            Text("${state.taskProgress}%", fontWeight = FontWeight.Black)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun MiuixMetricCard"""
hero_new = """                        if (state.taskRunning) {
                            Text("${state.taskProgress}%", fontWeight = FontWeight.Black)
                        }
                    }
                }
                Spacer(Modifier.height(11.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    MiuixStatusChip(
                        modifier = Modifier.weight(1f),
                        label = "Root",
                        value = if (state.rootGranted) state.rootManager else "未授权",
                        positive = state.rootGranted,
                    )
                    MiuixStatusChip(
                        modifier = Modifier.weight(1f),
                        label = "挂载",
                        value = state.mountEngine,
                        positive = state.mountHealthy,
                    )
                }
            }
        }
    }
}

@Composable
private fun MiuixStatusChip(
    modifier: Modifier,
    label: String,
    value: String,
    positive: Boolean,
) {
    val tokens = LocalMiuixTokens.current
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(16.dp),
        color = tokens.textPrimary.copy(alpha = .045f),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 11.dp, vertical = 9.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                Modifier.size(7.dp).background(
                    if (positive) tokens.success else tokens.warning,
                    CircleShape,
                ),
            )
            Spacer(Modifier.width(7.dp))
            Column(Modifier.weight(1f)) {
                Text(label, color = tokens.textSecondary, fontSize = 9.sp)
                Text(value, color = tokens.textPrimary, fontSize = 11.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

@Composable
private fun MiuixMetricCard"""
text = once(text, hero_tail, hero_new, "Home hero status chips")
text = once(text, '                    if (weight.loading) "读取中" else weight.weight.toString(),', '                    weight.weight.toString(),', "Home cached weight value")
text = once(
    text,
    "                weight.loading -> LinearProgressIndicator(Modifier.fillMaxWidth())",
    """                weight.loading -> Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(Modifier.size(14.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.width(8.dp))
                    Text("正在后台校验系统粗细…", color = tokens.textSecondary, fontSize = 10.sp)
                }""",
    "Home weight loading indicator",
)
write(path, text)


# ---------------------------------------------------------------------------
# Settings and management surfaces: lighter, less card-heavy.
# ---------------------------------------------------------------------------
path = "android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/settings/SettingsHubScreen.kt"
text = read(path)
text = once(text, "shape = RoundedCornerShape(23.dp),", "shape = RoundedCornerShape(21.dp),", "Settings tabs shape")
text = once(text, "modifier = Modifier.width(78.dp),", "modifier = Modifier.width(74.dp),", "Settings tab width")
text = once(text, "Modifier.padding(horizontal = 9.dp, vertical = 8.dp)", "Modifier.padding(horizontal = 8.dp, vertical = 7.dp)", "Settings tab padding")
text = once(text, "fontSize = 32.sp, fontWeight = FontWeight.Black", "fontSize = 29.sp, fontWeight = FontWeight.Black", "Settings title")
text = once(text, "verticalArrangement = Arrangement.spacedBy(10.dp),\n        content = content,", "verticalArrangement = Arrangement.spacedBy(8.dp),\n        content = content,", "Settings list spacing")
text = once(
    text,
    "Card(shape = RoundedCornerShape(26.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow.copy(alpha = .86f))) {\n        Column(Modifier.fillMaxWidth().padding(16.dp))",
    "Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow.copy(alpha = .72f))) {\n        Column(Modifier.fillMaxWidth().padding(14.dp))",
    "Settings cards",
)
text = once(
    text,
    "Card(shape = RoundedCornerShape(28.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow.copy(alpha = .9f))) {\n        Column(Modifier.fillMaxWidth().padding(17.dp))",
    "Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow.copy(alpha = .76f))) {\n        Column(Modifier.fillMaxWidth().padding(15.dp))",
    "Settings status cards",
)
write(path, text)

path = "android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportOverlay.kt"
text = read(path)
text = once(text, "shape = RoundedCornerShape(28.dp),", "shape = RoundedCornerShape(22.dp),", "Import glass radius")
text = once(text, "shadowElevation = if (style == UiStyle.MIUIX) 4.dp else 2.dp,", "shadowElevation = if (style == UiStyle.MIUIX) 2.dp else 1.dp,", "Import glass shadow")
text = once(text, "embedded && style == UiStyle.MIUIX -> scheme.primary.copy(alpha = if (dark) .18f else .10f)", "embedded && style == UiStyle.MIUIX -> tokens.elevatedCardBackground.copy(alpha = if (dark) .78f else .70f)", "Import glass color")
write(path, text)


# ---------------------------------------------------------------------------
# Release metadata and regression gate.
# ---------------------------------------------------------------------------
path = "module.prop"
text = read(path)
text = once(text, "version=v3.2.0", "version=v3.3.0", "module version")
text = once(text, "versionCode=30200", "versionCode=30300", "module version code")
write(path, text)

update_path = ROOT / "update.json"
update = json.loads(update_path.read_text(encoding="utf-8"))
update["version"] = "v3.3.0"
update["versionCode"] = 30300
update["zipUrl"] = "https://github.com/xgl34222220-ops/LuoShu/releases/download/v3.3.0/LuoShu-v3.3.0.zip"
update["changelog"] = "https://raw.githubusercontent.com/xgl34222220-ops/LuoShu/v3.3.0/RELEASE_NOTES_v3.3.0.md"
update_path.write_text(json.dumps(update, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

(ROOT / "RELEASE_NOTES_v3.3.0.md").write_text(
    """# 洛书 v3.3.0

本版把 v3.2.0 稳定基线上的字体切换性能优化与 App 界面/加载性能优化合并为正式版本，核心方向是“预处理一次，前台秒开/秒切”。

## 性能
- 合并 PR #181：导入/预热阶段预构建 100–900 UI + Mono 共 18 个字体成品，后续切换命中缓存时不再在前台重复启动 FontTools。
- 字体库改为本地索引优先；已有索引时进入字体库不再执行 Root 目录指纹扫描，导入、删除或手动刷新才重建。
- 字体卡片预览改为按字体索引一次批量预热，一次 Root 调用替代每张卡片各自启动 `su -> preview_export`。
- 预览缓存按字体索引指纹复用；字体库正常滚动路径不再产生逐卡 Root 进程。
- 首页全局粗细值持久缓存，启动立即显示上次值；后台静默校验，并合并/节流重复 Root 读取。

## UI / 交互
- MIUIx 首页把 Root / 挂载状态并入当前字体 Hero，去掉重复的大状态区块。
- 全局粗细卡始终优先显示数值，用轻量后台校验状态替代大号“读取中”。
- 字体库标题、卡片、预览尺寸与间距整体收紧，首屏信息密度更合理。
- 管理工具统一为更轻的玻璃层，降低整块强调色造成的视觉干扰。
- 设置中心降低标题、分段标签和卡片视觉重量，减少“满屏大卡片”的同质感。
- MIUIx 悬浮 Dock 更薄、更轻，液态选中胶囊更紧凑。

## 安全
- 保留 v3.2.0 的事务快照、payload 校验、挂载同步、Play/GMS provider 同步与失败回滚链路。
- 不重新引入 v3.2.3 / v3.2.4 的 OnePlus / ColorOS 高风险挂载改动。
""",
    encoding="utf-8",
)

(ROOT / "scripts/app_font_loading_performance_test.sh").write_text(
    r'''#!/system/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
VM="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt"
PREVIEW="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeFontPreview.kt"
LIBRARY="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryScreenCompact.kt"
BRIDGE="$ROOT/common/app_bridge.sh"
SHELL="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuAppShell.kt"

grep -q 'else -> Unit // 本地索引优先' "$VM"
grep -q 'preview_export_batch' "$VM"
grep -q 'rootFallback: Boolean = true' "$PREVIEW"
grep -q 'rootFallback = false' "$LIBRARY"
grep -q 'preview_export_batch)' "$BRIDGE"
! grep -A3 'LaunchedEffect(Unit)' "$SHELL" | grep -q 'refreshSystemWeight()'
printf '%s\n' 'app font loading performance checks passed'
''',
    encoding="utf-8",
)

print("v3.3.0 refactor applied")
