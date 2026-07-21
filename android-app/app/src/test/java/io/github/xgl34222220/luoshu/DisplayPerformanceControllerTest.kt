package io.github.xgl34222220.luoshu

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class DisplayPerformanceControllerTest {
    @Test
    fun selectsHighestRefreshRateAtCurrentResolution() {
        val current = DisplayModeCandidate(1, 1440, 3200, 60f)
        val selected = selectHighestSameResolutionMode(
            modes = listOf(
                current,
                DisplayModeCandidate(2, 1440, 3200, 90f),
                DisplayModeCandidate(3, 1440, 3200, 120f),
                DisplayModeCandidate(4, 1080, 2400, 144f),
            ),
            current = current,
        )
        assertEquals(3, selected?.modeId)
        assertEquals(120f, selected?.refreshRate ?: 0f, 0.001f)
    }

    @Test
    fun neverSwitchesResolutionForAHigherRate() {
        val current = DisplayModeCandidate(8, 1080, 2400, 60f)
        val selected = selectHighestSameResolutionMode(
            modes = listOf(
                current,
                DisplayModeCandidate(9, 1440, 3200, 165f),
            ),
            current = current,
        )
        assertEquals(8, selected?.modeId)
    }

    @Test
    fun keepsCurrentModeWhenRatesTie() {
        val current = DisplayModeCandidate(11, 1080, 2400, 120f)
        val selected = selectHighestSameResolutionMode(
            modes = listOf(
                DisplayModeCandidate(10, 1080, 2400, 120f),
                current,
            ),
            current = current,
        )
        assertEquals(11, selected?.modeId)
    }

    @Test
    fun returnsNullWhenNoSameResolutionModeExists() {
        val selected = selectHighestSameResolutionMode(
            modes = listOf(DisplayModeCandidate(1, 720, 1600, 120f)),
            current = DisplayModeCandidate(2, 1080, 2400, 60f),
        )
        assertNull(selected)
    }
}
