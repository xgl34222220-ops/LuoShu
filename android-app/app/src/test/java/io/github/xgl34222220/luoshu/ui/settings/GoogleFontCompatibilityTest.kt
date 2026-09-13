package io.github.xgl34222220.luoshu.ui.settings

import org.junit.Assert.*
import org.junit.Test

class GoogleFontCompatibilityTest {
    private fun state(name: String, managed: Boolean, disabled: Boolean, user: Int = 0) =
        """{"status":"diagnostic","state":"$name","title":"状态","message":"说明","user":$user,"managed":$managed,"componentDisabled":$disabled,"canEnable":true,"canRestore":true}"""

    @Test fun ownedDisabledOffersRestoreOnly() {
        val result = parseGoogleFontCompatibility(state("enabled", true, true), 0)
        assertFalse(result.canEnable)
        assertTrue(result.canRestore)
        assertTrue(result.managed)
    }
    @Test fun externalDisableCannotBeClaimedOrRestored() {
        val result = parseGoogleFontCompatibility(state("external", false, true), 0)
        assertFalse(result.canEnable)
        assertFalse(result.canRestore)
    }
    @Test fun offOnlyOffersExplicitEnable() {
        val result = parseGoogleFontCompatibility(state("off", false, false), 0)
        assertTrue(result.canEnable)
        assertFalse(result.canRestore)
    }
    @Test fun conflictingJournalDisablesActions() {
        val result = parseGoogleFontCompatibility(state("conflict", true, true), 0)
        assertFalse(result.canRestore)
        assertFalse(result.canEnable)
    }
    @Test(expected = IllegalArgumentException::class) fun wrongUserIsRejected() {
        parseGoogleFontCompatibility(state("off", false, false, 10), 0)
    }
    @Test(expected = IllegalArgumentException::class) fun unknownStateIsRejected() {
        parseGoogleFontCompatibility(state("something-new", false, false), 0)
    }
    @Test(expected = IllegalArgumentException::class) fun errorIsNotDiagnosticSuccess() {
        parseGoogleFontCompatibility("""{"status":"error","message":"失败"}""", 0)
    }
    @Test fun commandsUseOnlyPinnedActionsAndAppUser() {
        val command = googleFontCommand("enable", 10)
        assertTrue(command.contains("enable --user 10 --json"))
        assertTrue(command.contains("/data/adb/modules/LuoShu/common/google_font_fallback.sh"))
        assertFalse(command.contains("--user all"))
    }
    @Test(expected = IllegalArgumentException::class) fun arbitraryCommandIsRejected() { googleFontCommand("enable;reboot", 0) }
    @Test(expected = IllegalArgumentException::class) fun invalidUserIsRejected() { googleFontCommand("restore", -1) }
    @Test fun validActionsAreReportedInChinese() {
        assertTrue(googleFontActionMessage("enable", "component-disabled").contains("完整重启"))
        assertTrue(googleFontActionMessage("restore", "restored").contains("恢复"))
    }
    @Test(expected = IllegalArgumentException::class) fun unexpectedActionOutputIsNotSuccess() { googleFontActionMessage("enable", "ok") }
}
