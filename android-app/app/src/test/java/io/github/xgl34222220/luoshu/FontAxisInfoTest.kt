package io.github.xgl34222220.luoshu

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FontAxisInfoTest {
    private fun parse(axes: String) = parseWeightAxisInfo(JSONObject("""{"status":"ok","axes":$axes}"""))

    @Test fun customAxisNameAndRangeComeFromTheFont() {
        val info = parse("""[{"tag":"XTRA","name":"细节纹理","min":-2,"default":1.5,"max":8}]""")
        assertFalse(info.hasWeight)
        assertEquals("细节纹理", info.visibleAxes.single().name)
        assertEquals(1.5f, info.axes.single().default)
    }

    @Test fun weightDefaultsAreNotAssumedToBe400() {
        val info = parse("""[{"tag":"wght","min":300,"default":450,"max":800}]""")
        assertTrue(info.hasWeight)
        assertEquals(300, info.min)
        assertEquals(450, info.default)
        assertEquals(800, info.max)
    }

    @Test fun hiddenAxesRemainMetadataWithoutBecomingControls() {
        val info = parse("""[{"tag":"XTRA","min":0,"default":1,"max":2,"hidden":true}]""")
        assertEquals(1, info.axes.size)
        assertTrue(info.visibleAxes.isEmpty())
        assertEquals(1f, info.axes.single().default)
    }

    @Test fun oldBridgeResponsesWithoutNamesOrFlagsStillWork() {
        val info = parse("""[{"tag":"wght","min":100,"default":400,"max":900}]""")
        assertEquals("", info.visibleAxes.single().name)
        assertFalse(info.axes.single().hidden)
    }

    @Test fun malformedDefaultDoesNotTurnIntoAClampedSlider() {
        assertTrue(runCatching { parse("""[{"tag":"wght","min":100,"default":950,"max":900}]""") }.isFailure)
    }

    @Test fun duplicateTagsCannotOverwriteOneAnother() {
        val axis = """{"tag":"wght","min":100,"default":400,"max":900}"""
        assertTrue(runCatching { parse("[$axis,$axis]") }.isFailure)
    }

    @Test fun nonFiniteValuesAndNonAsciiTagsAreRejected() {
        assertTrue(runCatching { parse("""[{"tag":"wght","min":100,"default":400,"max":1e50}]""") }.isFailure)
        assertTrue(runCatching { parse("""[{"tag":"设计轴名","min":0,"default":1,"max":2}]""") }.isFailure)
    }

    @Test fun fontNamesAreBoundedAndCannotInsertControlLines() {
        val info = parse("""[{"tag":"XTRA","name":" 纹理\n轴 ","min":0,"default":1,"max":2}]""")
        assertEquals("纹理 轴", info.axes.single().name)
        val longName = "x".repeat(200)
        assertEquals(128, parse("""[{"tag":"XTRA","name":"$longName","min":0,"default":1,"max":2}]""").axes.single().name.length)
    }
}
