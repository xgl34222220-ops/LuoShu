package io.github.xgl34222220.luoshu.ui.coverage

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class FontCoverageContractTest {
    @Test fun sourceLimitationsDoNotOverrideArchivedReplaceableCount() {
        val data = parseCoverage(JSONObject("""{
            "schema":"device-font-slot-trace-v1", "inventoryRomKind":"generic",
            "summary":{"inventorySlots":15,"textInventorySlots":15,"replaceableSlots":15,
                       "replaced":11,"issues":4,"sourceUnavailable":4},
            "slots":[{"path":"/system/fonts/Bold.ttf","state":"source-unavailable",
                      "category":"issue","safeToRetry":false,"replacementRoles":["latin"],
                      "capabilityKnown":true,"reason":"当前字体缺少真实字重，尚未替换"}]
        }"""))
        assertEquals(15, data.summary.replaceable)
        assertEquals(11, data.summary.replaced)
        assertEquals(4, data.summary.issues)
        assertTrue(data.slots.single().capabilityKnown)
        assertFalse(data.slots.single().safeToRetry)
    }

    @Test fun dynamicAndRuntimeSourcesRemainVisibleAndDistinct() {
        val data = parseCoverage(JSONObject("""{
            "schema":"device-font-slot-trace-v1",
            "summary":{"inventorySlots":2,"textInventorySlots":0,"replaceableSlots":0,
                       "dynamicSlots":1,"runtimeSlots":1,"issues":2},
            "slots":[
              {"path":"/data/themes/font.ttf","source":"dynamic-font","state":"unreplaced-dynamic",
               "category":"issue","safeToRetry":false},
              {"path":"/apex/com.font/font.ttf","source":"runtime-font","state":"unreplaced-runtime",
               "category":"issue","safeToRetry":false}
            ]
        }"""))
        assertEquals(1, data.summary.dynamic)
        assertEquals(1, data.summary.runtime)
        assertEquals(0, data.summary.replaceable)
        assertEquals(listOf("动态字体", "运行容器"), data.slots.map { coverageSourceLabel(it.source) })
        assertTrue(data.slots.all { !it.safeToRetry })
    }

    @Test fun collectionCapabilitiesAndVariableAxesAreReadable() {
        val data = parseCoverage(JSONObject("""{
            "schema":"device-font-slot-trace-v1","summary":{"partial":1},
            "slots":[{"path":"/system/fonts/Mixed.ttc","state":"partial","fontFaces":[
              {"faceIndex":0,"replacementRoles":["latin","digit"],"weight":400,"style":"normal",
               "variationAxes":{"wght":{"min":100,"default":400,"max":900}}},
              {"faceIndex":1,"replacementRoles":["cjk"],"weight":700,"style":"italic",
               "preservedReason":"当前字体缺少真实字重，尚未替换"}
            ]}]
        }"""))
        val faces = data.slots.single().faceDetails
        assertEquals(2, faces.size)
        assertTrue(faces[0].contains("英文 · 数字"))
        assertTrue(faces[0].contains("可变字体：字重 100–900"))
        assertTrue(faces[1].contains("中文 · 斜体 · 字重 700"))
        assertTrue(faces[1].contains("尚未替换"))
        assertEquals(1, data.summary.partial)
    }

    @Test fun genericAndPartialStatusUseChineseLabels() {
        assertEquals("自动检测", coverageDetectionLabel("GENERIC"))
        assertEquals("部分字体生效", verificationLabel("partial", false))
        assertEquals("等待完整重启", verificationLabel("partial", true))
        assertEquals("等待验证", verificationLabel("pending", false))
    }

    @Test fun oldCoverageWithoutFaceMetadataStillParses() {
        val data = parseCoverage(JSONObject("""{
            "schema":"device-font-slot-trace-v1","summary":{"inventorySlots":1},
            "slots":[{"path":"/system/fonts/Face.ttf","state":"loaded","category":"replaced"}]
        }"""))
        assertEquals(1, data.summary.textInventory)
        assertEquals(1, data.summary.replaced)
        assertTrue(data.slots.single().faceDetails.isEmpty())
    }
}
