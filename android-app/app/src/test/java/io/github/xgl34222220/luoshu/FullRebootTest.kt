package io.github.xgl34222220.luoshu

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class FullRebootTest {
    @Test
    fun rebootUsesTheBridgeWithEnoughTimeForEveryFallback() {
        assertEquals("sh '/data/adb/modules/LuoShu/common/app_bridge.sh' reboot",
            fullRebootCommand("/data/adb/modules/LuoShu/common/app_bridge.sh"))
        // svc start-up plus two 6 s settle windows must fit; the old 4 s cut-off killed the request.
        assertTrue(FULL_REBOOT_TIMEOUT_MS >= 30_000L)
    }

    @Test
    fun failureMessagesComeFromTheBridgeOrTheTimeout() {
        assertNull(rebootFailureMessage(ShellResult(0, "", "")))
        assertTrue(rebootFailureMessage(ShellResult(124, "", "命令执行超时"))!!.contains("超时"))
        assertEquals("整机重启命令没有生效，请长按电源键手动重启",
            rebootFailureMessage(ShellResult(1, "noise\n{\"status\":\"error\",\"message\":\"整机重启命令没有生效，请长按电源键手动重启\"}\n", "")))
        assertEquals("Permission denied", rebootFailureMessage(ShellResult(1, "", "Permission denied\n")))
        assertTrue(rebootFailureMessage(ShellResult(1, "", ""))!!.contains("手动重启"))
    }

    @Test
    fun viewModelRebootIsTheFullRebootPathWithoutBusyGate() {
        val source = listOf("src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt",
            "app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt")
            .map(::File).first { it.isFile }.readText()
        val body = source.substringAfter("fun rebootDevice()").substringBefore("fun refreshLogs()")
        assertTrue(body.contains("fullRebootCommand(bridge)"))
        assertTrue(body.contains("FULL_REBOOT_TIMEOUT_MS"))
        assertTrue(!body.contains("operationBusy ||"))
    }
}
