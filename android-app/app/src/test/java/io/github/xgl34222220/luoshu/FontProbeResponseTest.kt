package io.github.xgl34222220.luoshu

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class FontProbeResponseTest {
    private val fallback = "字体覆盖检测失败"

    @Test
    fun preservesAnalyzerErrorReturnedOnStdoutWithNonzeroExit() {
        val result = ShellResult(1, """{"status":"error","message":"找不到字体族对应的真实文件"}""", "")
        assertEquals("找不到字体族对应的真实文件", failureMessage(result))
    }

    @Test
    fun structuredErrorTakesPrecedenceOverUnrelatedShellWarning() {
        val result = ShellResult(1, """{"status":"error","message":"No module named 'xml'"}""", "Root shell warning")
        assertEquals("No module named 'xml'", failureMessage(result))
    }

    @Test
    fun rejectsStructuredErrorEvenWhenWrapperReturnsZero() {
        val result = ShellResult(0, """{"status":"error","message":"无法读取字体文件"}""", "")
        assertEquals("无法读取字体文件", failureMessage(result))
    }

    @Test
    fun preservesInterpreterErrorWhenNoJsonWasProduced() {
        val result = ShellResult(127, "", "CANNOT LINK EXECUTABLE: missing library\n")
        assertEquals("CANNOT LINK EXECUTABLE: missing library", failureMessage(result))
    }

    @Test
    fun acceptsCompleteResponseAfterShellOutput() {
        val result = ShellResult(0, "shell message\n{not json\n" +
            """{"status":"ok","data":{"glyphs":7000}}""", "")
        assertEquals(7000, parseFontProbeResponse(result, fallback).getJSONObject("data").getInt("glyphs"))
    }

    @Test
    fun doesNotAcceptSuccessDataFromFailedProcess() {
        val result = ShellResult(1, """{"status":"ok","data":{"glyphs":7000}}""", "")
        assertEquals(fallback, failureMessage(result))
    }

    private fun failureMessage(result: ShellResult): String? =
        assertThrows(IllegalStateException::class.java) {
            parseFontProbeResponse(result, fallback)
        }.message
}
