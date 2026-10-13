package io.github.xgl34222220.luoshu.ui.settings

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.IOException

class OnlineUpdateSourcesTest {
    private val zip = "https://github.com/xgl34222220-ops/LuoShu/releases/download/refactor-v3.0.0/LuoShu-v3.0.0.zip"
    private val apk = "https://github.com/xgl34222220-ops/LuoShu/releases/download/refactor-v3.0.0/LuoShu-App-v3.0.0.apk"
    private val metadata = """{"version":"v3.0.0","versionCode":80000,"zipUrl":"$zip","changelog":"https://raw.githubusercontent.com/xgl34222220-ops/LuoShu/refactor-v3.0.0/RELEASE_NOTES.md"}"""
    private val moduleSha = "a".repeat(64)
    private val appSha = "b".repeat(64)

    private class FakeNetwork(private val responses: Map<String, String>) {
        val requested = mutableListOf<Pair<String, String>>()
        fun fetch(url: String, accept: String): String {
            requested += url to accept
            return responses[url] ?: throw IOException("unreachable")
        }
    }

    @Test
    fun metadataMirrorListIsFixedTrustedAndOrdered() {
        val urls = updateMetadataUrls("update.json")
        assertEquals(
            listOf(
                "https://raw.githubusercontent.com/xgl34222220-ops/LuoShu/main/update.json",
                "https://cdn.jsdelivr.net/gh/xgl34222220-ops/LuoShu@main/update.json",
                "https://api.github.com/repos/xgl34222220-ops/LuoShu/contents/update.json?ref=main",
            ),
            urls,
        )
        try {
            updateMetadataUrls("../evil.json")
            fail("arbitrary metadata paths must be rejected")
        } catch (_: IllegalArgumentException) {
        }
    }

    @Test
    fun rawGithubFailureFallsBackToJsDelivrAndShaIsVerified() {
        val network = FakeNetwork(
            mapOf(
                "https://cdn.jsdelivr.net/gh/xgl34222220-ops/LuoShu@main/update.json" to metadata,
                "$zip.sha256" to "$moduleSha  LuoShu-v3.0.0.zip\n",
                "$apk.sha256" to appSha,
            ),
        )
        val update = resolveOnlineUpdate("update.json", network::fetch)
        assertEquals(80000, update.versionCode)
        assertEquals(moduleSha, update.sha256)
        assertEquals(apk, update.appUrl)
        assertEquals(appSha, update.appSha256)
        assertEquals("", update.warning)
        assertEquals("https://raw.githubusercontent.com/xgl34222220-ops/LuoShu/main/update.json", network.requested.first().first)
    }

    @Test
    fun contentsApiMirrorAsksForTheRawBlob() {
        val api = "https://api.github.com/repos/xgl34222220-ops/LuoShu/contents/update-prerelease.json?ref=main"
        val network = FakeNetwork(mapOf(api to metadata, "$zip.sha256" to moduleSha, "$apk.sha256" to appSha))
        resolveOnlineUpdate("update-prerelease.json", network::fetch)
        assertEquals("application/vnd.github.raw", network.requested.first { it.first == api }.second)
    }

    @Test
    fun invalidJsonFromOneMirrorTriesTheNext() {
        val network = FakeNetwork(
            mapOf(
                "https://raw.githubusercontent.com/xgl34222220-ops/LuoShu/main/update.json" to "<html>blocked</html>",
                "https://cdn.jsdelivr.net/gh/xgl34222220-ops/LuoShu@main/update.json" to metadata,
                "$zip.sha256" to moduleSha,
                "$apk.sha256" to appSha,
            ),
        )
        assertEquals(80000, resolveOnlineUpdate("update.json", network::fetch).versionCode)
    }

    @Test
    fun shaFallsBackToTheReleasesApiWhenGithubDownloadsAreUnreachable() {
        val release = """{"assets":[
            {"name":"LuoShu-v3.0.0.zip.sha256","url":"https://api.github.com/repos/xgl34222220-ops/LuoShu/releases/assets/11"},
            {"name":"LuoShu-App-v3.0.0.apk.sha256","url":"https://api.github.com/repos/xgl34222220-ops/LuoShu/releases/assets/12"}]}"""
        val network = FakeNetwork(
            mapOf(
                "https://raw.githubusercontent.com/xgl34222220-ops/LuoShu/main/update.json" to metadata,
                "https://api.github.com/repos/xgl34222220-ops/LuoShu/releases/tags/refactor-v3.0.0" to release,
                "https://api.github.com/repos/xgl34222220-ops/LuoShu/releases/assets/11" to moduleSha,
                "https://api.github.com/repos/xgl34222220-ops/LuoShu/releases/assets/12" to appSha,
            ),
        )
        val update = resolveOnlineUpdate("update.json", network::fetch)
        assertEquals(moduleSha, update.sha256)
        assertEquals(appSha, update.appSha256)
        assertTrue(network.requested.any { it.first.endsWith("/assets/11") && it.second == "application/octet-stream" })
    }

    @Test
    fun missingModuleShaFailsTheWholeCheckInsteadOfShowingAnUnverifiedDownload() {
        val network = FakeNetwork(mapOf("https://raw.githubusercontent.com/xgl34222220-ops/LuoShu/main/update.json" to metadata))
        try {
            resolveOnlineUpdate("update.json", network::fetch)
            fail("module checksum is mandatory")
        } catch (error: IllegalStateException) {
            assertTrue(error.message.orEmpty().contains("无法校验模块 ZIP"))
        }
    }

    @Test
    fun malformedShaIsAFailureNotAnEmptyChecksum() {
        val network = FakeNetwork(
            mapOf(
                "https://raw.githubusercontent.com/xgl34222220-ops/LuoShu/main/update.json" to metadata,
                "$zip.sha256" to "Not Found",
            ),
        )
        try {
            resolveOnlineUpdate("update.json", network::fetch)
            fail("an invalid checksum must not be accepted")
        } catch (error: IllegalStateException) {
            assertTrue(error.message.orEmpty().contains("SHA-256"))
        }
    }

    @Test
    fun missingAppShaWithdrawsTheApkWithAVisibleWarning() {
        val network = FakeNetwork(
            mapOf(
                "https://raw.githubusercontent.com/xgl34222220-ops/LuoShu/main/update.json" to metadata,
                "$zip.sha256" to moduleSha,
            ),
        )
        val update = resolveOnlineUpdate("update.json", network::fetch)
        assertEquals(moduleSha, update.sha256)
        assertEquals("", update.appUrl)
        assertEquals("", update.appSha256)
        assertTrue(update.warning.contains("APK"))
    }

    @Test
    fun untrustedDownloadHostsAreRejected() {
        val evil = metadata.replace(zip, "https://evil.example/LuoShu-v3.0.0.zip")
        val network = FakeNetwork(mapOf("https://raw.githubusercontent.com/xgl34222220-ops/LuoShu/main/update.json" to evil))
        try {
            resolveOnlineUpdate("update.json", network::fetch)
            fail("untrusted zip host must be rejected")
        } catch (error: IllegalArgumentException) {
            assertTrue(error.message.orEmpty().contains("官方发布页"))
        }
        assertFalse(network.requested.any { it.first.contains("evil.example") })
        assertEquals(null, parseTrustedReleaseAsset("https://github.com/xgl34222220-ops/LuoShu/releases/download/../x/LuoShu.zip"))
        assertEquals(null, parseTrustedReleaseAsset("https://github.com/other/LuoShu/releases/download/t/LuoShu-v1.zip"))
        assertEquals("refactor-v3.0.0" to "LuoShu-v3.0.0.zip", parseTrustedReleaseAsset(zip))
    }

    @Test
    fun everyMirrorFailingReportsEachAttempt() {
        try {
            resolveOnlineUpdate("update.json", FakeNetwork(emptyMap())::fetch)
            fail("expected failure")
        } catch (error: UpdateFetchFailure) {
            assertEquals(3, error.attempts.size)
            assertTrue(error.message.orEmpty().contains("cdn.jsdelivr.net"))
        }
    }
}
