package io.github.xgl34222220.luoshu

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject

internal data class FontLibraryFingerprint(val value: String, val currentFont: String)
internal data class FontLibraryScan(
    val index: CachedFontIndex,
    val checkedFingerprint: FontLibraryFingerprint? = null,
)

/** Reads are separate from module status: neither cached rows nor refresh wait for ROM diagnostics. */
internal interface FontLibrarySource {
    suspend fun cached(): CachedFontIndex?
    suspend fun preview(): CachedFontIndex? = null
    suspend fun fingerprint(): FontLibraryFingerprint
    suspend fun scan(refresh: Boolean): CachedFontIndex
    suspend fun scanForVerification(refresh: Boolean): FontLibraryScan = FontLibraryScan(scan(refresh))
}

/** Publishes known rows before any slow validation. A failed check must never manufacture an empty library. */
internal suspend fun loadFontLibrary(
    known: CachedFontIndex?,
    force: Boolean,
    source: FontLibrarySource,
    publish: (CachedFontIndex, verified: Boolean) -> Unit,
): CachedFontIndex {
    val initial = known ?: source.cached()
    // Retain the rows, but revoke action readiness for every new check, including known
    // rows. A directory change must not leave the previous list actionable while scanning.
    initial?.let { publish(it, false) }
    val preview = if (initial == null) source.preview()?.also { publish(it, false) } else null
    val fingerprint = if (!force && initial != null) source.fingerprint() else null
    if (initial != null && initial.fingerprint.startsWith("font-list-v5:") && initial.fingerprint == fingerprint?.value) {
        val verified = initial.copy(currentFont = fingerprint.currentFont).withSourceRevision()
        publish(verified, true)
        return verified
    }

    // First-run cache misses scan before checking: the scan initializes public storage.
    // A matching new module rechecks in the same request; older modules need a
    // separate fingerprint call before these rows become actionable.
    val scan = source.scanForVerification(refresh = force || initial != null)
    val scanned = scan.index.withSourceRevision()
    // Preserve a known list until this replacement is confirmed. In particular, a failed
    // post-scan permission check must not replace known rows with an unconfirmed empty scan.
    if (initial == null && preview == null) publish(scanned, false)
    val afterScan = scan.checkedFingerprint ?: source.fingerprint()
    check(scanned.fingerprint.startsWith("font-list-v5:") && scanned.fingerprint == afterScan.value) {
        "字体目录在扫描期间发生变化，列表尚未核实，请刷新重试"
    }
    val verified = scanned.copy(currentFont = afterScan.currentFont)
    publish(verified, true)
    return verified
}

private fun CachedFontIndex.withSourceRevision(): CachedFontIndex =
    copy(fonts = fonts.map { it.copy(revision = fingerprint) })

/** Recheck the live index at confirmation time; a dialog may outlive the selected row. */
internal fun fontLibraryContains(verified: Boolean, fonts: List<FontItem>, fontId: String, requireValid: Boolean): Boolean =
    verified && fontId.isNotBlank() && fontId != "default" &&
        fonts.any { it.id == fontId && (!requireValid || it.valid) }

internal class RootFontLibrarySource(
    private val diagnostics: (String, Long, Int) -> Unit = { _, _, _ -> },
    private val execute: suspend (String, Long) -> ShellResult = RootShell::fontInventory,
) : FontLibrarySource {
    private suspend fun request(action: String, timeoutMs: Long): ShellResult {
        val started = System.nanoTime()
        var code = -1
        try {
            return execute(action, timeoutMs).also { code = it.code }
        } finally {
            diagnostics(action, (System.nanoTime() - started) / 1_000_000L, code)
        }
    }

    override suspend fun cached(): CachedFontIndex? {
        val result = request("cached", 8_000L)
        // Only a successfully read cache may degrade to a cache miss. Execution failures
        // and cancellation still propagate; corruption must not prevent a fresh scan forever.
        val root = if (result.code == 0) parseCachedRoot(result.stdout) else parseRoot(result)
        if (root == null) return null
        when (root.optString("status")) {
            "error" -> {
                if (root.optString("code") in setOf("cache_miss", "cache-miss")) return null
                error(root.optString("message", "字体索引读取失败"))
            }
            "ok" -> Unit
            else -> return null
        }
        if (root.optJSONObject("data")?.optJSONArray("fonts") == null) return null
        return try {
            parseIndex(root)
        } catch (_: JSONException) {
            null
        } catch (_: IllegalArgumentException) {
            null
        }
    }

    private suspend fun parseCachedRoot(raw: String): JSONObject? = withContext(Dispatchers.Default) {
        val line = raw.lineSequence().firstOrNull { it.trimStart().startsWith("{") }
            ?: return@withContext null
        try {
            JSONObject(line.trim())
        } catch (_: JSONException) {
            null
        }
    }

    override suspend fun preview(): CachedFontIndex {
        val root = parseRoot(request("preview", 8_000L))
        require(root.optString("status") == "ok") { root.optString("message", "字体文件预览读取失败") }
        // Never trust an early file listing as a completed validation, even with bad backend flags.
        val index = parseIndex(root)
        return index.copy(fingerprint = "", fonts = index.fonts.map {
            it.copy(valid = false, error = "等待字体核查", provisional = true)
        })
    }

    override suspend fun fingerprint(): FontLibraryFingerprint {
        val result = request("fingerprint", 8_000L)
        val root = parseRoot(result)
        require(root.optString("status") == "ok") { root.optString("message", "无法核查字体目录或读取权限") }
        val data = root.getJSONObject("data")
        val fingerprint = data.optString("fingerprint")
        require(fingerprint.isNotBlank()) { "字体目录指纹缺失" }
        return FontLibraryFingerprint(fingerprint, data.optString("current", "default"))
    }

    override suspend fun scan(refresh: Boolean): CachedFontIndex {
        return scanForVerification(refresh).index
    }

    override suspend fun scanForVerification(refresh: Boolean): FontLibraryScan {
        val root = parseRoot(request(if (refresh) "refresh" else "scan", 60_000L))
        require(root.optString("status") == "ok") { root.optString("message", "字体库读取失败") }
        val index = parseIndex(root)
        val data = root.getJSONObject("data")
        val proof = data.optJSONObject("verification")
        require(!data.has("verification") || proof != null) { "字体索引核查记录格式错误" }
        // Older modules still use the separate check. A malformed new proof must
        // fail, rather than silently blessing rows or causing a retry loop.
        val checked = proof?.let {
            require(it.optString("schema") == "font-list-verification-v1" &&
                index.fingerprint.startsWith("font-list-v5:") &&
                it.optString("fingerprint") == index.fingerprint &&
                it.optString("current") == index.currentFont) { "字体索引核查记录不匹配" }
            FontLibraryFingerprint(index.fingerprint, index.currentFont)
        }
        return FontLibraryScan(index, checked)
    }

    private suspend fun parseRoot(result: ShellResult): JSONObject = withContext(Dispatchers.Default) {
        val line = result.stdout.lineSequence().firstOrNull { it.trimStart().startsWith("{") }
        val root = line?.let { JSONObject(it.trim()) }
        // Cache misses are an ordinary result, even when the bridge uses a non-zero exit code.
        if (root != null && root.optString("code") in setOf("cache_miss", "cache-miss")) return@withContext root
        require(result.code == 0) { root?.optString("message").orEmpty().ifBlank { result.stderr.ifBlank { "无法连接字体库，请检查模块与 Root 权限" } } }
        root ?: error("未收到字体库数据")
    }

    private suspend fun parseIndex(root: JSONObject): CachedFontIndex = withContext(Dispatchers.Default) {
        val data = root.getJSONObject("data")
        // A malformed/missing array is not evidence that the user's library is empty.
        val fonts = data.optJSONArray("fonts") ?: error("字体索引缺少字体列表")
        CachedFontIndex(
            fingerprint = data.optString("fingerprint"),
            currentFont = data.optString("current", "default"),
            fonts = parseFontItems(fonts),
            savedAt = System.currentTimeMillis(),
        )
    }
}

internal fun parseFontItems(array: JSONArray): List<FontItem> = buildList {
    val seen = HashSet<String>()
    for (index in 0 until array.length()) {
        val item = requireNotNull(array.optJSONObject(index)) { "字体索引包含无效字体记录" }
        val id = (item.opt("id") as? String)?.trim().orEmpty()
        require(id.isNotBlank()) { "字体索引缺少有效字体 ID" }
        if (id == "default") continue
        require(seen.add(id)) { "字体索引包含重复字体 ID：$id" }
        val weightsArray = item.optJSONArray("weights") ?: JSONArray()
        val weights = buildList {
            for (weightIndex in 0 until weightsArray.length()) {
                weightsArray.optString(weightIndex).trim().takeIf { it.isNotBlank() }?.let(::add)
            }
        }
        add(FontItem(
            id = id,
            name = item.optString("name", id),
            format = item.optString("format", "TTF"),
            size = item.optString("size", ""),
            date = item.optString("date", ""),
            variable = item.optBoolean("variable", weights.contains("variable")),
            valid = item.optBoolean("valid", true),
            error = item.optString("error", ""),
            weights = weights,
            supportsCjk = item.optBoolean("supportsCjk", true),
            revision = item.optString("revision", ""),
            provisional = item.optBoolean("provisional", false),
        ))
    }
}

/** Size/date labels are rounded; the library revision also catches same-name, same-size replacements. */
internal val FontItem.sourceRevision: String
    get() = "$id|$size|$date|$revision"
