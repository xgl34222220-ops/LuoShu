package io.github.xgl34222220.luoshu.ui.logs

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class FontAuditConclusionTest {
    @Test
    fun systemUiStockFontsAreCounted() {
        assertEquals("SystemUI 仍加载原厂字体 3 个", fontAuditConclusion("gap:systemui=3/0"))
    }

    @Test
    fun replacedSlotStockIsCalledOut() {
        val line = fontAuditConclusion("gap:systemServer=40/1,systemui=2/1,launcher=1/0")
        assertEquals(
            "system_server 仍加载已替换槽位的原厂字体 1 个；SystemUI 仍加载原厂字体 2 个（其中 1 个是洛书已替换的槽位）；桌面 仍加载原厂字体 1 个",
            line,
        )
    }

    @Test
    fun serverStockWithoutReplacedSlotIsQuiet() {
        assertTrue(fontAuditConclusion("gap:systemServer=40/0").contains("无法解析"))
    }

    @Test
    fun okInactiveAndMissing() {
        assertTrue(fontAuditConclusion("ok").startsWith("按进程字体审计"))
        assertEquals("按进程字体审计：当前没有洛书字体负载，已跳过", fontAuditConclusion("inactive:no-payload"))
        assertEquals("", fontAuditConclusion("not-collected"))
        assertEquals("", fontAuditConclusion(""))
        assertEquals("按进程字体审计未能采集", fontAuditConclusion("unknown:python-unavailable"))
    }

    @Test
    fun stockInodeParityGetsDedicatedLine() {
        assertTrue(
            xmlParityConclusion("mismatch:zh-Hans(stock-inode:fm=MiSansVF.ttf@253.5:12)", "none")
                .contains("同名不同 inode"),
        )
    }
}
