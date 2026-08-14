package io.github.xgl34222220.luoshu.ui.settings

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SystemCenterViewModelTest {
    @Test
    fun parsesHealthAndConflicts() {
        val report = """
            healthVersion=1
            modulePresent=true
            moduleVersion=v2.4.1 Beta 1
            moduleVersionCode=20401
            rootManager=APatch
            androidSdk=36
            activeFont=my-font
            payloadFonts=18
            lockState=idle
            alignmentState=verified
            cachePending=false
            rebootRequired=true
            recentWarnings=2
            recentErrors=0
            conflictCount=1
            conflict=OtherFont|其它字体|system/fonts|directory|4
        """.trimIndent()

        val state = parseHealthReport(report)
        assertTrue(state.modulePresent)
        assertEquals("APatch", state.rootManager)
        assertEquals(18, state.payloadFonts)
        assertTrue(state.rebootRequired)
        assertEquals(1, state.conflicts.size)
        assertEquals("system/fonts", state.conflicts.single().target)
        assertEquals(HealthLevel.WARNING, state.level)
    }

    @Test
    fun missingPayloadIsErrorForCustomFont() {
        val state = parseHealthReport(
            """
                healthVersion=1
                modulePresent=true
                activeFont=custom
                payloadFonts=0
                lockState=idle
                cachePending=false
            """.trimIndent(),
        )
        assertEquals(HealthLevel.ERROR, state.level)
    }

    @Test
    fun healthyDefaultInstallStaysHealthy() {
        val state = parseHealthReport(
            """
                healthVersion=1
                modulePresent=true
                activeFont=default
                payloadFonts=0
                lockState=idle
                alignmentState=verified
                cachePending=false
                recentErrors=0
            """.trimIndent(),
        )
        assertFalse(state.loading)
        assertEquals(HealthLevel.HEALTHY, state.level)
    }
}
