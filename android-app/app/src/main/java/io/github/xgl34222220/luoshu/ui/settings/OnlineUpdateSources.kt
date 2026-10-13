package io.github.xgl34222220.luoshu.ui.settings

import org.json.JSONObject

/** Fetches a URL as text; throws on any network/HTTP failure. */
internal typealias UpdateTextFetcher = (url: String, accept: String) -> String

private const val REPO = "xgl34222220-ops/LuoShu"
internal const val TRUSTED_RELEASE_DOWNLOAD_PREFIX = "https://github.com/$REPO/releases/download/"

/**
 * Fixed, trusted metadata mirrors, tried in order. raw.githubusercontent.com is often unreachable
 * on mainland networks; jsDelivr serves the same repository file, and the GitHub contents API
 * serves the raw blob from api.github.com. No other host is ever contacted.
 */
internal fun updateMetadataUrls(file: String): List<String> {
    require(file == "update.json" || file == "update-prerelease.json") { "未知的更新元数据" }
    return listOf(
        "https://raw.githubusercontent.com/$REPO/main/$file",
        "https://cdn.jsdelivr.net/gh/$REPO@main/$file",
        "https://api.github.com/repos/$REPO/contents/$file?ref=main",
    )
}

internal fun acceptFor(url: String, fallback: String): String =
    if (url.startsWith("https://api.github.com/repos/$REPO/contents/")) "application/vnd.github.raw" else fallback

/** Release asset URLs must point at this repository's GitHub releases; anything else is rejected. */
internal fun parseTrustedReleaseAsset(url: String): Pair<String, String>? {
    if (!url.startsWith(TRUSTED_RELEASE_DOWNLOAD_PREFIX)) return null
    val rest = url.removePrefix(TRUSTED_RELEASE_DOWNLOAD_PREFIX)
    val parts = rest.split('/')
    if (parts.size != 2) return null
    val (tag, asset) = parts
    val safe = Regex("[A-Za-z0-9._+-]+")
    if (!tag.matches(safe) || !asset.matches(safe) || tag.startsWith(".") || asset.startsWith(".")) return null
    return tag to asset
}

internal class UpdateFetchFailure(message: String, val attempts: List<String>) : IllegalStateException(message)

/** Tries each URL in order; returns the first successful body, or throws with every attempt's reason. */
internal fun fetchFirstAvailable(
    urls: List<String>,
    accept: String,
    fetch: UpdateTextFetcher,
    validate: (String) -> Unit = {},
): String {
    val attempts = mutableListOf<String>()
    for (url in urls) {
        try {
            val body = fetch(url, acceptFor(url, accept))
            validate(body)
            return body
        } catch (error: InterruptedException) {
            throw error
        } catch (error: Exception) {
            if (error is kotlinx.coroutines.CancellationException) throw error
            attempts += "${hostOf(url)}：${error.message ?: error.javaClass.simpleName}"
        }
    }
    throw UpdateFetchFailure("所有更新源均不可用（${attempts.joinToString("；")}）", attempts)
}

internal fun parsePublishedSha256(raw: String): String {
    val value = raw.trim().split(Regex("\\s+"), limit = 2).firstOrNull().orEmpty().lowercase()
    require(value.matches(Regex("[0-9a-f]{64}"))) { "SHA-256 校验文件无效" }
    return value
}

/**
 * The .sha256 asset is fetched from its release download URL first; if github.com is unreachable,
 * the same asset is read through the Releases API on api.github.com. Failure is an error: the
 * caller must not present an unverifiable download as verified.
 */
internal fun fetchReleaseSha256(assetUrl: String, fetch: UpdateTextFetcher): String {
    val (tag, asset) = parseTrustedReleaseAsset(assetUrl) ?: error("下载地址不是洛书官方发布页：$assetUrl")
    val shaAsset = "$asset.sha256"
    val direct = "$TRUSTED_RELEASE_DOWNLOAD_PREFIX$tag/$shaAsset"
    val attempts = mutableListOf<String>()
    try {
        return parsePublishedSha256(fetch(direct, "text/plain"))
    } catch (error: InterruptedException) {
        throw error
    } catch (error: Exception) {
        if (error is kotlinx.coroutines.CancellationException) throw error
        attempts += "github.com：${error.message ?: error.javaClass.simpleName}"
    }
    try {
        val release = JSONObject(fetch("https://api.github.com/repos/$REPO/releases/tags/$tag", "application/vnd.github+json"))
        val assets = release.optJSONArray("assets") ?: error("发布信息缺少资产列表")
        val apiUrl = (0 until assets.length())
            .map { assets.getJSONObject(it) }
            .firstOrNull { it.optString("name") == shaAsset }
            ?.optString("url")
            .orEmpty()
        require(apiUrl.startsWith("https://api.github.com/repos/$REPO/releases/assets/")) { "发布中没有 $shaAsset" }
        return parsePublishedSha256(fetch(apiUrl, "application/octet-stream"))
    } catch (error: InterruptedException) {
        throw error
    } catch (error: Exception) {
        if (error is kotlinx.coroutines.CancellationException) throw error
        attempts += "api.github.com：${error.message ?: error.javaClass.simpleName}"
    }
    throw UpdateFetchFailure("无法获取 $shaAsset（${attempts.joinToString("；")}）", attempts)
}

internal fun deriveAppUrl(zipUrl: String): String {
    val slash = zipUrl.lastIndexOf('/')
    if (slash <= 0) return ""
    val file = zipUrl.substring(slash + 1)
    if (!file.startsWith("LuoShu-") || !file.endsWith(".zip")) return ""
    val artifact = file.removePrefix("LuoShu-").removeSuffix(".zip")
    return zipUrl.substring(0, slash + 1) + "LuoShu-App-$artifact.apk"
}

internal data class ResolvedUpdate(
    val version: String,
    val versionCode: Int,
    val zipUrl: String,
    val changelogUrl: String,
    val sha256: String,
    val appUrl: String,
    val appSha256: String,
    val warning: String,
)

/**
 * Metadata falls back across fixed mirrors. The module SHA-256 is mandatory: without it the whole
 * check fails. A missing App checksum only withdraws the APK download, with a visible warning.
 */
internal fun resolveOnlineUpdate(
    channelFile: String,
    fetch: UpdateTextFetcher,
    ensureActive: () -> Unit = {},
): ResolvedUpdate {
    val metadata = fetchFirstAvailable(updateMetadataUrls(channelFile), "application/json", fetch) { body ->
        JSONObject(body)
    }
    ensureActive()
    val root = JSONObject(metadata)
    val zipUrl = root.optString("zipUrl").trim()
    val versionCode = root.optInt("versionCode", 0)
    require(versionCode > 0 && zipUrl.startsWith("https://")) { "更新元数据不完整" }
    require(parseTrustedReleaseAsset(zipUrl) != null) { "更新元数据中的下载地址不是洛书官方发布页" }

    val moduleSha = try {
        fetchReleaseSha256(zipUrl, fetch)
    } catch (error: UpdateFetchFailure) {
        throw IllegalStateException("无法校验模块 ZIP：${error.message}", error)
    }
    ensureActive()
    var appUrl = deriveAppUrl(zipUrl)
    var appSha = ""
    var warning = ""
    if (appUrl.isNotBlank()) {
        try {
            appSha = fetchReleaseSha256(appUrl, fetch)
        } catch (error: UpdateFetchFailure) {
            appUrl = ""
            warning = "App APK 的 SHA-256 校验文件无法获取，已隐藏 APK 下载；请从发布页手动核对。"
        }
    }
    ensureActive()
    return ResolvedUpdate(
        version = root.optString("version").trim(),
        versionCode = versionCode,
        zipUrl = zipUrl,
        changelogUrl = root.optString("changelog").trim(),
        sha256 = moduleSha,
        appUrl = appUrl,
        appSha256 = appSha,
        warning = warning,
    )
}

private fun hostOf(url: String): String = url.removePrefix("https://").substringBefore('/')
