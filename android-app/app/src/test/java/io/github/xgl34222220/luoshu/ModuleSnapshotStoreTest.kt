package io.github.xgl34222220.luoshu

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ModuleSnapshotStoreTest {
    @Test
    fun displayHistoryNeverRestoresPermissionMountOrTasks() {
        val previous = ModuleSnapshot(
            loading = false, rootGranted = true, installed = true,
            version = "v2.0.0", versionCode = 70000, activeFont = "mix", effectiveFont = "mix",
            fontEffectState = "live-mounted", liveApplied = true, activation = "live-mounted",
            taskType = "mix", taskId = "old-task", taskState = "running", rebootRequired = true,
        )
        val cached = decodeModuleDisplay(encodeModuleDisplay(previous))!!
        assertTrue(cached.loading)
        assertTrue(cached.statusCached)
        assertEquals("mix", cached.activeFont)
        assertFalse(cached.rootGranted)
        assertFalse(cached.installed)
        assertFalse(cached.liveApplied)
        assertFalse(cached.rebootRequired)
        assertEquals("unknown", cached.mountState)
        assertEquals("", cached.taskId)
        assertEquals("idle", cached.taskState)
    }

    @Test
    fun persistedDisplayOmitsRuntimeEvidence() {
        val json = JSONObject(encodeModuleDisplay(ModuleSnapshot(version = "v2.0.0", versionCode = 70000)))
        assertEquals(setOf("schema", "version", "versionCode", "activeFont"), json.keySet())
    }

    @Test
    fun corruptOrUnsupportedDisplayIsIgnored() {
        assertNull(decodeModuleDisplay("broken"))
        assertNull(decodeModuleDisplay("{\"schema\":2,\"version\":\"v2.0.0\",\"versionCode\":70000}"))
        assertNull(decodeModuleDisplay("{\"schema\":1,\"version\":\"v2.0.0\",\"versionCode\":0}"))
        assertNull(decodeModuleDisplay("{\"schema\":1,\"version\":\"\",\"versionCode\":70000}"))
    }

    @Test
    fun liveMountLabelKeepsFullRebootLimitVisible() {
        val state = ModuleSnapshot(
            activeFont = "NewFont", effectiveFont = "NewFont", fontEffectState = "live-mounted",
            liveApplied = true, rebootRequired = true,
        )
        assertEquals("NewFont（当前启动已挂载，重启后完整生效）", state.effectiveLabel)
    }

    @Test
    fun defaultFontStagedForRebootDoesNotClaimItIsAlreadyRestored() {
        val state = ModuleSnapshot(activeFont = "default", fontEffectState = "pending-reboot", rebootRequired = true)
        assertEquals("系统默认字体（等待完整重启）", state.effectiveLabel)
    }

    @Test
    fun cancellationCannotRelabelConfirmedSuccessDuringCachePersistence() {
        assertTrue(canCancelFontTask(jobActive = true, terminalConfirmed = false))
        assertFalse(canCancelFontTask(jobActive = true, terminalConfirmed = true))
        assertFalse(canCancelFontTask(jobActive = false, terminalConfirmed = false))
    }
}
