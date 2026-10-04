package io.github.xgl34222220.luoshu

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Test

class FontLibraryLoaderTest {
    private fun index(fingerprint: String = "font-list-v5:a", ids: List<String> = listOf("A")) = CachedFontIndex(
        fingerprint, "default", ids.map { id ->
            FontItem(id, id, "TTF", "1 MB", "2026-10-02", false, true, "", listOf("regular"))
        }, 1L,
    )

    private class Source(var cachedIndex: CachedFontIndex?, var fresh: CachedFontIndex) : FontLibrarySource {
        var cachedReads = 0
        var checks = 0
        var scans = 0
        var forced = false
        var previewIndex: CachedFontIndex? = null
        var scanGate: CompletableDeferred<Unit>? = null
        var checkFailure: Exception? = null
        var currentFingerprint = fresh.fingerprint
        var checkGate: CompletableDeferred<Unit>? = null
        override suspend fun cached(): CachedFontIndex? = cachedIndex.also { cachedReads++ }
        override suspend fun preview(): CachedFontIndex? = previewIndex
        override suspend fun fingerprint(): FontLibraryFingerprint {
            checks++
            checkGate?.await()
            checkFailure?.let { throw it }
            return FontLibraryFingerprint(currentFingerprint, "A")
        }
        override suspend fun scan(refresh: Boolean): CachedFontIndex {
            scans++
            forced = refresh
            scanGate?.await()
            return fresh
        }
    }

    @Test
    fun moduleCacheIsPublishedBeforeBlockedValidation() = runBlocking {
        val gate = CompletableDeferred<Unit>()
        val visible = CompletableDeferred<CachedFontIndex>()
        val source = Source(index(), index()).apply { checkGate = gate }
        val verified = mutableListOf<Boolean>()
        val job = launch {
            loadFontLibrary(null, false, source) { rows, checked ->
                verified += checked
                visible.complete(rows)
            }
        }
        withTimeout(1_000L) { assertEquals(listOf("A"), visible.await().fonts.map { it.id }) }
        assertEquals(listOf(false), verified)
        assertTrue(job.isActive)
        gate.complete(Unit)
        job.join()
        assertEquals(listOf(false, true), verified)
        assertEquals(0, source.scans)
    }

    @Test
    fun localCacheChecksWithoutReadingModuleCacheOrRescanning() = runBlocking {
        val known = index()
        val source = Source(null, known)
        val loaded = loadFontLibrary(known, false, source) { _, _ -> }
        assertEquals(0, source.cachedReads)
        assertEquals(1, source.checks)
        assertEquals(0, source.scans)
        assertEquals("A", loaded.currentFont)
        assertEquals("font-list-v5:a", loaded.fonts.single().revision)
    }

    @Test
    fun firstRunCacheMissScansWithoutRequiringAnExistingDirectory() = runBlocking {
        val source = Source(null, index())
        assertEquals(1, loadFontLibrary(null, false, source) { _, _ -> }.fonts.size)
        assertEquals(1, source.checks)
        assertEquals(1, source.scans)
        assertFalse(source.forced)
    }

    @Test
    fun importAndDeleteReplaceTheOldListIncludingAnEmptyResult() = runBlocking {
        val old = index()
        val source = Source(null, index("font-list-v5:b", listOf("B", "C")))
        val imported = loadFontLibrary(old, false, source) { _, _ -> }
        assertEquals(listOf("B", "C"), imported.fonts.map { it.id })
        assertFalse(source.forced)
        source.fresh = index("font-list-v5:empty", emptyList())
        source.currentFingerprint = source.fresh.fingerprint
        val deleted = loadFontLibrary(imported, false, source) { _, _ -> }
        assertTrue(deleted.fonts.isEmpty())
        assertEquals("font-list-v5:empty", deleted.fingerprint)
    }

    @Test
    fun knownEmptyLibraryDoesNotRescanForever() = runBlocking {
        val empty = index("font-list-v5:empty", emptyList())
        val source = Source(null, empty)
        loadFontLibrary(empty, false, source) { _, _ -> }
        assertEquals(0, source.scans)
        assertEquals(0, source.cachedReads)
    }

    @Test
    fun manualRefreshBypassesFingerprintHit() = runBlocking {
        val source = Source(null, index())
        loadFontLibrary(index(), true, source) { _, _ -> }
        assertEquals(1, source.scans)
        assertTrue(source.forced)
    }

    @Test
    fun legacyCacheWithoutFingerprintRemainsVisibleButMustBeScanned() = runBlocking {
        val source = Source(index(""), index())
        val states = mutableListOf<Boolean>()
        loadFontLibrary(null, false, source) { _, verified -> states += verified }
        assertEquals(listOf(false, true), states)
        assertEquals(1, source.scans)
    }

    @Test
    fun permissionFailureKeepsKnownRowsUnverifiedAndCanRecover() = runBlocking {
        val source = Source(index(), index()).apply { checkFailure = SecurityException("permission denied") }
        val states = mutableListOf<Pair<CachedFontIndex, Boolean>>()
        val result = runCatching { loadFontLibrary(null, false, source) { row, verified -> states += row to verified } }
        assertTrue(result.exceptionOrNull() is SecurityException)
        assertEquals(listOf(false), states.map { it.second })
        assertEquals("A", states.single().first.fonts.single().id)
        assertEquals(0, source.scans)
        source.checkFailure = null
        loadFontLibrary(states.single().first, false, source) { row, verified -> states += row to verified }
        assertTrue(states.last().second)
    }

    @Test
    fun cancellingValidationDoesNotPublishAFalseEmptyOrVerifiedList() = runBlocking {
        val visible = CompletableDeferred<Unit>()
        val source = Source(index(), index()).apply { checkGate = CompletableDeferred() }
        val states = mutableListOf<Boolean>()
        val job = launch { loadFontLibrary(null, false, source) { _, verified -> states += verified; visible.complete(Unit) } }
        withTimeout(1_000L) { visible.await() }
        job.cancelAndJoin()
        assertEquals(listOf(false), states)
        assertEquals(0, source.scans)
    }

    @Test
    fun scanFingerprintMismatchKeepsRowsUnverifiedWithoutAnAutomaticRescanLoop() = runBlocking {
        val source = Source(null, index("font-list-v5:during-scan")).apply { currentFingerprint = "font-list-v5:later" }
        val published = mutableListOf<Pair<CachedFontIndex, Boolean>>()
        val failure = runCatching {
            loadFontLibrary(index(), false, source) { rows, verified -> published += rows to verified }
        }.exceptionOrNull()
        assertTrue(failure?.message.orEmpty().contains("扫描期间"))
        assertEquals("font-list-v5:a", published.last().first.fingerprint)
        assertTrue(published.none { it.second })
        assertEquals(1, source.scans)
        assertEquals(2, source.checks)
        // A later explicit/foreground check can recover once the directory is stable.
        source.fresh = index("font-list-v5:later")
        val recovered = loadFontLibrary(published.last().first, false, source) { rows, verified -> published += rows to verified }
        assertEquals("font-list-v5:later", recovered.fingerprint)
        assertTrue(published.last().second)
    }

    @Test
    fun knownRowsLoseActionReadinessBeforeABlockedCheck() = runBlocking {
        val published = CompletableDeferred<Boolean>()
        val source = Source(null, index()).apply { checkGate = CompletableDeferred() }
        val job = launch { loadFontLibrary(index(), false, source) { _, verified -> published.complete(verified) } }
        withTimeout(1_000L) { assertFalse(published.await()) }
        job.cancelAndJoin()
        assertEquals(0, source.scans)
    }

    @Test
    fun scanPermissionFailureCannotPublishVerifiedRows() = runBlocking {
        val source = Source(null, index()).apply { checkFailure = SecurityException("permission lost after scan") }
        val states = mutableListOf<Boolean>()
        assertTrue(runCatching { loadFontLibrary(null, false, source) { _, verified -> states += verified } }.isFailure)
        assertEquals(listOf(false), states)
        assertEquals(1, source.scans)
    }

    @Test
    fun unconfirmedEmptyScanCannotClearAKnownLibrary() = runBlocking {
        val source = Source(null, index("font-list-v5:empty", emptyList())).apply {
            currentFingerprint = "font-list-v5:changed-again"
        }
        val states = mutableListOf<Pair<CachedFontIndex, Boolean>>()
        assertTrue(runCatching {
            loadFontLibrary(index(), false, source) { rows, verified -> states += rows to verified }
        }.isFailure)
        assertEquals(listOf("A"), states.last().first.fonts.map { it.id })
        assertFalse(states.last().second)
        assertEquals(1, source.scans)
    }

    @Test
    fun staleDialogAndPermissionFailureCannotAuthorizeAnAbsentFont() {
        val old = index().fonts.single()
        assertFalse(fontLibraryContains(false, listOf(old), old.id, true))
        assertFalse(fontLibraryContains(true, emptyList(), old.id, true))
        assertFalse(fontLibraryContains(true, emptyList(), old.id, false))
        assertTrue(fontLibraryContains(true, listOf(old), old.id, true))
        val invalid = old.copy(valid = false)
        assertFalse(fontLibraryContains(true, listOf(invalid), old.id, true))
        assertTrue(fontLibraryContains(true, listOf(invalid), old.id, false))
    }

    @Test
    fun sameNameSameDisplaySizeAndDateReplacementInvalidatesPreviewAndAxes() {
        val old = index().fonts.single().copy(revision = "before")
        val replacement = old.copy(revision = "after")
        assertNotEquals(old.sourceRevision, replacement.sourceRevision)
    }

    @Test
    fun parserPreservesNativeWeightsAndVariableCapability() {
        val fonts = parseFontItems(JSONArray("""[{"id":"variable","variable":true,"weights":["variable"]},{"id":"static","weights":["regular","bold"],"supportsCjk":false}]"""))
        assertTrue(fonts.first().variable)
        assertEquals(listOf("regular", "bold"), fonts.last().weights)
        assertFalse(fonts.last().supportsCjk)
    }

    @Test
    fun rootSourceHandlesCacheMissAndNeverRequestsStatus() = runBlocking {
        val commands = mutableListOf<String>()
        val source = RootFontLibrarySource { command, _ ->
            commands += command
            if (command == "cached") ShellResult(1, """{"status":"error","code":"cache_miss","message":"cache miss"}""", "")
            else ShellResult(0, """{"status":"ok","data":{"fonts":[],"fingerprint":"font-list-v5:empty","current":"default"}}""", "")
        }
        val result = loadFontLibrary(null, false, source) { _, _ -> }
        assertTrue(result.fonts.isEmpty())
        assertEquals(4, commands.size)
        assertEquals("cached", commands[0])
        assertEquals("preview", commands[1])
        assertEquals("scan", commands[2])
        assertEquals("fingerprint", commands[3])
        assertFalse(commands.any { it.contains("status") })
    }

    @Test
    fun scanAndCheckInOneRequestAvoidsAnotherRootInterpreter() = runBlocking {
        val commands = mutableListOf<String>()
        val source = RootFontLibrarySource { action, _ ->
            commands += action
            val proof = if (action == "refresh")
                """, "verification":{"schema":"font-list-verification-v1","fingerprint":"font-list-v5:new","current":"A"}""" else ""
            ShellResult(0, """{"status":"ok","data":{"fonts":[{"id":"B","valid":true}],"fingerprint":"font-list-v5:new","current":"A"$proof}}""", "")
        }
        val states = mutableListOf<Boolean>()
        val loaded = loadFontLibrary(index(), true, source) { _, ready -> states += ready }
        assertEquals(listOf("refresh"), commands)
        assertEquals(listOf(false, true), states)
        assertEquals("B", loaded.fonts.single().id)
        assertEquals("A", loaded.currentFont)
    }

    @Test
    fun staleLocalListUsesVerifiedModuleScanWithoutForcingHeaderReads() = runBlocking {
        val actions = mutableListOf<Pair<String, Long>>()
        val source = RootFontLibrarySource { action, timeout ->
            actions += action to timeout
            when (action) {
                "fingerprint" -> ShellResult(0, """{"status":"ok","data":{"fingerprint":"font-list-v5:new","current":"B"}}""", "")
                "scan" -> ShellResult(0, """{"status":"ok","data":{"fonts":[{"id":"B","valid":true}],"fingerprint":"font-list-v5:new","current":"B","verification":{"schema":"font-list-verification-v1","fingerprint":"font-list-v5:new","current":"B"}}}""", "")
                else -> error("Unexpected request: $action")
            }
        }
        val states = mutableListOf<Pair<CachedFontIndex, Boolean>>()
        val loaded = loadFontLibrary(index(), false, source) { rows, ready -> states += rows to ready }
        assertEquals(listOf("fingerprint" to 8_000L, "scan" to 60_000L), actions)
        assertEquals(listOf(false, true), states.map { it.second })
        assertEquals("A", states.first().first.fonts.single().id)
        assertEquals("B", loaded.fonts.single().id)
        assertEquals("font-list-v5:new", loaded.fonts.single().revision)
    }

    @Test
    fun mismatchedBatchedProofCannotAuthorizeOrClearKnownRows() = runBlocking {
        for (proof in listOf(
            """{"schema":"font-list-verification-v1","fingerprint":"font-list-v5:stale","current":"default"}""",
            """{"schema":"font-list-verification-v1","fingerprint":"font-list-v5:new","current":"changed"}""",
            """{"schema":"unknown","fingerprint":"font-list-v5:new","current":"default"}""",
            "null",
            "false",
            "\"broken\"",
        )) {
            var calls = 0
            val source = RootFontLibrarySource { _, _ ->
                calls++
                ShellResult(0, """{"status":"ok","data":{"fonts":[],"fingerprint":"font-list-v5:new","current":"default","verification":$proof}}""", "")
            }
            val states = mutableListOf<Pair<CachedFontIndex, Boolean>>()
            assertTrue(runCatching { loadFontLibrary(index(), true, source) { rows, ready -> states += rows to ready } }.isFailure)
            assertEquals(1, calls)
            assertEquals("A", states.last().first.fonts.single().id)
            assertTrue(states.none { it.second })
        }
    }

    @Test
    fun rootSourceRejectsMalformedSuccessInsteadOfClearingTheIndex() = runBlocking {
        val source = RootFontLibrarySource { _, _ -> ShellResult(0, """{"status":"ok","data":{}}""", "") }
        assertTrue(runCatching { source.scan(false) }.isFailure)
    }

    @Test
    fun malformedOrDuplicateRowsCannotClearKnownLibraryOrBecomeVerified() = runBlocking {
        for (rows in listOf("[null]", "[1]", "[{}]", "[{\"id\":null}]", "[{\"id\":123}]",
                            "[{\"id\":\"\"}]", "[{\"id\":\"A\"},{\"id\":\" A \"}]")) {
            var calls = 0
            val source = RootFontLibrarySource { _, _ ->
                calls++
                ShellResult(0, """{"status":"ok","data":{"fonts":$rows,"fingerprint":"font-list-v5:new"}}""", "")
            }
            val states = mutableListOf<Pair<CachedFontIndex, Boolean>>()
            assertTrue(runCatching { loadFontLibrary(index(), true, source) { value, ready -> states += value to ready } }.isFailure)
            assertEquals(1, calls)
            assertEquals("A", states.last().first.fonts.single().id)
            assertTrue(states.none { it.second })
        }
    }

    @Test
    fun malformedCachedRowsAreACacheMissAndCanRecoverWithFreshScan() = runBlocking {
        val actions = mutableListOf<String>()
        val source = RootFontLibrarySource { action, _ ->
            actions += action
            val rows = if (action == "cached") "[null]" else "[{\"id\":\"B\",\"valid\":true}]"
            val proof = if (action == "scan")
                """, "verification":{"schema":"font-list-verification-v1","fingerprint":"font-list-v5:new","current":"default"}""" else ""
            ShellResult(0, """{"status":"ok","data":{"fonts":$rows,"fingerprint":"font-list-v5:new","current":"default"$proof}}""", "")
        }
        val verified = mutableListOf<Boolean>()
        val result = loadFontLibrary(null, false, source) { _, ready -> verified += ready }
        assertEquals(listOf("cached", "preview", "scan"), actions)
        assertEquals(listOf(false, true), verified)
        assertEquals("B", result.fonts.single().id)
    }

    @Test
    fun rootSourceDoesNotConvertPermissionDenialIntoCacheMiss() = runBlocking {
        val source = RootFontLibrarySource { _, _ -> ShellResult(1, "", "permission denied") }
        assertTrue(runCatching { source.cached() }.exceptionOrNull()?.message.orEmpty().contains("permission denied"))
    }

    @Test
    fun successfullyReadDamagedModuleCacheFallsBackToScanEvenForForcedRefresh() = runBlocking {
        val damagedCaches = listOf(
            "{broken JSON",
            """{"status":"ok","data":{}}""",
            """{"status":"ok"}""",
            """{"status":"ok","data":{"fonts":"broken"}}""",
            "{}",
            "empty or truncated file",
        )
        for (damaged in damagedCaches) {
            for (force in listOf(false, true)) {
                val commands = mutableListOf<String>()
                val source = RootFontLibrarySource { command, _ ->
                    commands += command
                    if (command == "cached") ShellResult(0, damaged, "")
                    else ShellResult(0, """{"status":"ok","data":{"fonts":[],"fingerprint":"font-list-v5:empty","current":"default"}}""", "")
                }
                val verifiedStates = mutableListOf<Boolean>()
                val result = loadFontLibrary(null, force, source) { _, verified -> verifiedStates += verified }
                assertEquals("font-list-v5:empty", result.fingerprint)
                assertEquals(4, commands.size)
                assertEquals("preview", commands[1])
                assertEquals(if (force) "refresh" else "scan", commands[2])
                assertEquals(listOf(false, true), verifiedStates)
            }
        }
    }

    @Test
    fun damagedOutputWithRootExecutionFailureMustNotFallBackToScan() = runBlocking {
        var calls = 0
        val source = RootFontLibrarySource { _, _ ->
            calls++
            ShellResult(1, "{broken JSON", "Root execution failed")
        }
        assertTrue(runCatching { loadFontLibrary(null, true, source) { _, _ -> } }.isFailure)
        assertEquals(1, calls)
    }

    @Test
    fun explicitCacheReadPermissionErrorMustNotFallBackToScan() = runBlocking {
        var calls = 0
        val source = RootFontLibrarySource { _, _ ->
            calls++
            ShellResult(0, """{"status":"error","message":"permission denied"}""", "")
        }
        val failure = runCatching { loadFontLibrary(null, true, source) { _, _ -> } }.exceptionOrNull()
        assertTrue(failure?.message.orEmpty().contains("permission denied"))
        assertEquals(1, calls)
    }

    @Test
    fun cancelledCacheRequestMustNotFallBackToScan() = runBlocking {
        var calls = 0
        val source = RootFontLibrarySource { _, _ ->
            calls++
            throw CancellationException("request cancelled")
        }
        val failure = runCatching { loadFontLibrary(null, true, source) { _, _ -> } }.exceptionOrNull()
        assertTrue(failure is CancellationException)
        assertEquals(1, calls)
    }


    @Test
    fun firstRunShowsRealPreviewRowsBeforeScanCompletes() = runBlocking {
        val gate = CompletableDeferred<Unit>()
        val visible = CompletableDeferred<CachedFontIndex>()
        val full = index(ids = (1..100).map { "Font$it" })
        val source = Source(null, full).apply {
            previewIndex = full.copy(fingerprint = "", fonts = full.fonts.map {
                it.copy(valid = false, error = "等待字体核查", provisional = true)
            })
            scanGate = gate
        }
        val verified = mutableListOf<Boolean>()
        val job = launch {
            loadFontLibrary(null, false, source) { rows, ready ->
                visible.complete(rows)
                verified += ready
            }
        }
        val first = withTimeout(1_000L) { visible.await() }
        assertEquals(100, first.fonts.size)
        assertTrue(first.fonts.none { it.valid })
        assertEquals(listOf(false), verified)
        assertTrue(job.isActive)
        gate.complete(Unit)
        job.join()
        assertEquals(listOf(false, true), verified)
    }

    @Test
    fun rootPreviewNeverTrustsBackendValidOrFingerprintFlags() = runBlocking {
        val source = RootFontLibrarySource { action, _ ->
            assertEquals("preview", action)
            ShellResult(0, """{"status":"ok","data":{"fingerprint":"font-list-v5:unsafe","fonts":[{"id":"A","valid":true}]}}""", "")
        }
        val preview = source.preview()
        assertEquals("", preview.fingerprint)
        assertFalse(preview.fonts.single().valid)
        assertTrue(preview.fonts.single().provisional)
    }

    @Test
    fun legacyV4EqualityCannotMarkTheListVerified() = runBlocking {
        val legacy = index("v4:old")
        val source = Source(legacy, legacy)
        val states = mutableListOf<Boolean>()
        assertTrue(runCatching { loadFontLibrary(null, false, source) { _, ready -> states += ready } }.isFailure)
        assertEquals(1, source.scans)
        assertTrue(states.none { it })
    }

    @Test
    fun requestStagesIncludeExitCodeAndCancellationWithoutHidingTheError() = runBlocking {
        val stages = mutableListOf<Triple<String, Long, Int>>()
        val phaseResults = mutableListOf<Pair<String, ShellResult>>()
        val cached = ShellResult(0, """{"status":"error","code":"cache_miss"}""", "[font-request] private protocol")
        val source = RootFontLibrarySource(
            diagnostics = { action, duration, code -> stages += Triple(action, duration, code) },
            phaseDiagnostics = { action, result -> phaseResults += action to result },
        ) { action, _ ->
            if (action == "cached") cached
            else throw CancellationException("stopped")
        }
        assertNull(source.cached())
        assertTrue(runCatching { source.preview() }.exceptionOrNull() is CancellationException)
        assertEquals(listOf("cached", "preview"), stages.map { it.first })
        assertEquals(listOf(0, -1), stages.map { it.third })
        assertTrue(stages.all { it.second >= 0 })
        assertEquals(listOf("cached" to cached), phaseResults)
    }

}
