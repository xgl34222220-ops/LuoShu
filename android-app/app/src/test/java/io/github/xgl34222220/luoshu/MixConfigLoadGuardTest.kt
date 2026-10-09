package io.github.xgl34222220.luoshu

import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class MixConfigLoadGuardTest {
    @Test
    fun firstReadAppliesAndSwitchingTabsDoesNotReloadTheDraft() {
        val guard = MixConfigLoadGuard()
        val first = requireNotNull(guard.begin(force = false))
        assertTrue(guard.complete(first))
        guard.edited()
        assertNull(guard.begin(force = false))
    }

    @Test
    fun editDuringSlowInitialReadRejectsTheOlderModuleSelection() {
        val guard = MixConfigLoadGuard()
        val first = requireNotNull(guard.begin(force = false))
        guard.edited()
        assertFalse(guard.complete(first))
        assertNull(guard.begin(force = false))
    }

    @Test
    fun draftCreatedBeforeInitialReadIsAlsoPreserved() {
        val guard = MixConfigLoadGuard()
        guard.edited()
        val first = requireNotNull(guard.begin(force = false))
        assertFalse(guard.complete(first))
    }

    @Test
    fun explicitRefreshMayReplaceTheDraftPresentWhenRequested() {
        val guard = MixConfigLoadGuard()
        guard.edited()
        val refresh = requireNotNull(guard.begin(force = true))
        assertTrue(guard.complete(refresh))
    }

    @Test
    fun editAfterExplicitRefreshStillWinsOverItsLateResponse() {
        val guard = MixConfigLoadGuard()
        guard.edited()
        val refresh = requireNotNull(guard.begin(force = true))
        guard.edited()
        assertFalse(guard.complete(refresh))
    }

    @Test
    fun failedOrCancelledInitialReadCanRetryWithoutLosingDraftEdits() {
        val guard = MixConfigLoadGuard()
        val failed = requireNotNull(guard.begin(force = false))
        guard.edited()
        assertTrue(guard.failed(failed))
        val retry = requireNotNull(guard.begin(force = false))
        assertFalse(guard.complete(retry))
        assertNull(guard.begin(force = false))
    }

    @Test
    fun failedExplicitRefreshKeepsCompletedInitialization() {
        val guard = MixConfigLoadGuard()
        assertTrue(guard.complete(requireNotNull(guard.begin(force = false))))
        guard.edited()
        assertTrue(guard.failed(requireNotNull(guard.begin(force = true))))
        assertNull(guard.begin(force = false))
        assertNotNull(guard.begin(force = true))
    }

    @Test
    fun duplicateLoadDoesNotStartASecondRead() {
        val guard = MixConfigLoadGuard()
        val first = requireNotNull(guard.begin(force = false))
        assertNull(guard.begin(force = false))
        assertNull(guard.begin(force = true))
        assertTrue(guard.failed(first))
        assertNotNull(guard.begin(force = false))
    }

    @Test
    fun oldCompletionCannotReleaseOrReplaceANewerRequest() {
        val guard = MixConfigLoadGuard()
        val old = requireNotNull(guard.begin(force = false))
        guard.failed(old)
        val newer = requireNotNull(guard.begin(force = false))
        assertFalse(guard.complete(old))
        assertFalse(guard.failed(old))
        assertNull(guard.begin(force = true))
        assertTrue(guard.complete(newer))
    }

    @Test
    fun fontTaskStartedWhileReadingPreventsTheOldConfigurationFromApplying() {
        val guard = MixConfigLoadGuard()
        val first = requireNotNull(guard.begin(force = false))
        assertFalse(guard.complete(first, allowApply = false))
        assertNull(guard.begin(force = false))
    }
}
