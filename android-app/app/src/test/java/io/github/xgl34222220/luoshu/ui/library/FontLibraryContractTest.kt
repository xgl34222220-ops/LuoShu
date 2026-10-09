package io.github.xgl34222220.luoshu.ui.library

import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.ModuleSnapshot
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FontLibraryContractTest {
    private val regular = font(id = "regular", name = "Beta", date = "2026-07-17")
    private val variable = font(id = "variable", name = "Alpha", date = "2026-07-18", variable = true)
    private val multi = font(id = "multi", name = "Gamma", date = "2026-07-19", weights = listOf("regular", "bold"))
    private val invalid = font(id = "invalid", name = "Broken", date = "2026-07-20", valid = false)

    private val state = FontLibraryUiState(
        activeFontId = "multi",
        fonts = listOf(regular, variable, multi, invalid),
        totalCount = 4,
    )

    @Test
    fun filtersDoNotMutateTheUnderlyingIndex() {
        assertEquals(listOf("variable"), state.forDisplay(FontLibraryFilter.VARIABLE, FontLibrarySort.NAME).fonts.map { it.id })
        assertEquals(listOf("multi"), state.forDisplay(FontLibraryFilter.MULTI_WEIGHT, FontLibrarySort.NAME).fonts.map { it.id })
        assertEquals(listOf("invalid"), state.forDisplay(FontLibraryFilter.INVALID, FontLibrarySort.NAME).fonts.map { it.id })
        assertEquals(4, state.fonts.size)
    }

    @Test
    fun activeFirstKeepsTheCurrentFontAtTheTop() {
        val result = state.forDisplay(FontLibraryFilter.ALL, FontLibrarySort.ACTIVE_FIRST)
        assertEquals("multi", result.fonts.first().id)
        assertEquals(4, result.visibleCount)
    }

    @Test
    fun newestSortUsesTheImportedDateDescending() {
        val result = state.forDisplay(FontLibraryFilter.ALL, FontLibrarySort.NEWEST)
        assertEquals(listOf("invalid", "multi", "variable", "regular"), result.fonts.map { it.id })
    }

    @Test
    fun missingSuBlocksActionsWithoutClaimingAFontOperationIsRunning() {
        val error = "未找到 Root 命令 su"
        val access = fontLibraryAccessState(
            ModuleSnapshot(loading = false, error = error), operationBusy = false, mixBusy = false,
        )

        assertTrue(access.actionsBlocked)
        assertFalse(access.operationRunning)
        assertEquals(error, access.error)
    }

    @Test
    fun deniedRootDoesNotAuthorizeActionsEvenWhenAModuleWasSeen() {
        val access = fontLibraryAccessState(
            ModuleSnapshot(loading = false, installed = true, rootGranted = false),
            operationBusy = false, mixBusy = false,
        )

        assertTrue(access.actionsBlocked)
        assertFalse(access.operationRunning)
        assertTrue(access.error.contains("Root"))
    }

    @Test
    fun missingModuleIsAnErrorRatherThanAnEndlessBusyState() {
        val access = fontLibraryAccessState(
            ModuleSnapshot(loading = false, rootGranted = true, installed = false),
            operationBusy = false, mixBusy = false,
        )

        assertTrue(access.actionsBlocked)
        assertFalse(access.operationRunning)
        assertTrue(access.error.contains("模块"))
    }

    @Test
    fun cachedOrCheckingConnectionBlocksActionsWithoutInventingProgressOrAnError() {
        for (snapshot in listOf(
            ModuleSnapshot(),
            ModuleSnapshot(loading = false, statusCached = true, installed = true, rootGranted = true),
        )) {
            val access = fontLibraryAccessState(snapshot, operationBusy = false, mixBusy = false)
            assertTrue(access.actionsBlocked)
            assertFalse(access.operationRunning)
            assertEquals("", access.error)
        }
    }

    @Test
    fun verifiedIdleConnectionEnablesActionsAndActualTransactionsKeepTheirProgress() {
        val snapshot = ModuleSnapshot(loading = false, installed = true, rootGranted = true)
        val idle = fontLibraryAccessState(snapshot, operationBusy = false, mixBusy = false)
        assertFalse(idle.actionsBlocked)
        assertFalse(idle.operationRunning)
        assertEquals("", idle.error)

        for ((directBusy, mixBusy) in listOf(true to false, false to true)) {
            val running = fontLibraryAccessState(snapshot, directBusy, mixBusy)
            assertTrue(running.actionsBlocked)
            assertTrue(running.operationRunning)
            assertEquals("", running.error)
        }
    }

    private fun font(
        id: String,
        name: String,
        date: String,
        variable: Boolean = false,
        valid: Boolean = true,
        weights: List<String> = emptyList(),
    ) = FontItem(
        id = id,
        name = name,
        format = "TTF",
        size = "1 MB",
        date = date,
        variable = variable,
        valid = valid,
        error = if (valid) "" else "损坏",
        weights = weights,
    )
}
